#!/bin/bash
# macOS/Linux counterpart to "Run SLR Tools.bat". Double-click it in Finder
# (a .command opens in Terminal) or run: bash "Run SLR Tools.command"
cd "$(dirname "$0")" || exit 1
printf '\033]0;SLR Tools (local runner)\007'
echo
echo "   SLR Tools  (local runner)"
echo

pause_and_exit() {
  echo
  read -n 1 -s -r -p "   Press any key to close this window..."
  echo
  exit "$1"
}

# Opening this file from inside a zip extracts it alone to a temp folder,
# leaving none of the app next to it. Catch that before anything else.
if [ ! -f "requirements.txt" ] || [ ! -f "pyrpa/UI/rpa_tools.py" ]; then
  echo "   This file is not sitting with the rest of the app."
  echo
  echo "   If you opened it from inside the .zip, macOS copied just this one"
  echo "   file to a temporary folder. Close this window, double-click the .zip"
  echo "   in Finder to unpack it, and run this file from the unpacked folder."
  echo
  echo "   Current folder: $(pwd)"
  pause_and_exit 1
fi

# This app needs Python 3.12 or newer: the pinned numpy/pandas versions refuse
# to install on anything older. macOS ships an old python3, so try the
# version-specific names first and fall back to a version check on python3.
PYCMD=""
for candidate in python3.13 python3.14 python3.12; do
  if command -v "$candidate" >/dev/null 2>&1; then
    PYCMD="$candidate"
    break
  fi
done

if [ -z "$PYCMD" ] && command -v python3 >/dev/null 2>&1; then
  # /usr/bin/python3 is a stub that pops the Xcode Command Line Tools installer
  # when the tools aren't present. Only probe it once we know they are.
  probe=1
  if [ "$(command -v python3)" = "/usr/bin/python3" ] && ! xcode-select -p >/dev/null 2>&1; then
    probe=0
  fi
  if [ "$probe" = "1" ] && python3 -c "import sys; sys.exit(0 if sys.version_info >= (3,12) else 1)" >/dev/null 2>&1; then
    PYCMD="python3"
  fi
fi

if [ -z "$PYCMD" ]; then
  echo "   This app needs Python 3.12 or newer, and none was found."
  echo
  echo "   Detected on this machine:"
  for candidate in python3 python3.12 python3.13 python3.14; do
    if command -v "$candidate" >/dev/null 2>&1; then
      echo "     $candidate -> $(command -v "$candidate")"
    fi
  done
  echo
  echo "   Install Python 3.13 from https://www.python.org/downloads/ (the macOS"
  echo "   64-bit universal2 installer), then run this again."
  pause_and_exit 1
fi

# A .venv left over from an older Python cannot run this app either.
if [ -x ".venv/bin/python" ]; then
  if ! ".venv/bin/python" -c "import sys; sys.exit(0 if sys.version_info >= (3,12) else 1)" >/dev/null 2>&1; then
    echo "   The existing .venv folder was built with a Python older than 3.12,"
    echo "   so the dependencies cannot install into it."
    echo
    echo "   Delete the .venv folder next to this file, then run this again."
    pause_and_exit 1
  fi
fi

echo "   Using $PYCMD ($("$PYCMD" -c 'import sys; print(sys.version.split()[0])'))"
echo

if [ ! -x ".venv/bin/python" ]; then
  echo "   First run: setting up a private Python environment in .venv"
  echo "   This happens once and takes a few minutes. Later runs start straight up."
  echo
  if ! "$PYCMD" -m venv .venv; then
    echo "   Could not create the environment. Check that Python installed correctly."
    pause_and_exit 1
  fi
  ".venv/bin/python" -m pip install --upgrade pip >/dev/null 2>&1
  echo "   Installing dependencies from requirements.txt..."
  echo
  if ! ".venv/bin/python" -m pip install -r requirements.txt; then
    echo
    echo "   Dependency install failed. The first run needs an internet connection."
    echo "   Delete the .venv folder and try again."
    pause_and_exit 1
  fi
  echo
fi

# Streamlit asks for an email on first run and blocks until it gets one.
# Writing its credentials file up front skips that prompt entirely.
if [ ! -f "$HOME/.streamlit/credentials.toml" ]; then
  mkdir -p "$HOME/.streamlit"
  printf '[general]\nemail = ""\n' > "$HOME/.streamlit/credentials.toml"
fi

echo "   Starting the app. Your browser opens at http://localhost:8501"
echo "   If it does not, paste that address into your browser yourself."
echo
echo "   Leave this window open while you work."
echo "   Press Ctrl+C here to stop the app."
echo

".venv/bin/python" -m streamlit run "pyrpa/UI/rpa_tools.py"

echo
echo "   The app has stopped."
pause_and_exit 0
