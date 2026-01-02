#!/usr/bin/env python3
"""
DaemonZero Manager GUI & API Server.
Main entry point for the desktop-based management interface.
"""

import os
import subprocess
import json
import sys
import logging
import threading
import contextlib
import mimetypes
import zipfile
import shutil
import time
import docker
from pathlib import Path
from io import StringIO, BytesIO
from flask import Flask, render_template, jsonify, request, send_file

# Internal module imports (assumed to be in the same directory)
import dz_manage
import webview
import platform_utils
import setup_linux

# --- Global Logging Configuration ---
# Standardized logging for the entire application.
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("dz_launcher")

def get_resource_path(relative_path: str) -> str:
    """
    Resolve the absolute path to a resource, supporting both development 
    environments and PyInstaller bundles.
    """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except (AttributeError, Exception):
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)

# --- Flask App Initialization ---
app = Flask(__name__, template_folder=get_resource_path("templates"))

# --- Error Handling & Request Logging ---

@app.before_request
def log_request_info():
    """Log incoming request details for debugging."""
    if request.path.startswith('/api'):
        logger.info(f"API Request: {request.method} {request.path}")

@app.after_request
def log_response_info(response):
    """Log response status for tracking errors in CLI."""
    if request.path.startswith('/api'):
        level = logging.INFO
        if response.status_code >= 400:
            level = logging.WARNING
        if response.status_code >= 500:
            level = logging.ERROR
        logger.log(level, f"API Response: {response.status_code} {request.path}")
    return response

@app.errorhandler(Exception)
def handle_exception(e):
    """
    Global error handler to ensure all backend failures are logged with full 
    tracebacks and returned as JSON.
    """
    # Log the full traceback to the CLI
    logger.exception(f"Unhandled Exception on {request.path}")
    
    # Return JSON to the frontend instead of the default HTML error page
    return jsonify({
        "success": False,
        "message": f"Internal Server Error: {str(e)}",
        "type": type(e).__name__
    }), 500

# --- Directory Configuration ---
HOME_DIR = Path.home()
BASE_DATA_DIR = HOME_DIR / "daemon-zero"
MANAGER_CONFIG_PATH = BASE_DATA_DIR / "manager_config.json"

# Internal variables for runtime logging capture
manage_lock = threading.Lock()

# --- Helper Functions ---

def load_manager_config() -> dict:
    """Load the manager's global configuration from disk."""
    if not MANAGER_CONFIG_PATH.exists():
        return {
            "default_api_keys": {},
            "default_models": {},
            "docker_installed": False,
            "user_in_group": False
        }
    try:
        return json.loads(MANAGER_CONFIG_PATH.read_text())
    except Exception as e:
        logger.error(f"Failed to load manager config: {e}")
        return {}

def save_manager_config(config: dict):
    """Save the manager's global configuration to disk."""
    try:
        BASE_DATA_DIR.mkdir(parents=True, exist_ok=True)
        MANAGER_CONFIG_PATH.write_text(json.dumps(config, indent=4))
    except Exception as e:
        logger.error(f"Failed to save manager config: {e}")

def check_docker_image() -> bool:
    """
    Check if the daemon-zero Docker image is available locally.
    """
    try:
        res = subprocess.run(
            ["docker", "images", "-q", "daemon-zero"],
            capture_output=True, text=True, check=True
        )
        return bool(res.stdout.strip())
    except (subprocess.SubprocessError, FileNotFoundError):
        return False

def check_system() -> dict:
    """
    Perform system checks to determine if Docker and user permissions are correctly configured.
    """
    status = {
        "docker_installed": False,
        "user_in_group": False,
        "base_dir_ready": False,
        "docker_image_ready": False,
        "ready": False
    }
    
    # 1. Docker Installation Check
    try:
        subprocess.run(["docker", "--version"], capture_output=True, check=True)
        status["docker_installed"] = True
    except (subprocess.SubprocessError, FileNotFoundError):
        pass
        
    # 2. User Group Membership Check
    try:
        res = subprocess.run(["groups"], capture_output=True, text=True)
        if "docker" in res.stdout:
            status["user_in_group"] = True
    except subprocess.SubprocessError:
        pass

    # 3. Directory Readiness
    status["base_dir_ready"] = BASE_DATA_DIR.exists()
    
    # 4. Docker Image Check
    if status["docker_installed"] and status["user_in_group"]:
        status["docker_image_ready"] = check_docker_image()
    
    # Aggregate status
    status["ready"] = (
        status["docker_installed"] and 
        status["user_in_group"] and 
        status["base_dir_ready"] and
        status["docker_image_ready"]
    )
    return status

