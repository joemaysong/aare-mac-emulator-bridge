"""Stage only the native adapter's identity in the dedicated emulator; no vehicle ADB."""
import json
import re
import subprocess
import hashlib
import shlex
import time
from pathlib import Path

FILE = 'files/ev6-relay-identity'
PACKAGE = 'net.prototux.aare'


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



def app_shell(adb, serial, script, data=None):
    """Only the dedicated emulator: root adbd or a genuinely debuggable app."""
    uid = shell(adb, serial, 'id -u').decode().strip()
    if uid == '0':
        private = '/data/user/0/' + PACKAGE
        command = 'sh -c ' + shlex.quote('cd ' + private + ' && ' + script)
    else:
        command = f'run-as {PACKAGE} sh -c ' + shlex.quote(script)
    return shell(adb, serial, command, data)


def check_private_access(adb, serial):
    app_shell(adb, serial, 'test -d files && test -w files')


def wait_native_identity(path, nonce, timeout=25.0):
    # Real Bluetooth power-on inventory took 9.5s; allow a bounded 25s startup.
    # This is a local startup limit, not an AA protocol timeout.
    # IPC sockets become ready before the main-thread Bluetooth inventory runs.
    # Wait for the matching doctor receipt, never infer an address from pairing cache.
    deadline = time.monotonic() + timeout
    while True:
        try:
            receipt = json.loads(path.read_text())
        except FileNotFoundError:
            receipt = None
        if receipt is not None:
            if receipt.get('session_nonce') != nonce:
                raise ValueError('native identity session mismatch')
            if receipt.get('report_complete'):
                raise RuntimeError('native session ended before identity staging')
            if any(e.get('event') == 'doctor' for e in receipt.get('events', [])):
                native_address(receipt, nonce)
                return receipt
        if time.monotonic() >= deadline:
            raise TimeoutError('native identity receipt deadline')
        time.sleep(min(0.05, max(0, deadline - time.monotonic())))

def stage(adb, serial, native_report, nonce, seconds):
    if not re.fullmatch(r'[0-9a-f]{32}', nonce) or not 10 <= seconds <= 600:
        raise ValueError('identity session parameters')
    receipt = wait_native_identity(native_report, nonce)
    address = native_address(receipt, nonce)
    uptime = shell(adb, serial, 'cat /proc/uptime').decode().split()[0]
    expires = int(float(uptime) * 1000) + seconds * 1000
    data = f'EV6RELAY1|{nonce}|{address}|{expires}|END\n'.encode('ascii')
    # Noclobber is atomic; never truncate a previous session's file.
    script = f'umask 077; set -C; cat > {FILE}'
    app_shell(adb, serial, script, data)
    # Root adbd must restore the app UID and SELinux label before consumption.
    if shell(adb, serial, 'id -u').decode().strip() == '0':
        app_shell(adb, serial, f'chown $(stat -c %u files):$(stat -c %g files) {FILE} && restorecon {FILE}')
    if app_shell(adb, serial, f'cat {FILE}').replace(b'\r\n', b'\n') != data:
        raise RuntimeError('emulator identity readback mismatch')
    return nonce


def cleanup(adb, serial, nonce):
    if not nonce or not re.fullmatch(r'[0-9a-f]{32}', nonce):
        return
    # The app normally consumes it once. Never remove a successor's file.
    script = f'if [ -e {FILE} ]; then IFS="|" read schema owner rest < {FILE}; [ "$schema" = EV6RELAY1 ] && [ "$owner" = {nonce} ] && rm {FILE}; fi'
    app_shell(adb, serial, script)



def verify_installed(adb, serial):
    """Reject an unpatched emulator before opening Bluetooth or forwarding."""
    build = Path(__file__).resolve().parents[1] / 'emulator-lab/audio72'
    proof = json.loads((build / 'verification.json').read_text())
    expected = proof['apk_sha256']
    if hashlib.sha256((build / 'aare-audio.apk').read_bytes()).hexdigest() != expected:
        raise RuntimeError('relay APK artifact drift')
    paths = shell(adb, serial, f'pm path {PACKAGE}').decode().strip().splitlines()
    if len(paths) != 1 or not re.fullmatch(r'package:/data/app/[A-Za-z0-9_~+/=.-]+/base\.apk', paths[0]):
        raise RuntimeError('unexpected relay APK install path')
    actual = shell(adb, serial, 'sha256sum ' + paths[0][8:]).decode().split()[0]
    if actual != expected:
        raise RuntimeError('identity-enabled AARE APK must be installed before wireless testing')
    return expected
