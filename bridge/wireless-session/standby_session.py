"""Opt-in test standby. Reopens AA identification, never sends a vehicle button action.
Each projection retains the existing 10-minute diagnostic session limit.
"""
from pathlib import Path
import argparse, fcntl, json, re, signal, subprocess, sys, threading, time
import run_session, relay_identity
from pairing_watch import PairingWatch
HERE = Path(__file__).resolve().parent

def clean(report):
    return (all(report.get(k) is True for k in ('wifi_restored', 'native_complete', 'private_sockets_removed'))
            and not any(report.get(k) for k in ('recovery_required', 'relay_identity_cleanup_incomplete', 'forward_cleanup_incomplete'))
            and (not report.get('relay_identity_staged') or report.get('relay_identity_cleaned') is True))

def decision(report, failures):
    if not clean(report): return 'recovery_required', failures
    if report.get('reason') == 'session_ended' and report.get('tcp_pair_connected'):
        return 'standby', 0
    if report.get('invitation_wait_expired') is True and not report.get('wifi_join_verified') and not report.get('tcp_pair_connected'):
        return 'waiting_invitation', failures
    failures = min(failures + 1, 3)
    return ('retry' if failures < 3 else 'cooldown'), failures

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--device', required=True)
    p.add_argument('--cached-service-diagnostic', action='store_true')
    a = p.parse_args()
    if not re.fullmatch(r'(?:[0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2}', a.device): p.error('explicit vehicle Bluetooth address required')
    # Check real emulator access before opening Bluetooth; --check alone only checks files.
    relay_identity.verify_installed(run_session.ADB, run_session.SERIAL)
    relay_identity.check_private_access(run_session.ADB, run_session.SERIAL)
    runtime = HERE / 'runtime'; runtime.mkdir(exist_ok=True, mode=0o700)
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP): signal.signal(sig, lambda *_: stop.set())
    with (runtime / 'standby.lock').open('a') as lock:
        try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: raise SystemExit('Standby already running')
        with PairingWatch(a.device) as watcher:
            return serve(a, runtime, stop, watcher)

def serve(a, runtime, stop, watcher):
        failures = 0
        last_wait = None
        unknown_since = None
        while not stop.is_set():
            state = watcher.state()
            if state != 'ready':
                if state == 'unknown':
                    if unknown_since is None: unknown_since=time.monotonic()
                    if time.monotonic()-unknown_since>15: raise RuntimeError('Pairing inventory unavailable; no radio actions')
                else: unknown_since=None
                if state!=last_wait: print(json.dumps({'state':state,'consecutive_failures':failures}),flush=True);last_wait=state
                if stop.wait(1): break
                continue
            unknown_since=None;last_wait=None
            probe = subprocess.run([sys.executable, str(HERE/'run_session.py'), '--check'], capture_output=True, text=True, timeout=30)
            try: ready = json.loads(probe.stdout).get('ready_for_explicit_connect') is True
            except ValueError: ready = False
            if not ready: raise SystemExit('Preflight blocked; no automatic recovery or radio changes')
            cmd = [sys.executable, str(HERE/'run_session.py'), '--connect', '--device', a.device, '--seconds', '600']
            if a.cached_service_diagnostic: cmd.append('--cached-service-diagnostic')
            with (runtime/'standby-child.log').open('w+') as log:
                child = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT)
                try:
                    while child.poll() is None and not stop.wait(.2): pass
                finally:
                    if child.poll() is None:
                        child.send_signal(signal.SIGINT)
                        try: child.wait(timeout=50)
                        except subprocess.TimeoutExpired: raise SystemExit('Child cleanup incomplete; no restart, retain recovery evidence')
                log.seek(0); report = {}
                for line in log:
                    try: obj = json.loads(line)
                    except ValueError: continue
                    if isinstance(obj, dict) and 'report' in obj: report = obj
            action, failures = decision(report, failures)
            print(json.dumps({'state': action, 'consecutive_failures': failures, 'report': report.get('report')}), flush=True)
            if stop.is_set(): return 0 if clean(report) else 1
            if action == 'recovery_required': return 1
            # Allow teardown before reconnecting only the identification channel.
            if stop.wait(1 if action == 'standby' else 120 if action == 'cooldown' else 15 if action == 'waiting_invitation' else 10*failures): break
        return 0

if __name__ == '__main__': raise SystemExit(main())
