# Instructions for Codex and other agents

Read README.md, docs/AGENT_RUNBOOK.md and docs/VALIDATION.md before acting.

- This is an integration project built on **prototux/AARE**, GPL-3.0. Preserve upstream credit, LICENSE, dependency pins and patch provenance.
- Default scope is **Mac only**. Do not access, install on, restart, pair, or change a vehicle unless the current user explicitly authorizes that separate test.
- Every ADB command must use `-s emulator-5580`; verify `emu avd name` is `AARE_Mac_API35` before mutation. Never use a default ADB target or `adb kill-server`.
- Never kill arbitrary Java/emulator processes. Only stop processes owned by this checkout, whose PID and command have both been verified.
- `--check`, build and simulated tests do not need a vehicle. Do not turn a build task into a real Bluetooth/Wi-Fi test.
- Runtime folders, credentials, generated APK signing keys, AVD images, TLS private keys and diagnostic captures are local artifacts. Never stage or upload them.
- Keep the upstream release APK intact and hash-verified. The emulator callback patch is local, creates a different signature, and is not a firmware patch.
- Network access/downloads happen only in explicit fetch/build/install steps. Do not silently add Google Play images or update YouTube/Maps.
- Do not auto-accept SDK license agreements, suppress macOS permission prompts, weaken TLS, extract third-party production keys, or bypass parked/driving restrictions.
- Run the portable audit and appropriate tests before committing. Source pins changing requires a separate reviewed update and revalidation; never silently use `latest`.
- Do not call a fake-radio or byte-relay test a successful EV6 projection. See the validation matrix for what was actually observed.
- A Wi-Fi recovery journal is an outstanding restore obligation. Do not delete it to make checks pass or start a competing session; retain the native radio lock.
