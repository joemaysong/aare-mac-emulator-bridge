import AppKit
import IOBluetooth
import CoreWLAN
import CoreLocation
import Darwin

// Dedicated wireless session app; original probe remains unchanged.
final class Probe: NSObject {
    var control: NativeControl?
    var stopping = false
    var finishReason = "native-control-ended"
    var wifiModified = false
    var wifiRestored = false
    var eventCount = 0
    var cachedServiceOnly = false
    var bridge: RfcommBridge?
    var inquiry: IOBluetoothDeviceInquiry?
    var device: IOBluetoothDevice?
    var channel: IOBluetoothRFCOMMChannel?
    var rfcommOpened = false
    // This is a local transport-start bound, not an AA protocol timeout.
    func boundRfcommOpen() {
        DispatchQueue.main.asyncAfter(deadline: .now() + 25) { [weak self] in
            guard let self = self, !self.finished, !self.stopping, !self.rfcommOpened else { return }
            self.finish("rfcomm_open_timeout")
        }
    }
    var events: [[String: Any]] = []
    var finished = false
    var incoming = Data()
    var frameCount = 0
    let uuid = IOBluetoothSDPUUID(data: Data([0x4d,0xe1,0x7a,0x00,0x52,0xcb,0x11,0xe6,0xbd,0xf4,0x08,0x00,0x20,0x0c,0x9a,0x66]))
    let output: String
    let openChannel: Bool
    init(output: String, openChannel: Bool) { self.output = output; self.openChannel = openChannel }
    func event(_ name: String, _ fields: [String: Any] = [:]) {
        var row = fields; row["event"] = name; row["uptime"] = ProcessInfo.processInfo.systemUptime
        eventCount += 1
        events.append(row)
        if events.count > 128 { events.removeFirst(events.count - 128) }
        persist()
    }
    func persist() {
        let report: [String: Any] = ["mode": "native-wireless-session", "pid": getpid(), "session_nonce": argument("--nonce") ?? "",
            "wifi_modified": wifiModified, "wifi_restored": wifiRestored, "event_count": eventCount,
            "aa_session_established": false, "report_complete": finished, "events": events]
        do { let data = try JSONSerialization.data(withJSONObject: report, options: [.prettyPrinted, .sortedKeys]); try data.write(to: URL(fileURLWithPath: output), options: .atomic) }
        catch { fputs("report write failed: \(error)\n", stderr) }
    }
    func finish(_ reason: String) {
        guard !finished && !stopping else { return }; stopping = true; finishReason = reason
        bridge?.close(); bridge = nil
        inquiry?.stop(); inquiry = nil
        let old = channel; channel = nil; _ = old?.close()
        event("finish_requested", ["reason": reason])
        control?.stop()
    }
    func complete(_ modified: Bool, restored: Bool) {
        wifiModified = modified; wifiRestored = restored
        bridge?.close(); bridge = nil
        let old = channel; channel = nil; _ = old?.close()
        finished = true
        event("finished", ["reason": finishReason])
        NSApplication.shared.terminate(nil)
    }
    func start(_ command: String, address: String?) {
        event("inventory_started")
        event("doctor", ["os": ProcessInfo.processInfo.operatingSystemVersionString,
            "bluetooth_power_raw": IOBluetoothHostController.default().map { Int($0.powerState.rawValue) } ?? -1,
            "local_bluetooth_address": IOBluetoothHostController.default()?.addressAsString() ?? "",
            "wifi_interfaces": CWWiFiClient.shared().interfaces()?.compactMap { $0.interfaceName } ?? []])
        let paired = IOBluetoothDevice.pairedDevices() as? [IOBluetoothDevice] ?? []
        event("paired_devices", ["count": paired.count])
        if command == "discover" {
            inquiry = IOBluetoothDeviceInquiry(delegate: self)
            inquiry?.inquiryLength = 12
            inquiry?.updateNewDeviceNames = false
            let status = inquiry?.start() ?? kIOReturnError
            event("inquiry_started", ["status": status])
            if status != kIOReturnSuccess { finish("inquiry_failed") }
            return
        }
        guard command == "probe" else { finish("inventory_complete"); return }
        guard let address = address, let selected = paired.first(where: {
            $0.addressString?.lowercased().replacingOccurrences(of: ":", with: "-") == address.lowercased().replacingOccurrences(of: ":", with: "-")
        }) else { finish("select_existing_paired_device"); return }
        device = selected
        if let record = selected.getServiceRecord(for: uuid) {
            var cached: BluetoothRFCOMMChannelID = 0
            let status = record.getRFCOMMChannelID(&cached)
            event("cached_aa_service", ["status": status, "channel": cached])
            if cachedServiceOnly {
                guard openChannel, status == kIOReturnSuccess, cached > 0, cached <= 30 else { finish("cached_service_invalid"); return }
                // Diagnostic route only: cached SDP is not fresh service validation.
                // WPP must still validate the peer; no Wi-Fi success is fabricated.
                event("cached_service_diagnostic_route")
                let opened = selected.openRFCOMMChannelAsync(&channel, withChannelID: cached, delegate: self)
                event("rfcomm_requested", ["status": opened])
                if opened != kIOReturnSuccess { finish("rfcomm_request_failed") }
                else { boundRfcommOpen() }
                return
            }
        }
        if cachedServiceOnly { finish("cached_service_missing"); return }
        event("sdp_begin")
        let result = selected.performSDPQuery(self)
        event("sdp_requested", ["status": result])
        if result != kIOReturnSuccess { finish("sdp_request_failed") }
    }
    @objc func deviceInquiryDeviceFound(_ sender: IOBluetoothDeviceInquiry!, device: IOBluetoothDevice!) {
        guard !finished && !stopping else { return }
        event("discovered_device", ["name": device.name ?? "", "address": device.addressString ?? ""])
    }
    @objc func deviceInquiryComplete(_ sender: IOBluetoothDeviceInquiry!, error: IOReturn, aborted: Bool) {
        guard !finished && !stopping else { return }
        event("inquiry_complete", ["status": error, "aborted": aborted]); finish("discovery_complete")
    }
    @objc func sdpQueryComplete(_ device: IOBluetoothDevice!, status: IOReturn) {
        guard !finished && !stopping else { return }
        event("sdp_completed", ["status": status])
        guard status == kIOReturnSuccess, let record = device.getServiceRecord(for: uuid) else { finish("aa_service_unavailable"); return }
        var id: BluetoothRFCOMMChannelID = 0
        let result = record.getRFCOMMChannelID(&id)
        event("aa_service", ["status": result, "channel": id])
        guard openChannel, result == kIOReturnSuccess else { finish("sdp_only_complete"); return }
        let opened = device.openRFCOMMChannelAsync(&channel, withChannelID: id, delegate: self)
        event("rfcomm_requested", ["status": opened])
        if opened != kIOReturnSuccess { finish("rfcomm_request_failed") }
        else { boundRfcommOpen() }
    }
    @objc func rfcommChannelOpenComplete(_ channel: IOBluetoothRFCOMMChannel!, status: IOReturn) {
        guard !finished && !stopping else { return }
        event("rfcomm_open", ["status": status])
        if status != kIOReturnSuccess { finish("rfcomm_failed"); return }
        rfcommOpened = true
        bridge?.receive({ [weak self] data in
            // Use a bounded synchronous hop so native writes stay on the run loop.
            var result = false
            DispatchQueue.main.sync {
                guard let self = self, !self.finished, !self.stopping, let active = self.channel else { return }
                var bytes = [UInt8](data)
                result = bytes.withUnsafeMutableBytes { active.writeSync($0.baseAddress, length: UInt16(data.count)) == kIOReturnSuccess }
                self.event("rfcomm_write", ["length": data.count, "success": result])
                if !result { self.finish("rfcomm_write_failed") }
            }
            return result
        }, ended: { [weak self] in DispatchQueue.main.async { self?.finish("bridge_peer_closed") } })
    }
    @objc func rfcommChannelData(_ channel: IOBluetoothRFCOMMChannel!, data: UnsafeMutableRawPointer!, length: Int) {
        guard !finished && !stopping else { return }
        if let bridge = bridge {
            guard length > 0, length <= 65539 else { finish("receive_limit"); return }
            bridge.send(Data(bytes: data, count: length), failed: { [weak self] in DispatchQueue.main.async { self?.finish("bridge_write_failed") } })
            return
        }
        guard length > 0, length <= 65539, incoming.count + length <= 131078 else { finish("receive_limit"); return }
        incoming.append(data.assumingMemoryBound(to: UInt8.self), count: length)
        while incoming.count >= 4 {
            let bytes = [UInt8](incoming.prefix(4))
            let size = Int(bytes[0]) * 256 + Int(bytes[1])
            let id = Int(bytes[2]) * 256 + Int(bytes[3])
            guard incoming.count >= size + 4 else { return }
            // Header recognition only. Protobuf validity is not established here.
            event("wpp_frame_header", ["message_id": id, "payload_length": size])
            incoming.removeFirst(size + 4); frameCount += 1
            if frameCount >= 4 { finish("header_observation_complete"); return }
        }
    }
    @objc func rfcommChannelClosed(_ channel: IOBluetoothRFCOMMChannel!) { finish("rfcomm_closed") }
}
let args = CommandLine.arguments
func argument(_ flag: String) -> String? { guard let i = args.firstIndex(of: flag), i+1 < args.count else { return nil }; return args[i+1] }
guard let output = argument("--output"), output.hasPrefix("/"), !FileManager.default.fileExists(atPath: output) else {
    fputs("Require --output NEW_ABSOLUTE_FILE [--probe --device PAIRED_ADDRESS --open-rfcomm]\n", stderr); exit(2)
}
guard let directory = argument("--bridge-directory"), let journalPath = argument("--journal"),
      journalPath.hasPrefix("/"), argument("--nonce")?.count == 32 else { exit(2) }
