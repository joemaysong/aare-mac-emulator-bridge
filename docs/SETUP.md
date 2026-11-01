# Complete setup and rebuild

The default endpoint of this procedure is **local Android + AARE Desktop projection on a Mac**. No vehicle is required. Run commands from the repository root. Paths may contain spaces; keep the quotes shown below.

## 1. Host requirements

- Apple Silicon Mac. The reference host was macOS 26.7 with 16 GB RAM. Other macOS versions and Intel Macs are unverified.
- About 20 GB of free disk space for the SDK, Android image, AVD, JDK, Gradle cache and app-images. This is not the source repository's size.
- Python 3.10+, Git and Xcode Command Line Tools/Xcode, including `xcrun swiftc` and `codesign`.
- Full JDK 17, including `java`, `javac`, `jar`, `keytool` and `jpackage`. The reference environment used Eclipse Temurin 17.0.21+9. A JRE is insufficient. JDK 21 has not been used as this export's tested baseline.
- [Official Android SDK command-line tools](https://developer.android.com/tools), installed and licensed by the user.
- `ffmpeg` for desktop H.264 decoding. Use a macOS distribution listed by the official project or Homebrew's `ffmpeg`; do not place an untrusted executable on PATH.

Typical prerequisite checks follow. Software installation, license terms and OS dialogs remain user-controlled:

```sh
xcode-select --install
# After installing an official Eclipse Temurin/OpenJDK 17 distribution:
export JAVA_HOME="$(/usr/libexec/java_home -v 17)"
export ANDROID_SDK_ROOT="$HOME/Library/Android/sdk"
export PATH="$JAVA_HOME/bin:$ANDROID_SDK_ROOT/platform-tools:$ANDROID_SDK_ROOT/cmdline-tools/latest/bin:$PATH"
java -version
javac -version
jpackage --version
ffmpeg -version
```

For a JDK extracted to a custom location rather than registered with macOS, set its `Contents/Home` directly. Do not copy the original author's workstation paths. Homebrew is optional; agents should not install it automatically just for this repository when another official installation method is available.

## 2. Android SDK packages

Install the official command-line tools under the SDK's `cmdline-tools/latest/` directory. Review and handle SDK license agreements normally:

```sh
sdkmanager --sdk_root="$ANDROID_SDK_ROOT" --licenses
sdkmanager --sdk_root="$ANDROID_SDK_ROOT" \
  'platform-tools' 'emulator' 'platforms;android-35' 'build-tools;35.0.0' \
  'system-images;android-35;google_apis;arm64-v8a'
```

Do not use `yes | sdkmanager --licenses` to treat legal terms as routine prompts. New SDK versions may recommend Android CLI instead; the sdkmanager compatibility entry point above still worked during rebuild validation. If it is removed later, update and validate the documented workflow separately.

Use the **Google APIs** image, not **Google Play**. Do not download an additional API 36/Play image. A fixed package ID does not make its revision immutable: `create-avd` records the installed image's `package.xml` at `build/installed-system-image-package.xml`. Reference versions were emulator 37.2.13 and platform-tools 37.0.1; later official releases have not all been validated.

```sh
python3 scripts/repro.py doctor
```

Expected results: Apple Silicon, a valid full JAVA_HOME, all required SDK files and ffmpeg available. Doctor does not download, invoke ADB or change radios.

## 3. Fetch pinned upstream dependencies

```sh
python3 scripts/repro.py fetch
```

This downloads only the official AARE APK, desktop release and source archive, plus Maven Central smali dependencies listed in `dependencies.lock.json`. Every artifact is SHA-256-verified; a digest mismatch stops the process. This command does not download Android images, Google Maps, YouTube, other APKs or a JDK.

To reuse an existing cache, pass `fetch --from-cache /path/to/cache`. Only manifest-listed files with matching hashes are copied, never an entire directory. Downloads are stored in ignored `.cache/downloads` and must not be committed.

## 4. Rebuild the JVM protocol core

```sh
python3 scripts/repro.py prepare-core
python3 scripts/repro.py build-core
```

Source is pinned to AARE commit `e8da04dc422abd36be60a81bb9fc7f782e8d7e84`. `prepare-core` generates a Gradle project containing only `aap` under `bridge/core`, excludes Android/headunit modules and Google's Gradle repository, and uses Maven Central and the plugin portal. It does not modify `.cache/upstream`.

The added `:aap:writeMacClasspath` task generates a JVM classpath for this checkout. It contains absolute paths, so rerun it after moving the directory or changing machines. Do not distribute an old generated classpath as a portable artifact. Builds use `--no-configuration-cache` because this task captures Gradle objects that otherwise fail configuration-cache serialization.

The first Gradle build downloads pinned Gradle/Maven dependencies. With the correct dependencies already cached, use `build-core --offline`. Missing first-run offline dependencies are a prerequisite issue, not proof of a source defect. Upstream `aap` tests also run in this step.

## 5. Generate the emulator-compatible APK

```sh
python3 scripts/patch_apk.py
```

In the original AVD, official 1.1.1 encountered a `c2.android.avc.encoder` format-option rejection and used its fallback path. `MediaCodec.reset()` cleared the asynchronous callback, resulting in no video. The patch only re-registers `Callback` and the encoder handler after reset; see the [source-equivalent patch](../patches/VideoEncoder.compat.patch).

The executable recipe:

1. Verifies the official APK's SHA-256.
2. Extracts `classes4.dex` and disassembles it with pinned smali 2.5.2 tools.
3. Checks that the unique reset invocation and register layout match the pinned release; otherwise it stops.
4. Adds callback registration only in `VideoEncoder.smali` and reassembles the DEX.
5. Verifies all other ZIP content is unchanged, except old signature metadata.
6. Runs zipalign, signs with a new local test key at `.cache/signing/emulator-debug.jks`, and verifies the signature.

Outputs are `build/apk-patch/aare-emulator.apk` and `verification.json`. **Different machines generate different signatures/APK hashes, so a single global patched APK hash is not an appropriate pass/fail check.** The official input, patch shape and unchanged content are the fixed verification points. This is neither the author's official signature nor a vehicle firmware patch.

The script refuses to overwrite an existing work directory. Before rebuilding, inspect and move your generated `build/apk-patch` aside under a different name. Do not replace this with deletion of the entire repository.

## 6. Build desktop receivers and the optional probe app

```sh
python3 scripts/repro.py build-desktop
python3 scripts/build_probe.py
```

The desktop build uses jars from the official AARE headunit release, adds an audio-statistics overlay with the same playback interface, and uses `jpackage` to generate two app-images on the current machine:

- `bridge/emulator-lab/apps/AARE Desktop.app`: direct connection to 127.0.0.1:55277.
- `bridge/emulator-lab/apps/AARE Bridge Desktop.app`: connection through the local relay on 55278.

Each app contains its own Java runtime. Do not redistribute the original lab machine's app wrapper with external SDK symlinks. Both generated apps receive a local ad-hoc code signature.

The optional `build/probe/AARE-Lab.apk` contains a touch counter and a quiet 3-second synthetic tone: 48 kHz PCM16, 440 Hz followed by 660 Hz. It has no recording or network permissions and does not play automatically. Its Android manifest/source and D8/aapt2/apksigner recipe are included in this repository.

## 7. Create and install into the dedicated AVD

```sh
python3 scripts/repro.py create-avd
python3 scripts/lab.py start --prepare-only
python3 scripts/lab.py install
python3 scripts/lab.py install --probe
python3 scripts/lab.py prepare
```

Configuration: `AARE_Mac_API35`, API 35 ARM64, 2048 MB RAM, 2 cores, 720×1280 at 240 dpi, host GPU. It uses port 5580 and therefore `emulator-5580`. Creation refuses to overwrite an existing AVD with this name. Do not use `--force` to erase the user's existing AVD.

If `adb install -r` fails because official and local signatures differ, preserve necessary data and obtain the user's agreement before uninstalling `net.prototux.aare` from **only the dedicated emulator**, then installing the local APK. Do not retry on another ADB device or copy signing keys into the public repository.

## AARE UI settings

In AARE 1.1.1 inside the dedicated emulator, verify:

1. Advanced: enable the head-unit server at `localabstract:aare_hu`; LAN accept is unnecessary.
2. Advanced: enable Phone screen on server.
3. Car screen: enable Phone screen.
4. Android Accessibility: have the user enable AARE's MirrorTouchService so mirrored touches can be delivered.
5. Car audio: for emulator audio projection, open Screen-capture permission, approve the required emulator recording/media-capture grants, and select **Entire screen**, not an individual app.
6. Open the receiver after capture consent. Leave and re-enter Phone screen to use the new token. A token from before boot, a token left unused too long, or an expired token does not prove active capture permission.

```sh
python3 scripts/lab.py start
```

The desktop receiver is a fake head unit. In a parked local test, select `Parked` to display the restricted Phone screen. This is only a Mac simulation option and must not be applied to a real car.

If an initial certificate prompt appears, first verify that it is between your own emulator and local headunit, then follow AARE's normal trust workflow. Do not bypass TLS checks or import untrusted production keys. This repository does not supply official Google AA private keys.

## 8. Video, audio and touch acceptance

Read [VALIDATION.md](VALIDATION.md). Confirm visible video manually, operate a setting through the projection and verify the emulator actually changes, check scrolling with a manual drag, and play the synthetic tone in AARE Lab. Confirm audible Mac output and increasing received/played byte counts in audio-stats.

Do not record PASS merely because a click tool reports success. The original automation sometimes sent DOWN/UP without MOVE, requiring manual drag verification.

For a local relay test, close the direct receiver, run `python3 scripts/lab.py relay`, and repeat these checks. `lab.py stop` stops only this checkout's receivers and the verified dedicated AVD, not other Java processes, the ADB server or a vehicle.

## 9. Maps and YouTube boundaries

The original Google APIs image included full Maps/YouTube APKs but only a stub of the official Google AA sender. AARE is a separate sender, and Mac Desktop is the receiver; these are not one app inside the emulator.

In the original experiment, Maps 11.129.0103 loaded map tiles and could be mirrored; routes, GPS and navigation voice were not verified. YouTube 19.17.42 was too old, requested an update and returned search 400; video playback did not pass. The image's test signing identity may also prevent a direct update with Google's official APK.

This repository does not download map/video apps, provide APK sources for them, or create a second Google Play AVD. If a newer image bundles different versions, record and revalidate them instead of inheriting the original results.