class ManageArgs:
    """
    Mock argument object to simulate CLI arguments when calling dz_manage directly.
    """
    def __init__(self, **kwargs):
        self.name = "default"
        self.port = None
        self.ephemeral = False
        self.data = False
        self.force = False
        self.__dict__.update(kwargs)

def run_manage_backend(func, **kwargs) -> tuple:
    """
    Run a backend management function and capture its log output for the GUI.
    Returns (success_bool, message_string).
    """
    output = StringIO()
    success = False
    args = ManageArgs(**kwargs)
    
    # Use global lock to isolate stdout capture across multithreaded requests
    with manage_lock:
        try:
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
                func(args)
            msg = output.getvalue()
            success = "ERROR" not in msg.upper()
        except Exception as e:
            logger.exception(f"Backend Task Error in {func.__name__}")
            msg = output.getvalue() + f"\n[CRITICAL ERROR] {str(e)}"
            success = False
        
    return success, msg

# --- Setup State Management ---

class SetupManager:
    """
    Orchestrates the asynchronous system setup process (Docker, Permissions, Dirs).
    Captures live logs and tracks progress for the frontend wizard.
    """
    def __init__(self, log_file):
        self.logs = []
        self.is_running = False
        self.progress = 0
        self.status_text = "Idle"
        self.error = None
        self.lock = threading.RLock()  # Use reentrant lock to prevent deadlock during status polling
        self.log_file = Path(log_file)
        self.start_time = None  # Track when task started for timeout detection
        logger.debug(f"SetupManager initialized with log file: {self.log_file}")

    def add_log(self, message: str):
        """Append a message to the in-memory log list and persist to file."""
        with self.lock:
            ts_message = f"[{time.strftime('%H:%M:%S')}] {message}"
            self.logs.append(ts_message)
            # Maintain a rolling window of recent logs in memory
            if len(self.logs) > 500:
                self.logs.pop(0)
            
            try:
                self.log_file.parent.mkdir(parents=True, exist_ok=True)
                with open(self.log_file, "a") as f:
                    f.write(ts_message + "\n")
            except Exception as e:
                logger.error(f"Failed to persist setup log: {e}")

    def prepare_setup(self, task_name: str):
        """Reset status flags and prepare for a new setup task."""
        with self.lock:
            self.is_running = True
            self.progress = 0
            self.status_text = task_name
            self.error = None
            self.logs = []
            self.start_time = time.time()
            self.add_log(f"--- Task Initialization: {task_name} ---")

    def start_task(self, name: str):
        """Mark a specific sub-task as active."""
        with self.lock:
            self.status_text = name
            self.add_log(f"--- Processing Sub-task: {name} ---")

    def finish_task(self, success: bool, message: str):
        """Conclude the current setup task."""
        with self.lock:
            self.is_running = False
            self.status_text = "Finished Successfully" if success else "Task Failed"
            self.progress = 100 if success else self.progress
            if not success:
                self.error = message
            self.add_log(f"--- Task Concluded: {'SUCCESS' if success else 'FAILURE'} ({message}) ---")

    def manual_reset(self):
        """Manually reset the setup manager state (emergency use only)."""
        with self.lock:
            self.is_running = False
            self.status_text = "Manually Reset"
            self.error = None
            self.start_time = None
            self.add_log("[MANUAL RESET] Setup state forcefully cleared.")

    def get_status(self) -> dict:
        """Return a snapshot of the current setup progress."""
        with self.lock:
            # Auto-timeout detection (15 minutes)
            if self.is_running and self.start_time and (time.time() - self.start_time > 900):
                self.is_running = False
                self.error = "Task timed out after 15 minutes."
                self.add_log("[TIMEOUT] Task exceeded maximum duration.")
            
            return {
                "logs": self.logs,
                "is_running": self.is_running,
                "progress": self.progress,
                "status_text": self.status_text,
                "error": self.error
            }

