#!/bin/zsh
set -euo pipefail
SESSION="${0:A:h}"
ROOT="${SESSION:h}"
JAVA_HOME="${JAVA_HOME:?Set JAVA_HOME to a full JDK 17 or 21}"
APP="$SESSION/build/AARE Wireless Session.app"
mkdir -p "$APP/Contents/MacOS" "$SESSION/build/classes"
"$JAVA_HOME/bin/javac" -cp "$(cat "$ROOT/core/aap/build/mac-classpath.txt")" \
  -d "$SESSION/build/classes" "$SESSION/java/EmulatorWirelessSession.java"
xcrun swiftc "$SESSION/native/WifiLease.swift" "$SESSION/native/CoreWifiRadio.swift" \
  "$ROOT/native-host/RfcommBridge.swift" "$SESSION/native/NativeControl.swift" "$SESSION/native/main.swift" \
  -o "$APP/Contents/MacOS/aare-wireless-session" \
  -framework AppKit -framework IOBluetooth -framework CoreWLAN -framework CoreLocation
/usr/bin/python3 - "$APP" <<'PY'
import plistlib,sys
from pathlib import Path
(Path(sys.argv[1])/'Contents/Info.plist').write_bytes(plistlib.dumps({
 'CFBundleIdentifier':'org.ev6.aare.mac.wireless-session', 'CFBundleName':'AARE Wireless Session',
 'CFBundleExecutable':'aare-wireless-session', 'CFBundlePackageType':'APPL','CFBundleVersion':'1',
 'NSBluetoothAlwaysUsageDescription':'Connect the selected paired car for Android Auto projection.',
 'NSLocalNetworkUsageDescription':'Relay the emulator projection to the selected car.',
 'NSLocationWhenInUseUsageDescription':'Verify the selected car Wi-Fi SSID and BSSID before projection.',
 'NSLocationUsageDescription':'Verify and restore the Wi-Fi association used by this session.'}))
PY
codesign --force --sign - "$APP"
codesign --verify --deep --strict "$APP"
print "Built isolated wireless session; no vehicle, emulator or radio actions."
