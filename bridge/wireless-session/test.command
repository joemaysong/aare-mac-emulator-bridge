#!/bin/zsh
set -euo pipefail
SESSION="${0:A:h}"
mkdir -p "$SESSION/build"
xcrun swiftc "$SESSION/native/WifiLease.swift" "$SESSION/tests/wifi/main.swift" \
  -o "$SESSION/build/wifi-lease-tests"
"$SESSION/build/wifi-lease-tests"
xcrun swiftc "$SESSION/native/WifiLease.swift" "$SESSION/native/CoreWifiRadio.swift" \
  "$SESSION/native/NativeControl.swift" "$SESSION/tests/native-control/main.swift" \
  -framework CoreWLAN -o "$SESSION/build/native-control-tests"
python3 -m unittest discover -s "$SESSION/tests" -v
