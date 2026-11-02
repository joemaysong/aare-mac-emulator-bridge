"""Stage only the native adapter's identity in the dedicated emulator; no vehicle ADB."""
import json
import re
import subprocess
import hashlib
from pathlib import Path

FILE = 'files/ev6-relay-identity'
PACKAGE = 'net.prototux.aare'
BUILD = Path(__file__).resolve().parents[2] / 'build/relay-identity'


def native_address(receipt, nonce):
    if receipt.get('session_nonce') != nonce:
        raise ValueError('native identity session mismatch')
    doctors = [e for e in receipt.get('events', []) if e.get('event') == 'doctor']
    if len(doctors) != 1:
        raise ValueError('native identity evidence missing')
    event = doctors[0]
    # Native event fields are flattened in the session report.
    address = str(event.get('local_bluetooth_address', '')).upper().replace('-', ':')
    if event.get('bluetooth_power_raw') != 1 or not re.fullmatch(r'(?:[0-9A-F]{2}:){5}[0-9A-F]{2}', address):
        raise ValueError('native Bluetooth identity unavailable')
    if int(address[:2], 16) & 1 or address in ('00:00:00:00:00:00', '02:00:00:00:00:00'):
        raise ValueError('invalid native Bluetooth identity')
    return address


def shell(adb, serial, command, data=None):
    if serial != 'emulator-5580':
        raise ValueError('dedicated emulator required')
    p = subprocess.run([str(adb), '-s', serial, 'shell', command], input=data,
                       capture_output=True, timeout=10)
    if p.returncode:
        raise RuntimeError('emulator identity operation failed')
    return p.stdout


def stage(adb, serial, native_report, nonce, seconds):
    if not re.fullmatch(r'[0-9a-f]{32}', nonce) or not 10 <= seconds <= 600:
        raise ValueError('identity session parameters')
    receipt = json.loads(native_report.read_text())
    address = native_address(receipt, nonce)
    uptime = shell(adb, serial, 'cat /proc/uptime').decode().split()[0]
    expires = int(float(uptime) * 1000) + seconds * 1000
    data = f'EV6RELAY1|{nonce}|{address}|{expires}|END\n'.encode('ascii')
    command = f"run-as {PACKAGE} sh -c 'umask 077; test ! -e {FILE} && cat > {FILE}'"
    shell(adb, serial, command, data)
    if shell(adb, serial, f'run-as {PACKAGE} cat {FILE}').replace(b'\r\n', b'\n') != data:
        raise RuntimeError('emulator identity readback mismatch')
    return nonce


def cleanup(adb, serial, nonce):
    if not nonce or not re.fullmatch(r'[0-9a-f]{32}', nonce):
        return
    # The app normally consumes it once. Never remove a successor's file.
    command = f"run-as {PACKAGE} sh -c 'if [ -e {FILE} ]; then IFS=\"|\" read schema owner rest < {FILE}; [ \"$schema\" = EV6RELAY1 ] && [ \"$owner\" = {nonce} ] && rm {FILE}; fi'"
    shell(adb, serial, command)


def verify_installed(adb, serial):
    """Reject an unpatched emulator before opening Bluetooth or forwarding."""
    build = BUILD
    proof = json.loads((build / 'verification.json').read_text())
    expected = proof['apk_sha256']
    if hashlib.sha256((build / 'aare-relay.apk').read_bytes()).hexdigest() != expected:
        raise RuntimeError('relay APK artifact drift')
    paths = shell(adb, serial, f'pm path {PACKAGE}').decode().strip().splitlines()
    if len(paths) != 1 or not re.fullmatch(r'package:/data/app/[A-Za-z0-9_~+/=.-]+/base\.apk', paths[0]):
        raise RuntimeError('unexpected relay APK install path')
    actual = shell(adb, serial, 'sha256sum ' + paths[0][8:]).decode().split()[0]
    if actual != expected:
        raise RuntimeError('identity-enabled AARE APK must be installed before wireless testing')
    return expected