setup_manager = SetupManager(BASE_DATA_DIR / "setup.log")

# --- API Endpoints: Setup & System ---

@app.route('/')
def route_index():
    """Render the main manager dashboard."""
    return render_template('index.html', 
                           system_status=check_system(), 
                           manager_config=load_manager_config())

@app.route('/api/status')
def api_get_status():
    """Retrieve current system readiness status."""
    return jsonify(check_system())

@app.route('/api/setup/status')
def api_get_setup_status():
    """Poll for setup task progress and logs."""
    return jsonify(setup_manager.get_status())

@app.route('/api/setup/reset', methods=['POST'])
def api_reset_setup():
    """Manually reset stuck setup state (emergency endpoint)."""
    setup_manager.manual_reset()
    return jsonify({"success": True, "message": "Setup state has been reset."})

@app.route('/api/setup/install_docker', methods=['POST'])
def api_trigger_install_docker():
    """Asynchronously trigger the Docker installation process."""
    data = request.json or {}
    password = data.get('password')
    if not password:
        return jsonify({"success": False, "message": "Root/Sudo password is required for installation."}), 400

    if setup_manager.is_running:
        return jsonify({"success": False, "message": "A setup task is already in progress."}), 409

    setup_manager.prepare_setup("Docker Installation")

    def run_worker():
        try:
            if platform_utils.is_linux():
                success, msg = setup_linux.install_docker_ubuntu(password, logger=setup_manager.add_log)
                if success:
                    setup_manager.add_log("Base directories auto-configuration starting...")
                    setup_linux.setup_base_dirs(BASE_DATA_DIR, logger=setup_manager.add_log)
                setup_manager.finish_task(success, msg)
            else:
                setup_manager.finish_task(False, "Automatic Docker installation is only supported on Linux.")
        except Exception as e:
            logger.exception("Unexpected error during terminal installation.")
            setup_manager.finish_task(False, f"Crash: {str(e)}")

    threading.Thread(target=run_worker, daemon=True).start()
    return jsonify({"success": True, "message": "Installation worker spawned."})

@app.route('/api/setup/fix_group', methods=['POST'])
def api_trigger_group_fix():
    """Asynchronously update user group permissions for Docker."""
    data = request.json or {}
    password = data.get('password')
    if not password:
        return jsonify({"success": False, "message": "Root/Sudo password is required."}), 400

    if setup_manager.is_running:
        return jsonify({"success": False, "message": "A setup task is already in progress."}), 409

    setup_manager.prepare_setup("Fixing Group Permissions")

    def run_worker():
        try:
            if platform_utils.is_linux():
                success, msg = setup_linux.add_user_to_docker_group(password, logger=setup_manager.add_log)
                setup_manager.finish_task(success, msg)
            else:
                setup_manager.finish_task(False, "Group permission fix is only applicable to Linux.")
        except Exception as e:
            logger.exception("Unexpected error during group permissions fix.")
            setup_manager.finish_task(False, f"Crash: {str(e)}")

    threading.Thread(target=run_worker, daemon=True).start()
    return jsonify({"success": True, "message": "Group fix worker spawned."})

@app.route('/api/setup/dirs', methods=['POST'])
def api_trigger_dir_setup():
    """Asynchronously trigger the baseline directory structure creation."""
    if setup_manager.is_running:
        # Check if actually running or stale lock
        # For now, we allow a force retry if it's been in 'dirs' state too long? 
        # Better: just ensure finish_task is ALWAYS called.
        return jsonify({"success": False, "message": "A setup task is already in progress."}), 409

    setup_manager.prepare_setup("Initialization of Workspace Directories")

    def run_worker():
        try:
            success, msg = setup_linux.setup_base_dirs(BASE_DATA_DIR, logger=setup_manager.add_log)
            setup_manager.finish_task(success, msg)
        except Exception as e:
            logger.exception("Unexpected error during directory setup.")
            setup_manager.finish_task(False, f"Crash: {str(e)}")

    # Ensure thread is daemon so it doesn't block shutdown
    t = threading.Thread(target=run_worker, daemon=True)
    t.start()
    return jsonify({"success": True, "message": "Directory setup worker spawned."})

