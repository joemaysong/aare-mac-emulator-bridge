import Foundation
import Darwin

// Client of two independently blocking Unix streams; directory must be owned and 0700.
// rx = native -> JVM, tx = JVM -> native. No control bytes mix with WPP bytes.
final class RfcommBridge {
    let rx: Int32
    let tx: Int32
    private let queue = OperationQueue()
    private let lock = NSLock()
    private var stopped = false
    private var pending = 0
    init(directory: String) throws {
        let attrs = try FileManager.default.attributesOfItem(atPath: directory)
        guard (attrs[.ownerAccountID] as? NSNumber)?.uint32Value == getuid(),
              (attrs[.posixPermissions] as? NSNumber)?.intValue == 0o700,
              URL(fileURLWithPath: directory).resolvingSymlinksInPath().path == directory else {
            throw NSError(domain: "bridge-directory", code: 1)
        }
        func connectPath(_ name: String) throws -> Int32 {
            let path = directory + "/" + name
            var address = sockaddr_un(); address.sun_family = sa_family_t(AF_UNIX)
            guard path.utf8.count < MemoryLayout.size(ofValue: address.sun_path) else { throw NSError(domain: "bridge-path", code: 1) }
            withUnsafeMutablePointer(to: &address.sun_path) { p in p.withMemoryRebound(to: CChar.self, capacity: 104) { _ = strcpy($0, path) } }
            let fd = socket(AF_UNIX, SOCK_STREAM, 0)
            guard fd >= 0 else { throw NSError(domain: "bridge-socket", code: Int(errno)) }
            var yes: Int32 = 1; _ = setsockopt(fd, SOL_SOCKET, SO_NOSIGPIPE, &yes, 4)
            let status = withUnsafePointer(to: &address) { $0.withMemoryRebound(to: sockaddr.self, capacity: 1) { Darwin.connect(fd, $0, socklen_t(MemoryLayout<sockaddr_un>.size)) } }
            guard status == 0 else { Darwin.close(fd); throw NSError(domain: "bridge-connect", code: Int(errno)) }
            return fd
        }
        rx = try connectPath("native-rx.sock")
        do { tx = try connectPath("native-tx.sock") } catch { Darwin.close(rx); throw error }
        queue.maxConcurrentOperationCount = 1
    }
    func receive(_ body: @escaping (Data) -> Bool, ended: @escaping () -> Void) {
        DispatchQueue.global().async {
            var buffer = [UInt8](repeating: 0, count: 1024)
            while true {
                let count = Darwin.read(self.tx, &buffer, buffer.count)
                if count < 0 && errno == EINTR { continue }
                if count <= 0 { break }
                if !body(Data(buffer.prefix(count))) { break }
            }
            ended()
        }
    }
    func send(_ data: Data, failed: @escaping () -> Void) {
        lock.lock()
        if stopped || pending + data.count > 262144 { lock.unlock(); failed(); return }
        pending += data.count; lock.unlock()
        queue.addOperation {
            var offset = 0
            data.withUnsafeBytes { bytes in
                while offset < data.count {
                    let n = Darwin.write(self.rx, bytes.baseAddress!.advanced(by: offset), data.count-offset)
                    if n < 0 && errno == EINTR { continue }
                    if n <= 0 { break }; offset += n
                }
            }
            self.lock.lock(); self.pending -= data.count; self.lock.unlock()
            if offset != data.count { failed() }
        }
    }
    func close() {
        lock.lock(); if stopped { lock.unlock(); return }; stopped = true; lock.unlock()
        // Shutdown wakes blocking readers/writers. Descriptors close only after queues finish.
        shutdown(rx, SHUT_RDWR); shutdown(tx, SHUT_RDWR)
    }
    deinit { Darwin.close(rx); Darwin.close(tx) }
}
