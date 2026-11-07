#!/bin/zsh
set -euo pipefail
SESSION="${0:A:h}"
if (( $# == 0 )); then
  python3 "$SESSION/run_session.py" --check
  print "To start: start-standby.command --device <paired address> [--cached-service-diagnostic]"
  exit 0
fi
python3 "$SESSION/standby_session.py" "$@"
