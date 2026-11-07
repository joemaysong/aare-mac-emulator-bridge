import unittest
from invitation_evidence import idle_wait_expired

class InvitationEvidenceTests(unittest.TestCase):
    log = ('wireless: <- WifiVersionRequest\nwireless: -> WifiVersionResponse\n'
           'WPP_IDLE_INVITATION_TIMEOUT\n')
    native = {'events': [{'event': 'rfcomm_open', 'status': 0}]}

    def test_pending_open_is_not_idle(self):
        self.assertFalse(idle_wait_expired(self.log, {'events': [
            {'event': 'rfcomm_requested', 'status': 0}]}, {}))

    def test_failed_open_is_not_idle(self):
        self.assertFalse(idle_wait_expired(self.log, {'events': [
            {'event': 'rfcomm_open', 'status': 1}]}, {}))

    def test_version_exchange_required(self):
        for missing in ('wireless: <- WifiVersionRequest', 'wireless: -> WifiVersionResponse'):
            self.assertFalse(idle_wait_expired(self.log.replace(missing, ''), self.native, {}))

    def test_true_idle_wait(self):
        self.assertTrue(idle_wait_expired(self.log, self.native, {}))

    def test_started_projection_not_idle(self):
        for marker in ('wireless: <- WifiStartRequest', 'WPP_CREDENTIALS_PARSED'):
            self.assertFalse(idle_wait_expired(self.log + marker, self.native, {}))
        for key in ('wifi_join_verified', 'tcp_pair_connected'):
            self.assertFalse(idle_wait_expired(self.log, self.native, {key: True}))

if __name__ == '__main__':
    unittest.main()
