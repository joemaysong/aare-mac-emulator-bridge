# Public source and private runtime data

This repository intentionally contains no authentication tokens, personal API keys, Wi-Fi passwords, pairing databases, vehicle originals, actual vehicle network addresses, TLS private keys, APK signing keys/certificates, AVDs, raw microphone recordings or media captures.

Only source code, documentation, example identifiers and dependency/source SHA-256 values belong in Git. A SHA-256 checksum is public integrity metadata, not an authentication key. Credentials such as `never-log-this-secret` in the simulated tests are invented fixtures.

The local debug keystore is generated separately for each checkout under ignored `.cache/signing/`; the example `android` password applies only to that newly generated test key. Do not reuse it as a production signing identity or upload the key. AARE's runtime TLS material is also local; do not copy it into this repository or an issue report.

The wireless coordinator sends real AP credentials only through user-owned private UNIX sockets; normal reports omit payloads and sensitive exception text. The password-free Wi-Fi restore journal still contains private network identifiers and must remain local. Do not attach it publicly without deliberate redaction.

Before every publication:

```sh
git status --short
git add <reviewed-source-paths>
python3 scripts/audit_public.py
git diff --cached --stat
```

The audit examines the candidate source set, rejects generated/binary/key/capture paths, common credential patterns, workstation paths and non-example MAC identifiers, and detects disagreement between the index and working tree. It also verifies that representative private runtime paths are ignored. Pattern checks are one layer; review the actual proposed content as well.

If a private object is accidentally published, removing it in a later commit does not remove Git history or copies. Stop further publication, identify the exact object and destination, revoke/rotate the affected credential if necessary, and coordinate cleanup with the owner. Do not expose the value again in issue descriptions or logs.