@app.route('/api/setup/pull_image', methods=['POST'])
def api_trigger_image_pull():
    """Asynchronously pull the daemon-zero Docker image from Docker Hub."""
    if setup_manager.is_running:
        return jsonify({"success": False, "message": "A setup task is already in progress."}), 409

    setup_manager.prepare_setup("Downloading Docker Image")

    def run_worker():
        try:
            setup_manager.add_log("[INFO] Pulling josepavese/daemon-zero:latest from Docker Hub...")
            setup_manager.add_log("[INFO] This may take several minutes depending on your connection.")
            setup_manager.progress = 5
            
            # Use Docker SDK for real progress tracking
            client = docker.from_env()
            
            # Pull with progress tracking
            image_name = "josepavese/daemon-zero:latest"
            layers_progress = {}
            
            # Stream the pull process
            pull_stream = client.api.pull(image_name, stream=True, decode=True)
            for line in pull_stream:
                # Check for explicit errors in the stream
                if 'error' in line:
                    error_msg = line.get('error', 'Unknown Docker error')
                    error_detail = line.get('errorDetail', {}).get('message', '')
                    full_error = f"{error_msg} {error_detail}".strip()
                    setup_manager.add_log(f"[ERROR] Pull failed: {full_error}")
                    setup_manager.finish_task(False, f"Pull Error: {full_error}")
                    return

                if 'status' in line:
                    status = line['status']
                    layer_id = line.get('id', '')
                    
                    # Track progress for each layer
                    if 'progressDetail' in line and line['progressDetail']:
                        detail = line['progressDetail']
                        if 'current' in detail and 'total' in detail:
                            layers_progress[layer_id] = (detail['current'], detail['total'])
                    
                    # Log meaningful status updates
                    if layer_id:
                        # Optional: filter noisy status like 'Waiting' or 'Pulling fs layer' 
                        # but keep 'Downloading' and 'Extracting'
                        if "Downloading" in status or "Extracting" in status or "Pull complete" in status:
                            setup_manager.add_log(f"{status}: {layer_id}")
                    elif status not in ['Pulling fs layer', 'Waiting', 'Verifying Checksum']:
                        setup_manager.add_log(f"{status}")
                    
                    # Calculate overall progress
                    if layers_progress:
                        total_current = sum(c for c, t in layers_progress.values())
                        total_size = sum(t for c, t in layers_progress.values())
                        if total_size > 0:
                            # Scale progress from 5% to 90%
                            progress = int((total_current / total_size) * 85) + 5
                            setup_manager.progress = min(90, progress)
            
            setup_manager.progress = 92
            setup_manager.add_log("[INFO] Pull stream finished. Verifying image...")
            
            # Verify if image actually exists before tagging
            try:
                client.images.get(image_name)
            except docker.errors.ImageNotFound:
                setup_manager.add_log("[ERROR] Image not found after pull completion.")
                setup_manager.finish_task(False, "Image not found after pull. Check internet connection or disk space.")
                return

            setup_manager.progress = 95
            setup_manager.add_log("[INFO] Finalizing and tagging image...")
            
            # Wait a moment for Docker to finalize the image
            time.sleep(2)
            
            # Tag the image using subprocess (more reliable than SDK for tagging)
            tag_result = subprocess.run(
                ["docker", "tag", image_name, "daemon-zero:latest"],
                capture_output=True, text=True
            )
            
            if tag_result.returncode != 0:
                setup_manager.finish_task(False, f"Failed to tag image: {tag_result.stderr}")
                return
            
            setup_manager.progress = 100
            setup_manager.finish_task(True, "Docker image downloaded and ready!")
            
        except docker.errors.APIError as e:
            logger.exception("Docker API error during image pull")
            setup_manager.finish_task(False, f"Failed to pull image: {str(e)}")
        except Exception as e:
            logger.exception("Unexpected error during image pull")
            setup_manager.finish_task(False, f"Error: {str(e)}")

    threading.Thread(target=run_worker, daemon=True).start()
    return jsonify({"success": True, "message": "Image pull worker spawned."})

