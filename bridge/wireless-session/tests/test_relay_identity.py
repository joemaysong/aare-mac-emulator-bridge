import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import relay_identity as r

class IdentityTest(unittest.TestCase):
    nonce='1'*32
    def receipt(self, address='00:11:22:33:44:55'):
        return dict(session_nonce=self.nonce,events=[dict(event='doctor',bluetooth_power_raw=1,local_bluetooth_address=address)])
    def test_actual_adapter_and_nonce(self):
        self.assertEqual(r.native_address(self.receipt(),self.nonce),'00:11:22:33:44:55')
        with self.assertRaises(ValueError): r.native_address(self.receipt(),'2'*32)
        for address in ['','02:00:00:00:00:00','00:00:00:00:00:00','FF:FF:FF:FF:FF:FF','01:22:33:44:55:66']:
            with self.assertRaises(ValueError):r.native_address(self.receipt(address),self.nonce)
        receipt=self.receipt();receipt['events'][0]['bluetooth_power_raw']=0
        with self.assertRaises(ValueError):r.native_address(receipt,self.nonce)
    def test_stage_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'native.json';p.write_text(json.dumps(self.receipt()));stored=[]
            def shell(adb,serial,command,data=None):
                self.assertEqual(serial,'emulator-5580')
                if command=='cat /proc/uptime':return b'10.00 0.00\n'
                if command=='id -u':return b'2000\n'
                if data:stored.append(data);self.assertIn('set -C',command);return b''
                return stored[-1]
            with patch.object(r,'shell',side_effect=shell):
                self.assertEqual(r.stage('adb','emulator-5580',p,self.nonce,300),self.nonce)
            self.assertEqual(stored,[f'EV6RELAY1|{self.nonce}|00:11:22:33:44:55|310000|END\n'.encode()])
    def test_no_vehicle_serial(self):
        with self.assertRaises(ValueError):r.shell('adb','vehicle','anything')
    def test_cleanup_is_identity_scoped(self):
        with patch.object(r,'shell',return_value=b'2000') as shell:
            r.cleanup('adb','emulator-5580',self.nonce)
            self.assertIn(self.nonce,shell.call_args.args[2]);self.assertIn('$owner',shell.call_args.args[2])
    def test_installed_apk_is_pinned(self):
        build=Path(r.__file__).resolve().parents[1]/'emulator-lab/audio72'
        digest=json.loads((build/'verification.json').read_text())['apk_sha256']
        for actual, valid in [(digest,True),('0'*64,False)]:
            with patch.object(r,'shell',side_effect=[b'package:/data/app/~~abc/net.prototux.aare-xyz/base.apk\n', (actual+'  /data/app/base.apk\n').encode()]):
                if valid:self.assertEqual(r.verify_installed('adb','emulator-5580'),digest)
                else:
                    with self.assertRaises(RuntimeError):r.verify_installed('adb','emulator-5580')
    def test_install_path_rejects_shell_injection(self):
        with patch.object(r,'shell',return_value=b'package:/data/app/x;id/base.apk\n') as shell:
            with self.assertRaises(RuntimeError):r.verify_installed('adb','emulator-5580')
            self.assertEqual(shell.call_count,1)
    def test_root_private_access_keeps_app_directory(self):
        with patch.object(r,'shell',side_effect=[b'0\n',b'']) as shell:
            r.check_private_access('adb','emulator-5580')
            self.assertIn('cd /data/user/0/net.prototux.aare',shell.call_args.args[2])
            self.assertNotIn('chmod',shell.call_args.args[2])
    def test_private_access_failure_is_not_ignored(self):
        with patch.object(r,'shell',side_effect=[b'2000\n',RuntimeError('not debuggable')]):
            with self.assertRaises(RuntimeError):r.check_private_access('adb','emulator-5580')
    def test_identity_waits_for_inventory_after_ipc(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'native.json'
            def writer():
                time.sleep(0.02)
                tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(dict(session_nonce=self.nonce,events=[])));tmp.replace(p)
                time.sleep(0.04)
                tmp.write_text(json.dumps(self.receipt()));tmp.replace(p)
            worker=threading.Thread(target=writer);worker.start()
            try:self.assertEqual(r.wait_native_identity(p,self.nonce,1)['events'][0]['event'],'doctor')
            finally:worker.join()
    def test_identity_wait_is_bounded_and_session_scoped(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'native.json'
            with self.assertRaises(TimeoutError):r.wait_native_identity(p,self.nonce,0)
            p.write_text(json.dumps(dict(session_nonce='2'*32,events=[])))
            with self.assertRaises(ValueError):r.wait_native_identity(p,self.nonce,1)
            receipt=self.receipt();receipt['report_complete']=True;p.write_text(json.dumps(receipt))
            with self.assertRaises(RuntimeError):r.wait_native_identity(p,self.nonce,1)
if __name__=='__main__':unittest.main()
