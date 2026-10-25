#!/bin/bash
# Double-click on a Mac to run the scan and open the page in your browser.
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  echo "First run: setting up Python packages (takes a minute)..."
  python3 -m venv .venv && ./.venv/bin/pip install -q -r requirements.txt
fi
./.venv/bin/python -m scanner.run --out site "$@" && open site/index.html
