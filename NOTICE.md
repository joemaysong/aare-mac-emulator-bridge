# Attribution and scope

**AARE was created by [prototux](https://github.com/prototux) and the [AARE contributors](https://github.com/prototux/AARE/graphs/contributors).**

- Original project: <https://github.com/prototux/AARE>
- Original release used here: [v1.1.1](https://github.com/prototux/AARE/releases/tag/v1.1.1)
- Protocol/source baseline: [`e8da04dc422abd36be60a81bb9fc7f782e8d7e84`](https://github.com/prototux/AARE/tree/e8da04dc422abd36be60a81bb9fc7f782e8d7e84)
- Upstream license: **GNU GPL version 3**, reproduced in [LICENSE](LICENSE).

This repository provides Mac emulator setup/reproduction scripts, a small emulator encoder compatibility patch, local audio diagnostics, and experimental native Mac Bluetooth/Wi-Fi/AAP transport integration. It does not claim authorship of AARE's Android Auto implementation, Android app, desktop head unit, protocol definitions or original upstream tests.

The original AARE release artifacts are fetched from the author's release and verified by SHA-256. Generated APKs, the SDK/JDK, third-party jars and source archives are not committed. The complete upstream source for that pinned revision remains obtainable using the included fetch recipe. The source-equivalent encoder modification and the executable smali transformation are included here; protocol logic is consumed from upstream rather than rewritten or attributed to this repository.

The diagnostic `AudioOutputs` replacement is a local compatible implementation of the upstream desktop interface. The native transport/relay and reproduction scripts are additions by the aare-mac-emulator-bridge contributors. New repository code is distributed under GPL-3.0-only; preserve the upstream project's original notices and license when fetching, modifying or redistributing it.

Other dependencies retain their own licenses: Android SDK/Google APIs system images are distributed under Google's applicable terms; Eclipse Temurin/OpenJDK, Kotlin, protobuf, Gradle, smali and their dependencies retain upstream licensing. Their URLs and hashes are recorded in `dependencies.lock.json`; they are not relicensed by this repository. Android system images, Google Maps and YouTube are not redistributed here.

This is a community experiment, not an official Google, Apple, Kia, Hyundai or AARE product. AARE's upstream capabilities and upstream vehicle testing must not be confused with this repository's **not yet verified** Mac-to-EV6 wireless projection.
