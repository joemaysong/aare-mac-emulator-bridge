# Wireless vehicle experiment: 2026-11-01

Historical snapshot: see the [2026-11-02 checkpoint](SESSION_UPDATE_20261102.md)
for subsequent work. This is a sanitized observation report, not a successful
projection claim.
AARE and its upstream authors remain credited in the repository README and NOTICE.

## Boundary reached

The latest controlled attempt established RFCOMM, exchanged WPP versions, received
a start request and successfully parsed a Wi-Fi information response. The head unit
started its AP on demand. Mac association was not verified, so no vehicle TCP pair,
AAP/TLS acceptance or projected video/audio/touch was established.

The tool reported native cleanup complete, Wi-Fi restored, no recovery required
and removal of temporary IPC sockets. The internet default route remained on USB.
This does not prove successful simultaneous USB internet and car Wi-Fi association.
The independent head-unit controller remained in AA cleanup with AP still active.
Mac cleanup and head-unit cleanup are separate outcomes.

## Diagnostic improvement

Previously a native JOIN failure could appear only as a generic cancellation.
The coordinator now records failure_stage=wifi_join and a fixed failure_reason.
The native app records wifi_join_failed with a whitelisted category and numeric
system error code. It never serializes error descriptions, userInfo, SSID, BSSID
or credentials. Existing IPC replies and Wi-Fi recovery behavior remain unchanged.

Categories distinguish privacy, journal, cancellation, DHCP/identity, ownership,
credential shape, unavailable interface, missing network, unsupported security and
system Wi-Fi errors. A numeric error does not alone prove an incorrect password.
This diagnostic build is offline-tested; its next real association attempt is pending.

## Legacy failure-code mismatch

The adapter reports generic association failure as WPP status -11 (Wi-Fi network
unavailable). The inspected older receiver enum lacks that value, and the receiver
logged it as unsolicited. This is a concrete compatibility gap, but its causal
contribution to the stuck native cleanup has not been established independently.
No guessed status-code mapping, protocol-success fabrication or TLS change is included.

Next: obtain the sanitized association cause, confirm an appropriate legacy error
response, finish receiver-side cleanup separately, then retry association and TCP.
Only subsequent endpoint acceptance and visible media tests can establish projection.
No raw captures, identifiers, credentials, firmware or head-unit mutation tools are
included in this update.
