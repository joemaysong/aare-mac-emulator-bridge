import json
import unittest
from unittest.mock import patch
import relay_identity as subject

class Clock:
    now = 0.0
    def monotonic(self): return self.now
    def sleep(self, seconds): self.now += seconds

class Receipt:
    def __init__(self, clock, delay=9.5, nonce='a'*32, complete=False):
        self.clock, self.delay, self.nonce, self.complete = clock, delay, nonce, complete
    def read_text(self):
        return json.dumps(dict(session_nonce=self.nonce, report_complete=self.complete,
            events=[] if self.clock.now < self.delay else [dict(event='doctor',
                bluetooth_power_raw=1, local_bluetooth_address='AA:BB:CC:DD:EE:FF')]))

class IdentityWaitTest(unittest.TestCase):
    def run_wait(self, receipt, clock):
        with patch.object(subject.time, 'monotonic', clock.monotonic), patch.object(subject.time, 'sleep', clock.sleep):
            return subject.wait_native_identity(receipt, 'a'*32)
    def test_power_on_inventory_after_old_five_second_limit(self):
        clock=Clock();result=self.run_wait(Receipt(clock),clock)
        self.assertEqual(subject.native_address(result,'a'*32),'AA:BB:CC:DD:EE:FF')
        self.assertGreaterEqual(clock.now,9.5);self.assertLess(clock.now,10)
    def test_no_receipt_is_still_bounded(self):
        clock=Clock()
        with self.assertRaises(TimeoutError): self.run_wait(Receipt(clock,100),clock)
        self.assertAlmostEqual(clock.now,25)
    def test_old_generation_never_reused(self):
        clock=Clock()
        with self.assertRaises(ValueError): self.run_wait(Receipt(clock,0,nonce='b'*32),clock)
        self.assertEqual(clock.now,0)
    def test_ended_native_not_restarted(self):
        clock=Clock()
        with self.assertRaises(RuntimeError): self.run_wait(Receipt(clock,0,complete=True),clock)
        self.assertEqual(clock.now,0)
if __name__=='__main__': unittest.main()
