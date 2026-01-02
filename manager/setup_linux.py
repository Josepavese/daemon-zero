import subprocess
import os
from pathlib import Path

def run_with_sudo(command, password, logger=print):
    """Run a command with sudo -S and stream output to logger."""
    full_command = f"echo '{password}' | sudo -S {command}"
    process = subprocess.Popen(
        full_command, 
        shell=True, 
        stdout=subprocess.PIPE, 
        stderr=subprocess.STDOUT, 
        text=True,
        bufsize=1,
        universal_newlines=True
    )
    
    # Capture output line by line
    for line in process.stdout:
        logger(line.strip())
    
    process.wait()
    return process

def install_docker_ubuntu(password, logger=print):
    """Install Docker on Ubuntu/Debian using the official convenience script."""
    logger("[INFO] Starting Docker installation process...")
    
    # 1. Download script
    logger("[INFO] Downloading Docker installation script...")
    res = subprocess.run(["curl", "-fsSL", "https://get.docker.com", "-o", "get-docker.sh"], capture_output=True)
    if res.returncode != 0:
        return False, "Failed to download Docker installation script."
        
    # 2. Run script with sudo
    logger("[INFO] Running Docker installation script (this may take a few minutes)...")
    proc = run_with_sudo("sh get-docker.sh", password, logger=logger)
    subprocess.run(["rm", "get-docker.sh"]) # cleanup
    
    if proc.returncode != 0:
        return False, "Docker installation failed. See logs above."
        
    return True, "Docker installed successfully."

def add_user_to_docker_group(password, logger=print):
    """Add current user to docker group."""
    logger("[INFO] Adding user to docker group...")
    user = os.getenv("USER") or subprocess.run(["whoami"], capture_output=True, text=True).stdout.strip()
    proc = run_with_sudo(f"usermod -aG docker {user}", password, logger=logger)
    if proc.returncode != 0:
        return False, "Failed to add user to docker group."
    return True, "User added to docker group. Note: A log out/in might be required."

def create_desktop_shortcut(logger=print):
    """Create a .desktop entry for DZ Manager on Linux."""
    logger("[INFO] Creating desktop shortcut...")
    home = Path.home()
    shortcut_path = home / ".local" / "share" / "applications" / "daemon-zero-manager.desktop"
    
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
        shortcut_path.chmod(0o755)
        logger(f"[SUCCESS] Shortcut created at {shortcut_path}")
        return True, f"Shortcut created at {shortcut_path}"
    except Exception as e:
        logger(f"[ERROR] Failed to create shortcut: {e}")
        return False, str(e)

def setup_base_dirs(base_dir, logger=print):
    """Create necessary directories for DZ."""
    logger(f"[INFO] Setting up base directories in {base_dir}...")
    dirs = ["config", "agents", "memory", "knowledge"]
    try:
        base_path = Path(base_dir)
        for d in dirs:
            dir_path = base_path / d
            dir_path.mkdir(parents=True, exist_ok=True)
            logger(f"[OK] Created: {d}")
        return True, "Directories created successfully."
    except Exception as e:
        logger(f"[ERROR] Directory creation failed: {e}")
        return False, str(e)
