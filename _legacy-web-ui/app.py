#!/usr/bin/env python3
r"""Summoner Randomizer — self-contained ISO creation tool.

    python app.py                 # http://127.0.0.1:8091
    python app.py --lan           # also reachable on the LAN (opt-in)
    python app.py --port 9000

Everything lives inside this folder:

    app.py            this file (server + jobs + config)
    discover.py       disc identification (game, VPP revision, supported?)
    rando_core.py     VPP reader, transforms, pipeline
    index.html        the UI
    builds.json       which build came from which seed + mode
    config.json       disc locations the user has added
    work/in/          discs the user adds or uploads
    work/out/         generated ISOs

The app ships no game data and never sends a disc image anywhere. You bring your
own disc; it writes a new, size-preserving ISO next to it.

Stdlib only. No Flask, no pip installs.
"""
from __future__ import annotations

import argparse
import json
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import discover
import rando_core as rc

APP = Path(__file__).resolve().parent
WORK = APP / "work"
IN_DIR = WORK / "in"
OUT_DIR = WORK / "out"
CONFIG = APP / "config.json"
MANIFEST = APP / "builds.json"

STATE = {"running": False, "log": [], "result": None, "error": None}
DRY = {"running": False, "log": [], "result": None, "error": None}
LOCK = threading.Lock()
# disc identify results are expensive (full magic scan); cache by path+size+mtime
DISC_CACHE: dict[tuple, dict] = {}


# --------------------------------------------------------------------------- #
# config + manifest
# --------------------------------------------------------------------------- #
def _read_json(p: Path, default):
    try:
        return json.loads(p.read_text("utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _write_json_atomic(p: Path, data):
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True), "utf-8")
    tmp.replace(p)


def load_config() -> dict:
    cfg = _read_json(CONFIG, {})
    if not isinstance(cfg, dict):
        cfg = {}
    cfg.setdefault("disc_dirs", [])
    cfg.setdefault("discs", [])
    return cfg


CONFIG_DATA = load_config()
BUILDS = _read_json(MANIFEST, {}).get("builds", {}) if isinstance(_read_json(MANIFEST, {}), dict) else {}


def save_config():
    _write_json_atomic(CONFIG, CONFIG_DATA)


def save_manifest():
    _write_json_atomic(MANIFEST, {"builds": BUILDS})


# --------------------------------------------------------------------------- #
# discs
# --------------------------------------------------------------------------- #
def _identify_cached(p: Path) -> dict:
    try:
        st = p.stat()
        key = (str(p.resolve()), st.st_size, st.st_mtime_ns)
    except OSError:
        return discover.identify(p).as_dict()
    hit = DISC_CACHE.get(key)
    if hit is not None:
        return hit
    info = discover.identify(p).as_dict()
    if len(DISC_CACHE) > 64:
        DISC_CACHE.clear()
    DISC_CACHE[key] = info
    return info


def list_isos() -> list[dict]:
    """Every disc we know about: the work/in folder, configured folders, configured files."""
    seen: dict[str, dict] = {}

    def add(p: Path, source: str):
        if not p.is_file() or p.suffix.lower() != ".iso":
            return
        key = str(p.resolve())
        if key in seen:
            return
        d = dict(_identify_cached(p))
        d["name"] = p.name
        d["source"] = source
        d["mtime"] = p.stat().st_mtime
        seen[key] = d

    if IN_DIR.exists():
        for p in sorted(IN_DIR.glob("*.iso")):
            add(p, "work/in")

    for entry in CONFIG_DATA.get("disc_dirs", []):
        d = Path(entry)
        if d.is_dir():
            for p in sorted(d.glob("*.iso")):
                add(p, "added folder")

    for entry in CONFIG_DATA.get("discs", []):
        add(Path(entry), "added file")

    return sorted(seen.values(), key=lambda r: r["name"].lower())


def add_disc(path: str) -> dict:
    """Register a disc by path. Validated + identified before it is accepted."""
    p = Path(path).expanduser()
    if not p.is_file():
        raise ValueError(f"not a file: {p}")
    if p.suffix.lower() != ".iso":
        raise ValueError("expected a .iso disc image")
    info = _identify_cached(p)
    if info["game"] == "unknown" and not info["vpp_count"]:
        raise ValueError(f"does not look like a Summoner disc: {info['reason']}")
    discs = CONFIG_DATA.setdefault("discs", [])
    key = str(p.resolve())
    if key not in discs:
        discs.append(key)
        save_config()
    return info


