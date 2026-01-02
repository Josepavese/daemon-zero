import subprocess
import os
from pathlib import Path

def run_with_sudo(command, password):
    """Run a command with sudo -S to allow providing password via stdin."""
    full_command = f"echo '{password}' | sudo -S {command}"
    return subprocess.run(full_command, shell=True, capture_output=True, text=True)

def install_docker_ubuntu(password):
    """Install Docker on Ubuntu/Debian using the official convenience script."""
    print("[INFO] Installing Docker on Ubuntu...")
    
    # 1. Download script
    res = subprocess.run(["curl", "-fsSL", "https://get.docker.com", "-o", "get-docker.sh"], capture_output=True)
    if res.returncode != 0:
        return False, "Failed to download Docker installation script."
        
    # 2. Run script with sudo
    res = run_with_sudo("sh get-docker.sh", password)
    subprocess.run(["rm", "get-docker.sh"]) # cleanup
    
    if res.returncode != 0:
        return False, res.stderr or "Docker installation failed."
        
    return True, "Docker installed successfully."

def add_user_to_docker_group(password):
    """Add current user to docker group."""
    user = os.getenv("USER") or subprocess.run(["whoami"], capture_output=True, text=True).stdout.strip()
    res = run_with_sudo(f"usermod -aG docker {user}", password)
    if res.returncode != 0:
        return False, res.stderr or "Failed to add user to docker group."
    return True, "User added to docker group. Note: A log out/in might be required."

def create_desktop_shortcut():
    """Create a .desktop entry for DZ Manager on Linux."""
    home = Path.home()
    shortcut_path = home / ".local" / "share" / "applications" / "daemon-zero-manager.desktop"
    
    # We need the absolute path to the current executable or script
    # If running as script, use sys.executable + script_path
    # If compiled with pyinstaller, use sys.executable
    import sys
    app_path = os.path.abspath(sys.argv[0])
    
    content = f"""[Desktop Entry]
Name=DaemonZero Manager
Comment=Manage and Launch DaemonZero Agents
Exec={app_path}
Icon=utilities-terminal
Terminal=false
Type=Application
Categories=Development;
"""
    
    try:
        shortcut_path.parent.mkdir(parents=True, exist_ok=True)
        shortcut_path.write_text(content)
        # Ensure executable permission
        shortcut_path.chmod(0o755)
        return True, f"Shortcut created at {shortcut_path}"
    except Exception as e:
        return False, str(e)

def setup_base_dirs(base_dir):
    """Create necessary directories for DZ."""
    dirs = ["config", "agents", "memory", "knowledge"]
    try:
        base_path = Path(base_dir)
        for d in dirs:
            (base_path / d).mkdir(parents=True, exist_ok=True)
        return True, "Directories created successfully."
    except Exception as e:
        return False, str(e)
