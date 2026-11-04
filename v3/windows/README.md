# LMT Studio V3 for Windows

Windows 10/11 x64. This is a local editor opened in your browser. No separate Python, Homebrew, Git or Terminal setup is required for the recipient.

1. Run LMT-Studio-V3-Setup-x64.exe and install for your Windows account.
2. Open LMT Studio V3 from Start or the desktop.
3. Choose the default output folder, optionally enter your own Pixabay key, and click “Thiết lập và mở V3”.
4. The setup downloads FFmpeg from gyan.dev and verifies its published SHA256 plus subtitle support. First use of speech recognition/background removal downloads the relevant models.
5. V3 opens at http://127.0.0.1:8503. Upload your own media and start rendering. Closing the browser/setup window keeps background rendering alive.

Optional “Start V3 after Windows sign-in” restores interrupted work after login once first setup has completed. The PC must be powered on and awake. Interrupted MP4 encoding starts again from saved inputs. Cancelled, failed and completed tasks are not automatically retried.

Your projects, key, models and logs are under %LOCALAPPDATA%\LMTStudioPro\V3. Uninstalling the application preserves that data. Never share this folder or your personal keys. Setup requires Internet and sufficient disk space for runtime, models, source videos and outputs. This installer does not contain the developer's projects or credentials. Windows ARM and 32-bit Windows are not supported by this build.

The installer is not code-signed yet. Verify the source and release checksum before installing; do not disable Windows security protections. A signed Windows release is a separate distribution step. First setup can fail on managed corporate PCs, unavailable download hosts, antivirus restrictions or lack of disk space; the setup window provides the error and can be retried.

Build: run `python v3/windows/build.py` on Windows with Python 3.12 x64, PyInstaller and Inno Setup 6. The GitHub Actions workflow builds and uploads the installer plus SHA256. Windows-specific tests validate locking, folder paths, FFmpeg progress and recovery using that runtime; manual first-install testing on a clean Windows PC is still required before general release.

Third-party sources: https://www.python.org/ · https://pypi.org/ · https://www.gyan.dev/ffmpeg/builds/
FFmpeg is downloaded directly on the recipient's PC, not redistributed inside this installer. Runtime libraries retain their license metadata.