@app.route('/api/setup/create_shortcut', methods=['POST'])
def api_trigger_shortcut_creation():
    """Trigger the creation of a Linux desktop entry."""
    if setup_manager.is_running:
        return jsonify({"success": False, "message": "A setup task is already in progress."}), 409
        
    def run_worker():
        setup_manager.start_task("Desktop Entry Creation")
        try:
            if platform_utils.is_linux():
                success, msg = setup_linux.create_desktop_shortcut(logger=setup_manager.add_log)
                setup_manager.finish_task(success, msg)
            else:
                setup_manager.finish_task(False, "Desktop shortcuts are only supported on Linux.")
        except Exception as e:
            logger.exception("Unexpected error during shortcut creation.")
            setup_manager.finish_task(False, f"Crash: {str(e)}")

    threading.Thread(target=run_worker, daemon=True).start()
    return jsonify({"success": True, "message": "Shortcut worker spawned."})

# --- API Endpoints: Manager Config ---

@app.route('/api/manager_config', methods=['GET', 'POST'])
def api_manager_config_handler():
    """Retrieve or update global manager configuration."""
    try:
        if request.method == 'POST':
            data = request.json
            if not isinstance(data, dict):
                return jsonify({"error": "Valid JSON object required"}), 400
            save_manager_config(data)
            return jsonify({"success": True})
        return jsonify(load_manager_config())
    except Exception:
        logger.exception("Error handling manager config")
        return jsonify({"error": "Internal config error"}), 500

# --- API Endpoints: Instance Orchestration ---

@app.route('/api/instances')
def api_list_instances():
    """List all managed DaemonZero agent instances."""
    try:
        raw_agents = dz_manage.get_agents()
        return jsonify([{
            "name": a.get("display_name", a["name"]),
            "status": a.get("status", ""),
            "port": a.get("port", "N/A")
        } for a in raw_agents])
    except Exception:
        logger.exception("Failed to fetch instance list")
        return jsonify([]), 500

@app.route('/api/start/<name>', methods=['POST'])
def api_start_instance(name):
    """Start or initialize a specific agent instance."""
    # Sanitize instance name to prevent malicious path traversal
    safe_name = dz_manage.sanitize_name(name)
    if not safe_name:
        return jsonify({"success": False, "message": "Invalid instance name provided."}), 400

    instance_dir = BASE_DATA_DIR / safe_name
    config_dir = instance_dir / "config"
    tmp_dir = config_dir / "tmp"
    
    try:
        # Check if we need to auto-initialize configuration for a new instance
        if not config_dir.exists():
            logger.info(f"Initializing configuration for new instance: {safe_name}")
            config_dir.mkdir(parents=True, exist_ok=True)
            tmp_dir.mkdir(parents=True, exist_ok=True)
            
            mgr_cfg = load_manager_config()
            
            # 1. Inject API Keys from global settings
            env_lines = [f"{k}={v}" for k, v in mgr_cfg.get("default_api_keys", {}).items() if v]
            env_lines.append("WORK_DIR=/dz/usr/projects") # Default workspace path inside container
            (config_dir / ".env").write_text("\n".join(env_lines))
                
            # 2. Inject Model Preferences
            models = mgr_cfg.get("default_models", {})
            if models:
                settings_data = {
                    "chat_model_provider": models.get("chat_provider", "groq"),
                    "chat_model_name": models.get("chat_model", "llama-3.3-70b-versatile"),
                    "util_model_provider": models.get("util_provider", "groq"),
                    "util_model_name": models.get("util_model", "llama-3.1-8b-instant"),
                    "browser_model_provider": models.get("browser_provider", "groq"),
                    "browser_model_name": models.get("browser_model", "llama-3.1-8b-instant")
                }
                (tmp_dir / "settings.json").write_text(json.dumps(settings_data, indent=4))
        
        success, msg = run_manage_backend(dz_manage.start_agent, name=safe_name)
        return jsonify({"success": success, "message": msg})
    except Exception as e:
        logger.exception(f"Crash during instance '{safe_name}' startup.")
        return jsonify({"success": False, "message": f"Server Error: {str(e)}"}), 500

