import unittest
from standby_session import clean, decision, serve
from unittest.mock import patch, Mock
from types import SimpleNamespace
from pathlib import Path
import tempfile
class StandbyTests(unittest.TestCase):
 def good(self):return dict(wifi_restored=True,native_complete=True,private_sockets_removed=True,relay_identity_staged=True,relay_identity_cleaned=True,reason='session_ended',tcp_pair_connected=True)
 def test_normal_end_waits(self):self.assertEqual(decision(self.good(),2),('standby',0))
 def test_each_cleanup_gate(self):
  for k in ('wifi_restored','native_complete','private_sockets_removed','relay_identity_cleaned'):
   r=self.good();r[k]=False;self.assertEqual(decision(r,0)[0],'recovery_required')
 def test_retry_limit(self):
  r=self.good();r['reason']='stopped';r['tcp_pair_connected']=False
  self.assertEqual(decision(r,0),('retry',1));self.assertEqual(decision(r,2),('cooldown',3))
 def test_invitation_wait_not_failure(self):
  r=self.good();r.update(reason='stopped',tcp_pair_connected=False,invitation_wait_expired=True)
  self.assertEqual(decision(r,2),('waiting_invitation',2))
  r['wifi_join_verified']=True;self.assertEqual(decision(r,2),('cooldown',3))
 def test_dirty_wait_stops(self):
  r=self.good();r.update(invitation_wait_expired=True,native_complete=False)
  self.assertEqual(decision(r,0)[0],'recovery_required')
 def test_cooldown_is_bounded(self):
  r=self.good();r.update(reason='stopped',tcp_pair_connected=False)
  self.assertEqual(decision(r,100),('cooldown',3))
 def test_cooldown_wait_is_interruptible(self):
  waits=[]
  class Stop:
   def is_set(self):return False
   def wait(self,n):waits.append(n);return n==120
  watcher=SimpleNamespace(state=lambda:'ready')
  child=Mock();child.poll.return_value=0
  with tempfile.TemporaryDirectory() as tmp, patch('standby_session.subprocess.run',return_value=SimpleNamespace(stdout='{"ready_for_explicit_connect":true}')), patch('standby_session.subprocess.Popen',return_value=child), patch('standby_session.decision',return_value=('cooldown',3)):
   self.assertEqual(serve(SimpleNamespace(device='00-11-22-33-44-55',cached_service_diagnostic=False),Path(tmp),Stop(),watcher),0)
  self.assertIn(120,waits)
 def test_missing_receipt(self):self.assertFalse(clean({}))
 def test_forward_failure(self):
  r=self.good();r['forward_cleanup_incomplete']=True;self.assertFalse(clean(r))
if __name__=='__main__':unittest.main()
