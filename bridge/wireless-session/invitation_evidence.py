"""Classify idle invitation waits only after an established protocol channel."""
def idle_wait_expired(protocol_log, native, report):
    opened = any(e.get('event') == 'rfcomm_open' and e.get('status') == 0
                 for e in native.get('events', []))
    return (opened
            and 'wireless: <- WifiVersionRequest' in protocol_log
            and 'wireless: -> WifiVersionResponse' in protocol_log
            and 'WPP_IDLE_INVITATION_TIMEOUT' in protocol_log
            and 'wireless: <- WifiStartRequest' not in protocol_log
            and 'WPP_CREDENTIALS_PARSED' not in protocol_log
            and not report.get('wifi_join_verified')
            and not report.get('tcp_pair_connected'))