@app.route('/api/stop/<name>', methods=['POST'])
def api_stop_instance(name):
    """Stop a specific agent instance."""
    success, msg = run_manage_backend(dz_manage.stop_agent, name=dz_manage.sanitize_name(name))
    return jsonify({"success": success, "message": msg})

@app.route('/api/delete/<name>', methods=['POST'])
def api_delete_instance(name):
    """Delete an agent instance and optionally its data files."""
    data = request.json or {}
    success, msg = run_manage_backend(dz_manage.delete_agent, 
                                     name=dz_manage.sanitize_name(name), 
                                     force=True, 
                                     data=data.get('delete_data', False))
    return jsonify({"success": success, "message": msg})

@app.route('/api/config/<name>', methods=['GET'])
def api_read_instance_config(name):
    """Fetch the current configuration files for an instance."""
    safe_name = dz_manage.sanitize_name(name)
    if not safe_name: return jsonify({"error": "Invalid name"}), 400
        
    instance_dir = BASE_DATA_DIR / safe_name
    env_path = instance_dir / "config" / ".env"
    settings_path = instance_dir / "config" / "tmp" / "settings.json"
    
    config = {"env": "", "settings": ""}
    try:
        if env_path.exists(): config["env"] = env_path.read_text()
        if settings_path.exists(): config["settings"] = settings_path.read_text()
        return jsonify(config)
    except Exception:
        logger.exception(f"Failed to read config for {safe_name}")
        return jsonify({"error": "Could not read configuration files."}), 500

@app.route('/api/config/<name>', methods=['POST'])
def api_update_instance_config(name):
    """Save new configuration content for an instance."""
    safe_name = dz_manage.sanitize_name(name)
    if not safe_name: return jsonify({"error": "Invalid name"}), 400
        
    data = request.json or {}
    instance_dir = BASE_DATA_DIR / safe_name
    
    try:
        (instance_dir / "config" / "tmp").mkdir(parents=True, exist_ok=True)
        if "env" in data:
            (instance_dir / "config" / ".env").write_text(data["env"])
        if "settings" in data:
            # Validate JSON if provided
            try:
                json.loads(data["settings"])
                (instance_dir / "config" / "tmp" / "settings.json").write_text(data["settings"])
            except json.JSONDecodeError:
                return jsonify({"error": "Invalid JSON provided for settings."}), 400
                
        return jsonify({"success": True})
    except Exception:
        logger.exception(f"Failed to update config for {safe_name}")
        return jsonify({"success": False, "message": "Save failed due to server error."}), 500

@app.route('/api/logs/<name>')
def api_get_instance_logs(name):
    """Retrieve the most recent log snapshot for an instance."""
    safe_name = dz_manage.sanitize_name(name)
    container_name = f"daemon-zero-{safe_name}"
    try:
        # Fetch last 1000 lines to balance detail with performance
        proc = subprocess.run(["docker", "logs", "--tail", "1000", container_name], 
                               capture_output=True, text=True, timeout=5)
        return jsonify({"logs": proc.stdout + proc.stderr})
    except subprocess.TimeoutExpired:
        return jsonify({"logs": "[ERROR] Log retrieval timed out."})
    except Exception:
        logger.exception(f"Unexpected error fetching logs for {container_name}")
        return jsonify({"logs": "[CRITICAL] Server error while fetching logs."})

# --- API Endpoints: Remote Workspace Browser ---

