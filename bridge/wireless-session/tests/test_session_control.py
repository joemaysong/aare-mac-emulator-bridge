import os
import base64
import json
from pathlib import Path
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
from session_control import SessionControl, ProtocolError, read_line, send_line
from stream_bridge import open_vehicle_stream, connect_socket


def enc(value):
    return base64.b64encode(value.encode()).decode()


JOIN = ['JOIN', enc('test-car'), enc('never-log-this-secret'), enc('aa:bb:cc:dd:ee:ff'), 'WPA2_PERSONAL']
READY = ['READY', enc('192.168.50.1'), '5288']


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.native, self.fake_native = socket.socketpair()
        self.stop = threading.Event()
        self.session = SessionControl(self.native, stop=self.stop, deadline=time.monotonic() + 5)
        self.threads = []
        self.sockets = [self.native, self.fake_native]

    def tearDown(self):
        self.stop.set()
        for s in self.sockets:
            s.close()
        if self.session.relay_thread:
            self.session.relay_thread.join(1)
        for t in self.threads:
            t.join(1)

    def join(self, reply=None):
        reply = reply or ['JOINED', '192.168.50.2', 'en0', '255.255.255.0', '192.168.50.1']
        def native():
            self.assertEqual(read_line(self.fake_native, self.stop, time.monotonic() + 3), JOIN)
            send_line(self.fake_native, reply)
        t = threading.Thread(target=native); t.start(); self.threads.append(t)
        return self.session.handle(JOIN)

    def test_verified_join(self):
        self.assertEqual(self.join(), ['JOINED', '192.168.50.2', '192.168.50.1'])
        self.assertTrue(self.session.report['wifi_join_verified'])
        self.assertNotIn('never-log-this-secret', json.dumps(self.session.report))

    def test_no_ready_before_join(self):
        with self.assertRaises(ProtocolError):
            self.session.handle(READY)

    def test_invalid_security_and_base64_never_reach_native(self):
        for fields in [JOIN[:4] + ['WEP'], ['JOIN', '!', JOIN[2], JOIN[3], JOIN[4]],
                       JOIN[:3] + [enc('not-bssid'), JOIN[4]]]:
            with self.assertRaises(ProtocolError):
                self.session.handle(fields)
        self.fake_native.settimeout(0.02)
        with self.assertRaises(socket.timeout):
            self.fake_native.recv(1)

    def test_reject_stale_or_wrong_dhcp(self):
        with self.assertRaises(ProtocolError):
            self.join(['JOINED', '192.168.50.2', 'en0', '255.255.255.0', '172.20.10.1'])
        self.assertFalse(self.session.report['wifi_join_verified'])

    def test_reject_duplicate_join(self):
        self.join()
        with self.assertRaises(ProtocolError):
            self.session.handle(JOIN)

    def test_reject_wrong_endpoint_or_port(self):
        self.join()
        for endpoint, port in [('172.20.10.1', '5288'), ('127.0.0.1', '5288'),
                               ('192.168.50.2', '5288'), ('192.168.50.255', '5288'),
                               ('192.168.50.1', '65536'), ('192.168.50.1', '0')]:
            with self.assertRaises(ProtocolError):
                self.session.handle(['READY', enc(endpoint), port])

    def test_failed_tcp_never_acknowledges_ready(self):
        self.join()
        self.session.opener = lambda *a, **kw: (_ for _ in ()).throw(ConnectionRefusedError())
        with self.assertRaises(ConnectionRefusedError):
            self.session.handle(READY)
        self.assertFalse(self.session.report['tcp_pair_connected'])

    def test_ready_binary_round_trip_and_cancel(self):
        self.join()
        phone, emulator = socket.socketpair(); car, hu = socket.socketpair()
        self.sockets.extend([emulator, hu])
        self.session.opener = lambda *a, **kw: (phone, car)
        self.assertEqual(self.session.handle(READY), ['READY_OK'])
        emulator.sendall(b'\x00TLS\xffpayload'); hu.settimeout(1)
        self.assertEqual(hu.recv(100), b'\x00TLS\xffpayload')
        hu.sendall(b'\x00touch\xfe'); emulator.settimeout(1)
        self.assertEqual(emulator.recv(100), b'\x00touch\xfe')
        self.stop.set(); self.session.relay_thread.join(2)
        self.assertTrue(self.session.report['relay']['sockets_closed'])
        self.assertFalse(self.session.report['projection_verified'])
        with self.assertRaises(ProtocolError):
            self.session.handle(READY)

    def test_control_frame_limits_and_cancel(self):
        self.fake_native.sendall(b'x' * 8192)
        with self.assertRaises(ProtocolError):
            read_line(self.native, self.stop, time.monotonic() + 2)
        self.stop.set()
        with self.assertRaises(InterruptedError):
            read_line(self.native, self.stop, time.monotonic() + 2)

    def test_car_failure_does_not_consume_emulator(self):
        with patch('stream_bridge.connect_socket', side_effect=ConnectionRefusedError()) as connect:
            with self.assertRaises(ConnectionRefusedError):
                open_vehicle_stream('192.168.50.2', '192.168.50.1', 5288)
            self.assertEqual(connect.call_count, 1)

    def test_phone_failure_closes_car_socket(self):
        a, b = socket.socketpair(); self.sockets.append(b)
        with patch('stream_bridge.connect_socket', side_effect=[a, ConnectionRefusedError()]):
            with self.assertRaises(ConnectionRefusedError):
                open_vehicle_stream('192.168.50.2', '192.168.50.1', 5288)
        self.assertEqual(a.fileno(), -1)

    def test_cancelled_connect_does_not_open_connection(self):
        self.stop.set()
        with self.assertRaises(InterruptedError):
            connect_socket(('127.0.0.1', 1), stop=self.stop)


