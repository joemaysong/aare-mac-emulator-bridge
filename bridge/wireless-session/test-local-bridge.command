#!/bin/zsh
set -euo pipefail
ROOT="${0:A:h:h}"
LAB="$ROOT/emulator-lab"
ADB="${ADB:-$HOME/Library/Android/sdk/platform-tools/adb}"
if ! "$ADB" -s emulator-5580 get-state >/dev/null 2>&1; then
 /usr/bin/open "$LAB/apps/AARE Android Emulator.app"
 for attempt in {1..60}; do
  "$ADB" -s emulator-5580 get-state >/dev/null 2>&1 && break
  sleep 1
 done
fi
"$LAB/start.command" --prepare-only
# Only this lab's two Desktop apps; never terminate other Java or emulator processes.
python3 - "$LAB" <<'PYEND'
import os,signal,subprocess,sys
paths=[sys.argv[1]+"/apps/"+name+"/Contents/MacOS/AARE Desktop" for name in ["AARE Desktop.app","AARE Bridge Desktop.app"]]
for row in subprocess.check_output(["ps","-axo","pid=,command="],text=True).splitlines():
 f=row.strip().split(None,1)
 if len(f)==2 and any(f[1]==p or f[1].startswith(p+" ") for p in paths):os.kill(int(f[0]),signal.SIGTERM)
PYEND
RUN="$ROOT/wireless-session/evidence/local-$(date -u +%Y%m%dT%H%M%SZ)-$$"
python3 -u "$ROOT/wireless-session/stream_bridge.py" --seconds 600 --report "$RUN.json" > "$RUN.log" 2>&1 &
relay_pid=$!
trap 'kill -TERM "$relay_pid" 2>/dev/null || true' EXIT INT TERM
ready=0
for attempt in {1..50}; do
 if /usr/bin/grep -q LOCAL_BRIDGE_LISTENING "$RUN.log"; then ready=1; break; fi
 kill -0 "$relay_pid" 2>/dev/null || break
 sleep 0.1
done
[[ "$ready" == 1 ]] || { cat "$RUN.log"; exit 1; }
/usr/bin/open "$LAB/apps/AARE Bridge Desktop.app"
print "Mac-only test: emulator-5580 -> local bridge 55278 -> Desktop"
print "Closes automatically after 10 minutes, or when you close AARE Bridge Desktop."
wait "$relay_pid"
cat "$RUN.json"
