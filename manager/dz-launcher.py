#!/usr/bin/env python3
import os
import subprocess
import json
import sys
from pathlib import Path
from flask import Flask, render_template, jsonify, request, redirect, url_for, send_file, send_from_directory
import script_utils
import dz_manage
import webview
from io import StringIO, BytesIO
import contextlib
import mimetypes
import zipfile
import shutil
import threading
import time
import platform_utils
import setup_linux

app = Flask(__name__)

def get_resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

# Configuration
HOME_DIR = Path.home()
BASE_DATA_DIR = HOME_DIR / "agent-zero"
MANAGER_CONFIG_PATH = BASE_DATA_DIR / "manager_config.json" # Store in agent-zero dir for persistence
app.template_folder = get_resource_path("templates")

def load_manager_config():
    if not MANAGER_CONFIG_PATH.exists():
        return {
            "default_api_keys": {},
            "default_models": {},
            "docker_installed": False,
            "user_in_group": False
        }
    return json.loads(MANAGER_CONFIG_PATH.read_text())

def save_manager_config(config):
    MANAGER_CONFIG_PATH.write_text(json.dumps(config, indent=4))

def check_system():
    """Verify docker and group."""
    status = {
        "docker_installed": False,
        "user_in_group": False,
        "base_dir_ready": False,
        "ready": False
    }
    
    # Docker install check
    try:
        subprocess.run(["docker", "--version"], capture_output=True, check=True)
        status["docker_installed"] = True
    except:
        pass
        
    # User group check
    try:
        res = subprocess.run(["groups"], capture_output=True, text=True)
        if "docker" in res.stdout:
            status["user_in_group"] = True
    except:
        pass

    # Basic dirs
    status["base_dir_ready"] = BASE_DATA_DIR.exists()
    
    status["ready"] = status["docker_installed"] and status["user_in_group"] and status["base_dir_ready"]
    return status

# Helper class for args
class ManageArgs:
    def __init__(self, **kwargs):
        self.name = "default"
        self.port = None
        self.ephemeral = False
        self.data = False
        self.force = False
        self.__dict__.update(kwargs)

import threading

# Lock for stdout capture to prevent race conditions in multithreaded Flask
manage_lock = threading.Lock()

def run_manage_function(func, **kwargs):
    """Run an dz_manage function and capture its output."""
    output = StringIO()
    success = False
    args = ManageArgs(**kwargs)
    
    # Acquire lock to ensure we only capture stdout from THIS function execution
    # since contextlib.redirect_stdout patches global sys.stdout
    with manage_lock:
        try:
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
                func(args)
            msg = output.getvalue()
            if "ERROR" in msg:
                success = False
            else:
                success = True
        except Exception as e:
            msg = output.getvalue() + f"\nException: {str(e)}"
            success = False
        
    return success, msg

@app.route('/api/instances')
def api_instances():
    # Use direct function call to get structured data
    try:
        raw_agents = dz_manage.get_agents()
        instances = []
        for a in raw_agents:
            # Map robustly
            instances.append({
                "name": a.get("display_name", a["name"]),
                "status": a.get("status", ""),
                "port": a.get("port") or "N/A"
            })
        return jsonify(instances)
    except Exception as e:
        print(f"Error fetching instances: {e}")
        return jsonify([])

@app.route('/')
def index():
    status = check_system()
    config = load_manager_config()
    return render_template('index.html', system_status=status, manager_config=config)

@app.route('/api/status')
def api_status():
    return jsonify(check_system())

@app.route('/api/setup/install_docker', methods=['POST'])
def api_install_docker():
    data = request.json
    password = data.get('password')
    if not password:
        return jsonify({"success": False, "message": "Password required"})

    # Use the new Python-based installer
    if platform_utils.is_linux():
        success, message = setup_linux.install_docker_ubuntu(password)
        if success:
            # Also setup base directories
            setup_linux.setup_base_dirs(BASE_DATA_DIR)
            return jsonify({"success": True, "message": message})
        else:
            return jsonify({"success": False, "message": message})
    
    return jsonify({"success": False, "message": "Platform not supported for auto-install yet."})

