"""Preflight version mismatch must not create ADB forwarding or open radios."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import run_session as r

class IdentityGateTest(unittest.TestCase):
    def test_old_apk_rejected_before_forward(self):
        with patch.object(r.subprocess,'check_output',side_effect=['AARE_Mac_API35\nOK','1']) as adb, patch.object(r.relay_identity,'verify_installed',side_effect=RuntimeError('old APK')):
            with self.assertRaises(RuntimeError):r.emulator_forward()
            self.assertEqual(adb.call_count,2)
            for call in adb.call_args_list:self.assertNotIn('forward',call.args[0])
    def test_valid_apk_precedes_new_forward(self):
        events=[]
        def adb(cmd,**kwargs):
            events.append(cmd[3:])
            if 'avd' in cmd:return 'AARE_Mac_API35\nOK'
            if 'getprop' in cmd:return '1'
            return ''
        with patch.object(r.subprocess,'check_output',side_effect=adb), patch.object(r.relay_identity,'verify_installed',side_effect=lambda *a:events.append(['verified'])), patch.object(r.relay_identity,'check_private_access',return_value=None):
            self.assertTrue(r.emulator_forward())
        self.assertLess(events.index(['verified']),events.index(['forward','--list']))
        self.assertEqual(events[-1],['forward','--no-rebind','tcp:55277','localabstract:aare_hu'])
    def test_foreign_forward_not_replaced(self):
        with patch.object(r.subprocess,'check_output',side_effect=['AARE_Mac_API35\nOK','1','another tcp:55277 tcp:99']) as adb, patch.object(r.relay_identity,'verify_installed',return_value='verified'), patch.object(r.relay_identity,'check_private_access',return_value=None):
            with self.assertRaises(RuntimeError):r.emulator_forward()
            self.assertEqual(adb.call_count,3)
if __name__=='__main__':unittest.main()
