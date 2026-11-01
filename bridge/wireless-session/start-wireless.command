#!/bin/zsh
set -euo pipefail
SESSION="${0:A:h}"
if (( $# == 0 )); then
  python3 "$SESSION/run_session.py" --check
else
  python3 "$SESSION/run_session.py" "$@"
fi
