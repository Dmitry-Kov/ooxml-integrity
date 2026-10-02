#!/usr/bin/env python3
"""The only way out of the agents' network in the review-history benchmark.

Agents run on an internal Docker network with no route out. This process runs
in a container on that network and on the default bridge, and offers two
things: an HTTP CONNECT proxy on port 3128 that opens tunnels only to the
allowed hosts on port 443, and a plain TCP relay on port 11434 to the host's
Ollama. Every connection is logged as one JSON line on stdout: allowed or
denied, host, port, bytes each way. Standard library only.

    python review_history_agents_egress.py api.anthropic.com chatgpt.com ...
"""
from __future__ import annotations

import json
import socket
import sys
import threading
import time

OLLAMA = ("host.docker.internal", 11434)


def log(**record) -> None:
    record["at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    print(json.dumps(record), flush=True)


def pump(source: socket.socket, target: socket.socket, counter: list, index: int) -> None:
    try:
        while chunk := source.recv(65536):
            target.sendall(chunk)
            counter[index] += len(chunk)
    except OSError:
        pass
    finally:
        for s in (source, target):
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass


def tunnel(downstream: socket.socket, upstream: socket.socket, **record) -> None:
    counter = [0, 0]
    back = threading.Thread(target=pump, args=(upstream, downstream, counter, 1), daemon=True)
    back.start()
    pump(downstream, upstream, counter, 0)
    back.join()
    log(**record, sent=counter[0], received=counter[1])
    downstream.close()
    upstream.close()


def permitted(request: str, allowed: set[str]) -> str | None:
    """The host of a CONNECT request line to an allowed host on port 443, else None."""
    parts = request.split()
    if len(parts) != 3 or parts[0] != "CONNECT" or ":" not in parts[1]:
        return None
    host, _, port = parts[1].rpartition(":")
    return host.lower() if host.lower() in allowed and port == "443" else None


def connect_proxy(client: socket.socket, peer: str, allowed: set[str]) -> None:
    head = b""
    while b"\r\n\r\n" not in head and len(head) < 16384:
        chunk = client.recv(4096)
        if not chunk:
            break
        head += chunk
    request = head.split(b"\r\n", 1)[0].decode("latin-1", "replace")
    host = permitted(request, allowed)
    if host is None:
        log(kind="connect", allowed=False, client=peer, request=request[:200])
        client.sendall(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n")
        client.close()
        return
    try:
        upstream = socket.create_connection((host, 443), timeout=30)
        upstream.settimeout(None)
    except OSError as error:
        log(kind="connect", allowed=True, client=peer, host=host, error=str(error))
        client.sendall(b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\n\r\n")
        client.close()
        return
    client.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
    tunnel(client, upstream, kind="connect", allowed=True, client=peer, host=host)


def relay(client: socket.socket, peer: str) -> None:
    try:
        upstream = socket.create_connection(OLLAMA, timeout=30)
        upstream.settimeout(None)
    except OSError as error:
        log(kind="ollama", allowed=True, client=peer, error=str(error))
        client.close()
        return
    tunnel(client, upstream, kind="ollama", allowed=True, client=peer, host="%s:%d" % OLLAMA)


def serve(port: int, handler, *args) -> None:
    server = socket.create_server(("0.0.0.0", port), reuse_port=False)
    while True:
        client, address = server.accept()
        threading.Thread(target=handler, args=(client, address[0], *args), daemon=True).start()


def main(argv: list[str]) -> int:
    allowed = {host.lower() for host in argv}
    log(kind="start", allowed_hosts=sorted(allowed), ollama="%s:%d" % OLLAMA)
    threading.Thread(target=serve, args=(11434, relay), daemon=True).start()
    serve(3128, connect_proxy, allowed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
