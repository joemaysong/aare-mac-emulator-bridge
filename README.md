# AARE Mac Emulator Bridge

Run an **Android 15 emulator + AARE** on an Apple Silicon Mac, validate local video, audio and touch, and build a separate experimental Mac Bluetooth/Wi-Fi projection bridge.

**AARE was created by [prototux](https://github.com/prototux); the original project is [prototux/AARE](https://github.com/prototux/AARE).** AARE provides the Android Auto protocol implementation, Android app and desktop receiver. This repository adds Mac reproduction scripts, an emulator encoder compatibility patch and transport integration. Upstream uses GPL-3.0; see [NOTICE.md](NOTICE.md) and [LICENSE](LICENSE) for attribution, licensing and modification boundaries.

> **The Mac local environment can be rebuilt and tested; actual Mac-to-EV6 wireless projection has not been verified successfully.** Passing simulated tests does not establish vehicle acceptance of certificates, phone roles or AAP. This repository contains no vehicle flashing, vehicle APK installation, forced AP startup, vehicle-control APIs or head-unit patches.

## What is included

- SHA-256-locked download and build recipes for official AARE v1.1.1 and a pinned source commit.
- Scripts to create, start, install into and stop the dedicated `AARE_Mac_API35` AVD. Every ADB command explicitly targets `emulator-5580`.
- A small compatibility patch that re-registers the callback after `MediaCodec.reset()`. It changes only `classes4.dex` in the official APK and uses a locally generated test signature.
- Rebuildable Mac receivers based on the official desktop release, optional audio statistics, and source for a synthetic-tone/touch probe app.
- A local opaque AAP relay and a separate Mac RFCOMM → WPP → CoreWLAN → TCP → emulator AAP bridge.
- A journal written before Wi-Fi changes, cancellation/timeout/disconnect cleanup, crash recovery and tests.
- [AGENTS.md](AGENTS.md) and a [step-by-step runbook](docs/AGENT_RUNBOOK.md) for other Codex instances or agents.

SDKs/JDKs, AVD disk images, release APKs, third-party jars, private TLS/signing keys, personal accounts, Wi-Fi passwords, vehicle identifiers and raw experimental recordings are excluded. Explicit steps fetch or generate local artifacts, which are covered by `.gitignore`.

## Validation status

| Item | Status |
|---|---|
| Mac AARE Desktop video in the original lab | Visible 1280×720 H.264; actual frame rate not measured |
| Taps and manual drag/scroll | Passed in the original lab; an automation tool sometimes omitted MOVE events |
| Audio | Original lab received 48 kHz stereo PCM; the user confirmed the synthetic two-tone sound was audible |
| Phone screen and Google Maps tiles | Passed in the original lab; not navigation or location validation |
| YouTube bundled with the old image | Too old; service errors; playback did not pass |
| New Mac supervisor, real JVM WPP, native IPC and fake radio | Local integration tests passed |
| Rebuild and tests of this portable export | See the [validation record](docs/VALIDATION.md) |
| Real-car WPP and association attempt | Wi-Fi information received; association/TCP not verified; tool reported restoration. See [latest progress](docs/WIRELESS_PROGRESS.md). |
| EV6 certificate/AAP acceptance and actual vehicle video/audio/touch | **Not verified** |

Reference platform: Apple Silicon Mac, macOS 26.7, 16 GB RAM; Android API 35 `google_apis;arm64-v8a`, 2 GB guest RAM and 2 cores. Intel Macs, other Android images, other head units and long-session stability have not been validated. Original lab results are scoped manual observations, not a guarantee that every clone reproduces them automatically.

## Start from a fresh checkout

Install Xcode Command Line Tools, a full JDK 17 including `javac` and `jpackage`, Python 3.10+, the official Android SDK command-line tools and `ffmpeg`. Follow the [complete setup guide](docs/SETUP.md), including normal user review of SDK license terms.

```sh
git clone https://github.com/joemaysong/aare-mac-emulator-bridge.git
cd aare-mac-emulator-bridge

# Point to your full JDK installation, not a JRE.
export JAVA_HOME="/path/to/jdk/Contents/Home"
export ANDROID_SDK_ROOT="$HOME/Library/Android/sdk"
export PATH="$JAVA_HOME/bin:$ANDROID_SDK_ROOT/platform-tools:$PATH"

python3 scripts/repro.py doctor
python3 scripts/repro.py fetch
python3 scripts/repro.py prepare-core
python3 scripts/repro.py build-core
python3 scripts/patch_apk.py
python3 scripts/repro.py build-desktop
python3 scripts/build_probe.py                    # Optional synthetic-tone/touch APK
python3 scripts/repro.py create-avd               # Refuses to overwrite an existing AVD
python3 scripts/lab.py start --prepare-only       # Boot Android; do not open a receiver
python3 scripts/lab.py install                    # Only the verified emulator-5580 AVD
python3 scripts/lab.py install --probe            # Optional
```

On the first `prepare-only` run, the dedicated AVD is started. If AARE is not installed, the script asks you to install it and does not open a receiver. After installation, run `python3 scripts/lab.py prepare` to open AARE.

Inside the emulator, follow the [UI setup and permission steps](docs/SETUP.md#aare-ui-settings) to enable the head-unit server, Phone screen, Accessibility and, when needed, Entire screen capture. These are user-visible grants; scripts do not silently approve them.

```sh
python3 scripts/lab.py start       # Open the direct receiver using ADB forward 55277
python3 scripts/lab.py stop        # Stop only this checkout's receivers and dedicated AVD
```

Upstream release: [`v1.1.1`](https://github.com/prototux/AARE/releases/tag/v1.1.1). Source commit: [`e8da04dc422abd36be60a81bb9fc7f782e8d7e84`](https://github.com/prototux/AARE/tree/e8da04dc422abd36be60a81bb9fc7f782e8d7e84). Do not silently substitute `latest`. SDK package IDs are pinned, but Google may update image revisions. Creation records `package.xml`; **this does not promise a byte-identical copy of the original lab's system image**.

## Tests without a vehicle

```sh
zsh bridge/wireless-session/build.command
zsh bridge/wireless-session/test.command
python3 scripts/audit_public.py
```

These steps do not use vehicle ADB or initiate real Bluetooth/Wi-Fi connections. Tests cover the Swift restoration policy, private IPC, real JVM WPP and binary relay; the radio is a fake.

For a manual Desktop-through-relay test, close any running receiver and execute `python3 scripts/lab.py relay`. Only one receiver can consume AARE's projection connection at a time. `Parked` in the fake Mac receiver is a desktop simulation state, not a vehicle restriction bypass.

## Future real-car test entry point

Read the [architecture](docs/ARCHITECTURE.md) and [recovery procedure](docs/RECOVERY.md) first. Without separate authorization for the current real-car test, run only:

```sh
./bridge/wireless-session/start-wireless.command   # Defaults to --check only
```

For a later authorized test, confirm the vehicle is parked, power is stable and interruption of existing projection is acceptable. The user must explicitly select an already-paired vehicle:

```sh
./bridge/wireless-session/start-wireless.command \
  --connect --device AA-BB-CC-DD-EE-FF --seconds 300
```

The address above is a placeholder. If a particular device does not answer a fresh SDP query, the verified diagnostic workflow may use `--cached-service-diagnostic`. A cache is not fresh SDP validation; real WPP must still succeed. The tool does not start the car AP or modify the head unit. If the car does not send StartRequest/credentials, the Mac must wait or clean up, never fabricate success.

In a run report, `tcp_pair_connected` means only that both sockets connected. `aap_tls_accepted` and `projection_verified` require independent evidence. A successful handshake or nonzero byte count is not proof of projection.

## Documentation

- [SETUP: dependencies, full rebuild and GUI permissions](docs/SETUP.md)
- [ARCHITECTURE: components, data flow and responsibility boundaries](docs/ARCHITECTURE.md)
- [VALIDATION: tested/untested behavior, commands and results](docs/VALIDATION.md)
- [RECOVERY: cancellation, Wi-Fi restoration, rollback and removal](docs/RECOVERY.md)
- [AGENT_RUNBOOK: phased reproduction and handoff instructions](docs/AGENT_RUNBOOK.md)
- [NOTICE: original authors, licensing and modification scope](NOTICE.md)
