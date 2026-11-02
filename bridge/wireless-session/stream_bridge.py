"""Opaque, bounded AAP transport. This module never terminates or alters TLS.

The desktop mode listens on loopback only; vehicle mode is deliberately a separate
entry point that requires a verified Wi-Fi association from the session coordinator.
No payloads, certificates or credentials are logged.
"""
import argparse
import errno
import json
import selectors
import signal
import socket
import sys
import threading
import time
from pathlib import Path


class DuplexRelay:
    def __init__(self, phone, headunit, *, stop=None, idle_seconds=30, max_seconds=300,
                 capacity=262144):
        self.sockets = (phone, headunit)
        self.stop = stop or threading.Event()
        self.idle_seconds = idle_seconds
        self.max_seconds = max_seconds
        self.capacity = capacity
        self.report = {'mode': 'opaque-aap-relay', 'tls_terminated': False,
                       'phone_to_headunit': 0, 'headunit_to_phone': 0,
                       'max_buffer_bytes': 0, 'reason': 'not_started'}

    def run(self):
        a, b = self.sockets
        peer = {a: b, b: a}
        pending = {a: bytearray(), b: bytearray()}
        eof, write_closed = set(), set()
        started = last = time.monotonic()
        try:
            for s in self.sockets:
                s.setblocking(False)
            with selectors.DefaultSelector() as selector:
                registered = set()
                while True:
                    now = time.monotonic()
                    if self.stop.is_set():
                        self.report['reason'] = 'cancelled'
                        break
                    if now - started >= self.max_seconds:
                        self.report['reason'] = 'session_deadline'
                        break
                    if now - last >= self.idle_seconds:
                        self.report['reason'] = 'idle_timeout'
                        break
                    for src in self.sockets:
                        dst = peer[src]
                        if src in eof and not pending[dst] and dst not in write_closed:
                            try:
                                dst.shutdown(socket.SHUT_WR)
                            except OSError:
                                pass
                            write_closed.add(dst)
                    if len(eof) == 2 and not any(pending.values()):
                        self.report['reason'] = 'eof'
                        break
                    for s in self.sockets:
                        events = 0
                        if s not in eof and len(pending[peer[s]]) < self.capacity:
                            events |= selectors.EVENT_READ
                        if pending[s]:
                            events |= selectors.EVENT_WRITE
                        if s in registered:
                            if events:
                                selector.modify(s, events)
                            else:
                                selector.unregister(s)
                                registered.remove(s)
                        elif events:
                            selector.register(s, events)
                            registered.add(s)
                    for key, events in selector.select(0.1):
                        s = key.fileobj
                        if events & selectors.EVENT_WRITE:
                            try:
                                n = s.send(pending[s])
                            except BlockingIOError:
                                n = 0
                            if n:
                                del pending[s][:n]
                                direction = 'phone_to_headunit' if s is b else 'headunit_to_phone'
                                self.report[direction] += n
                                last = time.monotonic()
                        if events & selectors.EVENT_READ:
                            dst = peer[s]
                            try:
                                data = s.recv(min(65536, self.capacity - len(pending[dst])))
                            except BlockingIOError:
                                continue
                            if data:
                                pending[dst].extend(data)
                                last = time.monotonic()
                                self.report['max_buffer_bytes'] = max(
                                    self.report['max_buffer_bytes'], len(pending[dst]))
                            else:
                                eof.add(s)
        except OSError as error:
            self.report['reason'] = 'socket_error'
            self.report['error_type'] = type(error).__name__
        finally:
            for s in self.sockets:
                s.close()
            self.report['elapsed_seconds'] = round(time.monotonic() - started, 3)
            self.report['sockets_closed'] = all(s.fileno() == -1 for s in self.sockets)
        return self.report


