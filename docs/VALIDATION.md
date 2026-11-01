# Validation record and reproducible checks

Date: 2026-11-01. The following separates historical manual observations from tests rerun from this portable source export. Paths and machine/vehicle identifiers from the original private workspace are deliberately omitted.

## Portable export build validation

| Check | Result | What it establishes |
|---|---|---|
| Hash-verified pinned upstream source extraction | PASS | Uses the declared AARE commit/archive, not a modified private research checkout |
| Generated JVM-only core build | PASS | New checkout-relative classpath and classes rebuilt successfully |
| Upstream aap JUnit tests | 20 tests,0 failures/errors | Protocol unit tests only |
| Official v1.1.1 APK transformation | PASS | Original hash verified; only classes4.dex content changes; other content checked; new local APK signature verified |
| Standard SDK build of optional probe APK | PASS | `javac` → D8 → aapt2 → zipalign → apksigner, without private research jars |
| Two desktop app-images | PASS | Generated via jpackage from official headunit release; local code signatures verified |
| Native Mac wireless app + Java WPP adapter | PASS | Rebuilt from the portable source structure with configured JAVA_HOME |
| Python transport/native IPC/supervisor tests | 22 tests,0 failures | Includes real JVM WPP and real Swift IPC with a fake radio |
| Swift Wi-Fi lease checks | 28 assertions passing | Multiple simulated restore/cancel/error scenarios;28 is an assertion count, not28 distinct cases |
| Public-candidate audit | Required before commit | Checks the actual nonignored/tracked source set for private artifacts, workstation paths, token/private-key patterns and non-example network addresses |

The first probe build revealed that the original setup had build-tools but not `platforms;android-35`. The declared SDK platform was then installed and the new standard build recipe succeeded. This dependency is now explicitly checked and documented. No additional Android system image was downloaded for this export validation.

No fresh AVD was created, no new APK was installed, no GUI media acceptance was repeated, and no real car or radio association was invoked during publication/rebuild validation. The existing user's AVD and car-side work remain untouched. A successful build is not a fresh full-system reproduction or a new vehicle acceptance result.

## Historical manual observations from the original lab

- Android15 ARM64 Google APIs image; dedicated2GB/2core AVD.
- Visible1280×720 H.264 video through AARE Desktop; configured30fps, actual fps/latency not benchmarked.
- Projection taps changed Android UI. Manual drag scrolled; the automation tool itself sometimes omitted MOVE events, so synthetic drag alone was not used as proof.
- 48kHz stereo PCM received and submitted to Java SourceDataLine. The user heard the quiet440Hz→660Hz three-second synthetic tone, both direct and through the local relay.
- Closing/reopening Desktop restored the projection. Bounded relay EOF and cancellation cleanup were observed.
- Phone screen mirrored Android UI; Maps tiles loaded. This was not GPS/routing/navigation-voice validation.
- Preinstalled old YouTube requested an update / search returned400; playback did not pass. No alternate Google Play AVD was completed.

Those results justify the starting lab recipe but are not automatically inherited by every clone or newer SDK image revision. The portable app-images use a newly generated standard jpackage runtime and the emulator uses the official SDK launcher, so their fresh GUI behavior must still be observed on each host.

## What the automated integration test actually does

The full supervisor test launches the real Java WPP adapter, a compiled Swift native control fixture and the real Python coordinator. Bluetooth packets and Wi-Fi are test fixtures. It exchanges valid WPP version/start/info/status messages, verifies JOIN/READY ordering, forwards opaque binary data both ways, ends the link, receives the native restore receipt and checks socket/journal cleanup. It does not exercise macOS CoreWLAN or a physical car.

Other checks include invalid credentials/framing, BSSID shape, subnet mismatch, duplicate JOIN/READY, refusing READY before verified JOIN, TCP failure before touching the emulator connection, cancellation while idle/backpressured, large exact binary duplex transfer, half-close, native peer EOF and stale-journal recovery.

```sh
export JAVA_HOME="/path/to/full/jdk/Contents/Home"
python3 scripts/repro.py build-core --offline   # only after dependencies are already cached
zsh bridge/wireless-session/build.command
zsh bridge/wireless-session/test.command
python3 scripts/audit_public.py
```

## Human acceptance checklist on a new Mac

Record actual SDK image revision, emulator/tools/JDK versions, patched-input/output hashes and fresh settings. Mark each result PASS/FAIL/NOT_RUN with supporting observation:

| Stage | Minimum evidence |
|---|---|
| Android boot | Named AVD booted on emulator-5580 |
| AARE APK | Installed package/version and source/signature provenance |
| Desktop video | Human-visible changing frames, not just bytes or an encoder log |
| Tap | Receiver action reflected in Android UI |
| Drag | Actual scrolling with MOVE events or manual observation |
| Audio | PCM stats plus human audible output confirmation |
| Reconnect | Close/reopen gives visible projection again |
| Local relay | Same checks with one receiver through55278 |
| Cold restart | Repeat grants and media checks after a full AVD shutdown |

Do not upload raw private logs/captures as evidence. Summaries, sanitized metadata and synthetic test results are sufficient for the public record.

## Still NOT_RUN / not accepted

- Real CoreWLAN scan/associate/DHCP/restoration through the new live coordinator.
- First-use macOS TCC permission prompts and actual AP coexistence with USB Internet.
- Full Mac-to-EV6 WPP/Wi-Fi/TCP/AAP acceptance and certificate compatibility.
- Actual EV6 video/audio/input, HFP/phone-role requirements and clean real-car handoff.
- Long-run stability, measured fps, latency, multipoint touch, microphone/calls and navigation.
- A reproducible exact byte-identical SDK system image; package revisions are external.

The latest controlled attempt progressed beyond version exchange to a Wi-Fi
information response. Mac association and vehicle TCP/AAP were not verified;
tool-side restoration was reported complete while head-unit cleanup remained
unresolved. See [the sanitized experiment and diagnostic changes](WIRELESS_PROGRESS.md).
No head-unit firmware or deployment artifacts are included here.
