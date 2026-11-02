# Reproduction runbook for Codex and other agents

The target is a reproducible **Mac emulator + AARE lab**, followed by an explicitly gated experimental vehicle transport. Read [AGENTS.md](../AGENTS.md), [SETUP.md](SETUP.md), [ARCHITECTURE.md](ARCHITECTURE.md) and [VALIDATION.md](VALIDATION.md). Preserve attribution to **prototux/AARE** and its pinned GPL-3.0 source/release.

## Phase A — Inventory; no mutation

1. Confirm Apple Silicon, macOS, Python, Xcode tools, full JDK17, Android SDK and ffmpeg.
2. Run `python3 scripts/repro.py doctor`. Do not launch radios or contact a car to resolve a missing build dependency.
3. Confirm disk headroom, existing AVD names and whether emulator port5580 is already occupied. Never overwrite an existing AVD.
4. Explain which steps download dependencies and which require normal user-visible OS/Android grants. Do not auto-accept license terms.

Record actual versions; baseline package IDs and reference versions are in `dependencies.lock.json`. A newer SDK image revision is a changed environment, not automatically a failure or automatically equivalent.

## Phase B — Fetch and build independently

Use a fresh checkout and its own generated folders, not hard-coded paths into the original author's research directory.

```sh
python3 scripts/repro.py fetch
python3 scripts/repro.py prepare-core
python3 scripts/repro.py build-core
python3 scripts/patch_apk.py
python3 scripts/repro.py build-desktop
python3 scripts/build_probe.py
zsh bridge/wireless-session/build.command
zsh bridge/wireless-session/test.command
```

Expected artifacts: JVM classpath/protocol classes,20 upstream aap tests passing, one local-signed emulator APK with only classes4.dex content changed, two local desktop app-images, optional probe APK, separate native wireless app and simulated transport tests passing. Do not compare a regenerated debug-signed APK's whole-file hash with someone else's; compare the official input, transformation and unchanged content.

If a generated work directory exists, inspect it and move it aside explicitly instead of wiping arbitrary folders. If a dependency is missing offline, report that prerequisite; do not silently switch versions.

## Phase C — Dedicated Android environment

Create `AARE_Mac_API35` only when absent. Start it on5580. Before **every ADB mutation**, use explicit `-s emulator-5580` and verify AVD name. Install only this project’s lab APK/probe there.

Follow the human-readable UI setup in SETUP.md. Normal permission dialogs require user participation/approval; do not alter secure settings behind the UI to manufacture consent.

AARE and Android are different layers: the Android emulator runs Android apps; AARE provides AAP/Phone screen; Desktop is the receiver. A Maps tile rendering is not a navigation success. The baseline YouTube is known not to play; do not spend the user's bandwidth adding another Google Play image without being asked.

## Phase D — Human-observed local acceptance

1. Confirm visible changing video in the Desktop receiver.
2. Tap a known control in the projection and confirm the Android state actually changes.
3. Ask for a manual drag if automation only sends DOWN/UP. Verify scroll movement.
4. With the normal screen/audio capture consent, play the synthetic test tone and inspect bounded audio stats. A human should confirm the Mac speaker output.
5. Close/reopen Desktop; repeat through the local opaque relay on55278. Only one receiver can consume the phone-side AAP server.
6. Log what was observed, exact versions and limitations. Do not collect microphone audio, personal accounts or real vehicle data for this phase.

## Phase E — Prepare wireless, still no vehicle contact

Run `start-wireless.command` without arguments. It only checks build paths, competing receiver and pending recovery journal. No `--connect` is implied by a request to build/test locally.

The Mac transport is compiled and covered with fake-radio + actual JVM/native IPC integration. Real CoreWLAN association, OS permissions, vehicle AAP acceptance and actual vehicle media remain a separate gate.

## Phase F — Only after fresh explicit real-car authorization

Confirm parked/stable power and permitted interruption of existing projection. Identify an already-paired target; no auto pairing. Obtain actual normal car-provided AP/start/credential messages. The explicit command is documented in README; use the user's real target, never an example address.

Keep Bluetooth/WPP held during Wi-Fi/AAP. Do not reinterpret `tcp_pair_connected` as successful AAP/TLS or video. The opaque relay intentionally cannot certify endpoint acceptance. Verify actual screen/audio/touch independently and preserve the precise boundary reached.

If the vehicle has an AP startup/controller problem, stop at that evidence. Do not upload a firmware patch, clear ownership files, forge success, force a restart or borrow a CarPlay ticket to make AA proceed. Car-side changes are a separate project and authorization.

## Phase G — Stop and restore

Use Ctrl-C/normal closure. Confirm final native receipt + Wi-Fi original state + absence of recovery obligation. If restore is incomplete, retain the journal and follow RECOVERY.md. Never delete a journal to pass preflight.

For handoff, report: phase reached, exact failing boundary, output paths, unresolved recovery, user-observed media status, and next action. Keep real network identifiers/credentials, keys, AVDs and recordings out of public commits. Use `python3 scripts/audit_public.py` before publishing.

## Suggested user prompt for another agent

> Read this repository's AGENTS.md and docs/AGENT_RUNBOOK.md. Rebuild the pinned Android+AARE Mac lab on this Apple Silicon Mac. Keep original AARE/prototux credit. Begin with doctor and dependency inventory, then rebuild and run simulated tests; use only AARE_Mac_API35 on emulator-5580. Verify local video, speaker audio and touch with me. Do not access or modify a vehicle, start wireless projection, add Google Play images, or publish logs/keys without a separate request. Report proven results separately from untested vehicle compatibility.

## Later optional experiments

Read [the 2026-11-02 checkpoint](SESSION_UPDATE_20261102.md) before running the
wireless supervisor or changing APKs/privileged overlays. The default encoder-only
APK supports local Desktop work; wireless identity preflight requires the separately
built identity APK. Never interrupt another session or overwrite its retained signer.
