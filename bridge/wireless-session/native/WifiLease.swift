import Foundation
import Darwin

// Foundation rewrites /private/tmp to /tmp, unlike POSIX/Python realpath.
// Permit only those OS aliases; reject arbitrary symlink components.
func canonicalPrivatePath(_ path: String) -> Bool {
    guard let value = realpath(path, nil) else { return false }
    defer { free(value) }
    let resolved = String(cString: value)
    return path == resolved || ((path.hasPrefix("/tmp/") || path.hasPrefix("/var/")) && resolved == "/private" + path)
}

// POSIX metadata is sufficient for this guard; Foundation also reads unrelated
// extended attributes, which can block before the session watchdog starts.
func ownedPrivateDirectory(_ path: String) -> Bool {
    var info = stat()
    guard lstat(path, &info) == 0,
          info.st_uid == getuid(),
          (info.st_mode & S_IFMT) == S_IFDIR,
          (info.st_mode & 0o7777) == 0o700 else { return false }
    return canonicalPrivatePath(path)
}

struct WifiSnapshot: Equatable {
    var powered: Bool
    var ssid: String?
    var bssid: String?
    var associated: Bool
}
struct WifiAddress { let ip: String; let mask: String; let gateway: String }
protocol WifiRadio {
    var name: String { get }
    func snapshot() -> WifiSnapshot
    func power(_ enabled: Bool) throws
    func find(ssid: String, bssid: String?, security: String) throws -> String
    func associate(ssid: String, bssid: String, password: String, security: String) throws
    func disassociate()
    func address() -> WifiAddress?
}

