#!/bin/bash
# macOS Finder entrypoint. All paths are quoted for folders with spaces.
set -eu
cd "$(dirname "$0")/.."
if ! command -v python3 >/dev/null 2>&1; then
  echo 'Cần cài Python 3.12 trở lên từ https://www.python.org/downloads/macos/'
  read -r -p 'Nhấn Enter để đóng...' unused_input
  exit 1
fi
python3 v2/start_local_worker.py || {
  read -r -p 'Nhấn Enter để đóng...' unused_input
  exit 1
}
