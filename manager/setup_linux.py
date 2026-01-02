"""
System Setup Utilities for Linux.
Handles Docker installation, group permissions, and directory structure setup.
"""

import subprocess
import os
import logging
from pathlib import Path

# --- Constants ---
DOCKER_INSTALL_URL = "https://get.docker.com"

def run_with_sudo(command_list, password, logger_func=print):
    """
    Execute a command with sudo and a provided password.
    
    Args:
        command_list (list): The command to run as a list of strings (e.g., ["apt-get", "update"]).
        password (str): The sudo password to pipe to the command.
        logger_func (callable): Function to receive stdout/stderr lines for logging.
        
    Returns:
        subprocess.Popen: The completed process object.
    """
    # For sudo -S to work with list-based arguments, we need to pass the password to stdin.
    # We avoid shell=True to prevent potential injection via the command arguments.
    full_cmd = ["sudo", "-S"] + command_list
    
    process = subprocess.Popen(
        full_cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        universal_newlines=True
    )
    
    # Send the password followed by a newline to satisfy sudo -S
    process.stdin.write(f"{password}\n")
    process.stdin.flush()
    
    # Capture and log output line by line as it arrives
    for line in process.stdout:
        # Strip potential password prompts or whitespace
        clean_line = line.strip()
        if clean_line:
            logger_func(clean_line)
    
    process.wait()
    return process

def install_docker_ubuntu(password, logger=print):
    """
    Install Docker on Ubuntu/Debian using the official convenience script.
    
    Args:
        password (str): Sudo password for installation.
        logger (callable): Logging function.
        
    Returns:
        tuple (bool, str): (Success status, Message).
    """
    logger("[INFO] Initiating Docker installation process...")
    
    script_path = Path("get-docker.sh")
    
    # 1. Download the installation script using curl
    logger("[INFO] Fetching Docker installation script...")
    try:
        subprocess.run(
            ["curl", "-fsSL", DOCKER_INSTALL_URL, "-o", str(script_path)],
            check=True, capture_output=True
        )
    except subprocess.CalledProcessError as e:
        return False, f"Failed to download Docker script: {e.stderr.decode()}"
        
    # 2. Execute the script with sudo
    logger("[INFO] Executing Docker installation (this might take a few minutes)...")
    try:
        proc = run_with_sudo(["sh", str(script_path)], password, logger_func=logger)
        if proc.returncode != 0:
            return False, "Docker installation command failed. Please check logs for details."
    finally:
        # Always cleanup the script file
        if script_path.exists():
            script_path.unlink()
            
    return True, "Docker has been installed successfully."

def add_user_to_docker_group(password, logger=print):
    """
    Grant the current user permission to run Docker commands without sudo.
    
    Args:
        password (str): Sudo password.
        logger (callable): Logging function.
    """
    logger("[INFO] Configuring user permissions for Docker...")
    
    # Safely identify the current user
    user = os.getenv("USER") or subprocess.run(["whoami"], capture_output=True, text=True).stdout.strip()
    
    proc = run_with_sudo(["usermod", "-aG", "docker", user], password, logger_func=logger)
    
    if proc.returncode != 0:
        return False, "Failed to update user group permissions."
        
    return True, "User added to Docker group. IMPORTANT: You must log out and back in for this to take effect."

def create_desktop_shortcut(logger=print):
    """
    Generate a Linux .desktop entry to easily launch the DaemonZero Manager.
    """
    logger("[INFO] Generating desktop shortcut...")
    
    home = Path.home()
    shortcut_path = home / ".local" / "share" / "applications" / "daemon-zero-manager.desktop"
    
    import sys
    # Resolve the path to the current executable (manager)
    app_path = os.path.abspath(sys.argv[0])
    
    desktop_entry_content = f"""[Desktop Entry]
Name=DaemonZero Manager
Comment=Orchestration and Management for DaemonZero Agents
Exec={app_path}
Icon=utilities-terminal
Terminal=false
Type=Application
Categories=Development;
"""
    
    try:
        shortcut_path.parent.mkdir(parents=True, exist_ok=True)
        shortcut_path.write_text(desktop_entry_content)
        shortcut_path.chmod(0o755)
        logger(f"[SUCCESS] Desktop entry created successfully at {shortcut_path}")
        return True, "Desktop shortcut created successfully."
    except Exception as e:
        logger(f"[ERROR] An error occurred while creating the shortcut: {e}")
        return False, f"Error creating shortcut: {str(e)}"

def setup_base_dirs(base_dir, logger=print):
    """
    Create the foundational directory structure for DaemonZero data persistence.
    
    Args:
        base_dir (str/Path): The root directory for data.
        logger (callable): Logging function.
    """
    logger(f"[INFO] Establishing directory hierarchy at {base_dir}...")
    
    required_dirs = ["config", "agents", "memory", "knowledge"]
    base_path = Path(base_dir)
    
    try:
        for d in required_dirs:
            dir_path = base_path / d
            dir_path.mkdir(parents=True, exist_ok=True)
            logger(f"[OK] Directory verified: {d}")
        return True, "Base directory structure is ready."
    except Exception as e:
        logger(f"[ERROR] Found an issue while setting up directories: {e}")
        return False, f"Directory setup failed: {str(e)}"
