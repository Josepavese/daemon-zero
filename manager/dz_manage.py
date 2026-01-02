#!/usr/bin/env python3

import argparse
import subprocess
import sys
import os
import shutil
from pathlib import Path

import re

# Configuration
DEFAULT_IMAGE = "daemon-zero" # formerly agent0ai/agent-zero
BASE_PORT = 50080
HOME_DIR = Path.home()
BASE_DATA_DIR = HOME_DIR / "daemon-zero"

def sanitize_name(name):
    """Sanitize name to be Docker-compatible (alphanumeric, dots, underscores, dashes)."""
    # Replace spaces with dashes
    s = name.replace(" ", "-")
    # Remove chars that are not allowed
    s = re.sub(r'[^a-zA-Z0-9_.-]', '', s)
    return s

def check_docker():
    """Check if docker is available and running."""
    if shutil.which("docker") is None:
        print("[ERROR] Docker is not installed or not in PATH.")
        sys.exit(1)
    
    try:
        subprocess.run(["docker", "info"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    except subprocess.CalledProcessError:
        print("[ERROR] Docker daemon is not running or user does not have permission.")
        sys.exit(1)

def container_exists(name):
    """Check if container exists (running or stopped)."""
    res = subprocess.run(
        ["docker", "ps", "-a", "--filter", f"name=^{name}$", "--format", "{{.Names}}"],
        capture_output=True, text=True
    )
    return res.stdout.strip() == name

def is_container_running(name):
    """Check if container is running."""
    res = subprocess.run(
        ["docker", "ps", "--filter", f"name=^{name}$", "--format", "{{.Names}}"],
        capture_output=True, text=True
    )
    return res.stdout.strip() == name

def get_port_mapping(name):
    """Get the host port mapped to port 80 for the container."""
    res = subprocess.run(
        ["docker", "port", name, "80"],
        capture_output=True, text=True
    )
    # Output format: 0.0.0.0:50080\n[::]:50080
    if not res.stdout:
        return None
    try:
        # Take the first line and split
        return res.stdout.splitlines()[0].split(":")[-1]
    except IndexError:
        return None

def find_available_port(start_port):
    """Find next available port starting from start_port."""
    # Simple check, not robust against race conditions but sufficient for single-user CLI
    import socket
    port = start_port
    while True:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(('localhost', port)) != 0:
                return port
        port += 1

def start_agent(args):
    """Start an agent instance."""
    safe_name = sanitize_name(args.name)
    name = f"daemon-zero-{safe_name}"
    
    # 1. Check if already running
    if is_container_running(name):
        port = get_port_mapping(name)
        print(f"[INFO] Container '{name}' is already running on port {port}.")
        return

    # 2. Check if stopped (exists but exited)
    if container_exists(name):
        print(f"[INFO] Container '{name}' exists but is stopped. Restarting...")
        subprocess.run(["docker", "start", name], check=True)
        port = get_port_mapping(name)
        print(f"[SUCCESS] Container '{name}' started on port {port}.")
        return

    # 3. New Instance
    # Determine port
    if args.port:
        port = args.port
    else:
        # Auto-assign if not specified
        port = find_available_port(BASE_PORT)
        print(f"[INFO] Auto-selected port {port} for new instance.")

    # Prepare Directories
    instance_dir = BASE_DATA_DIR / args.name
    # If default, use base. If named instance, create subdir? 
    # Current README says ~/daemon-zero/{config...}
    # To support multiple instances properly, we should probably segregate data.
    # However, user README implies a single shared structure or maybe just one instance.
    # PROPOSAL: 
    # - Default instance maps to ~/daemon-zero/ root folders as per README.
    # - Named instances map to ~/agent-zero/<name>/{...} to prevent conflict?
    # Let's stick to README structure for "default" and segregation for others.
    
    if safe_name == "default":
        # Default instance
        if args.ephemeral:
             data_mounts = [
                f"-v{BASE_DATA_DIR}/config:/a0/config",
                f"-v{BASE_DATA_DIR}/agents:/a0/agents",
            ]
        else:
            data_mounts = [
                f"-v{BASE_DATA_DIR}/config:/a0/config",
                f"-v{BASE_DATA_DIR}/agents:/a0/agents",
                f"-v{BASE_DATA_DIR}/memory:/a0/memory",
                f"-v{BASE_DATA_DIR}/knowledge:/a0/knowledge"
            ]
        # Ensure base dirs exist
        for d in ["config", "agents", "memory", "knowledge"]:
            (BASE_DATA_DIR / d).mkdir(parents=True, exist_ok=True)

    else:
        # Named instance
        instance_path = BASE_DATA_DIR / safe_name
        
        # Ensure dirs exist
        for d in ["config", "agents", "memory/embeddings", "memory/default", "knowledge", "config/tmp", "workspace"]:
            (instance_path / d).mkdir(parents=True, exist_ok=True)
            
        # Ensure .env exists (empty) if not present, to avoid docker directory creation issue if mapped as file
        env_file = instance_path / "config" / ".env"
        if not env_file.exists():
            env_file.touch()

        if args.ephemeral:
            data_mounts = [
                f"-v{instance_path}/config:/a0/config",
                f"-v{instance_path}/agents:/a0/agents",
                f"-v{instance_path}/config/.env:/a0/.env",
                f"-v{instance_path}/config/tmp:/a0/tmp",
                f"-v{instance_path}/workspace:/a0/usr/projects"
            ]
        else:
            data_mounts = [
                f"-v{instance_path}/config:/a0/config",
                f"-v{instance_path}/agents:/a0/agents",
                f"-v{instance_path}/memory:/a0/memory",
                f"-v{instance_path}/knowledge:/a0/knowledge",
                f"-v{instance_path}/config/.env:/a0/.env",
                f"-v{instance_path}/config/tmp:/a0/tmp",
                f"-v{instance_path}/workspace:/a0/usr/projects"
            ]


    print(f"[INFO] Starting new {'ephemeral ' if args.ephemeral else ''}container '{name}' on port {port}...")
    
    cmd = [
        "docker", "run", "-d",
        "--name", name,
        "--restart=unless-stopped" if not args.ephemeral else "--rm",
        "-p", f"{port}:80"
    ] + data_mounts + [DEFAULT_IMAGE]

    try:
        subprocess.run(cmd, check=True)
        print(f"[SUCCESS] Started '{name}' on http://localhost:{port}")
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Failed to start container: {e}")

def stop_agent(args):
    """Stop an agent instance."""
    safe_name = sanitize_name(args.name)
    name = f"daemon-zero-{safe_name}"
    
    if not container_exists(name):
        print(f"[WARN] Container '{name}' does not exist.")
        return

    if not is_container_running(name):
        print(f"[INFO] Container '{name}' is already stopped.")
        return

    print(f"[INFO] Stopping container '{name}'...")
    subprocess.run(["docker", "stop", name], check=True)
    print(f"[SUCCESS] Stopped '{name}'.")

def delete_agent(args):
    """Delete an agent instance and optionally its data."""
    safe_name = sanitize_name(args.name)
    name = f"daemon-zero-{safe_name}"
    
    # 1. Check existence
    if not container_exists(name):
        print(f"[WARN] Container '{name}' does not exist.")
        # If forcing data delete, we might still proceed, but for now let's rely on container name
        # However, user might want to clean up data of an already removed container.
        # Let's check data dir existence too.
    
    # Check data dir
    if safe_name == "default":
        data_path = BASE_DATA_DIR
        # For default, we don't delete the root base dir as it contains other agents
        is_default = True
    else:
        data_path = BASE_DATA_DIR / safe_name
        is_default = False
    
    data_exists = data_path.exists() if not is_default else (BASE_DATA_DIR / "config").exists()

    if not container_exists(name) and not (args.data and data_exists):
        print(f"[ERROR] No container '{name}' and no data found to delete.")
        return

    # 2. Confirmation
    if not args.force:
        msg = f"Are you sure you want to delete container '{name}'?"
        if args.data:
            msg += f" AND PERMANENTLY DELETE data at '{data_path}'?"
        
        confirm = input(f"{msg} [y/N]: ")
        if confirm.lower() != 'y':
            print("[INFO] Aborted.")
            return

    # 3. Stop and Remove Container
    if container_exists(name):
        if is_container_running(name):
            print(f"[INFO] Stopping container '{name}'...")
            subprocess.run(["docker", "stop", name], check=True)
        
        print(f"[INFO] Removing container '{name}'...")
        subprocess.run(["docker", "rm", name], check=True)
        print(f"[SUCCESS] Container '{name}' removed.")

    # 4. Remove Data
    if args.data:
        if is_default:
            print(f"[INFO] Deleting default agent data (config, agents, memory, knowledge) from {BASE_DATA_DIR}...")
            # Only delete the specific text subdirs to avoid wiping other agent dirs
            for sub in ["config", "agents", "memory", "knowledge"]:
                p = BASE_DATA_DIR / sub
                if p.exists():
                    shutil.rmtree(p)
                    print(f"  - Deleted {p}")
        else:
            if data_path.exists():
                print(f"[INFO] Deleting data directory {data_path}...")
                try:
                    shutil.rmtree(data_path)
                except PermissionError:
                    print(f"[WARN] Permission denied deleting {data_path}. Attempting cleanup via Docker...")
                    # Fallback: Use docker to delete files owned by root
                    # We mount the PARENT directory to /clean and delete the folder name inside
                    parent = data_path.parent.resolve()
                    dirname = data_path.name
                    cmd = [
                        "docker", "run", "--rm",
                        "-v", f"{parent}:/clean_target",
                        "alpine", "rm", "-rf", f"/clean_target/{dirname}"
                    ]
                    try:
                        subprocess.run(cmd, check=True)
                        print(f"[SUCCESS] Data directory deleted via Docker.")
                    except subprocess.CalledProcessError as e:
                        print(f"[ERROR] Failed to delete data via Docker fallback: {e}")
                except Exception as e:
                    print(f"[ERROR] Failed to delete data: {e}")
                
                if not data_path.exists():
                     print(f"[SUCCESS] Data directory deleted.")
            else:
                print(f"[WARN] Data directory {data_path} not found.")

def restart_agent(args):
    """Restart an agent instance."""
    stop_agent(args)
    start_agent(args)

def get_agents():
    """Get list of agent instances as dictionaries."""
    res = subprocess.run(
        ["docker", "ps", "-a", "--filter", "name=^daemon-zero-", "--format", "{{.Names}}|{{.Status}}"],
        capture_output=True, text=True
    )
    
    agents = []
    if not res.stdout:
        return agents

    for line in res.stdout.splitlines():
        if not line: continue
        parts = line.split("|")
        c_name = parts[0]
        c_status = parts[1]
        
        port = get_port_mapping(c_name)
        display_name = c_name.replace("daemon-zero-", "")
        
        agents.append({
            "name": c_name, # full docker name
            "display_name": display_name, 
            "status": c_status,
            "port": port
        })
    return agents

def list_agents(args):
    """List all daemon-zero containers."""
    print(f"{'NAME':<30} {'STATUS':<20} {'PORT':<10}")
    print("-" * 60)
    
    agents = get_agents()
    
    if not agents:
        print("No agents found.")
        return

    for a in agents:
        port_str = a['port'] if a['port'] else "N/A"
        print(f"{a['display_name']:<30} {a['status']:<20} {port_str:<10}")
    


def logs_agent(args):
    """View logs for an agent."""
    safe_name = sanitize_name(args.name)
    name = f"daemon-zero-{safe_name}"
    if not container_exists(name):
        print(f"[ERROR] Container '{name}' not found.")
        return
    
    # Run docker logs -f
    try:
        subprocess.run(["docker", "logs", "-f", name])
    except KeyboardInterrupt:
        print("\n[INFO] Log view exited.")

def main():
    parser = argparse.ArgumentParser(description="Manage DaemonZero Instances")
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # Start
    p_start = subparsers.add_parser("start", help="Start an agent instance")
    p_start.add_argument("name", nargs="?", default="default", help="Name of the agent instance (default: default)")
    p_start.add_argument("--port", type=int, help="Specific host port to bind (default: auto)")
    p_start.add_argument("--ephemeral", action="store_true", help="Run in ephemeral mode (auto-remove on stop, no persistent memory/knowledge)")
    p_start.set_defaults(func=start_agent)

    # Stop
    p_stop = subparsers.add_parser("stop", help="Stop an agent instance")
    p_stop.add_argument("name", nargs="?", default="default", help="Name of the agent instance")
    p_stop.set_defaults(func=stop_agent)

    # Delete
    p_delete = subparsers.add_parser("delete", help="Delete an agent instance")
    p_delete.add_argument("name", nargs="?", default="default", help="Name of the agent instance")
    p_delete.add_argument("--data", action="store_true", help="Also delete persistent data directory")
    p_delete.add_argument("--force", "-f", action="store_true", help="Force deletion without confirmation")
    p_delete.set_defaults(func=delete_agent)

    # Restart
    p_restart = subparsers.add_parser("restart", help="Restart an agent instance")
    p_restart.add_argument("name", nargs="?", default="default", help="Name of the agent instance")
    p_restart.add_argument("--port", type=int, help="Specific host port (if re-creating)")
    p_restart.set_defaults(func=restart_agent)

    # List
    p_list = subparsers.add_parser("list", help="List all agent instances")
    p_list.set_defaults(func=list_agents)

    # Logs
    p_logs = subparsers.add_parser("logs", help="Follow logs of an instance")
    p_logs.add_argument("name", nargs="?", default="default", help="Name of the agent instance")
    p_logs.set_defaults(func=logs_agent)

    args = parser.parse_args()
    
    check_docker()
    
    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