let journal = URL(fileURLWithPath: journalPath)
let parent = journal.deletingLastPathComponent()
guard ownedPrivateDirectory(parent.path) else { exit(2) }
let app = NSApplication.shared
app.setActivationPolicy(.accessory)
let probe = Probe(output: output, openChannel: true)
probe.cachedServiceOnly = args.contains("--cached-service-diagnostic")
let recovery = args.contains("--recover-only")
do {
    probe.control = try NativeControl(directory: directory, journal: journal)
    probe.control?.joinFailed = { kind, code in probe.event("wifi_join_failed", ["kind": kind, "code": code]) }
    probe.control?.ended = { modified, restored in probe.complete(modified, restored: restored) }
    if !recovery { probe.bridge = try RfcommBridge(directory: URL(fileURLWithPath: directory).resolvingSymlinksInPath().path) }
} catch { fputs("Native IPC initialization failed\n", stderr); exit(2) }
let location = CLLocationManager()
if !recovery && location.authorizationStatus == .notDetermined {
    location.requestWhenInUseAuthorization()
}
var signals: [DispatchSourceSignal] = []
for number in [SIGINT, SIGTERM, SIGHUP] {
    signal(number, SIG_IGN)
    let source = DispatchSource.makeSignalSource(signal: number, queue: .main)
    source.setEventHandler { probe.finish("cancelled") }; source.resume(); signals.append(source)
}
DispatchQueue.main.async {
    probe.event("native_session_started")
    let wifiState = probe.control?.lease.radio.snapshot()
    probe.event("wifi_visibility", ["location_authorization": location.authorizationStatus.rawValue,
        "powered": wifiState?.powered ?? false, "associated": wifiState?.associated ?? false,
        "ssid_visible": wifiState?.ssid != nil, "bssid_visible": wifiState?.bssid != nil])
    probe.control?.run(recovery: recovery)
    if !recovery { probe.start("probe", address: argument("--device")) }
}
let lifetime = min(700.0, max(10.0, Double(argument("--seconds") ?? "300") ?? 300))
DispatchQueue.main.asyncAfter(deadline: .now() + lifetime) { probe.finish("native_session_deadline") }
app.run()
