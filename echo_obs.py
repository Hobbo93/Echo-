"""Echo's remote control for OBS Studio (OBS's built-in WebSocket server, protocol v5).

Go live / end the stream, switch scenes and read stream health. Used by echo_live.py (/live on
Telegram, the Live panel in Echo HQ). Standard library only: a tiny WebSocket client is below.

Settings (private, in %USERPROFILE%\\.echo_telegram.json): obs_host (default 127.0.0.1:4455) and
obs_password. In OBS: Tools > WebSocket Server Settings > Enable, and the same password.
"""
import base64
import hashlib
import json
import os
import socket
import struct
import uuid

import echo_connect


class OBSError(RuntimeError):
    pass


# ==========================================
# MINIMAL WEBSOCKET CLIENT (RFC 6455, text frames)
# ==========================================

class _WebSocket:
    def __init__(self, host, port, timeout=10):
        self.sock = socket.create_connection((host, port), timeout=timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall((f"GET / HTTP/1.1\r\nHost: {host}:{port}\r\nUpgrade: websocket\r\n"
                           f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n"
                           "Sec-WebSocket-Protocol: obswebsocket.json\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
        head = b""
        while b"\r\n\r\n" not in head:
            chunk = self.sock.recv(1024)
            if not chunk:
                raise OBSError("OBS closed the connection.")
            head += chunk
        head, self.buf = head.split(b"\r\n\r\n", 1)
        if b" 101 " not in head.split(b"\r\n", 1)[0]:
            raise OBSError("OBS didn't accept the connection.")
        accept = base64.b64encode(hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest())
        if accept not in head:
            raise OBSError("Unexpected reply from OBS.")

    def _read(self, n):
        while len(self.buf) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise OBSError("OBS closed the connection.")
            self.buf += chunk
        data, self.buf = self.buf[:n], self.buf[n:]
        return data

    def _frame(self, opcode, payload):
        header = bytes([0x80 | opcode])
        n = len(payload)
        if n < 126:
            header += bytes([0x80 | n])
        elif n < 65536:
            header += bytes([0x80 | 126]) + struct.pack(">H", n)
        else:
            header += bytes([0x80 | 127]) + struct.pack(">Q", n)
        mask = os.urandom(4)
        self.sock.sendall(header + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(payload)))

    def send(self, obj):
        self._frame(0x1, json.dumps(obj).encode("utf-8"))

    def recv(self):
        message = b""
        while True:
            b1, b2 = self._read(2)
            opcode, n = b1 & 0x0F, b2 & 0x7F
            if n == 126:
                n = struct.unpack(">H", self._read(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", self._read(8))[0]
            mask = self._read(4) if b2 & 0x80 else None
            data = self._read(n)
            if mask:
                data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
            if opcode == 0x8:
                raise OBSError("OBS closed the connection (wrong password?).")
            if opcode == 0x9:
                self._frame(0xA, data)
                continue
            if opcode in (0x0, 0x1):
                message += data
                if b1 & 0x80:
                    return json.loads(message.decode("utf-8"))

    def close(self):
        try:
            self._frame(0x8, b"")
            self.sock.close()
        except OSError:
            pass


# ==========================================
# OBS REQUESTS
# ==========================================

def _settings():
    c = echo_connect._cfg()
    host, _, port = str(c.get("obs_host", "127.0.0.1:4455")).partition(":")
    return host or "127.0.0.1", int(port or 4455), str(c.get("obs_password", ""))


def is_configured():
    return bool(echo_connect._cfg().get("obs_password"))


def _auth(password, salt, challenge):
    secret = base64.b64encode(hashlib.sha256((password + salt).encode()).digest()).decode()
    return base64.b64encode(hashlib.sha256((secret + challenge).encode()).digest()).decode()


def call(*requests):
    """Send one or more (requestType, requestData) to OBS; returns their responseData, in order."""
    host, port, password = _settings()
    try:
        ws = _WebSocket(host, port)
    except OSError:
        raise OBSError("OBS isn't open (or its remote control is off). Open OBS on the PC and try again.") from None
    try:
        hello = ws.recv()
        ident = {"rpcVersion": 1, "eventSubscriptions": 0}
        auth = hello.get("d", {}).get("authentication")
        if auth:
            ident["authentication"] = _auth(password, auth["salt"], auth["challenge"])
        ws.send({"op": 1, "d": ident})
        if ws.recv().get("op") != 2:
            raise OBSError("OBS refused Echo's password.")
        results = []
        for kind, data in requests:
            rid = uuid.uuid4().hex
            ws.send({"op": 6, "d": {"requestType": kind, "requestId": rid, "requestData": data or {}}})
            while True:
                msg = ws.recv()
                if msg.get("op") == 7 and msg["d"].get("requestId") == rid:
                    break
            status = msg["d"].get("requestStatus", {})
            if not status.get("result"):
                raise OBSError(status.get("comment") or f"OBS couldn't do {kind} (code {status.get('code')}).")
            results.append(msg["d"].get("responseData") or {})
        return results
    finally:
        ws.close()


def status():
    """{'live', 'seconds', 'scene', 'scenes', 'dropped_pct', 'fps', 'cpu'} from OBS."""
    stream, scenes, stats = call(("GetStreamStatus", None), ("GetSceneList", None), ("GetStats", None))
    total = stream.get("outputTotalFrames") or 0
    skipped = stream.get("outputSkippedFrames") or 0
    return {
        "live": bool(stream.get("outputActive")),
        "reconnecting": bool(stream.get("outputReconnecting")),
        "seconds": int((stream.get("outputDuration") or 0) / 1000),
        "scene": scenes.get("currentProgramSceneName", ""),
        "scenes": [s.get("sceneName", "") for s in reversed(scenes.get("scenes", []))],
        "dropped_pct": round(100 * skipped / total, 1) if total else 0.0,
        "fps": round(stats.get("activeFps") or 0, 1),
        "cpu": round(stats.get("cpuUsage") or 0, 1),
    }


def start():
    call(("StartStream", None))


def stop():
    call(("StopStream", None))


def find_scene(name, scenes):
    """The scene the owner meant: exact, starts-with, contains, then initials ('brb' = Be Right Back), ignoring case."""
    want = name.strip().lower()

    def initials(s):
        return "".join(w[0] for w in s.lower().split() if w)

    for test in (lambda s: s.lower() == want, lambda s: s.lower().startswith(want), lambda s: want in s.lower(),
                 lambda s: initials(s) == want.replace(" ", "")):
        hits = [s for s in scenes if test(s)]
        if hits:
            return hits[0]
    return None


def switch(name):
    scenes = status()["scenes"]
    scene = find_scene(name, scenes)
    if not scene:
        raise OBSError(f"There's no OBS scene called '{name}'. Scenes: " + (", ".join(scenes) or "none yet"))
    call(("SetCurrentProgramScene", {"sceneName": scene}))
    return scene
