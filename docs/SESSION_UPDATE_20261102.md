# Mac emulator and wireless bridge update

Status: 2026-11-02 (Asia/Taipei). AARE remains based on prototux/AARE v1.1.1 at the
existing pinned commit. The following are separate experiments, not a new upstream
release or a claim of accepted EV6 projection. See [NOTICE](../NOTICE.md).

## Wireless bridge and identity

The supervisor now distinguishes vehicle TCP failure from emulator TCP failure,
records whether a vehicle socket was actually connected and retains the original
cleanup obligations. It also prepares a one-use, nonce/expiry-bound identity file
in the dedicated emulator using the actual Mac adapter reported by the native
session. The optional app helper consumes it only for wireless TCP sessions, binds
it to that session's Bluetooth channel, and sends the pairing identity request
once channels are running. Expired, invalid and multicast addresses are rejected.
No actual adapter or vehicle identifier is committed. New tests use only fixtures.

The installed AARE hash must equal the locally built identity-enabled artifact
before the supervisor opens radio work. The existing plain encoder-patched APK
therefore fails this wireless preflight; it remains usable for local Desktop tests.
The staging file is cleaned only for its matching owner even if readback fails.
A native report and identity file are private runtime material, never publication.

### Build the optional identity-enabled APK

Complete the pinned fetch and encoder-only APK build from SETUP first. Use the
same checkout-local signing key; do not regenerate it for an existing installation.

```sh
export JAVA_HOME="/path/to/full/jdk/Contents/Home"
export ANDROID_SDK_ROOT="/path/to/android-sdk"
python3 bridge/emulator-lab/relay-identity/build.py
```

Requires platforms;android-35, build-tools;35.0.0 and the declared smali jars.
The builder verifies the encoder-patched input and its official upstream hash,
runs the 17-check Java helper test, injects only CarSession, its Bluetooth response
listener and the authored helper, and compares canonical smali after DEX assembly.
Output is build/relay-identity/aare-relay.apk plus verification.json. The original
encoder fix remains. APK content outside classes4.dex/signing metadata is retained.
No install, emulator restart, Bluetooth or Wi-Fi action occurs in the builder.

This portable export uses the same local key as scripts/patch_apk.py. It is not
signed with the upstream author's key or the private original lab key. The helper
has no extra manifest permissions. An APK signature or matching hash is not proof
that an active privileged Magisk overlay will load the new code: verify the
installed path/hash and loaded generation after any separately authorized update.
The current verifier accepts the normal data-app base.apk layout only; a system
overlay path is rejected until its loading contract is separately verified. Do not
bypass that preflight to combine the two experiments.

At the recorded private candidate 69 checkpoint, its matching identity APK had
been built but not installed because another emulator session was active. The
vehicle package was also not deployed. End-to-end identity acceptance, stable
vehicle frames/touch and complete teardown remain unverified. The subsequent
portable build/test described here is not that missing vehicle acceptance.

## Optional privileged audio experiment

A separate local maintenance session installed official Magisk 31.1 in a copy of
the API 35 emulator ramdisk and preserved the original AVD and launcher. It did not
modify the shared SDK image or EV6. A local Magisk module installed the retained
encoder-fixed AARE 1.1.1 APK in system/priv-app and granted MODIFY_AUDIO_ROUTING and
CAPTURE_AUDIO_OUTPUT. After a cold start, AARE registered its audio policy and the
Mac received/played non-silent 48 kHz stereo PCM. This differs from MediaProjection
consent: Phone screen still needs fresh screen-capture permission after restart.

To recreate the module container only, with an independently checked package and
retained signing identity, run:

```sh
python3 scripts/build_privileged_module.py --apk /path/to/retained/aare.apk \
  --sha256 REPLACE_WITH_LOCALLY_VERIFIED_APK_SHA256
```

This builds build/privileged-module/aare-lab-magisk.zip; it does not root an AVD,
patch a ramdisk or install a module. Obtain Magisk 31.1 separately from
[topjohnwu/Magisk](https://github.com/topjohnwu/Magisk/releases/tag/v31.1), preserve
its license and use its own AVD patch workflow on a **copy** of this AVD's matching
ramdisk. Do not modify the shared SDK image. Stop the dedicated AVD and retain a
complete AVD directory, .ini, original ramdisk and launcher before any root change;
retain the current version separately throughout verification. Point only this
lab's launcher at that private copied ramdisk. Root provisioning is optional and
not part of the default portable setup or automated publication tests.

## YouTube and Maps checkpoint

The obsolete test-signed YouTube 19.17.42 from the image could not accept a normal
Google-signed update. The local maintenance experiment used a reversible module
with an empty system/product/app/YouTube/.replace entry to hide the image package,
then installed unmodified Google-signed YouTube 21.43.523. APK signature checking
and an independent digest listing matched. Neither that APK nor Google software,
accounts, downloaded archives or rooted images is redistributed here. The old
image was not modified. Verify your own source, signer and compatibility; this is
a dated observation rather than an automatic download/update instruction.

The completed maintenance record verified playback in the emulator, system audio
routed to Mac and privileged state after cold start. A later still-running Desktop
UI test observed YouTube search, scroll and video frames through **Phone screen**.
Maps tiles were visible, but its drag response was still under investigation at
this checkpoint. This publication does not close that active test or claim Maps
navigation, GPS, route guidance, fresh sound acceptance or complete UI validation.
AARE's ordinary YouTube media-browser entry is not the Android YouTube app surface;
use Phone screen. Google Maps is also mirrored; the navigation placeholder is not
proof that Maps is missing. Parked is the Desktop simulation's state only.

## Rollback and session coordination

- Keep local Desktop tests separate from the identity-enabled wireless experiment;
  do not replace its APK/overlay while a different session is using the AVD.
- To undo only privileged AARE, disable its module and reboot the dedicated AVD;
  retain the matching data-app APK and check which version loads afterward.
- To undo the YouTube replacement, uninstall the replacement first, then disable
  the hide module and reboot, so incompatible signers do not coexist.
- For full restoration, stop owned emulator/Desktop processes, keep the changed
  AVD separately and restore the retained AVD directory/.ini, original launcher
  and ramdisk selection; verify AVD identity and boot before declaring success.
- Never upload the AVD, ramdisk, account data, signing keys, identity receipts or
  raw captures. No root operation or real radio/vehicle test was performed by
  the portable-publication verification.
