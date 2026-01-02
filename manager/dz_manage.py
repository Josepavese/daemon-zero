#!/usr/bin/env python3
"""
DaemonZero Instance Manager (CLI & API Backend)
Handles Docker container orchestration for DaemonZero agents.
"""

import argparse
import subprocess
import sys
import os
import shutil
import logging
import re
import socket
import contextlib
from pathlib import Path
from io import StringIO

# --- Logging Configuration ---
# Configure logging to output to both console and optionally be captured by the manager GUI.
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("dz_manage")

# --- Configuration Constants ---
DEFAULT_IMAGE = "daemon-zero"
BASE_PORT = 50080
HOME_DIR = Path.home()
BASE_DATA_DIR = HOME_DIR / "daemon-zero"

def sanitize_name(name: str) -> str:
    """
    Sanitize an instance name to be Docker-compatible.
    Allowed characters: alphanumeric, dots, underscores, dashes.
    """
    # Replace spaces with dashes
    s = name.replace(" ", "-")
    # Remove characters that are not allowed by Docker naming conventions
    s = re.sub(r'[^a-zA-Z0-9_.-]', '', s)
    return s

def check_docker():
    """
    Verify if Docker is installed and the daemon is accessible.
    Exits the process if Docker is not available.
    """
    if shutil.which("docker") is None:
        logger.error("Docker is not installed or not in PATH.")
        return False
    
    try:
        # Use a simple command to probe the daemon
        subprocess.run(["docker", "info"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        logger.error("Docker daemon is not running or the current user lacks permissions.")
        return False

def container_exists(name: str) -> bool:
    """Check if a Docker container with the specified name exists (running or stopped)."""
    try:
        res = subprocess.run(
            ["docker", "ps", "-a", "--filter", f"name=^{name}$", "--format", "{{.Names}}"],
            capture_output=True, text=True, check=True
        )
        return res.stdout.strip() == name
    except subprocess.SubprocessError as e:
        logger.error(f"Failed to check container existence for '{name}': {e}")
        return False

def is_container_running(name: str) -> bool:
    """Check if a Docker container with the specified name is currently running."""
    try:
        res = subprocess.run(
            ["docker", "ps", "--filter", f"name=^{name}$", "--format", "{{.Names}}"],
            capture_output=True, text=True, check=True
        )
        return res.stdout.strip() == name
    except subprocess.SubprocessError as e:
        logger.error(f"Failed to check if container '{name}' is running: {e}")
        return False

def get_port_mapping(name: str) -> str:
    """
    Retrieve the host port mapped to the container's internal port 80.
    Returns the port as a string or None if not found.
    """
    try:
        res = subprocess.run(
            ["docker", "port", name, "80"],
            capture_output=True, text=True, check=True
        )
        # Expected output format: 0.0.0.0:50080 or [::]:50080
        if not res.stdout:
            return None
        # Split by newline and colon to isolate the port number
        first_line = res.stdout.splitlines()[0]
        return first_line.split(":")[-1]
    except (subprocess.SubprocessError, IndexError) as e:
        logger.debug(f"Could not retrieve port mapping for '{name}': {e}")
        return None

def find_available_port(start_port: int) -> int:
    """
    Find the next available TCP port starting from the given port number.
    Tries to bind to 0.0.0.0 to ensure the port is truly free for Docker to use.
    """
    port = start_port
    while port <= 65535:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                # Set SO_REUSEADDR to avoid "Address already in use" errors during quick retries
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(('0.0.0.0', port))
                return port
            except socket.error:
                port += 1
    
    raise RuntimeError("No available ports found in the valid range (up to 65535).")

def start_agent(args):
    """
    Initialize and start a DaemonZero agent instance.
    Handles directory creation, volume mapping, and container execution.
    """
    safe_name = sanitize_name(args.name)
    container_name = f"daemon-zero-{safe_name}"
    
    # 1. Existing container handling
    if is_container_running(container_name):
        port = get_port_mapping(container_name)
        logger.info(f"Container '{container_name}' is already running on port {port}.")
        return

    if container_exists(container_name):
        logger.info(f"Container '{container_name}' exists but is stopped. Restarting...")
        try:
            subprocess.run(["docker", "start", container_name], check=True)
            port = get_port_mapping(container_name)
            logger.info(f"[SUCCESS] Container '{container_name}' started on port {port}.")
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to restart container '{container_name}': {e}")
        return

    # 2. Port Selection
    port = args.port if args.port else find_available_port(BASE_PORT)
    if not args.port:
        logger.info(f"Auto-selected available port {port} for new instance.")

    # 3. Directory and Volume Configuration
    data_mounts = []
    
    if safe_name == "default":
        # Legacy support for 'default' instance using root data directory
        instance_path = BASE_DATA_DIR
        subdirs = ["config", "agents", "memory", "knowledge"]
        for d in subdirs:
            (instance_path / d).mkdir(parents=True, exist_ok=True)
        
        # Define mounts for default structure
        data_mounts = [
            "-v", f"{instance_path}/config:/dz/config",
            "-v", f"{instance_path}/agents:/dz/agents",
        ]
        if not args.ephemeral:
            data_mounts += [
                "-v", f"{instance_path}/memory:/dz/memory",
                "-v", f"{instance_path}/knowledge:/dz/knowledge"
            ]
    else:
        # Modern structure with named instance segregation
        instance_path = BASE_DATA_DIR / safe_name
        subdirs = ["config", "agents", "memory/embeddings", "memory/default", "knowledge", "config/tmp", "workspace"]
        for d in subdirs:
            (instance_path / d).mkdir(parents=True, exist_ok=True)
            
        # Ensure .env exists to prevent Docker from creating a directory instead of a file
        env_file = instance_path / "config" / ".env"
        if not env_file.exists():
            env_file.touch()

        # Shared mounts for named instances
        data_mounts = [
            "-v", f"{instance_path}/config:/dz/config",
            "-v", f"{instance_path}/agents:/dz/agents",
            "-v", f"{instance_path}/config/.env:/dz/.env",
            "-v", f"{instance_path}/config/tmp:/dz/tmp",
            "-v", f"{instance_path}/workspace:/dz/usr/projects"
        ]
        if not args.ephemeral:
            data_mounts += [
                "-v", f"{instance_path}/memory:/dz/memory",
                "-v", f"{instance_path}/knowledge:/dz/knowledge",
            ]

    # 4. Container Execution
    logger.info(f"Spawning {'ephemeral ' if args.ephemeral else ''}container '{container_name}' on port {port}...")
    
    cmd = [
        "docker", "run", "-d",
        "--name", container_name,
        "--restart=unless-stopped" if not args.ephemeral else "--rm",
        "-p", f"{port}:80"
    ] + data_mounts + [DEFAULT_IMAGE]

    try:
        subprocess.run(cmd, check=True)
        logger.info(f"[SUCCESS] Agent '{safe_name}' is accessible at http://localhost:{port}")
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to launch Docker container: {e}")
        raise

def stop_agent(args):
    """Gracefully stop a running agent instance."""
    safe_name = sanitize_name(args.name)
    container_name = f"daemon-zero-{safe_name}"
    
    if not container_exists(container_name):
        logger.warning(f"Container '{container_name}' does not exist.")
        return

    if not is_container_running(container_name):
        logger.info(f"Container '{container_name}' is already stopped.")
        return

    logger.info(f"Stopping container '{container_name}'...")
    try:
        subprocess.run(["docker", "stop", container_name], check=True)
        logger.info(f"[SUCCESS] Stopped '{container_name}'.")
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to stop container '{container_name}': {e}")

def delete_agent(args):
    """
    Remove an agent instance. 
    Optionally deletes the associated local data directory.
    """
    safe_name = sanitize_name(args.name)
    container_name = f"daemon-zero-{safe_name}"
    
    is_default = (safe_name == "default")
    data_path = BASE_DATA_DIR if is_default else BASE_DATA_DIR / safe_name
    
    # Check if anything exists to delete
    c_exists = container_exists(container_name)
    d_exists = data_path.exists() if not is_default else (BASE_DATA_DIR / "config").exists()

    if not c_exists and not (args.data and d_exists):
        logger.error(f"Nothing found to delete for agent '{safe_name}'.")
        return

    # Interactive confirmation if not forced
    if not args.force:
        msg = f"Permanently DELETE container '{container_name}'?"
        if args.data:
            msg += f" (This will ALSO WIPED all data at {data_path})"
        
        confirm = input(f"{msg} [y/N]: ")
        if confirm.lower() != 'y':
            logger.info("Operation aborted by user.")
            return

    # 1. Container Cleanup
    if c_exists:
        if is_container_running(container_name):
            logger.info(f"Stopping running container '{container_name}'...")
            try:
                subprocess.run(["docker", "stop", container_name], check=True)
            except subprocess.SubprocessError: 
                pass # Continue to removal
        
        logger.info(f"Removing container '{container_name}'...")
        try:
            subprocess.run(["docker", "rm", container_name], check=True)
            logger.info(f"[SUCCESS] Container '{container_name}' removed.")
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to remove container: {e}")

    # 2. Data Cleanup
    if args.data and d_exists:
        logger.info(f"Wiping data directory: {data_path}")
        try:
            if is_default:
                # Protect other instance folders if cleaning 'default'
                for sub in ["config", "agents", "memory", "knowledge"]:
                    p = BASE_DATA_DIR / sub
                    if p.exists():
                        shutil.rmtree(p)
            else:
                shutil.rmtree(data_path)
            logger.info("[SUCCESS] Data wiped.")
        except PermissionError:
            # Fallback for files created by root inside Docker
            logger.warning("Permission denied during deletion. Using Docker fallback for cleanup...")
            parent = data_path.parent.resolve()
            folder_name = data_path.name
            cleanup_cmd = [
                "docker", "run", "--rm",
                "-v", f"{parent}:/target",
                "alpine", "rm", "-rf", f"/target/{folder_name}"
            ]
            try:
                subprocess.run(cleanup_cmd, check=True)
                logger.info("[SUCCESS] Data wiped via Docker fallback.")
            except subprocess.SubprocessError as e:
                logger.error(f"Docker cleanup fallback failed: {e}")
        except Exception as e:
            logger.error(f"Detailed failure during data deletion: {e}")

def get_agents() -> list:
    """
    Retrieve a list of all containers managed by DaemonZero.
    Returns a list of dictionaries with instance metadata.
    """
    try:
        res = subprocess.run(
            ["docker", "ps", "-a", "--filter", "name=^daemon-zero-", "--format", "{{.Names}}|{{.Status}}"],
            capture_output=True, text=True, check=True
        )
    except (subprocess.SubprocessError, FileNotFoundError) as e:
        logger.debug(f"Docker listing skipped (Docker missing or error): {e}")
        return []
    
    agents = []
    for line in res.stdout.splitlines():
        if not line: continue
        try:
            name, status = line.split("|")
            display_name = name.replace("daemon-zero-", "")
            port = get_port_mapping(name)
            
            agents.append({
                "name": name,
                "display_name": display_name, 
                "status": status,
                "port": port or "N/A"
            })
        except ValueError:
            continue
    return agents

def list_agents(args):
    """Print a table of all DaemonZero agents to the console."""
    agents = get_agents()
    if not agents:
        logger.info("No agents are currently registered.")
        return

    print(f"\n{'NAME':<30} {'STATUS':<25} {'PORT':<10}")
    print("-" * 75)
    for a in agents:
        print(f"{a['display_name']:<30} {a['status']:<25} {a['port']:<10}")
    print()

def logs_agent(args):
    """
    Stream live logs from a specific agent container.
    """
    safe_name = sanitize_name(args.name)
    container_name = f"daemon-zero-{safe_name}"
    
    if not container_exists(container_name):
        logger.error(f"Cannot find instance '{safe_name}'.")
        return
    
    logger.info(f"Attaching to logs for '{container_name}' (Ctrl+C to detach)...")
    try:
        subprocess.run(["docker", "logs", "-f", container_name])
    except KeyboardInterrupt:
        print("\n[INFO] Detached from logs.")

def main():
    """Main CLI Entrypoint."""
    parser = argparse.ArgumentParser(description="DaemonZero Instance Orchestrator")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Start Command
    p_start = subparsers.add_parser("start", help="Launch or restart an instance")
    p_start.add_argument("name", nargs="?", default="default", help="Instance name")
    p_start.add_argument("--port", type=int, help="Host port (default: auto-assign)")
    p_start.add_argument("--ephemeral", action="store_true", help="Delete container on stop, no persistent storage")
    p_start.set_defaults(func=start_agent)

    # Stop Command
    p_stop = subparsers.add_parser("stop", help="Shutdown a running instance")
    p_stop.add_argument("name", nargs="?", default="default", help="Instance name")
    p_stop.set_defaults(func=stop_agent)

    # Delete Command
    p_delete = subparsers.add_parser("delete", help="Remove an instance and clean resources")
    p_delete.add_argument("name", nargs="?", default="default", help="Instance name")
    p_delete.add_argument("--data", action="store_true", help="Wipe configuration and knowledge directories")
    p_delete.add_argument("--force", "-f", action="store_true", help="Skip confirmation prompt")
    p_delete.set_defaults(func=delete_agent)

    # List Command
    p_list = subparsers.add_parser("list", help="Display all active and inactive instances")
    p_list.set_defaults(func=list_agents)

    # Logs Command
    p_logs = subparsers.add_parser("logs", help="View real-time logs from an instance")
    p_logs.add_argument("name", nargs="?", default="default", help="Instance name")
    p_logs.set_defaults(func=logs_agent)

    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return

    # Global prerequisites check
    check_docker()
    
    try:
        args.func(args)
    except Exception as e:
        logger.exception(f"An unexpected error occurred during command execution: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