def add_folder(path: str) -> dict:
    p = Path(path).expanduser()
    if not p.is_dir():
        raise ValueError(f"not a folder: {p}")
    dirs = CONFIG_DATA.setdefault("disc_dirs", [])
    key = str(p.resolve())
    if key not in dirs:
        dirs.append(key)
        save_config()
    n = len([f for f in p.glob("*.iso")])
    return {"folder": key, "isos": n}


def remove_disc(path: str) -> bool:
    key = str(Path(path).expanduser().resolve())
    changed = False
    for k in ("discs", "disc_dirs"):
        lst = CONFIG_DATA.get(k, [])
        if key in lst:
            lst.remove(key)
            changed = True
    if changed:
        save_config()
    return changed


# --------------------------------------------------------------------------- #
# builds
# --------------------------------------------------------------------------- #
def record_build(res: dict):
    BUILDS[res["name"]] = {
        "name": res["name"],
        "bytes": res["dst_bytes"],
        "sha256": res["dst_sha256"],
        "src_sha256": res.get("src_sha256"),
        "src": res.get("src"),
        "seed": res["seed"],
        "mode": res.get("mode", "custom"),
        "transforms": res.get("transforms", []),
        "edits": res.get("edits", 0),
        "size_preserved": res.get("size_preserved"),
        "built": time.time(),
        "reports": res.get("reports", []),
    }
    save_manifest()


def infer_from_name(name: str) -> dict:
    if not name.lower().endswith(".iso"):
        return {}
    parts = name[:-4].split("-")
    if len(parts) >= 3 and parts[1] in rc.MODES:
        return {"mode": parts[1], "seed": "-".join(parts[2:])}
    if len(parts) >= 2:
        return {"mode": None, "seed": "-".join(parts[1:])}
    return {}


def list_out() -> list[dict]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    files = []
    for p in sorted(OUT_DIR.glob("*.iso")):
        st = p.stat()
        meta = BUILDS.get(p.name) or {}
        row = {
            "name": p.name, "bytes": st.st_size, "mtime": st.st_mtime,
            "built": meta.get("built", st.st_mtime),
            "seed": meta.get("seed"), "mode": meta.get("mode"),
            "edits": meta.get("edits"), "sha256": meta.get("sha256"),
            "size_preserved": meta.get("size_preserved"),
            "transforms": meta.get("transforms", []),
            "tracked": bool(meta),
        }
        if not meta:
            row.update(infer_from_name(p.name))
        files.append(row)
    files.sort(key=lambda r: r["built"] or 0, reverse=True)
    return files


def _out_path(name: str) -> Path:
    if not name or "/" in name or "\\" in name or not name.lower().endswith(".iso"):
        raise ValueError("bad build name")
    root = OUT_DIR.resolve()
    p = (root / name).resolve()
    if p.parent != root:
        raise ValueError("build must live directly in the out dir")
    return p


