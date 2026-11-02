#!/usr/bin/env python3
"""Explicit opt-in live coordinator. --check never connects to a car or changes radios."""
import argparse
import datetime
import fcntl
import json
import os
from pathlib import Path
import re
import secrets
import selectors
import signal
import socket
import stat
import subprocess
import tempfile
import threading
import time

from session_control import SessionControl
import relay_identity

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
ADB = Path(os.environ.get('ANDROID_SDK_ROOT', str(Path.home() / 'Library/Android/sdk'))) / 'platform-tools/adb'
SERIAL = 'emulator-5580'
APP = HERE / 'build/AARE Wireless Session.app'
JOURNAL_NAME = 'wifi-recovery.json'


def private_directory(path):
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700 or path.resolve() != path:
        raise RuntimeError('private directory ownership/mode required')


def write_report(path, value):
    temporary = path.with_suffix('.new')
    with open(temporary, 'w', encoding='utf-8') as f:
        json.dump(value, f, indent=2); f.write('\n'); f.flush(); os.fsync(f.fileno())
    temporary.replace(path)


def preflight():
    java = Path(os.environ.get('JAVA_HOME', str(ROOT / 'runtime/jdk'))) / 'bin/java'
    cp = ROOT / 'core/aap/build/mac-classpath.txt'
    required = [java, cp, APP / 'Contents/MacOS/aare-wireless-session',
                HERE / 'build/classes/org/ev6/aare/mac/EmulatorWirelessSession.class', ADB]
    missing = [str(p) for p in required if not p.is_file()]
    if cp.is_file():
        missing.extend(p for p in cp.read_text().strip().split(':') if not Path(p).exists())
    processes = subprocess.run(['/bin/ps', '-axo', 'command='], capture_output=True, text=True, timeout=5).stdout
    desktop_active = any(exe in processes for exe in ('/AARE Desktop.app/Contents/MacOS/AARE Desktop', '/AARE Bridge Desktop.app/Contents/MacOS/AARE Bridge Desktop', '/AARE Bridge Desktop.app/Contents/MacOS/AARE Desktop'))
    return {'missing': missing, 'desktop_receiver_running': desktop_active,
            'recovery_pending': (HERE / 'runtime' / JOURNAL_NAME).exists(),
            'vehicle_access': False, 'radio_changes': False, 'ready_for_explicit_connect': not missing and not desktop_active and not (HERE / 'runtime' / JOURNAL_NAME).exists()}


def emulator_forward():
    def adb(*args):
        return subprocess.check_output([str(ADB), '-s', SERIAL, *args], text=True, stderr=subprocess.DEVNULL, timeout=10).strip()
    if adb('emu', 'avd', 'name').splitlines()[0].strip() != 'AARE_Mac_API35':
        raise RuntimeError('dedicated emulator not running')
    if adb('shell', 'getprop', 'sys.boot_completed').strip() != '1':
        raise RuntimeError('emulator not booted')
    relay_identity.verify_installed(ADB, SERIAL)
    entries = [s.split() for s in adb('forward', '--list').splitlines() if s.strip()]
    existing = [e for e in entries if len(e) == 3 and e[1] == 'tcp:55277']
    if existing:
        if existing != [[SERIAL, 'tcp:55277', 'localabstract:aare_hu']]:
            raise RuntimeError('forward port already owned')
        return False
    adb('forward', '--no-rebind', 'tcp:55277', 'localabstract:aare_hu')
    return True


def remove_owned_forward():
    prefix = [str(ADB), '-s', SERIAL]
    result = subprocess.run(prefix + ['forward', '--list'], capture_output=True, text=True, timeout=5)
    if [SERIAL, 'tcp:55277', 'localabstract:aare_hu'] in [s.split() for s in result.stdout.splitlines()]:
        subprocess.run(prefix + ['forward', '--remove', 'tcp:55277'], capture_output=True, timeout=5)


def copy_stream(source, destination, stop):
    source.settimeout(0.2); destination.settimeout(2)
    try:
        while not stop.is_set():
            try:
                data = source.recv(4096)
            except socket.timeout:
                continue
            if not data:
                break
            destination.sendall(data)
    except OSError:
        pass
    finally:
        stop.set()


def shutdown(sock):
    try:
        sock.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass
    sock.close()


