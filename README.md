# 🚀 DaemonZero Manager

DaemonZero is a professional, secure, and robust management suite for deploying and orchestrating AgentZero instances via Docker.

## 🌟 Philosophy

DaemonZero follows a **"One-Script"** philosophy. You don't need to manually clone the entire repository and manage dependencies. Simply download the installation script for your OS, and the Manager will handle the rest—from Docker setup to container orchestration.

## 🛠️ Quick Start

### 🐧 Linux (Ubuntu/Debian)
Open your terminal and run:
```bash
wget -qO- https://raw.githubusercontent.com/Josepavese/daemon-zero/main/install.sh | bash
```

### 🪟 Windows
1. Download `install.bat` from our [latest releases](https://github.com/Josepavese/daemon-zero/releases).
2. Right-click and **Run as Administrator**.
3. Follow the CLI prompts to initialize the environment.

## 🛡️ Security & Robustness
The backend has been hardened with:
- **Shell Injection Prevention**: All system commands use secure list-based arguments.
- **Unified Logging**: Structured ISO-timestamped logs for all system operations.
- **Path Sanitization**: Built-in protection against directory traversal attacks.
- **Non-Blocking Architecture**: Operations run in background threads to keep the UI responsive.

## 📦 Requirements
- **Docker**: Automatically installed/configured by the Manager.
- **Python 3.10+**: Baseline requirement for the host manager.

---
Built with ❤️ by [Jose Pavese](https://github.com/Josepavese)
