package org.ev6.aare.mac;

import java.io.*;
import java.net.UnixDomainSocketAddress;
import java.nio.channels.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.Base64;
import net.prototux.aare.aap.AapLog;
import net.prototux.aare.aap.wireless.*;

/** Live WPP only. The emulator remains the AAP/TLS endpoint. Never log credentials. */
public final class EmulatorWirelessSession {
    static SocketChannel connect(Path directory, String name) throws IOException {
        return SocketChannel.open(UnixDomainSocketAddress.of(directory.resolve(name + ".sock")));
    }
    static String encode(String value) {
        return Base64.getEncoder().encodeToString(value.getBytes(StandardCharsets.UTF_8));
    }
    static synchronized String[] request(SocketChannel channel, String... fields) throws IOException {
        byte[] message = (String.join("\t", fields) + "\n").getBytes(StandardCharsets.US_ASCII);
        if (message.length > 8192) throw new IOException("control limit");
        OutputStream output = Channels.newOutputStream(channel);
        output.write(message); output.flush();
        InputStream input = Channels.newInputStream(channel);
        ByteArrayOutputStream response = new ByteArrayOutputStream();
        while (response.size() < 8192) {
            int c = input.read();
            if (c == -1) throw new EOFException("control closed");
            if (c == 10) return response.toString(StandardCharsets.US_ASCII).split("\t", -1);
            if (c > 127 || c == 0) throw new IOException("control encoding");
            response.write(c);
        }
        throw new IOException("control limit");
    }
    public static void main(String[] args) throws Exception {
        if (args.length != 2) throw new IllegalArgumentException("private directory, tool identity required");
        Path directory = Path.of(args[0]);
        try (SocketChannel rx = connect(directory, "rx");
             SocketChannel tx = connect(directory, "tx");
             SocketChannel control = connect(directory, "control")) {
            AapLog log = new AapLog() {
                public void d(String s) {
                    if (s.startsWith("wireless: <- ") || s.startsWith("wireless: -> ")) System.out.println(s);
                }
                public void i(String s) { }
                public void w(String s, Throwable e) { }
                public void e(String s, Throwable e) { }
            };
            WirelessBootstrap bootstrap = new WirelessBootstrap(
                Channels.newInputStream(rx), Channels.newOutputStream(tx),
                new WirelessBootstrap.Listener() {
                    public JoinResult connectWifi(WifiCredentials credentials) {
                        System.out.println("WPP_CREDENTIALS_PARSED");
                        try {
                            String[] reply = request(control, "JOIN", encode(credentials.getSsid()),
                                encode(credentials.getPassword()), encode(credentials.getBssid() == null ? "" : credentials.getBssid()),
                                credentials.getSecurity().name());
                            if (reply.length == 3 && reply[0].equals("JOINED"))
                                return new JoinResult.Joined(reply[1], reply[2].isEmpty() ? null : reply[2]);
                        } catch (IOException ignored) { }
                        return new JoinResult.Failed(WppStatus.WIFI_NETWORK_UNAVAILABLE, "native association unavailable");
                    }
                    public void onReady(String ip, int port) {
                        try {
                            String[] reply = request(control, "READY", encode(ip), Integer.toString(port));
                            if (reply.length != 1 || !reply[0].equals("READY_OK")) throw new IOException("not connected");
                            System.out.println("WPP_READY_STREAM_CONNECTED");
                        } catch (IOException error) { throw new IllegalStateException("stream unavailable"); }
                    }
                }, log, new WirelessBootstrap.Options(60_000, 5_000, 2_000, 100, true, args[1]));
            Thread shutdown = new Thread(() -> { bootstrap.close(); try { control.close(); } catch (IOException ignored) { } });
            Runtime.getRuntime().addShutdownHook(shutdown);
            try {
                bootstrap.run();
                System.out.println("WPP_LINK_ENDED");
            } catch (Throwable error) {
                // Upstream exceptions may contain credentials. Print only their type.
                System.err.println("WIRELESS_SESSION_STOPPED type=" + error.getClass().getSimpleName());
                throw new IOException("wireless session stopped");
            } finally { bootstrap.close(); Runtime.getRuntime().removeShutdownHook(shutdown); }
        }
    }
}
