import Foundation
import CoreWLAN
import Darwin

final class CoreWifiRadio: WifiRadio {
    enum Failure: Error { case unavailable, missingNetwork, unsupportedSecurity }
    let interface: CWInterface
    var selected: CWNetwork?
    var name: String { interface.interfaceName! }
    init() throws {
        guard let value = CWWiFiClient.shared().interface(), value.interfaceName != nil else { throw Failure.unavailable }
        interface = value
    }
    func snapshot() -> WifiSnapshot {
        let ssid = interface.ssid(), bssid = interface.bssid()?.lowercased()
        return WifiSnapshot(powered: interface.powerOn(), ssid: ssid, bssid: bssid,
                            associated: interface.interfaceMode() == .station || ssid != nil)
    }
    func power(_ enabled: Bool) throws { try interface.setPower(enabled) }
    func matches(_ network: CWNetwork, security: String) -> Bool {
        switch security {
        case "OPEN": return network.supportsSecurity(.none)
        case "WPA2_PERSONAL": return network.supportsSecurity(.wpa2Personal)
        case "WPA2_WPA3_PERSONAL": return network.supportsSecurity(.wpa2Personal) || network.supportsSecurity(.wpa3Personal)
        default: return false
        }
    }
    func find(ssid: String, bssid: String?, security: String) throws -> String {
        let values = try interface.scanForNetworks(withSSID: Data(ssid.utf8))
        guard let found = values.first(where: { $0.ssid == ssid && $0.bssid != nil &&
            (bssid == nil || $0.bssid?.lowercased() == bssid?.lowercased()) && matches($0, security: security) }),
              let actual = found.bssid else { throw Failure.missingNetwork }
        selected = found; return actual.lowercased()
    }
    func associate(ssid: String, bssid: String, password: String, security: String) throws {
        guard let value = selected, value.ssid == ssid, value.bssid?.lowercased() == bssid.lowercased(), matches(value, security: security) else {
            throw Failure.missingNetwork
        }
        try interface.associate(to: value, password: security == "OPEN" ? nil : password)
        selected = nil
    }
    func disassociate() { interface.disassociate() }
    private func command(_ args: [String]) -> String? {
        let process = Process(); process.executableURL = URL(fileURLWithPath: "/usr/sbin/ipconfig"); process.arguments = args
        let pipe = Pipe(); process.standardOutput = pipe; process.standardError = FileHandle.nullDevice
        do { try process.run() } catch { return nil }
        let deadline = ProcessInfo.processInfo.systemUptime + 2
        while process.isRunning && ProcessInfo.processInfo.systemUptime < deadline { Thread.sleep(forTimeInterval: 0.02) }
        if process.isRunning { process.terminate(); return nil }
        guard process.terminationStatus == 0 else { return nil }
        return String(data: pipe.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines)
    }
    func address() -> WifiAddress? {
        guard let ip = command(["getifaddr", name]), !ip.hasPrefix("169.254."), ip != "0.0.0.0",
              let mask = command(["getoption", name, "subnet_mask"]), let router = command(["getoption", name, "router"]),
              let packet = command(["getpacket", name]) else { return nil }
        // Avoid reporting an old interface address as a new DHCP lease.
        let pattern = "(?m)^\\s*yiaddr\\s*=\\s*" + NSRegularExpression.escapedPattern(for: ip) + "\\s*$"
        guard packet.range(of: pattern, options: .regularExpression) != nil else { return nil }
        return WifiAddress(ip: ip, mask: mask, gateway: router)
    }
}
