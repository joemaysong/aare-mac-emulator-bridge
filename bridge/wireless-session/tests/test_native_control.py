import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
from session_control import read_line, send_line
from test_session_control import JOIN


class NativeIpcTests(unittest.TestCase):
    def exercise(self, ending):
        with tempfile.TemporaryDirectory(prefix='aare-native-test-', dir='/tmp') as temp:
            root = Path(temp).resolve()
            journal = root / 'wifi-recovery.json'; result = root / 'receipt.json'
            if ending == 'recover':
                journal.write_text(json.dumps({'version': 1, 'uid': os.getuid(), 'interface': 'en0',
                    'originalPower': False, 'originalSSID': '', 'originalBSSID': '', 'originalAssociated': False,
                    'targetSSID': 'test-car', 'targetBSSID': 'aa:bb:cc:dd:ee:ff'}))
                journal.chmod(0o600)
            with socket.socket(socket.AF_UNIX) as listener:
                listener.bind(str(root / 'native-control.sock')); listener.listen(1); listener.settimeout(3)
                process = subprocess.Popen([str(HERE / 'build/native-control-tests'), str(root), str(journal), str(result), ending],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                try:
                    peer, _ = listener.accept()
                    with peer:
                        if ending != 'recover':
                            send_line(peer, JOIN)
                            reply = read_line(peer, threading.Event(), time.monotonic() + 4)
                            self.assertEqual(reply, ['JOINED', '192.168.50.2', 'en0', '255.255.255.0', '192.168.50.1'])
                            self.assertNotIn('never-log-this-secret', journal.read_text())
                            if ending == 'quit':
                                send_line(peer, ['QUIT'])
                                self.assertEqual(read_line(peer, threading.Event(), time.monotonic() + 4), ['RESTORED'])
                        else:
                            self.assertEqual(read_line(peer, threading.Event(), time.monotonic() + 4), ['RESTORED'])
                    _, error = process.communicate(timeout=5)
                    self.assertEqual(process.returncode, 0, error)
                    self.assertEqual(json.loads(result.read_text()), {'mutated': True, 'restored': True, 'powered': False, 'hardware_access': False})
                    self.assertFalse(journal.exists())
                finally:
                    if process.poll() is None:
                        process.kill(); process.communicate()
                    else:
                        process.communicate()

    def test_quit_restores_original_wifi_off(self): self.exercise('quit')
    def test_peer_eof_restores_original_wifi_off(self): self.exercise('eof')
    def test_stale_journal_recovery(self): self.exercise('recover')


if __name__ == '__main__': unittest.main()
