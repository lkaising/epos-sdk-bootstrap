#!/usr/bin/python3
"""Isolated native load report. Resolves symbol addresses without calling them."""

import argparse
import ctypes
import hashlib
import json
from pathlib import Path
import platform
import re
import stat
import struct


DEFAULTS = {
    "ftdi_filename": "libftd2xx.so.1.4.8",
    "ftdi_sha256": "a6b2a5eacea47aa3b8fc5ab8d49a05abf2ba1e65db8f5b174b9486e92b73c94f",
    "epos_filename": "libEposCmd.so.6.8.1.0",
    "epos_sha256": "02478aa383eefd5f39458d4c75183ae04fb765c49d75a989e4d71e6a3a10ec2a",
}
SYMBOLS = ("VCS_OpenDevice", "VCS_CloseDevice", "VCS_GetDriverInfo")


def hash_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def mapped_paths(text, epos_path, ftdi_path):
    """Reject another object of either library family, including deleted files."""
    expected = {str(epos_path), str(ftdi_path)}
    found = set()
    for line in text.splitlines():
        fields = line.split(None, 5)
        if len(fields) < 6:
            continue
        path = fields[5]
        basename = path.rsplit("/", 1)[-1]
        if basename.startswith(("libEposCmd.so", "libftd2xx.so")) or path in expected:
            if path not in expected:
                raise ValueError(f"maps: foreign EPOS/FTDI object mapped at {path}")
            found.add(path)
    missing = expected - found
    if missing:
        raise ValueError("maps: expected library not mapped: " + ", ".join(sorted(missing)))
    return True


def check(args):
    report = {"ok": False, "ftdi_path": None, "epos_path": None,
              "maps_confirmed": False, "symbols": {name: False for name in args.symbol},
              "python": {"version": platform.python_version(), "bits": struct.calcsize("P") * 8},
              "error": None}
    step = "arguments"
    handles = []
    try:
        lib_dir = Path(args.lib_dir)
        if not lib_dir.is_absolute() or lib_dir.resolve() != lib_dir:
            raise ValueError(f"library directory must be absolute and canonical: {lib_dir}")
        for kind in ("ftdi", "epos"):
            filename = getattr(args, kind + "_filename")
            if filename in {"", ".", ".."} or "/" in filename or "\\" in filename:
                raise ValueError(f"invalid {kind} filename: {filename!r}")
            expected = getattr(args, kind + "_sha256")
            if not re.fullmatch(r"[0-9a-f]{64}", expected):
                raise ValueError(f"invalid {kind} SHA-256")
            path = lib_dir / filename
            report[kind + "_path"] = str(path)
            step = f"hash {path}"
            if not stat.S_ISREG(path.lstat().st_mode):
                raise ValueError(f"not a regular file: {path}")
            if hash_file(path) != expected:
                raise ValueError(f"SHA-256 mismatch: {path}")
        # Both hashes have passed. Keep these handles referenced until exit.
        step = f"load FTDI {report['ftdi_path']}"
        handles.append(ctypes.CDLL(report["ftdi_path"], mode=ctypes.RTLD_GLOBAL))
        step = f"load EPOS {report['epos_path']}"
        handles.append(ctypes.CDLL(report["epos_path"]))
        step = "maps /proc/self/maps"
        with open("/proc/self/maps", encoding="utf-8") as stream:
            report["maps_confirmed"] = mapped_paths(stream.read(), report["epos_path"], report["ftdi_path"])
        for name in args.symbol:
            step = f"export {name} in {report['epos_path']}"
            getattr(handles[1], name)  # dlsym only. Never call the returned function.
            report["symbols"][name] = True
        report["ok"] = True
    except (OSError, ValueError, AttributeError) as error:
        report["error"] = f"{step}: {error}"
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lib-dir", required=True)
    for name, default in DEFAULTS.items():
        parser.add_argument("--" + name.replace("_", "-"), default=default)
    parser.add_argument("--symbol", action="append")
    parser.add_argument("--json", action="store_true", help="emit the JSON report")
    args = parser.parse_args(argv)
    args.symbol = args.symbol if args.symbol is not None else list(SYMBOLS)
    print(json.dumps(check(args), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
