#!/usr/bin/env python3
"""Explicit emulator-only lifecycle. Never contacts a vehicle."""
import argparse
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import time
from common import ROOT, BRIDGE, LOCK, sdk, run, adb, require_emulator

LAB = BRIDGE / 'emulator-lab'
STATE = LAB / 'runtime'


def forward():
    lines = [x.split() for x in adb('forward', '--list', capture=True).splitlines() if x.strip()]
    expected = [LOCK['android']['serial'], 'tcp:55277', 'localabstract:aare_hu']
    for entry in lines:
        if len(entry) == 3 and entry[1] == 'tcp:55277':
            if entry != expected: raise RuntimeError('Port 55277 belongs to another ADB mapping')
            return
    adb('forward', '--no-rebind', 'tcp:55277', 'localabstract:aare_hu')


def prepare():
    require_emulator(); forward()
    adb('shell', 'am', 'start', '-n', 'net.prototux.aare/.ui.MainActivity')


def start(args):
    STATE.mkdir(parents=True, exist_ok=True)
    try:
        require_emulator()
    except (RuntimeError, subprocess.SubprocessError):
        with socket.socket() as check:
            if check.connect_ex(('127.0.0.1', LOCK['android']['port'])) == 0:
                raise RuntimeError('Port 5580 is occupied but dedicated AVD verification failed')
        log = STATE / 'emulator.log'
        if log.exists() and log.stat().st_size > 5 * 1024 * 1024: log.replace(STATE / 'emulator.previous.log')
        with log.open('ab') as output:
            process = subprocess.Popen([str(sdk() / 'emulator/emulator'), '-avd', LOCK['android']['avd'],
                '-port', '5580', '-memory', '2048', '-cores', '2', '-gpu', 'host', '-no-snapshot'],
                stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
        (STATE / 'emulator-process.json').write_text(json.dumps({'pid':process.pid,'avd':LOCK['android']['avd']}))
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            try: require_emulator(); break
            except (RuntimeError, subprocess.SubprocessError): time.sleep(1)
        else: raise RuntimeError('Dedicated AVD boot timed out; inspect emulator.log')
    forward()
    if adb('shell', 'pm', 'path', 'net.prototux.aare', capture=True):
        prepare()
    elif args.prepare_only:
        print('Dedicated AVD booted; install the patched AARE APK next. No receiver opened.')
        return
    else:
        raise RuntimeError('Dedicated AVD booted, but AARE is missing. Run lab.py install first.')
    if not args.prepare_only: run(['open', '-n', LAB / 'apps/AARE Desktop.app'])


def install(args):
    require_emulator()
    apk = ROOT / ('build/probe/AARE-Lab.apk' if args.probe else 'build/apk-patch/aare-emulator.apk')
    if not apk.is_file(): raise RuntimeError('Build the selected APK first')
    adb('install', '-r', str(apk))


def stop(args):
    # Only exact executables generated inside this checkout; no global Java/process kill.
    executables = [str(LAB / f'apps/{name}.app/Contents/MacOS/{name}') for name in ('AARE Desktop', 'AARE Bridge Desktop')]
    for line in subprocess.check_output(['ps', '-axo', 'pid=,command='], text=True).splitlines():
        fields = line.strip().split(None, 1)
        if len(fields) == 2 and any(fields[1] == exe or fields[1].startswith(exe + ' ') for exe in executables):
            os.kill(int(fields[0]), signal.SIGTERM)
    require_emulator()
    mappings = adb('forward', '--list', capture=True)
    if 'emulator-5580 tcp:55277 localabstract:aare_hu' in mappings: adb('forward', '--remove', 'tcp:55277')
    adb('emu', 'kill')


def relay(args):
    prepare()
    STATE.mkdir(parents=True, exist_ok=True)
    report = STATE / ('relay-' + str(time.time_ns()) + '.json')
    process = subprocess.Popen(['python3', str(BRIDGE / 'wireless-session/stream_bridge.py'),
        '--seconds', '300', '--report', str(report)])
    try:
        # Check listener existence without consuming its only accepted connection.
        time.sleep(0.3)
        if process.poll() is not None: raise RuntimeError('Local relay exited before launch')
        run(['open', '-n', LAB / 'apps/AARE Bridge Desktop.app'])
        process.wait()
    finally:
        if process.poll() is None: process.terminate(); process.wait(timeout=5)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('step', choices=['start','prepare','install','stop','relay'])
    parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--probe', action='store_true')
    args = parser.parse_args()
    {'start':start,'prepare':lambda _:prepare(),'install':install,'stop':stop,'relay':relay}[args.step](args)


if __name__ == '__main__': main()
