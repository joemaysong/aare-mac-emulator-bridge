#!/bin/zsh
set -euo pipefail
SESSION="${0:A:h}"
python3 "$SESSION/run_session.py" --recover