/// One serialized owner. Journal survives crashes; never stores the AP password.
final class WifiLease {
    enum Failure: Error { case privacy, journal, cancelled, address, ownership, credentials }
    let radio: WifiRadio
    let journal: URL
    let sleep: (Double) -> Void
    var baseline: WifiSnapshot?
    var targetSSID: String?
    var targetBSSID: String?
    var mutated = false
    var restored = true
    init(radio: WifiRadio, journal: URL, sleep: @escaping (Double) -> Void = { Thread.sleep(forTimeInterval: $0) }) {
        self.radio = radio; self.journal = journal; self.sleep = sleep
    }
    private func save() throws {
        guard let old = baseline else { throw Failure.journal }
        let value: [String: Any] = ["version": 1, "uid": getuid(), "interface": radio.name,
            "originalPower": old.powered, "originalSSID": old.ssid ?? "", "originalBSSID": old.bssid ?? "",
            "originalAssociated": old.associated, "targetSSID": targetSSID ?? "", "targetBSSID": targetBSSID ?? ""]
        let data = try JSONSerialization.data(withJSONObject: value, options: .sortedKeys)
        // Atomic 0600 replacement in the already validated private directory.
        let temporary = journal.deletingLastPathComponent().appendingPathComponent("lease-" + UUID().uuidString)
        let fd = Darwin.open(temporary.path, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW, 0o600)
        guard fd >= 0 else { throw Failure.journal }
        defer { Darwin.close(fd); try? FileManager.default.removeItem(at: temporary) }
        var offset = 0
        data.withUnsafeBytes { bytes in
            while offset < data.count {
                let n = Darwin.write(fd, bytes.baseAddress!.advanced(by: offset), data.count - offset)
                if n < 0 && errno == EINTR { continue }
                if n <= 0 { break }; offset += n
            }
        }
        guard offset == data.count, fsync(fd) == 0, rename(temporary.path, journal.path) == 0 else { throw Failure.journal }
        let parent = Darwin.open(journal.deletingLastPathComponent().path, O_RDONLY)
        guard parent >= 0 else { throw Failure.journal }
        defer { Darwin.close(parent) }
        guard fsync(parent) == 0 else { throw Failure.journal }
    }
    func loadRecovery() throws {
        let attrs = try FileManager.default.attributesOfItem(atPath: journal.path)
        guard (attrs[.ownerAccountID] as? NSNumber)?.uint32Value == getuid(),
              (attrs[.posixPermissions] as? NSNumber)?.intValue == 0o600,
              (attrs[.size] as? NSNumber)?.intValue ?? 9000 < 8192,
              canonicalPrivatePath(journal.path),
              let d = try JSONSerialization.jsonObject(with: Data(contentsOf: journal)) as? [String: Any],
              d["version"] as? Int == 1, d["uid"] as? UInt32 == getuid(), d["interface"] as? String == radio.name,
              let power = d["originalPower"] as? Bool, let ssid = d["originalSSID"] as? String,
              let bssid = d["originalBSSID"] as? String, let associated = d["originalAssociated"] as? Bool,
              let target = d["targetSSID"] as? String, let targetB = d["targetBSSID"] as? String else { throw Failure.journal }
        baseline = WifiSnapshot(powered: power, ssid: ssid.isEmpty ? nil : ssid, bssid: bssid.isEmpty ? nil : bssid, associated: associated)
        targetSSID = target.isEmpty ? nil : target; targetBSSID = targetB.isEmpty ? nil : targetB
        mutated = true; restored = false
    }
    func join(ssid: String, bssid: String?, password: String, security: String, cancelled: () -> Bool) throws -> WifiAddress {
        guard baseline == nil, !FileManager.default.fileExists(atPath: journal.path) else { throw Failure.journal }
        guard !ssid.isEmpty, ssid.utf8.count <= 32, !ssid.contains("\0"), password.utf8.count <= 64 else { throw Failure.credentials }
        guard ["OPEN", "WPA2_PERSONAL", "WPA2_WPA3_PERSONAL"].contains(security) else { throw Failure.credentials }
        let old = radio.snapshot()
        guard !old.associated || (old.ssid != nil && old.bssid != nil) else { throw Failure.privacy }
        guard !cancelled() else { throw Failure.cancelled }
        baseline = old; targetSSID = ssid
        try save() // Intent precedes even powering on Wi-Fi.
        mutated = true; restored = false
        if !old.powered { try radio.power(true) }
        guard !cancelled() else { throw Failure.cancelled }
        let actualBSSID = try radio.find(ssid: ssid, bssid: bssid, security: security)
        targetBSSID = actualBSSID.lowercased(); try save()
        guard !cancelled() else { throw Failure.cancelled }
        try radio.associate(ssid: ssid, bssid: actualBSSID, password: password, security: security)
        for _ in 0..<75 {
            guard !cancelled() else { throw Failure.cancelled }
            let current = radio.snapshot()
            if current.ssid == ssid, current.bssid?.lowercased() == targetBSSID, let value = radio.address() { return value }
            sleep(0.2)
        }
        throw Failure.address
    }
    func release() throws -> Bool {
        guard let old = baseline else { return true }
        var current = radio.snapshot()
        if !old.powered && !current.powered { return try complete() }
        // The original association was already restored, or no mutation took effect.
        if current == old { return try complete() }
        if current.associated {
            guard let target = targetSSID, let bssid = targetBSSID,
                  current.ssid == target, current.bssid?.lowercased() == bssid else { return false }
            // A car AP already connected before launch belongs to the baseline.
            if old.associated && current.ssid == old.ssid && current.bssid == old.bssid { return try complete() }
            radio.disassociate(); current = radio.snapshot()
        }
        if !old.powered {
            // Preserve an unrelated association selected after our disconnect.
            guard !current.associated else { return false }
            try radio.power(false)
            guard !radio.snapshot().powered else { return false }
            return try complete()
        }
        for _ in 0..<50 {
            current = radio.snapshot()
            if current.powered && current.ssid == old.ssid && current.associated == old.associated &&
                (!old.associated || current.bssid == old.bssid) { return try complete() }
            if !current.powered || current.associated { return false }
            sleep(0.2) // Allow OS saved-network auto reconnect; never guess credentials.
        }
        return false
    }
    private func complete() throws -> Bool {
        if FileManager.default.fileExists(atPath: journal.path) { try FileManager.default.removeItem(at: journal) }
        let fd = Darwin.open(journal.deletingLastPathComponent().path, O_RDONLY)
        guard fd >= 0 else { throw Failure.journal }; defer { Darwin.close(fd) }
        guard fsync(fd) == 0 else { throw Failure.journal }
        restored = true; return true
    }
}
