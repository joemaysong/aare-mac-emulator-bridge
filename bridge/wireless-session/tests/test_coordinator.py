"""Exercise the real supervisor, JVM and native IPC with a compiled fake radio.
No open(1), ADB, CoreWLAN instance, Bluetooth API or emulator is invoked.
"""
import argparse
import json
from pathlib import Path
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import run_session
from session_control import SessionControl
from test_session_control import frame, text_field, varint


class CoordinatorTest(unittest.TestCase):
    def test_full_supervisor_with_real_jvm_and_native_fake_radio(self):
        real_popen = subprocess.Popen
        errors = []; workers = []; native_process = []
        with tempfile.TemporaryDirectory(prefix='aare-supervisor-test-', dir='/tmp') as temp:
            isolated = Path(temp).resolve(); runtime = isolated / 'runtime'; runtime.mkdir(mode=0o700)
            shutil.copytree(HERE / 'build/classes', isolated / 'build/classes')
            stream_done = threading.Event()
            def start(fn):
                def guarded():
                    try: fn()
                    except BaseException as error: errors.append(error)
                t = threading.Thread(target=guarded); t.start(); workers.append(t)
            def headunit(directory):
                with socket.socket(socket.AF_UNIX) as rx, socket.socket(socket.AF_UNIX) as tx:
                    rx.connect(str(directory / 'native-rx.sock')); tx.connect(str(directory / 'native-tx.sock')); tx.settimeout(5)
                    def exact(n):
                        value = b''
                        while len(value) < n:
                            data = tx.recv(n - len(value))
                            if not data: raise EOFError()
                            value += data
                        return value
                    def expect(ident):
                        for _ in range(15):
                            count, number = struct.unpack('>HH', exact(4)); data = exact(count)
                            if number == ident: return data
                            self.assertEqual(number, 8)
                        self.fail('WPP response missing')
                    rx.sendall(frame(4, b'\x08\x01\x10\x00')); expect(5)
                    rx.sendall(frame(1, text_field(1, '192.168.50.1') + b'\x10' + varint(5288))); expect(2)
                    rx.sendall(frame(3, text_field(1, 'test-car') + text_field(2, 'never-log-this-secret') + text_field(3, 'aa:bb:cc:dd:ee:ff') + b'\x20\x08'))
                    expect(7); expect(6)
                    self.assertTrue(stream_done.wait(4))
            def launch(command, *args, **kwargs):
                if command[0] != 'open':
                    return real_popen(command, *args, **kwargs)
                option = lambda name: command[command.index(name) + 1]
                directory = Path(option('--bridge-directory'))
                start(lambda: headunit(directory))
                p = real_popen([str(HERE / 'build/native-control-tests'), str(directory),
                    option('--journal'), option('--output'), 'quit', option('--nonce')],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                native_process.append(p); return p
            def opener(*args, **kwargs):
                phone, emulator = socket.socketpair(); car, hu = socket.socketpair()
                def traffic():
                    with emulator, hu:
                        emulator.settimeout(3); hu.settimeout(3)
                        emulator.sendall(b'\x00AAP-video-audio\xff')
                        self.assertEqual(hu.recv(100), b'\x00AAP-video-audio\xff')
                        hu.sendall(b'\x00touch\xfe')
                        self.assertEqual(emulator.recv(100), b'\x00touch\xfe')
                        # WPP READY acknowledgement must be sent before the fake HU closes RFCOMM.
                        stream_done.set()
                start(traffic); return phone, car
            original_init = SessionControl.__init__
            def init(control, *args, **kwargs):
                return original_init(control, *args, **kwargs, opener=opener)
            args = argparse.Namespace(recover=False, seconds=10, device='00-11-22-33-44-55', cached_service_diagnostic=False)
            with patch.object(run_session, 'HERE', isolated), patch.object(run_session, 'preflight', return_value={'missing': [], 'desktop_receiver_running': False}), \
                 patch.object(run_session, 'emulator_forward', return_value=False), patch.object(run_session.relay_identity, 'stage', return_value=None), patch.object(run_session.relay_identity, 'cleanup', return_value=None), patch.object(run_session.subprocess, 'Popen', side_effect=launch), \
                 patch.object(SessionControl, '__init__', init):
                code = run_session.owned_run(args, runtime)
            for worker in workers: worker.join(3)
            for process in native_process:
                if process.poll() is None: process.kill(); process.wait()
            results = list((isolated / 'runs').glob('*/result.json')); self.assertEqual(len(results), 1)
            report = json.loads(results[0].read_text())
            self.assertEqual(code, 0, report)
            self.assertFalse(errors, errors)
            self.assertTrue(report['wifi_join_verified'])
            self.assertTrue(report['tcp_pair_connected'])
            self.assertTrue(report['wifi_restored'])
            self.assertTrue(report['native_complete'])
            self.assertTrue(report['private_sockets_removed'])
            self.assertFalse(report['projection_verified'])
            self.assertFalse(report['recovery_required'])
            self.assertGreater(report['relay']['phone_to_headunit'], 0)
            self.assertGreater(report['relay']['headunit_to_phone'], 0)
            self.assertNotIn('never-log-this-secret', results[0].read_text())


if __name__ == '__main__': unittest.main()