def connect_socket(address, *, stop, source_ip=None, interface=None, timeout=5):
    """Cancellable connect; force the Wi-Fi interface on Darwin, preserving USB internet."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        if stop.is_set():
            raise InterruptedError('cancelled')
        if interface is not None:
            if sys.platform != 'darwin':
                raise OSError('interface binding requires Darwin')
            # Darwin SDK netinet/in.h: IP_BOUND_IF = 25.
            sock.setsockopt(socket.IPPROTO_IP, 25, socket.if_nametoindex(interface))
        if source_ip:
            sock.bind((source_ip, 0))
        sock.setblocking(False)
        result = sock.connect_ex(address)
        if result not in (0, errno.EINPROGRESS, errno.EWOULDBLOCK, errno.EALREADY):
            raise OSError(result, 'connect failed')
        with selectors.DefaultSelector() as selector:
            selector.register(sock, selectors.EVENT_WRITE)
            deadline = time.monotonic() + timeout
            while result:
                if stop.is_set():
                    raise InterruptedError('cancelled')
                if time.monotonic() >= deadline:
                    raise TimeoutError('connect deadline')
                if selector.select(0.1):
                    result = sock.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
                    if result:
                        raise OSError(result, 'connect failed')
                    break
        return sock
    except BaseException:
        sock.close()
        raise


def open_vehicle_stream(local_ip, headunit_ip, headunit_port, *, stop=None,
                        phone_port=55277, interface=None):
    """Only call after real Wi-Fi join/IP verification, never after a mock join.

    Bind the vehicle connection to the actual Wi-Fi address. A failed car TCP
    connection must not consume the emulator's one available projection session.
    """
    stop = stop or threading.Event()
    car = phone = None
    stage = "vehicle_tcp"
    try:
        car = connect_socket((headunit_ip, headunit_port), stop=stop,
                             source_ip=local_ip, interface=interface)
        stage = "emulator_tcp"
        phone = connect_socket(('127.0.0.1', phone_port), stop=stop)
        return phone, car
    except BaseException as error:
        if isinstance(error, OSError):
            error.aare_connect_stage = stage
        for s in (phone, car):
            if s is not None:
                s.close()
        raise


def connect_vehicle_stream(local_ip, headunit_ip, headunit_port, *, stop=None,
                           phone_port=55277, max_seconds=300, interface=None):
    phone, car = open_vehicle_stream(local_ip, headunit_ip, headunit_port, stop=stop,
                                     phone_port=phone_port, interface=interface)
    return DuplexRelay(phone, car, stop=stop, max_seconds=max_seconds).run()


def main():
    p = argparse.ArgumentParser(description='Local desktop AAP bridge test; no vehicle actions')
    p.add_argument('--desktop-port', type=int, default=55278)
    p.add_argument('--phone-port', type=int, default=55277)
    p.add_argument('--seconds', type=int, default=300)
    p.add_argument('--report', type=Path, required=True)
    a = p.parse_args()
    if not 1 <= a.seconds <= 600 or not all(1024 <= n <= 65535 for n in (a.desktop_port, a.phone_port)):
        p.error('invalid port or session limit')
    if a.desktop_port == a.phone_port or a.report.exists():
        p.error('ports must differ and report must be new')
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    report = {'mode': 'local-desktop-bridge', 'vehicle_attempted': False}
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', a.desktop_port))
        listener.listen(1)
        listener.settimeout(0.2)
        deadline = time.monotonic() + 60
        print('LOCAL_BRIDGE_LISTENING', flush=True)
        try:
            while not stop.is_set() and time.monotonic() < deadline:
                try:
                    car, _ = listener.accept()
                    break
                except socket.timeout:
                    continue
            else:
                raise TimeoutError('no desktop peer')
            with car:
                phone = socket.create_connection(('127.0.0.1', a.phone_port), timeout=5)
                report.update(DuplexRelay(phone, car, stop=stop, max_seconds=a.seconds).run())
        except OSError as e:
            report.update(reason='connect_failed', error_type=type(e).__name__)
    a.report.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report), flush=True)


if __name__ == '__main__':
    main()
