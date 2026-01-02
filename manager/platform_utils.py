import platform
import sys
import subprocess
import os

def get_platform_info():
    """Detect platform details."""
    info = {
        "os": sys.platform,
        "release": platform.release(),
        "machine": platform.machine(),
        "distro": "",
        "distro_version": ""
    }
    
    if info["os"] == "linux":
        try:
            # Using /etc/os-release is the most reliable way on modern Linux
            with open("/etc/os-release") as f:
                for line in f:
                    if line.startswith("ID="):
                        info["distro"] = line.split("=")[1].strip().strip('"')
                    if line.startswith("VERSION_ID="):
                        info["distro_version"] = line.split("=")[1].strip().strip('"')
        except:
            pass
            
    return info

def is_ubuntu():
    info = get_platform_info()
    return info["distro"] == "ubuntu"

def is_linux():
    return sys.platform.startswith("linux")

def is_windows():
    return sys.platform == "win32"
