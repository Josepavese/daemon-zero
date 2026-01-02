# DaemonZero Manager (DZ-Manager)

The DZ Manager is the central orchestrator and installer for the DaemonZero ecosystem. It is designed to be the single entry point for users, handling everything from initial system setup to advanced instance management.

## 🛠️ Unified Installer Architecture

The Manager uses a Python-based setup engine (`setup_linux.py`, `platform_utils.py`) to provide a seamless installation experience:

1.  **Platform Detection**: Automatically identifies the OS distribution and architecture.
2.  **Docker Orchestration**: Installs and configures Docker, and manages user permissions (group management).
3.  **Dependency Management**: Ensures all OS-level and Python dependencies are met.
4.  **Desktop Integration**: Can create system-level shortcuts (`.desktop` files) for easy launching from the OS application menu.

## 🚀 Usage

### Recommended: Using Root Wrappers
For the best experience, use the launchers in the root directory:
- **Linux**: `./run.sh`
- **Windows**: `run.bat`

### Manual/Development Mode
If you prefer running from the `manager` directory directly:
```bash
pip install -r requirements.txt
python dz-launcher.py
```

### Production (Executable)
You can build a standalone executable using `build.sh`:
```bash
./build.sh
```
The resulting binary will be in `dist/daemon-zero-manager`.

## 📁 Structure

- `dz-launcher.py`: The main Flask-based GUI and API server.
- `dz_manage.py`: Core CLI logic for managing Docker-based DZ instances.
- `setup_linux.py`: Platform-specific installation routines.
- `platform_utils.py`: OS detection and utility functions.
- `templates/`: HTML5/JS UI for the manager.

## 🛡️ Security

- **Secrets**: The manager provides a UI to configure API keys, which are injected into instances via `.env` files.
- **Isolation**: Each DZ instance runs in its own Docker container with segregated workspace and memory.
- **Password Handling**: Sudo passwords requested during setup are used only for the current operation and are never stored on disk.
