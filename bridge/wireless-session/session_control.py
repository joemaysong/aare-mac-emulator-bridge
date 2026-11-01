"""Private IPC coordinator; no radio or ADB side effects on import."""
import base64
import ipaddress
import re
import socket
import threading
import time
from stream_bridge import DuplexRelay, open_vehicle_stream


class ProtocolError(Exception):
    pass


def read_line(sock, stop, deadline):
    data = bytearray()
    sock.settimeout(0.2)
    while len(data) < 8192:
        if stop.is_set():
            raise InterruptedError('cancelled')
        if time.monotonic() >= deadline:
            raise TimeoutError('IPC deadline')
        try:
            value = sock.recv(1)
        except socket.timeout:
            continue
        if not value:
            raise EOFError('IPC closed')
        if value == b'\n':
            return data.decode('ascii').split('\t')
        if value[0] > 127 or value == b'\0':
            raise ProtocolError('IPC encoding')
        data.extend(value)
    raise ProtocolError('IPC limit')


def send_line(sock, fields):
    data = ('\t'.join(fields) + '\n').encode('ascii')
    if len(data) > 8192 or any('\n' in s or '\r' in s or '\0' in s or '\t' in s for s in fields):
        raise ProtocolError('IPC fields')
    sock.settimeout(2)
    sock.sendall(data)


def decoded(value):
    try:
        return base64.b64decode(value, validate=True).decode('utf-8')
    except (ValueError, UnicodeError):
        raise ProtocolError('base64') from None


def private_ip(text):
    try:
        ip = ipaddress.IPv4Address(text)
    except ValueError:
        raise ProtocolError('IPv4 required') from None
    networks = ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16')
    if not any(ip in ipaddress.IPv4Network(n) for n in networks):
        raise ProtocolError('private network required')
    return ip


class SessionControl:
    def __init__(self, native, *, stop, deadline, phone_port=55277, opener=open_vehicle_stream):
        self.native = native
        self.stop = stop
        self.deadline = deadline
        self.phone_port = phone_port
        self.opener = opener
        self.wifi = None
        self.stream_started = False
        self.relay_thread = None
        self.report = {'wifi_join_verified': False, 'tcp_pair_connected': False,
                       'aap_tls_accepted': 'not_observed', 'projection_verified': False}

    def handle(self, fields):
        if fields[0] == 'JOIN' and len(fields) == 5 and self.wifi is None:
            ssid, password, bssid = map(decoded, fields[1:4])
            if not 1 <= len(ssid.encode()) <= 32 or '\0' in ssid or len(password.encode()) > 64:
                raise ProtocolError('credentials shape')
            if bssid and not re.fullmatch(r'(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}', bssid):
                raise ProtocolError('BSSID shape')
            if fields[4] not in ('OPEN', 'WPA2_PERSONAL', 'WPA2_WPA3_PERSONAL'):
                raise ProtocolError('security unsupported')
            send_line(self.native, fields)  # Private sockets only; never logged.
            reply = read_line(self.native, self.stop, min(self.deadline, time.monotonic() + 45))
            if len(reply) != 5 or reply[0] != 'JOINED':
                return ['FAILED']
            ip, interface, mask, gateway = reply[1:]
            private_ip(ip)
            if not re.fullmatch(r'en[0-9]{1,3}', interface):
                raise ProtocolError('interface shape')
            try:
                network = ipaddress.IPv4Network(f'{ip}/{mask}', strict=False)
            except ValueError:
                raise ProtocolError('netmask') from None
            if network.prefixlen < 16 or private_ip(gateway) not in network or ipaddress.IPv4Address(ip) in (network.network_address, network.broadcast_address):
                raise ProtocolError('DHCP network')
            self.wifi = (ip, interface, network, gateway)
            self.report['wifi_join_verified'] = True
            return ['JOINED', ip, gateway]
        if fields[0] == 'READY' and len(fields) == 3 and self.wifi and not self.stream_started:
            host = private_ip(decoded(fields[1]))
            ip, interface, network, _ = self.wifi
            if host not in network or str(host) == ip or host in (network.network_address, network.broadcast_address):
                raise ProtocolError('endpoint outside car network')
            if not re.fullmatch(r'[1-9][0-9]{0,4}', fields[2]) or not 1 <= int(fields[2]) <= 65535:
                raise ProtocolError('port')
            phone, car = self.opener(ip, str(host), int(fields[2]), stop=self.stop,
                                     phone_port=self.phone_port, interface=interface)
            self.stream_started = True
            self.report['tcp_pair_connected'] = True
            relay = DuplexRelay(phone, car, stop=self.stop,
                                max_seconds=max(0.1, self.deadline - time.monotonic()))
            def run():
                try:
                    self.report['relay'] = relay.run()
                finally:
                    self.stop.set()
            self.relay_thread = threading.Thread(target=run, name='opaque-aap-relay', daemon=True)
            self.relay_thread.start()
            return ['READY_OK']
        raise ProtocolError('unexpected phase')

    def serve(self, control):
        while not self.stop.is_set():
            send_line(control, self.handle(read_line(control, self.stop, self.deadline)))
