#!/usr/bin/env python3
"""PINE client for PCSX2 2.8.1 - read/write the emulated PS2's memory from outside.

Wire format (from pcsx2/PINE.cpp):
  request : [u32 total_len][u8 opcode][u32 addr][args...]      total_len = 4 + len(cmd)
  reply   : [u32 total_len][u8 result][payload...]             result 00 = OK, FF = FAIL

Opcodes: 0 read8, 1 read16, 2 read32, 3 read64, 4 write8, 5 write16, 6 write32,
         7 write64, 8 version, 9 savestate(slot), 0xA loadstate(slot), 0xB title,
         0xC id, 0xD uuid, 0xE gameversion, 0xF status
Batching: ParseCommand loops over the command buffer, so many reads can be sent in
one request. That makes reading a string cheap.

Usage:
  python pine.py status
  python pine.py title
  python pine.py r32 0x1245410 [count]
  python pine.py r8  0x1245410 32
  python pine.py str 0x1245410 [maxlen]
  python pine.py w32 0x1245410 0x12345678
  python pine.py save 1          # save state slot 1
  python pine.py load 1          # load state slot 1
  python pine.py watch 0x1245410 --len 32 --seconds 300 [--interval 0.25]
  python pine.py lvlwatch --seconds 300
"""
import argparse
import socket
import struct
import sys
import time

HOST = "127.0.0.1"
PORT = 28011
DEFAULT_TIMEOUT = 10.0

R8, R16, R32, R64 = 0, 1, 2, 3
W8, W16, W32, W64 = 4, 5, 6, 7
VERSION, SAVESTATE, LOADSTATE, TITLE, GAMEID, UUID, GAMEVER, STATUS = 8, 9, 0xA, 0xB, 0xC, 0xD, 0xE, 0xF

LEVEL_DATA = 0x01245410          # Level_data : name at +0x00, script at +0x20, start id at +0xA4
LEVEL_DATA_SCRIPT = 0x01245430
LEVEL_DATA_STARTID = 0x012454b4
NUM_LEVEL_TRIGGERS = 0x012844FC
LEVEL_TRIGGERS = 0x01238B78      # 100-byte trigger records, name at +0x00

STATUS_NAMES = {0: "Running", 1: "Paused", 2: "Shutdown"}


class Pine:
    def __init__(self, host=HOST, port=PORT, timeout=DEFAULT_TIMEOUT):
        self.sock = socket.create_connection((host, port), timeout=timeout)

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()

    def _recv_all(self, n):
        buf = b""
        while len(buf) < n:
            chunk = self.sock.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("PINE socket closed")
            buf += chunk
        return buf

    def _exchange(self, cmd: bytes) -> bytes:
        self.sock.sendall(struct.pack("<I", 4 + len(cmd)) + cmd)
        (length,) = struct.unpack("<I", self._recv_all(4))
        body = self._recv_all(length - 4)
        if not body:
            raise ConnectionError("empty PINE reply")
        if body[0] == 0xFF:
            raise RuntimeError("PINE reported failure (0xFF)")
        return body[1:]

    def _simple(self, opcode, extra: bytes = b"") -> bytes:
        return self._exchange(bytes([opcode]) + extra)

    # --- single-value helpers -------------------------------------------------
    def read(self, addr, size):
        op = {1: R8, 2: R16, 4: R32, 8: R64}[size]
        data = self._simple(op, struct.pack("<I", addr))
        return int.from_bytes(data[:size], "little")

    def write(self, addr, size, value):
        op = {1: W8, 2: W16, 4: W32, 8: W64}[size]
        self._simple(op, struct.pack("<I", addr) + int(value).to_bytes(size, "little", signed=False))

    def read_buffer(self, addr, length) -> bytes:
        """Read `length` bytes using batched 4-byte reads (fast)."""
        out = bytearray()
        addrs = list(range(addr, addr + length, 4))
        for start in range(0, len(addrs), 256):
            chunk = addrs[start:start + 256]
            cmd = b"".join(bytes([R32]) + struct.pack("<I", a) for a in chunk)
            data = self._exchange(cmd)
            out += data[: 4 * len(chunk)]
        return bytes(out[:length])

    def read_string(self, addr, maxlen=64):
        raw = self.read_buffer(addr, maxlen)
        return raw.split(b"\x00", 1)[0].decode("latin-1", "replace")

    # --- misc -----------------------------------------------------------------
    def status(self):
        v = self._simple(STATUS)
        return STATUS_NAMES.get(int.from_bytes(v[:4], "little"), "?")

    def title(self):
        return self._simple(TITLE).split(b"\x00", 1)[0].decode("latin-1", "replace")

    def game_id(self):
        return self._simple(GAMEID).split(b"\x00", 1)[0].decode("latin-1", "replace")

    def version(self):
        return self._simple(VERSION).split(b"\x00", 1)[0].decode("latin-1", "replace")

    def save_state(self, slot):
        self._simple(SAVESTATE, bytes([slot]))

    def load_state(self, slot):
        self._simple(LOADSTATE, bytes([slot]))


def _num(s):
    return int(s, 0)


def cmd_status(p):
    print(f"status : {p.status()}")
    print(f"version: {p.version()}")
    try:
        print(f"title  : {p.title()}")
        print(f"id     : {p.game_id()}")
    except Exception as e:  # noqa: BLE001
        print(f"title/id: (unavailable: {e})")