@app.route('/api/setup/fix_group', methods=['POST'])
def api_fix_group():
    data = request.json
    password = data.get('password')
    if platform_utils.is_linux():
        success, message = setup_linux.add_user_to_docker_group(password)
        return jsonify({"success": success, "message": message})
    
    return jsonify({"success": False, "message": "Platform not supported for auto-group-fix."})

@app.route('/api/setup/create_shortcut', methods=['POST'])
def api_create_shortcut():
    if platform_utils.is_linux():
        success, message = setup_linux.create_desktop_shortcut()
        return jsonify({"success": success, "message": message})
    return jsonify({"success": False, "message": "Shortcut creation only supported on Linux for now."})

@app.route('/api/manager_config', methods=['GET', 'POST'])
def api_manager_config():
    if request.method == 'POST':
        save_manager_config(request.json)
        return jsonify({"success": True})
    return jsonify(load_manager_config())

@app.route('/api/start/<name>', methods=['POST'])
def api_start(name):
    # Before starting, if it's a NEW instance (dirs don't exist), we might want to inject default keys and models
    instance_dir = BASE_DATA_DIR / name
    config_dir = instance_dir / "config"
    tmp_dir = config_dir / "tmp"
    
    is_new_config = not config_dir.exists()
    
    if is_new_config:
        config_dir.mkdir(parents=True, exist_ok=True)
        tmp_dir.mkdir(parents=True, exist_ok=True)
        
        manager_config = load_manager_config()
        
        # 1. Inject keys into .env
        env_content = ""
        for k, v in manager_config.get("default_api_keys", {}).items():
            if v: env_content += f"{k}={v}\n"
        
        # Set default workspace
        env_content += "WORK_DIR=/a0/usr/projects\n"
        
        if env_content:
            (config_dir / ".env").write_text(env_content)
            
        # 2. Inject models into settings.json
        # We start with a basic template or just the model fields
        default_models = manager_config.get("default_models", {})
        if default_models:
            settings_data = {
                "chat_model_provider": default_models.get("chat_provider", "groq"),
                "chat_model_name": default_models.get("chat_model", "llama-3.3-70b-versatile"),
                "util_model_provider": default_models.get("util_provider", "groq"),
                "util_model_name": default_models.get("util_model", "llama-3.1-8b-instant"),
                "browser_model_provider": default_models.get("browser_provider", "groq"),
                "browser_model_name": default_models.get("browser_model", "llama-3.1-8b-instant")
            }
            (tmp_dir / "settings.json").write_text(json.dumps(settings_data, indent=4))
    
    success, msg = run_manage_function(dz_manage.start_agent, name=name)
    return jsonify({"success": success, "message": msg})

@app.route('/api/stop/<name>', methods=['POST'])
def api_stop(name):
    success, msg = run_manage_function(dz_manage.stop_agent, name=name)
    return jsonify({"success": success, "message": msg})

@app.route('/api/delete/<name>', methods=['POST'])
def api_delete(name):
    # Retrieve flags
    data = request.json or {}
    success, msg = run_manage_function(dz_manage.delete_agent, name=name, force=True, data=data.get('delete_data'))
    return jsonify({"success": success, "message": msg})

@app.route('/api/config/<name>', methods=['GET'])
def api_get_config(name):
    """Get config files content."""
    # Security: basic path sanitization
    if ".." in name or "/" in name:
        return jsonify({"error": "Invalid name"}), 400
        
    instance_dir = BASE_DATA_DIR / name
    
    # Paths
    env_path = instance_dir / "config" / ".env"
    settings_path = instance_dir / "config" / "tmp" / "settings.json"
    
    config = {
        "env": "",
        "settings": ""
    }
    
    if env_path.exists():
        config["env"] = env_path.read_text()
    
    if settings_path.exists():
        config["settings"] = settings_path.read_text()
        
    return jsonify(config)

