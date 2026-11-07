# V17 vehicle integration checkpoint

On 2026-11-07 the owner promoted head-unit candidate92 to V17. The Mac tool has produced actual wireless AA video, responsive touch and audible media through the Android emulator. First-pair automatic connection, background standby re-arming, manual stop/reconnect and bounded unexpected-disconnect recovery were observed during the integration series. USB internet remained on the USB network interface while Wi-Fi joined the vehicle AP.

This is historical owner acceptance, not a new clean-clone test or certification of Android-phone equivalence. Source changes include standby orchestration, pairing/invitation observation, radio identity wait and restore obligations. Private SDK runtimes, emulator images, TLS/signing keys and captures remain excluded. No physical wired AA acceptance is claimed.

Publication verification: 23 standby/invitation Python tests passed. The larger Python integration suite was attempted but was not passed from this public tree: JVM/native compiled fixtures and the local audio72 APK/proof are not included. Run the documented build prerequisites and configure local paths first. No clean-clone full build is claimed for this checkpoint.
