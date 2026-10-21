#!/bin/bash
# Double-click launcher for macOS. Finder starts this in your home folder,
# so move to the folder that contains SignMaker.pyw before running it.
cd "$(dirname "$0")" || exit 1
export PATH="/opt/homebrew/bin:/usr/local/bin:${PATH}"

pause() { read -r -p "Press Return to close."; }

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 was not found."
  echo "Install it from https://www.python.org/downloads/macos/"
  echo "The python.org installer includes Tk, which Sign Maker needs."
  pause
  exit 1
fi

if ! python3 -c "import tkinter" >/dev/null 2>&1; then
  echo "This Python has no Tkinter."
  echo "Install Python from python.org rather than the Command Line Tools stub."
  pause
  exit 1
fi

if ! python3 -c "import PIL, fontTools" >/dev/null 2>&1; then
  echo "Install the Python libraries first, in Terminal:"
  echo "    cd \"$(pwd)\""
  echo "    python3 -m pip install -r requirements.txt"
  pause
  exit 1
fi

exec python3 SignMaker.pyw "$@"