def run(args):
    runtime = HERE / 'runtime'; private_directory(runtime)
    lock_fd = os.open(runtime / 'coordinator.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return owned_run(args, runtime)
    finally:
        os.close(lock_fd)


def owned_run(args, runtime):
    journal = runtime / JOURNAL_NAME
    if args.recover != journal.exists():
        raise RuntimeError('use --recover for outstanding Wi-Fi journal; recovery requires a journal')
    if not args.recover:
        check = preflight()
        if check['missing'] or check['desktop_receiver_running']:
            raise RuntimeError('build first and close the lab desktop receiver before connecting')
    private_directory(HERE / 'runs')
    nonce = secrets.token_hex(16)
    out = HERE / 'runs' / (datetime.datetime.now().strftime('%Y%m%d-%H%M%S-') + nonce[:8])
    private_directory(out)
    report = {'session_nonce': nonce, 'mode': 'wifi-recovery' if args.recover else 'emulator-wireless-session',
              'vehicle_software_modified': False, 'projection_verified': False,
              'wifi_restored': False, 'reason': 'starting'}
    write_report(out / 'result.json', report)
    stop = threading.Event()
    for number in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(number, lambda *_: stop.set())
    deadline = time.monotonic() + args.seconds
    timer = threading.Timer(args.seconds, stop.set); timer.daemon = True; timer.start()
    peers, listeners, workers = {}, {}, []
    jvm = native = control = None
    forward_created = False
    identity_nonce = None
    # Short path avoids Darwin sockaddr_un's 104-byte path limit.
    private = Path(tempfile.mkdtemp(prefix='aare-live-', dir='/tmp')).resolve()
    native_report = out / 'native.json'
    try:
        names = ['native-control'] if args.recover else ['native-control', 'native-rx', 'native-tx', 'rx', 'tx', 'control']
        for name in names:
            listener = socket.socket(socket.AF_UNIX); listener.bind(str(private / (name + '.sock'))); listener.listen(1)
            listeners[name] = listener
        if not args.recover:
            forward_created = emulator_forward()  # Explicit emulator serial; never probes vehicle ADB.
        command = ['open', '-n', '-W', str(APP), '--args', '--output', str(native_report),
                   '--bridge-directory', str(private), '--journal', str(journal), '--nonce', nonce,
                   '--seconds', str(args.seconds + 45)]
        if args.recover:
            command += ['--recover-only']
        else:
            command += ['--device', args.device]
            if args.cached_service_diagnostic:
                command += ['--cached-service-diagnostic']
        native = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if not args.recover:
            identity = runtime / 'tool-identity'
            if not identity.exists():
                previous = ROOT / 'runtime/tool-device-id'
                saved_identity = previous.read_text().strip() if previous.is_file() and not previous.is_symlink() else ''
                if not re.fullmatch(r'aare-mac-[0-9a-f]{32}', saved_identity):
                    saved_identity = 'aare-mac-' + secrets.token_hex(16)
                fd = os.open(identity, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
                with os.fdopen(fd, 'w') as f:
                    f.write(saved_identity)
            info = identity.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600:
                raise RuntimeError('identity ownership')
            serial = identity.read_text().strip()
            if not re.fullmatch(r'aare-mac-[0-9a-f]{32}', serial):
                raise RuntimeError('identity schema')
            cp = str(HERE / 'build/classes') + ':' + (ROOT / 'core/aap/build/mac-classpath.txt').read_text().strip()
            with (out / 'wpp.log').open('w') as log:
                jvm = subprocess.Popen([str(Path(os.environ.get('JAVA_HOME', str(ROOT / 'runtime/jdk'))) / 'bin/java'),
                    '-Xmx128m', '-cp', cp, 'org.ev6.aare.mac.EmulatorWirelessSession', str(private), serial],
                    stdout=log, stderr=subprocess.STDOUT)
        with selectors.DefaultSelector() as selector:
            for name, listener in listeners.items():
                selector.register(listener, selectors.EVENT_READ, name)
            accept_deadline = min(deadline, time.monotonic() + 25)
            while len(peers) < len(listeners):
                if stop.is_set() or time.monotonic() >= accept_deadline:
                    raise TimeoutError('native IPC start deadline')
                for key, _ in selector.select(0.2):
                    peers[key.data], _ = key.fileobj.accept(); selector.unregister(key.fileobj)
        if not args.recover:
            identity_nonce = nonce  # Own cleanup even if staging readback fails.
            relay_identity.stage(ADB, SERIAL, native_report, nonce, args.seconds)
            report['relay_identity_staged'] = True
        if args.recover:
            report['reason'] = 'recovery_requested'
        else:
            for a, b in [('native-rx', 'rx'), ('tx', 'native-tx')]:
                worker = threading.Thread(target=copy_stream, args=(peers[a], peers[b], stop), daemon=True)
                worker.start(); workers.append(worker)
            control = SessionControl(peers['native-control'], stop=stop, deadline=deadline)
            control.serve(peers['control'])
            report['reason'] = 'session_ended'
    except InterruptedError:
        report['reason'] = 'session_ended' if control and control.stream_started else 'cancelled'
    except (OSError, EOFError, RuntimeError, ValueError) as error:
        # Never serialize exception text: it may contain WPP credentials.
        report.update(reason='stopped', error_type=type(error).__name__)
    except Exception as error:
        report.update(reason='failed', error_type=type(error).__name__)
    finally:
        stop.set(); timer.cancel()
        if jvm and jvm.poll() is None:
            jvm.terminate()
            try:
                jvm.wait(timeout=5)
            except subprocess.TimeoutExpired:
                jvm.kill(); jvm.wait()
        for sock in peers.values():
            shutdown(sock)  # Native sees EOF and restores, including after coordinator failure.
        for listener in listeners.values():
            listener.close()
        for worker in workers:
            worker.join(2)
        if control:
            if control.relay_thread:
                control.relay_thread.join(2)
            report.update(control.report)
        # Recovery and normal teardown both wait for the native cleanup receipt.
        cleanup_deadline = time.monotonic() + 30
        receipt = {}
        while native and time.monotonic() < cleanup_deadline:
            try:
                receipt = json.loads(native_report.read_text())
            except (OSError, ValueError):
                receipt = {}
            if receipt.get('session_nonce') == nonce and receipt.get('report_complete'):
                break
            if native.poll() is not None and not receipt:
                break
            time.sleep(0.1)
        report['wifi_restored'] = receipt.get('session_nonce') == nonce and receipt.get('wifi_restored') is True and not journal.exists()
        report['native_complete'] = receipt.get('report_complete') is True and receipt.get('session_nonce') == nonce
        report['recovery_required'] = journal.exists() or not report['native_complete'] or not report['wifi_restored']
        # Do not kill a native worker blocked in a system Wi-Fi call: its own radio.lock
        # remains held, preventing a competing recovery process from mutating Wi-Fi.
        if native and native.poll() is None and report['native_complete']:
            try:
                native.wait(timeout=3)
            except subprocess.TimeoutExpired:
                pass
        for path in private.iterdir():
            path.unlink()
        private.rmdir()
        if forward_created:
            try:
                remove_owned_forward()
            except Exception:
                report['forward_cleanup_incomplete'] = True
        if identity_nonce:
            try:
                relay_identity.cleanup(ADB, SERIAL, identity_nonce)
                report['relay_identity_cleaned'] = True
            except Exception:
                report['relay_identity_cleanup_incomplete'] = True
        report['private_sockets_removed'] = not private.exists()
        write_report(out / 'result.json', report)
        print(json.dumps({'report': str(out / 'result.json'), **report}), flush=True)
    return 0 if report.get('wifi_restored') and report.get('native_complete') and not report.get('error_type') else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--check', action='store_true')
    action.add_argument('--connect', action='store_true')
    action.add_argument('--recover', action='store_true')
    parser.add_argument('--device', help='explicit existing paired Bluetooth address')
    parser.add_argument('--seconds', type=int, default=300)
    parser.add_argument('--cached-service-diagnostic', action='store_true')
    args = parser.parse_args()
    if args.check:
        print(json.dumps(preflight(), indent=2)); return 0
    if not 10 <= args.seconds <= 600:
        parser.error('session duration must be 10..600 seconds')
    if args.connect and (not args.device or not re.fullmatch(r'(?:[0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2}', args.device)):
        parser.error('an explicit paired Bluetooth address is required')
    try:
        return run(args)
    except Exception as error:
        print(json.dumps({'started': False, 'error_type': type(error).__name__}), flush=True)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