def cmd_read(p, addr, size):
    val = p.read(addr, size)
    print(f"[0x{addr:08X}] {size}-bit = 0x{val:0{size * 2}X}  ({val})")


def cmd_str(p, addr, maxlen):
    print(p.read_string(addr, maxlen))


def watch(p, addr, length, seconds, interval, label):
    print(f"# watching 0x{addr:08X} ({label}) for {seconds}s, every {interval}s", flush=True)
    last = None
    end = time.time() + seconds
    while time.time() < end:
        try:
            raw = p.read_buffer(addr, length)
        except Exception as e:  # noqa: BLE001
            print(f"[{time.strftime('%H:%M:%S')}] read error: {e}", flush=True)
            time.sleep(interval)
            continue
        if raw != last:
            name = raw.split(b"\x00", 1)[0].decode("latin-1", "replace")
            print(f"[{time.strftime('%H:%M:%S')}] CHANGED -> '{name}'  raw={raw[:32].hex()}", flush=True)
            last = raw
        time.sleep(interval)


def cmd_lvlwatch(p, seconds, interval):
    print("# time       level_name                      script                    startid  ntrig", flush=True)
    last = None
    end = time.time() + seconds
    while time.time() < end:
        name = p.read_string(LEVEL_DATA, 32)
        script = p.read_string(LEVEL_DATA_SCRIPT, 32)
        try:
            startid = p.read(LEVEL_DATA_STARTID, 4)
            ntrig = p.read(NUM_LEVEL_TRIGGERS, 4)
        except Exception:  # noqa: BLE001
            startid, ntrig = -1, -1
        key = (name, script, ntrig)
        if key != last:
            print(f"[{time.strftime('%H:%M:%S')}] {name:<30} {script:<25} {startid:<7} {ntrig}", flush=True)
            last = key
        time.sleep(interval)


def main(argv=None):
    ap = argparse.ArgumentParser(description="PINE client for PCSX2")
    ap.add_argument("--host", default=HOST)
    ap.add_argument("--port", type=int, default=PORT)
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status")
    sub.add_parser("title")

    for name in ("r8", "r16", "r32", "r64"):
        s = sub.add_parser(name)
        s.add_argument("addr")
        s.add_argument("count", nargs="?", type=int, default=1)

    s = sub.add_parser("str")
    s.add_argument("addr")
    s.add_argument("maxlen", nargs="?", type=int, default=64)

    for name in ("w8", "w16", "w32", "w64"):
        s = sub.add_parser(name)
        s.add_argument("addr")
        s.add_argument("value")

    s = sub.add_parser("save")
    s.add_argument("slot", type=int)
    s = sub.add_parser("load")
    s.add_argument("slot", type=int)

    s = sub.add_parser("watch")
    s.add_argument("addr")
    s.add_argument("--len", type=int, default=32)
    s.add_argument("--seconds", type=float, default=120)
    s.add_argument("--interval", type=float, default=0.25)
    s.add_argument("--label", default="")

    s = sub.add_parser("hash")
    s.add_argument("addr")
    s.add_argument("len", type=_num, nargs="?", default=4096)
    s.add_argument("--count", type=int, default=1)
    s.add_argument("--interval", type=float, default=2.0)

    s = sub.add_parser("lvlwatch")
    s.add_argument("--seconds", type=float, default=120)
    s.add_argument("--interval", type=float, default=0.25)

    a = ap.parse_args(argv)
    with Pine(a.host, a.port) as p:
        if a.cmd == "status":
            cmd_status(p)
        elif a.cmd == "title":
            print(p.title())
        elif a.cmd in ("r8", "r16", "r32", "r64"):
            size = int(a.cmd[1:]) // 8
            for i in range(a.count):
                cmd_read(p, _num(a.addr) + i * size, size)
        elif a.cmd == "str":
            cmd_str(p, _num(a.addr), a.maxlen)
        elif a.cmd in ("w8", "w16", "w32", "w64"):
            size = int(a.cmd[1:]) // 8
            p.write(_num(a.addr), size, _num(a.value))
            print(f"wrote 0x{_num(a.value):X} to 0x{_num(a.addr):08X} "
                  f"(read back 0x{p.read(_num(a.addr), size):X})")
        elif a.cmd == "save":
            p.save_state(a.slot)
            print(f"saved state slot {a.slot}")
        elif a.cmd == "load":
            p.load_state(a.slot)
            print(f"loaded state slot {a.slot}")
        elif a.cmd == "watch":
            watch(p, _num(a.addr), a.len, a.seconds, a.interval, a.label)
        elif a.cmd == "hash":
            import hashlib
            base = _num(a.addr)
            for i in range(a.count):
                raw = p.read_buffer(base, a.len)
                nz = sum(1 for b in raw if b)
                print(f"[{time.strftime('%H:%M:%S')}] md5={hashlib.md5(raw).hexdigest()[:16]} "
                      f"nonzero={nz}/{a.len}", flush=True)
                if i + 1 < a.count:
                    time.sleep(a.interval)
        elif a.cmd == "lvlwatch":
            cmd_lvlwatch(p, a.seconds, a.interval)
    return 0


if __name__ == "__main__":
    sys.exit(main())
