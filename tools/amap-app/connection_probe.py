"""Temporary HTTP proxy for observing the official App's destination hosts.

It records no headers, query strings, request bodies, or response bodies.
HTTPS is tunneled untouched; this cannot reveal signed navigation payloads.
"""

import select
import socket
from socketserver import StreamRequestHandler, ThreadingTCPServer
from urllib.parse import urlsplit


class Handler(StreamRequestHandler):
    rbufsize = 0  # Keep POST body bytes on the socket for the tunnel loop.

    def handle(self):
        first = self.rfile.readline(16384)
        if not first:
            return
        try:
            method, target, version = first.decode("iso-8859-1").strip().split(" ", 2)
            if method == "CONNECT":
                host, port_text = target.rsplit(":", 1)
                port = int(port_text)
                path = ""
                request_line = first
            else:
                parsed = urlsplit(target)
                host = parsed.hostname
                port = parsed.port or (443 if parsed.scheme == "https" else 80)
                path = parsed.path
                request_line = f"{method} {path or '/'}"
                if parsed.query:
                    request_line += f"?{parsed.query}"
                request_line = f"{request_line} {version}\r\n".encode("iso-8859-1")
            if not host or port < 1 or port > 65535:
                raise ValueError("invalid target")
        except (ValueError, UnicodeError):
            self.wfile.write(b"HTTP/1.1 400 Bad Request\r\n\r\n")
            return
        print(f"{method} {host}:{port}{path}", flush=True)
        try:
            remote = socket.create_connection((host, port), timeout=8)
            remote.settimeout(None)
            if method == "CONNECT":
                self.wfile.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            else:
                remote.sendall(request_line)
                while True:
                    line = self.rfile.readline(16384)
                    remote.sendall(line)
                    if line in (b"\r\n", b"\n", b""):
                        break
            sockets = (self.connection, remote)
            while True:
                readable, _, _ = select.select(sockets, (), (), 60)
                if not readable:
                    break
                for source in readable:
                    try:
                        data = source.recv(65536)
                    except OSError:
                        data = b""
                    if not data:
                        return
                    destination = remote if source is self.connection else self.connection
                    destination.sendall(data)
        except OSError:
            if method == "CONNECT":
                try:
                    self.wfile.write(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
                except OSError:
                    pass
        finally:
            try:
                remote.close()
            except UnboundLocalError:
                pass


class Server(ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == "__main__":
    with Server(("0.0.0.0", 18765), Handler) as server:
        server.serve_forever()
