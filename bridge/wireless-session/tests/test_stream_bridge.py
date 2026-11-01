import hashlib
import socket
import sys
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from stream_bridge import DuplexRelay


class BridgeTests(unittest.TestCase):
    def setup_relay(self, **kwargs):
        self.a, left = socket.socketpair()
        self.b, right = socket.socketpair()
        self.a.settimeout(4)
        self.b.settimeout(4)
        self.stop = threading.Event()
        self.relay = DuplexRelay(left, right, stop=self.stop, **kwargs)
        self.worker = threading.Thread(target=self.relay.run)
        self.worker.start()

    def tearDown(self):
        self.stop.set()
        self.a.close()
        self.b.close()
        self.worker.join(3)
        self.assertFalse(self.worker.is_alive())
        self.assertTrue(self.relay.report['sockets_closed'])

    @staticmethod
    def read_all(s):
        data = bytearray()
        while True:
            chunk = s.recv(32768)
            if not chunk:
                return bytes(data)
            data.extend(chunk)

    def test_large_binary_full_duplex_exact(self):
        self.setup_relay(capacity=65536)
        x = bytes(range(256)) * 4096
        y = b'\x00\xff\x17TLS-like\x00' * 100000
        failures = []

        def send(s, payload):
            try:
                s.sendall(payload)
                s.shutdown(socket.SHUT_WR)
            except Exception as e:
                failures.append(e)

        tx = [threading.Thread(target=send, args=(self.a, x)),
              threading.Thread(target=send, args=(self.b, y))]
        received = {}
        readers = [threading.Thread(target=lambda: received.update(a=self.read_all(self.a))),
                   threading.Thread(target=lambda: received.update(b=self.read_all(self.b)))]
        for t in tx + readers:
            t.start()
        for t in tx + readers:
            t.join(5)
            self.assertFalse(t.is_alive())
        self.worker.join(3)
        self.assertFalse(failures)
        self.assertEqual(hashlib.sha256(x).digest(), hashlib.sha256(received['b']).digest())
        self.assertEqual(hashlib.sha256(y).digest(), hashlib.sha256(received['a']).digest())
        self.assertEqual('eof', self.relay.report['reason'])
        self.assertLessEqual(self.relay.report['max_buffer_bytes'], 65536)

    def test_half_close_allows_response_after_request(self):
        self.setup_relay()
        self.a.sendall(b'request')
        self.a.shutdown(socket.SHUT_WR)
        self.assertEqual(b'request', self.read_all(self.b))
        self.b.sendall(b'response after request EOF')
        self.b.shutdown(socket.SHUT_WR)
        self.assertEqual(b'response after request EOF', self.read_all(self.a))
        self.worker.join(3)
        self.assertEqual('eof', self.relay.report['reason'])

    def test_cancel_idle_connection(self):
        self.setup_relay()
        self.stop.set()
        self.worker.join(1)
        self.assertFalse(self.worker.is_alive())
        self.assertEqual('cancelled', self.relay.report['reason'])

    def test_idle_timeout_is_bounded(self):
        self.setup_relay(idle_seconds=0.2)
        self.worker.join(1)
        self.assertEqual('idle_timeout', self.relay.report['reason'])

    def test_cancel_with_backpressure(self):
        self.setup_relay(capacity=8192)
        self.a.setblocking(False)
        end = time.monotonic() + 0.3
        while time.monotonic() < end:
            try:
                self.a.send(b'x' * 65536)
            except BlockingIOError:
                time.sleep(0.005)
        self.stop.set()
        self.worker.join(1)
        self.assertEqual('cancelled', self.relay.report['reason'])
        self.assertLessEqual(self.relay.report['max_buffer_bytes'], 8192)


if __name__ == '__main__':
    unittest.main()
