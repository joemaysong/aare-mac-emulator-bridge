import Foundation

final class FakeRadio: WifiRadio {
    let name = "en0"
    var state = WifiSnapshot(powered: false, ssid: nil, bssid: nil, associated: false)
    var reconnect: WifiSnapshot?
    var failFind = false, failAssociate = false, noAddress = false
    var actions: [String] = []
    func snapshot() -> WifiSnapshot { state }
    func power(_ enabled: Bool) throws { actions.append("power"); state.powered = enabled }
    func find(ssid: String, bssid: String?, security: String) throws -> String {
        if failFind { throw WifiLease.Failure.address }; return bssid ?? "aa:bb:cc:dd:ee:ff"
    }
    func associate(ssid: String, bssid: String, password: String, security: String) throws {
        actions.append("associate")
        if failAssociate { throw WifiLease.Failure.address }
        state = WifiSnapshot(powered: true, ssid: ssid, bssid: bssid, associated: true)
    }
    func disassociate() {
        actions.append("disassociate")
        state = reconnect ?? WifiSnapshot(powered: true, ssid: nil, bssid: nil, associated: false)
    }
    func address() -> WifiAddress? { noAddress ? nil : WifiAddress(ip: "192.168.50.2", mask: "255.255.255.0", gateway: "192.168.50.1") }
}

let root = FileManager.default.temporaryDirectory.appendingPathComponent("aare-wifi-tests-" + UUID().uuidString)
try FileManager.default.createDirectory(at: root, withIntermediateDirectories: false, attributes: [.posixPermissions: 0o700])
defer { try? FileManager.default.removeItem(at: root) }
var checks = 0
func check(_ condition: Bool) {
    checks += 1; precondition(condition, "Wi-Fi lease assertion \(checks)")
}
func fixture() -> (FakeRadio, WifiLease, URL) {
    let radio = FakeRadio(), journal = root.appendingPathComponent(UUID().uuidString)
    return (radio, WifiLease(radio: radio, journal: journal, sleep: { _ in }), journal)
}
func join(_ lease: WifiLease, cancelled: () -> Bool = { false }) throws {
    _ = try lease.join(ssid: "test-car", bssid: nil, password: "never-persist-this-password", security: "WPA2_PERSONAL", cancelled: cancelled)
}
do {
    let (radio, lease, journal) = fixture(); try join(lease)
    let text = try String(contentsOf: journal, encoding: .utf8)
    check(!text.contains("never-persist-this-password"))
    check((try FileManager.default.attributesOfItem(atPath: journal.path)[.posixPermissions] as! NSNumber).intValue == 0o600)
    check(try lease.release()); check(!radio.state.powered); check(!FileManager.default.fileExists(atPath: journal.path))
}
do {
    let (radio, lease, _) = fixture()
    radio.state = WifiSnapshot(powered: true, ssid: "original", bssid: "00:11:22:33:44:55", associated: true)
    radio.reconnect = radio.state; try join(lease)
    check(try lease.release()); check(radio.state == radio.reconnect!)
}
do {
    let (radio, lease, journal) = fixture(); try join(lease)
    radio.state = WifiSnapshot(powered: true, ssid: "user-chosen", bssid: "00:11:22:33:44:55", associated: true)
    let n = radio.actions.count
    check(try !lease.release()); check(radio.actions.count == n); check(FileManager.default.fileExists(atPath: journal.path))
}
do {
    let (radio, lease, _) = fixture(); radio.failAssociate = true
    do { try join(lease); fatalError("association should fail") } catch { }
    check(try lease.release()); check(!radio.state.powered)
}
do {
    let (radio, lease, journal) = fixture(); try join(lease)
    let recovery = WifiLease(radio: radio, journal: journal, sleep: { _ in })
    try recovery.loadRecovery(); check(try recovery.release()); check(!radio.state.powered)
}
do {
    let (radio, lease, journal) = fixture()
    radio.state = WifiSnapshot(powered: true, ssid: nil, bssid: nil, associated: true)
    do { try join(lease); fatalError("redacted association should fail") } catch { }
    check(radio.actions.isEmpty); check(!FileManager.default.fileExists(atPath: journal.path))
}
do {
    let (radio, lease, _) = fixture()
    do { try join(lease, cancelled: { radio.state.powered }); fatalError("cancel should fail") } catch { }
    check(try lease.release()); check(!radio.state.powered)
}
do {
    let (radio, lease, _) = fixture(); radio.noAddress = true
    do { try join(lease); fatalError("missing DHCP should fail") } catch { }
    check(try lease.release()); check(!radio.state.powered)
}
do {
    let (radio, lease, _) = fixture()
    radio.state = WifiSnapshot(powered: true, ssid: "test-car", bssid: "aa:bb:cc:dd:ee:ff", associated: true)
    try join(lease); check(try lease.release()); check(radio.state.associated); check(!radio.actions.contains("disassociate"))
}
do {
    let (radio, lease, journal) = fixture(); try join(lease)
    radio.state.bssid = "00:11:22:33:44:55"
    check(try !lease.release()); check(FileManager.default.fileExists(atPath: journal.path))
}
do {
    let (radio, lease, journal) = fixture()
    try Data("invalid".utf8).write(to: journal)
    do { try lease.loadRecovery(); fatalError("corrupt journal") } catch { }
    check(radio.actions.isEmpty)
}
do {
    let (radio, lease, journal) = fixture()
    do { _ = try lease.join(ssid: "test", bssid: nil, password: "", security: "WEP", cancelled: { false }); fatalError("unsupported") } catch { }
    check(radio.actions.isEmpty); check(!FileManager.default.fileExists(atPath: journal.path))
}
print("WIFI_LEASE_CHECKS=\(checks); all simulated radios; no hardware accessed")
