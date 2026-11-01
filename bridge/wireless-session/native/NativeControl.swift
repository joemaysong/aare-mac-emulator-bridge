import Foundation
import Darwin

final class NativeControl {
    let fd: Int32
    let lease: WifiLease
    let leaseLock: Int32
    let lock = NSLock()
    private var cancelled = false
    var ended: ((Bool, Bool) -> Void)?
    var joinFailed: ((String, Int) -> Void)?
    static func safeFailure(_ error: Error) -> (String, Int) {
        if let failure = error as? WifiLease.Failure {
            switch failure {
            case .privacy: return ("privacy", 0)
            case .journal: return ("journal", 0)
            case .cancelled: return ("cancelled", 0)
            case .address: return ("dhcp_or_identity", 0)
            case .ownership: return ("ownership", 0)
            case .credentials: return ("credentials_shape", 0)
            }
        }
        if let failure = error as? CoreWifiRadio.Failure {
            switch failure {
            case .unavailable: return ("interface_unavailable", 0)
            case .missingNetwork: return ("network_not_found", 0)
            case .unsupportedSecurity: return ("unsupported_security", 0)
            }
        }
        // Never include localizedDescription, userInfo, SSID, BSSID, or credentials.
        return ("system_wifi_error", (error as NSError).code)
    }
    init(directory: String, journal: URL, radio: WifiRadio? = nil) throws {
        let attrs = try FileManager.default.attributesOfItem(atPath: directory)
        guard (attrs[.ownerAccountID] as? NSNumber)?.uint32Value == getuid(),
              (attrs[.posixPermissions] as? NSNumber)?.intValue == 0o700,
              canonicalPrivatePath(directory) else { throw WifiLease.Failure.journal }
        let path = directory + "/native-control.sock"
        var address = sockaddr_un(); address.sun_family = sa_family_t(AF_UNIX)
        guard path.utf8.count < MemoryLayout.size(ofValue: address.sun_path) else { throw WifiLease.Failure.journal }
        withUnsafeMutablePointer(to: &address.sun_path) { p in p.withMemoryRebound(to: CChar.self, capacity: 104) { _ = strcpy($0, path) } }
        let descriptor = socket(AF_UNIX, SOCK_STREAM, 0)
        fd = descriptor
        guard fd >= 0 else { throw WifiLease.Failure.journal }
        var yes: Int32 = 1; _ = setsockopt(fd, SOL_SOCKET, SO_NOSIGPIPE, &yes, 4)
        let result = withUnsafePointer(to: &address) { $0.withMemoryRebound(to: sockaddr.self, capacity: 1) {
            Darwin.connect(descriptor, $0, socklen_t(MemoryLayout<sockaddr_un>.size))
        } }
        guard result == 0 else { Darwin.close(fd); throw WifiLease.Failure.journal }
        let lockPath = journal.deletingLastPathComponent().appendingPathComponent("radio.lock").path
        let owner = Darwin.open(lockPath, O_RDWR | O_CREAT | O_NOFOLLOW, 0o600)
        guard owner >= 0, flock(owner, LOCK_EX | LOCK_NB) == 0 else {
            if owner >= 0 { Darwin.close(owner) }; Darwin.close(fd); throw WifiLease.Failure.ownership
        }
        leaseLock = owner
        do {
            if let supplied = radio { lease = WifiLease(radio: supplied, journal: journal) }
            else { lease = WifiLease(radio: try CoreWifiRadio(), journal: journal) }
        }
        catch { Darwin.close(owner); Darwin.close(fd); throw error }
    }
    func stopped() -> Bool { lock.lock(); defer { lock.unlock() }; return cancelled }
    func stop() { lock.lock(); cancelled = true; lock.unlock(); shutdown(fd, SHUT_RDWR) }
    private func line() -> String? {
        var data = Data()
        while data.count < 8192 {
            var value: UInt8 = 0; let n = Darwin.read(fd, &value, 1)
            if n < 0 && errno == EINTR { continue }
            if n <= 0 || value > 127 || value == 0 { return nil }
            if value == 10 { return String(data: data, encoding: .ascii) }
            data.append(value)
        }
        return nil
    }
    private func write(_ value: String) -> Bool {
        let data = Array((value + "\n").utf8)
        return data.withUnsafeBytes { bytes in
            var offset = 0
            while offset < data.count {
                let n = Darwin.write(fd, bytes.baseAddress!.advanced(by: offset), data.count - offset)
                if n < 0 && errno == EINTR { continue }
                if n <= 0 { return false }; offset += n
            }
            return true
        }
    }
    func run(recovery: Bool) {
        DispatchQueue.global().async {
            do {
                if recovery { try self.lease.loadRecovery() }
                else {
                    while !self.stopped(), let line = self.line() {
                        let parts = line.components(separatedBy: "\t")
                        if parts == ["QUIT"] { break }
                        guard parts.count == 5, parts[0] == "JOIN" else { break }
                        func decoded(_ value: String) -> String? {
                            guard let data = Data(base64Encoded: value) else { return nil }
                            return String(data: data, encoding: .utf8)
                        }
                        guard let ssid = decoded(parts[1]), let password = decoded(parts[2]), let bssid = decoded(parts[3]) else { break }
                        do {
                            let value = try self.lease.join(ssid: ssid, bssid: bssid.isEmpty ? nil : bssid,
                                password: password, security: parts[4], cancelled: self.stopped)
                            guard self.write("JOINED\t\(value.ip)\t\(self.lease.radio.name)\t\(value.mask)\t\(value.gateway)") else { break }
                        } catch {
                            let safe = Self.safeFailure(error)
                            DispatchQueue.main.async { self.joinFailed?(safe.0, safe.1) }
                            _ = self.write("FAILED"); break
                        }
                    }
                }
            } catch { /* Journal remains for explicit recovery; no sensitive error text. */ }
            let restored = (try? self.lease.release()) == true
            _ = self.write(restored ? "RESTORED" : "RESTORE_INCOMPLETE")
            shutdown(self.fd, SHUT_RDWR)
            DispatchQueue.main.async { self.ended?(self.lease.mutated, restored && !FileManager.default.fileExists(atPath: self.lease.journal.path)) }
        }
    }
    deinit { Darwin.close(fd); Darwin.close(leaseLock) }
}