@app.route('/api/config/<name>', methods=['POST'])
def api_save_config(name):
    """Save config files."""
    if ".." in name or "/" in name:
        return jsonify({"error": "Invalid name"}), 400
        
    data = request.json
    instance_dir = BASE_DATA_DIR / name
    
    # Ensure dirs exist (in case they were deleted or manual creation)
    (instance_dir / "config" / "tmp").mkdir(parents=True, exist_ok=True)
    
    if "env" in data:
        (instance_dir / "config" / ".env").write_text(data["env"])
        
    if "settings" in data:
        (instance_dir / "config" / "tmp" / "settings.json").write_text(data["settings"])
        
    return jsonify({"success": True})

@app.route('/api/logs/<name>')
def api_logs(name):
    """Get logs via docker logs."""
    # dz_manage logs uses 'docker logs -f' which blocks.
    # We should just fetch current logs for the snapshot.
    # dz_manage.logs_agent is designed for interactive tailing.
    # Let's use subprocess directly here for docker logs just to get the last N lines or similar?
    # Or just call docker logs directly.
    container_name = f"agent-zero-{dz_manage.sanitize_name(name)}"
    try:
        res = subprocess.run(["docker", "logs", "--tail", "1000", container_name], capture_output=True, text=True)
        logs = res.stdout + res.stderr
    except Exception as e:
        logs = str(e)
    return jsonify({"logs": logs})

# File Browser Endpoints

def resolve_workspace_path(instance_name, subpath=""):
    """Securely resolve path within instance workspace."""
    if ".." in instance_name or "/" in instance_name:
        raise ValueError("Invalid instance name")
    
    workspace_root = (BASE_DATA_DIR / instance_name / "workspace").resolve()
    if not workspace_root.exists():
        # Fallback if dir doesn't exist yet
        return None, None
        
    if not subpath:
        return workspace_root, workspace_root
        
    # Prevent traversal
    target_path = (workspace_root / subpath).resolve()
    if not str(target_path).startswith(str(workspace_root)):
        raise ValueError("Path traversal attempted")
        
    return target_path, workspace_root

@app.route('/api/files/<name>')
def api_files_list(name):
    """List files in workspace."""
    subpath = request.args.get('path', '')
    try:
        target, root = resolve_workspace_path(name, subpath)
        if not target or not target.exists():
            return jsonify({"files": [], "path": subpath, "error": "Not found"})
            
        if not target.is_dir():
             return jsonify({"error": "Not a directory"}), 400
             
        items = []
        for item in target.iterdir():
            stat = item.stat()
            items.append({
                "name": item.name,
                "type": "dir" if item.is_dir() else "file",
                "size": stat.st_size if item.is_file() else 0,
                "path": str(item.relative_to(root))
            })
            
        # Sort: directories first, then files
        items.sort(key=lambda x: (x["type"] != "dir", x["name"].lower()))
        
        return jsonify({"files": items, "current_path": subpath})
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/api/files/<name>/download')
def api_files_download(name):
    """Download single file."""
    subpath = request.args.get('path', '')
    try:
        target, root = resolve_workspace_path(name, subpath)
        if not target or not target.is_file():
             return jsonify({"error": "File not found"}), 404
             
        return send_file(target, as_attachment=True, download_name=target.name)
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/api/files/<name>/zip')
def api_files_zip(name):
    """Zip folder and download."""
    subpath = request.args.get('path', '')
    try:
        target, root = resolve_workspace_path(name, subpath)
        if not target or not target.exists():
             return jsonify({"error": "Path not found"}), 404
             
        # Create zip in memory
        memory_file = BytesIO()
        with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
            if target.is_file():
                zf.write(target, target.name)
            else:
                for root_dir, dirs, files in os.walk(target):
                    for file in files:
                        file_path = Path(root_dir) / file
                        archive_name = file_path.relative_to(target.parent)
                        zf.write(file_path, archive_name)
        
        memory_file.seek(0)
        zip_name = f"{target.name}.zip" if subpath else f"{name}_workspace.zip"
        return send_file(memory_file, download_name=zip_name, as_attachment=True)
            
    except Exception as e:
        return jsonify({"error": str(e)}), 400

if __name__ == '__main__':
    print("Starting DaemonZero GUI on http://0.0.0.0:8080")
    app.run(host='0.0.0.0', port=8080, debug=True)