# Test fixture protobuf fields match the pinned upstream proto2 aaw definitions.
def varint(n):
    out = bytearray()
    while n >= 128:
        out.append((n & 127) | 128); n >>= 7
    return bytes(out + bytes([n]))


def text_field(number, value):
    data = value.encode(); return varint(number * 8 + 2) + varint(len(data)) + data


def frame(number, data):
    return struct.pack('>HH', len(data), number) + data


class RealJvmWppTest(unittest.TestCase):
    def test_real_wpp_to_coordinator_to_opaque_stream(self):
        root = HERE.parent
        java = Path(os.environ.get('JAVA_HOME', str(root / 'runtime/jdk'))) / 'bin/java'
        cp = str(HERE / 'build/classes') + ':' + (root / 'core/aap/build/mac-classpath.txt').read_text().strip()
        stop = threading.Event(); sockets = []; threads = []; errors = []
        with tempfile.TemporaryDirectory(prefix='aare-wpp-test-', dir='/tmp') as temp:
            directory = Path(temp).resolve(); listeners = {}
            for name in ('rx', 'tx', 'control'):
                s = socket.socket(socket.AF_UNIX); s.bind(str(directory / (name + '.sock'))); s.listen(1); s.settimeout(5)
                listeners[name] = s
            process = subprocess.Popen([str(java), '-Xmx128m', '-cp', cp,
                'org.ev6.aare.mac.EmulatorWirelessSession', str(directory), 'aare-mac-' + '0' * 32],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            try:
                rx = listeners['rx'].accept()[0]; tx = listeners['tx'].accept()[0]; control = listeners['control'].accept()[0]
                sockets.extend([rx, tx, control]); tx.settimeout(5)
                native, fake = socket.socketpair(); sockets.extend([native, fake])
                phone, emulator = socket.socketpair(); car, hu = socket.socketpair(); sockets.extend([emulator, hu])
                session = SessionControl(native, stop=stop, deadline=time.monotonic() + 10,
                    opener=lambda *a, **kw: (phone, car))
                def guarded(fn):
                    def run():
                        try: fn()
                        except (EOFError, InterruptedError, OSError): pass
                        except BaseException as e: errors.append(e)
                    t = threading.Thread(target=run); t.start(); threads.append(t)
                def native_join():
                    fields = read_line(fake, stop, time.monotonic() + 5)
                    self.assertEqual(fields[0], 'JOIN')
                    send_line(fake, ['JOINED', '192.168.50.2', 'en0', '255.255.255.0', '192.168.50.1'])
                guarded(native_join); guarded(lambda: session.serve(control))
                def read_exact(count):
                    data = b''
                    while len(data) < count:
                        part = tx.recv(count - len(data))
                        if not part: raise EOFError()
                        data += part
                    return data
                def expect(number):
                    for _ in range(15):
                        length, ident = struct.unpack('>HH', read_exact(4)); payload = read_exact(length)
                        if ident == number: return payload
                        self.assertEqual(ident, 8)  # Only keepalive may interleave.
                    self.fail('expected WPP frame')
                rx.sendall(frame(4, b'\x08\x01\x10\x00'))
                expect(5)
                rx.sendall(frame(1, text_field(1, '192.168.50.1') + b'\x10' + varint(5288)))
                expect(2)
                payload = text_field(1, 'fake-car') + text_field(2, 'never-log-this-secret') + text_field(3, 'aa:bb:cc:dd:ee:ff') + b'\x20\x08'
                rx.sendall(frame(3, payload))
                expect(7); status = expect(6)
                self.assertIn(b'\x08\x00', status)
                emulator.sendall(b'\x00opaque-AAP-TLS\xff'); hu.settimeout(3)
                self.assertEqual(hu.recv(100), b'\x00opaque-AAP-TLS\xff')
                hu.sendall(b'\x00touch\xfe'); emulator.settimeout(3)
                self.assertEqual(emulator.recv(100), b'\x00touch\xfe')
                self.assertTrue(session.report['tcp_pair_connected'])
                self.assertFalse(session.report['projection_verified'])
            finally:
                stop.set()
                for s in sockets + list(listeners.values()): s.close()
                process.terminate()
                try: output = process.communicate(timeout=5)[0]
                except subprocess.TimeoutExpired: process.kill(); output = process.communicate()[0]
                for t in threads: t.join(2)
                if 'session' in locals() and session.relay_thread: session.relay_thread.join(2)
            self.assertFalse(errors)
            self.assertIn('WPP_READY_STREAM_CONNECTED', output)
            self.assertNotIn('never-log-this-secret', output)
            self.assertNotIn('fake-car', output)


if __name__ == '__main__':
    unittest.main()