# --------------------------------------------------------------------------- #
# jobs
# --------------------------------------------------------------------------- #
def _log(state, msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    with LOCK:
        state["log"].append(line)
        state["log"] = state["log"][-200:]


def log(msg):
    _log(STATE, msg)


def _norm_request(req) -> tuple[Path, str, str, list[str], dict]:
    iso = req.get("iso")
    if not iso:
        raise ValueError("no disc selected")
    src = Path(iso)
    if not src.is_file():
        raise ValueError(f"disc not found: {iso}")

    info = _identify_cached(src)
    if not info["supported"]:
        raise ValueError(f"cannot edit this disc - {info['reason']}")

    seed = str(req.get("seed") or "SEED1")
    mode = req.get("mode") or "custom"
    if mode != "custom" and mode not in rc.MODES:
        raise ValueError(f"unknown mode: {mode}")
    transforms = list(rc.MODES[mode]["transforms"]) if mode in rc.MODES else list(req.get("transforms") or [])

    # Explicit per-feature control. `include` forces a feature on, `exclude` forces it
    # off, and both override whatever the mode preset says. This is what lets
    # "Everything except shops" or "Door Shuffle plus Ring Hunt" be expressed.
    include = [str(t) for t in (req.get("include") or []) if t]
    exclude = [str(t) for t in (req.get("exclude") or []) if t]
    for t in include + exclude:
        if t not in rc.TRANSFORMS:
            raise ValueError(f"unknown transform: {t}")
    transforms = [t for t in transforms if t not in exclude]
    for t in include:
        if t not in transforms:
            transforms.append(t)  # appended, so ordering stays deterministic

    # per-transform options, e.g. {"ring_hunt": {"anchor": "act3_finished"}}
    options = req.get("options") or {}
    if not isinstance(options, dict):
        raise ValueError("options must be an object")
    clean: dict = {}
    # A mode may carry preset dials (Progression's XP/level dials, Ring Hunt ·
    # Any Ring's anchor). Seed them first, so selecting a mode actually applies
    # its preset; the request's own options then merge on top of these defaults.
    if mode in rc.MODES:
        for tname, opts in (rc.MODES[mode].get("options") or {}).items():
            if tname in transforms and tname in rc.OPTION_AWARE and isinstance(opts, dict):
                clean[tname] = dict(opts)
    for tname, opts in options.items():
        if tname not in rc.TRANSFORMS:
            raise ValueError(f"options given for unknown transform: {tname}")
        if tname not in rc.OPTION_AWARE:
            raise ValueError(f"transform takes no options: {tname}")
        if not isinstance(opts, dict):
            raise ValueError(f"options for {tname} must be an object")
        spec = rc.OPTIONS.get(tname, {})
        for k, v in opts.items():
            if k not in spec:
                raise ValueError(f"unknown option {tname}.{k}")
            if v in (None, ""):
                continue
            field = spec[k]
            if field["type"] == "int":
                try:
                    v = int(v)
                except (TypeError, ValueError):
                    raise ValueError(f"{tname}.{k} must be a number") from None
                v = max(field.get("min", v), min(field.get("max", v), v))
            elif field["type"] == "bool":
                v = bool(v)
            elif field["type"] == "choice" and v not in field["choices"]:
                raise ValueError(f"{tname}.{k} must be one of {field['choices']}")
            clean.setdefault(tname, {})[k] = v
    # binary-layer patches: from the mode preset, or given explicitly
    binary = req.get("binary")
    if binary is None:
        binary = rc.MODES.get(mode, {}).get("binary") or []
    norm_binary: list[tuple[str, dict]] = []
    for b in binary:
        if isinstance(b, (list, tuple)) and len(b) == 2:
            norm_binary.append((str(b[0]), dict(b[1] or {})))
        else:
            norm_binary.append((str(b), {}))
    if norm_binary:
        if not getattr(rc, "_HAVE_BINARY", False):
            raise ValueError("binary layer unavailable (binary.py missing)")
        for bname, _bp in norm_binary:
            if bname not in rc.binary.PATCHES:
                raise ValueError(f"unknown binary patch: {bname}")
    return src, seed, mode, transforms, clean, norm_binary


def out_name_for(src: Path, seed: str, mode: str) -> str:
    safe = "".join(c for c in seed if c.isalnum() or c in "-_")[:40] or "SEED"
    stem = src.stem.replace(" ", "")
    return f"{stem}-{mode}-{safe}.iso" if mode and mode != "custom" else f"{stem}-{safe}.iso"


def run_randomize(src: Path, seed: str, mode: str, transforms: list[str],
                  options: dict | None = None, binary: list | None = None):
    try:
        name = out_name_for(src, seed, mode)
        log(f"start seed={seed} mode={mode} -> {name}")
        res = rc.randomize_iso(src, OUT_DIR / name, seed, transforms, progress=log,
                               options=options, binary_patches=binary)
        res.update(mode=mode, transforms=list(transforms), name=name,
                   edits=sum(r.get("changed", 0) for r in res["reports"]))
        log(f"done: {res['edits']} edits, sha256 {res['dst_sha256'][:16]}…")
        with LOCK:
            STATE["result"] = res
            record_build(res)
    except Exception as exc:  # noqa: BLE001
        log(f"ERROR: {exc}")
        traceback.print_exc()
        with LOCK:
            STATE["error"] = str(exc)
    finally:
        with LOCK:
            STATE["running"] = False


def run_dry(src: Path, seed: str, mode: str, transforms: list[str],
            options: dict | None = None, binary: list | None = None):
    try:
        _log(DRY, f"dry run seed={seed} mode={mode} (nothing is written)")
        res = rc.dry_run_iso(src, seed, transforms, progress=lambda m: _log(DRY, m),
                             options=options, binary_patches=binary)
        res.update(mode=mode, name=out_name_for(src, seed, mode))
        _log(DRY, f"dry run done: {res['changed_bytes_total']:,} blob bytes would change")
        with LOCK:
            DRY["result"] = res
    except Exception as exc:  # noqa: BLE001
        _log(DRY, f"ERROR: {exc}")
        traceback.print_exc()
        with LOCK:
            DRY["error"] = str(exc)
    finally:
        with LOCK:
            DRY["running"] = False


# --------------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------------- #
ALLOWED_FROM = None  # set in main()


class Handler(BaseHTTPRequestHandler):
    server_version = "SummonerRandomizer/0.3"

    def log_message(self, *a):
        pass

    def _send(self, code, payload, ctype="application/json", extra=None):
        body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _guard_local(self) -> bool:
        """Refuse non-local callers unless --lan was passed.

        There is no upload-to-internet path anywhere in this app, but a disc
        listing and an out-folder file server should still default to loopback.
        """
        if ALLOWED_FROM is None:
            return True
        host = (self.client_address[0] or "")
        if host in ALLOWED_FROM or host.startswith("127.") or host == "::1":
            return True
        self._send(403, {"error": "local access only (start with --lan to allow)"})
        return False

    # ---------------- GET ----------------
    def do_GET(self):
        u = urlparse(self.path)
        path, qs = u.path, parse_qs(u.query)
        if not self._guard_local():
            return

        if path in ("/", "/index.html"):
            return self._send(200, (APP / "index.html").read_bytes(), "text/html; charset=utf-8")
        if path == "/api/isos":
            return self._send(200, {"isos": list_isos(), "in_dir": str(IN_DIR), "out_dir": str(OUT_DIR)})
        if path == "/api/disc":
            p = (qs.get("path") or [""])[0]
            if not p:
                return self._send(400, {"error": "need ?path="})
            try:
                return self._send(200, _identify_cached(Path(p)))
            except Exception as exc:  # noqa: BLE001
                return self._send(400, {"error": str(exc)})
        if path == "/api/transforms":
            return self._send(200, {"available": sorted(rc.TRANSFORMS), "info": rc.TRANSFORM_INFO,
                                    "pending": rc.PENDING, "modes": rc.MODES,
                                    "options": rc.OPTIONS,
                                    "binary": (rc.binary.describe() if getattr(rc, "_HAVE_BINARY", False) else {})})
        if path == "/api/modes":
            return self._send(200, {"modes": rc.MODES, "order": list(rc.MODES),
                                    "custom": {"id": "custom", "label": "Custom",
                                               "blurb": "Hand-picked transform set.",
                                               "risk": "varies", "transforms": []},
                                    "info": rc.TRANSFORM_INFO, "pending": rc.PENDING,
                                    "options": rc.OPTIONS})
        if path == "/api/status":
            with LOCK:
                return self._send(200, {"running": STATE["running"], "log": STATE["log"],
                                        "result": STATE["result"], "error": STATE["error"],
                                        "dry": {"running": DRY["running"], "log": DRY["log"],
                                                "result": DRY["result"], "error": DRY["error"]}})
        if path == "/api/out":
            return self._send(200, {"dir": str(OUT_DIR), "files": list_out()})
        if path == "/api/hash":
            name = (qs.get("name") or [""])[0]
            try:
                p = _out_path(name)
            except ValueError as exc:
                return self._send(400, {"error": str(exc)})
            if not p.is_file():
                return self._send(404, {"error": "no such build"})
            digest = rc.sha256_file(p)
            with LOCK:
                BUILDS.setdefault(name, {})["sha256"] = digest
                save_manifest()
            return self._send(200, {"name": name, "sha256": digest})
        return self._send(404, {"error": "not found"})

    # ---------------- POST ----------------
    def do_POST(self):
        path = urlparse(self.path).path
        if not self._guard_local():
            return
        if path == "/api/upload":
            return self._upload()
        if path not in ("/api/randomize", "/api/dryrun", "/api/add-disc", "/api/add-folder", "/api/remove"):
            return self._send(404, {"error": "not found"})
        try:
            req = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        except json.JSONDecodeError:
            return self._send(400, {"error": "bad json"})

        if path == "/api/add-disc":
            try:
                return self._send(200, {"added": True, "disc": add_disc(req.get("path", ""))})
            except ValueError as exc:
                return self._send(400, {"error": str(exc)})
        if path == "/api/add-folder":
            try:
                return self._send(200, {"added": True, **add_folder(req.get("path", ""))})
            except ValueError as exc:
                return self._send(400, {"error": str(exc)})
        if path == "/api/remove":
            return self._send(200, {"removed": remove_disc(req.get("path", ""))})

        try:
            src, seed, mode, transforms, options, binary = _norm_request(req)
        except ValueError as exc:
            return self._send(400, {"error": str(exc)})

        dry = path == "/api/dryrun"
        target = DRY if dry else STATE
        with LOCK:
            if STATE["running"] or DRY["running"]:
                return self._send(409, {"error": "a job is already running"})
            if not transforms:
                return self._send(400, {"error": "no transforms selected"})
            target.update(running=True, log=[], result=None, error=None)
        _log(target, f"disc={src.name}")
        _log(target, f"mode={mode}")
        _log(target, f"transforms={transforms}")
        if options:
            _log(target, f"options={options}")
        runner = run_dry if dry else run_randomize
        threading.Thread(target=runner, args=(src, seed, mode, transforms, options, binary),
                         daemon=True).start()
        return self._send(200, {"started": True, "dry": dry, "mode": mode, "transforms": transforms,
                                "out": out_name_for(src, seed, mode)})

    def _upload(self):
        """Stream an uploaded disc into work/in. Never buffered in memory."""
        name = (parse_qs(urlparse(self.path).query).get("name") or [""])[0]
        if not name:
            name = self.headers.get("X-Filename", "") or "upload.iso"
        name = Path(name).name
        if not name.lower().endswith(".iso"):
            return self._send(400, {"error": "only .iso files"})
        total = int(self.headers.get("Content-Length", 0))
        IN_DIR.mkdir(parents=True, exist_ok=True)
        dest = IN_DIR / name
        if dest.exists():
            stem, suf = dest.stem, dest.suffix
            i = 2
            while dest.exists():
                dest = IN_DIR / f"{stem}-{i}{suf}"
                i += 1
        written = 0
        try:
            with dest.open("wb") as fh:
                remain = total
                while remain > 0:
                    chunk = self.rfile.read(min(1 << 20, remain))
                    if not chunk:
                        break
                    fh.write(chunk)
                    written += len(chunk)
                    remain -= len(chunk)
        except Exception as exc:  # noqa: BLE001
            return self._send(500, {"error": f"upload failed: {exc}"})
        info = _identify_cached(dest)
        return self._send(200, {"name": dest.name, "bytes": written, "disc": info})


def main():
    global ALLOWED_FROM
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8091)
    ap.add_argument("--lan", action="store_true", help="also accept non-local callers")
    ap.add_argument("--host")
    args = ap.parse_args()

    if not args.lan:
        ALLOWED_FROM = {"127.0.0.1", "::1"}
    host = args.host or ("0.0.0.0" if args.lan else "127.0.0.1")

    for d in (WORK, IN_DIR, OUT_DIR):
        d.mkdir(parents=True, exist_ok=True)

    srv = ThreadingHTTPServer((host, args.port), Handler)
    # Cheap startup: count candidate files only. Full identification is a whole-image
    # magic scan (1.2 GB / 3.1 GB) and must not run before the server can serve.
    n_in = len(list(IN_DIR.glob("*.iso"))) if IN_DIR.exists() else 0
    n_cfg = len(CONFIG_DATA.get("discs", [])) + sum(
        len(list(Path(d).glob("*.iso")))
        for d in CONFIG_DATA.get("disc_dirs", []) if Path(d).is_dir())
    print(f"Summoner Randomizer -> http://127.0.0.1:{args.port}/")
    print(f"  app    : {APP}")
    print(f"  discs  : {n_in} in work/in, {n_cfg} registered (identified on request)")
    print(f"  out    : {OUT_DIR}")
    print(f"  access : {'LAN allowed' if args.lan else 'local only'}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")


if __name__ == "__main__":
    main()