def resolve_secure_path(instance_name: str, subpath: str = "") -> tuple:
    """
    Safely resolve a path within an instance's workspace directory structure.
    Returns (ResolvedPath, RootPath) and prevents directory traversal.
    """
    safe_instance = dz_manage.sanitize_name(instance_name)
    workspace_root = (BASE_DATA_DIR / safe_instance / "workspace").resolve()
    
    if not workspace_root.exists():
        return None, None
        
    if not subpath:
        return workspace_root, workspace_root
        
    # Sanitize subpath to prevent '..' traversal attacks
    target_path = (workspace_root / subpath).resolve()
    if not str(target_path).startswith(str(workspace_root)):
        logger.warning(f"Security Alert: Blocked traversal attempt from {instance_name} to {subpath}")
        raise PermissionError("Path traversal is strictly prohibited.")
        
    return target_path, workspace_root

@app.route('/api/files/<name>')
def api_browser_list(name):
    """List contents of the workspace directory."""
    subpath = request.args.get('path', '')
    try:
        target, root = resolve_secure_path(name, subpath)
        if not target or not target.exists():
            return jsonify({"files": [], "path": subpath, "error": "Workspace not found."})
            
        if not target.is_dir():
             return jsonify({"error": "Path is not a directory."}), 400
             
        items = []
        for item in target.iterdir():
            stat = item.stat()
            items.append({
                "name": item.name,
                "type": "dir" if item.is_dir() else "file",
                "size": stat.st_size if item.is_file() else 0,
                "path": str(item.relative_to(root))
            })
            
        # Group directories at the top
        items.sort(key=lambda x: (x["type"] != "dir", x["name"].lower()))
        return jsonify({"files": items, "current_path": subpath})
    except PermissionError as e:
        return jsonify({"error": str(e)}), 403
    except Exception:
        logger.exception(f"Browser listing error for {name}")
        return jsonify({"error": "Internal browsing error."}), 500

@app.route('/api/files/<name>/download')
def api_browser_download(name):
    """Download a single file from the workspace."""
    subpath = request.args.get('path', '')
    try:
        target, _ = resolve_secure_path(name, subpath)
        if not target or not target.is_file():
             return jsonify({"error": "Target file not found."}), 404
             
        return send_file(target, as_attachment=True, download_name=target.name)
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/api/files/<name>/zip')
def api_browser_zip_download(name):
    """Bundle a workspace folder into a ZIP and download."""
    subpath = request.args.get('path', '')
    try:
        target, _ = resolve_secure_path(name, subpath)
        if not target or not target.exists():
             return jsonify({"error": "Target path not found."}), 404
             
        memory_file = BytesIO()
        with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
            if target.is_file():
                zf.write(target, target.name)
            else:
                for root_dir, _, files in os.walk(target):
                    for file in files:
                        file_path = Path(root_dir) / file
                        # Create relative archive paths
                        archive_name = file_path.relative_to(target.parent)
                        zf.write(file_path, archive_name)
        
        memory_file.seek(0)
        zip_name = f"{target.name}.zip" if subpath else f"{name}_workspace.zip"
        return send_file(memory_file, download_name=zip_name, as_attachment=True)
            
    except Exception:
        logger.exception(f"ZIP creation error for {name}")
        return jsonify({"error": "Failed to create archive."}), 500

# --- Entrypoint ---

def run_gui():
    """Start the manager application with the PyWebView desktop window."""
    logger.info("Initializing DaemonZero Manager GUI...")
    
    # Start Flask in a background daemon thread
    flask_thread = threading.Thread(target=lambda: app.run(host='127.0.0.1', port=8080, debug=False, use_reloader=False), daemon=True)
    flask_thread.start()
    
    # Give Flask a brief moment to bind to the port
    time.sleep(0.5)
    
    # Create the native desktop window
    webview.create_window('DaemonZero Manager', 'http://127.0.0.1:8080', width=1280, height=800)
    webview.start()

if __name__ == '__main__':
    # When running directly (development mode)
    if os.environ.get("DZ_CLI_MODE") == "1":
        app.run(host='0.0.0.0', port=8080, debug=True)
    else:
        run_gui()
