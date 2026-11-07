import Foundation
import Darwin

/// Test-only entry point. No real radio object is ever constructed.
final class TestRadio: WifiRadio {
    let name = "en0"
    var state = WifiSnapshot(powered: false, ssid: nil, bssid: nil, associated: false)
    func snapshot() -> WifiSnapshot { state }
    func power(_ enabled: Bool) throws { state.powered = enabled }
    func find(ssid: String, bssid: String?, security: String) throws -> String { "aa:bb:cc:dd:ee:ff" }
    func associate(ssid: String, bssid: String, password: String, security: String) throws {
        state = WifiSnapshot(powered: true, ssid: ssid, bssid: bssid, associated: true)
    }
    func disassociate() { state = WifiSnapshot(powered: true, ssid: nil, bssid: nil, associated: false) }
    func address() -> WifiAddress? { WifiAddress(ip: "192.168.50.2", mask: "255.255.255.0", gateway: "192.168.50.1") }
}
let secret = "DO_NOT_EMIT_CREDENTIALS"
let safe = NativeControl.safeFailure(NSError(domain: secret, code: -3900, userInfo: [NSLocalizedDescriptionKey: secret]))
precondition(safe.0 == "system_wifi_error" && safe.1 == -3900)
precondition(NativeControl.safeFailure(CoreWifiRadio.Failure.missingNetwork).0 == "network_not_found")
precondition(NativeControl.safeFailure(WifiLease.Failure.address).0 == "dhcp_or_identity")
let guardDirectory = "/private/tmp/aare-dir-guard-" + UUID().uuidString
precondition(mkdir(guardDirectory, 0o700) == 0)
precondition(ownedPrivateDirectory(guardDirectory))
precondition(chmod(guardDirectory, 0o755) == 0)
precondition(!ownedPrivateDirectory(guardDirectory))
precondition(chmod(guardDirectory, 0o700) == 0)
precondition(symlink(guardDirectory, guardDirectory + "-link") == 0)
precondition(!ownedPrivateDirectory(guardDirectory + "-link"))
precondition(unlink(guardDirectory + "-link") == 0)
precondition(rmdir(guardDirectory) == 0)
let args = CommandLine.arguments
guard args.count == 5 || args.count == 6 else { exit(2) }
let radio = TestRadio()
if args[4] == "recover" {
    radio.state = WifiSnapshot(powered: true, ssid: "test-car", bssid: "aa:bb:cc:dd:ee:ff", associated: true)
}
let control = try NativeControl(directory: args[1], journal: URL(fileURLWithPath: args[2]), radio: radio)
control.ended = { mutated, restored in
    var value: [String: Any] = ["mutated": mutated, "restored": restored, "powered": radio.state.powered, "hardware_access": false]
    if args.count == 6 {
        value["session_nonce"] = args[5]; value["report_complete"] = true
        value["wifi_restored"] = restored; value["wifi_modified"] = mutated
    }
    try! JSONSerialization.data(withJSONObject: value).write(to: URL(fileURLWithPath: args[3]))
    exit(restored ? 0 : 1)
}
control.run(recovery: args[4] == "recover")
dispatchMain()

