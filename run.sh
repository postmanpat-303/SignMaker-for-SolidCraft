#!/usr/bin/env bash
# Launch Sign Maker from a terminal (Linux, and macOS if you prefer the shell).
cd "$(dirname "$0")" || exit 1

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 was not found. Install Python 3.10 or newer." >&2
  exit 1
fi

if ! python3 -c "import tkinter" >/dev/null 2>&1; then
  echo "Tkinter is missing. On Debian, Ubuntu or Mint: sudo apt install python3-tk" >&2
  exit 1
fi

if ! python3 -c "import PIL, fontTools" >/dev/null 2>&1; then
  echo "Install the Python libraries first:" >&2
  echo "    python3 -m pip install -r requirements.txt" >&2
  exit 1
fi

exec python3 SignMaker.pyw "$@"
