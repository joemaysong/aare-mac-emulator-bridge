import unittest
from unittest.mock import patch
from pairing_watch import readiness
from standby_session import serve
class PairingTests(unittest.TestCase):
 target='01:11:22:33:44:55'
 def report(self,**extra):return {'events':[dict(event='pairing_state',uptime=100.,target=self.target.lower().replace(':','-'),powered=True,paired=True,**extra)]}
 def test_ready(self):self.assertEqual(readiness(self.report(),self.target,101),'ready')
 def test_wait_states(self):
  d=self.report();d['events'][0]['paired']=False;self.assertEqual(readiness(d,self.target,101),'waiting_pairing')
  d['events'][0]['powered']=False;self.assertEqual(readiness(d,self.target,101),'waiting_bluetooth')
 def test_stale_and_foreign(self):
  self.assertEqual(readiness(self.report(),self.target,110),'unknown')
  self.assertEqual(readiness(self.report(),'00-00-00-00-00-00',101),'unknown')
 def test_unknown(self):
  self.assertEqual(readiness({},self.target,100),'unknown')
  d=self.report();d['events'][0]['paired']=1;self.assertEqual(readiness(d,self.target,101),'unknown')
 def test_wait_has_no_subprocess_or_retry(self):
  class Stop:
   def is_set(self):return False
   def wait(self,n):return True
  class Watch:
   def state(self):return 'waiting_pairing'
  with patch('standby_session.subprocess.run') as run,patch('standby_session.subprocess.Popen') as child:
   self.assertEqual(serve(None,None,Stop(),Watch()),0);run.assert_not_called();child.assert_not_called()
if __name__=='__main__':unittest.main()
