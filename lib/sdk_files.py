"""Pinned release data and local archive operations. Never executes SDK code."""

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import zipfile


class SDKFileError(ValueError):
    """A path, archive, or native file failed a static check."""


def load_release(path=None):
    # JSON is data, unlike the shell defaults used by older bootstraps.
    path = Path(path) if path else Path(__file__).resolve().parents[1] / "config/sdk-release.json"
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def check_archive(path, release):
    path = Path(path)
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode):
        raise SDKFileError(f"archive is not a regular file: {path}")
    expected = release["archive"]
    if info.st_size != expected["size_bytes"]:
        raise SDKFileError(f"archive size mismatch at {path}: {info.st_size}, expected {expected['size_bytes']}")
    digest = sha256_file(path)
    if digest != expected["sha256"]:
        raise SDKFileError(f"archive SHA-256 mismatch at {path}: {digest}")
    return {"size": info.st_size, "sha256": digest}


def _elf_header(header, path, arch):
    if len(header) < 20:
        raise SDKFileError(f"truncated ELF at {path}: fewer than 20 bytes")
    machine = int.from_bytes(header[18:20], "little")
    if (header[:4] != b"\x7fELF" or header[4] != arch["elf_class"]
            or header[5] != arch["elf_data"] or machine != arch["elf_machine"]):
        raise SDKFileError(f"ELF mismatch at {path}: class={header[4]}, data={header[5]}, "
                           f"machine={machine}; host architecture {arch['uname_m']}")


def check_elf(path, arch=None):
    arch = arch or {"elf_class": 2, "elf_data": 1, "elf_machine": 62, "uname_m": "x86_64"}
    if not stat.S_ISREG(Path(path).lstat().st_mode):
        raise SDKFileError(f"ELF is not a regular file: {path}")
    with open(path, "rb") as stream:
        _elf_header(stream.read(20), path, arch)


def _member_type(info):
    kind = stat.S_IFMT(info.external_attr >> 16)
    if kind == 0:
        # Approved exception for the pinned DOS-created archive. Its directories
        # carry 0x10 and files 0x20/0x21, with no Unix type bits. Never infer type
        # from the filename alone or accept absent type bits on Unix creators.
        if info.create_system == 0 and info.external_attr in {0x10, 0x11}:
            kind = stat.S_IFDIR
        elif info.create_system == 0 and info.external_attr in {0x20, 0x21}:
            kind = stat.S_IFREG
    if kind not in {stat.S_IFDIR, stat.S_IFREG}:
        raise SDKFileError(f"archive member is not a regular file or directory: {info.filename}")
    if (kind == stat.S_IFDIR) != info.is_dir():
        raise SDKFileError(f"archive member type contradicts its name: {info.filename}")
    if kind == stat.S_IFDIR and info.file_size:
        raise SDKFileError(f"archive directory contains data: {info.filename}")
    return kind


def _validated_members(archive, release):
    root = release["archive"]["top_level_dir"]
    members = archive.infolist()
    seen, spelling, kinds = set(), {}, {}
    for info in members:
        raw = info.filename
        path = raw[:-1] if raw.endswith("/") else raw
        parts = path.split("/")
        if (raw != info.orig_filename or not path or "\\" in raw
                or any(ord(c) < 32 or ord(c) == 127 for c in raw)
                or any(p in {"", ".", ".."} for p in parts)
                or parts[0] != root):
            raise SDKFileError(f"unsafe archive member path: {raw!r}")
        kind = _member_type(info)
        if path in seen:
            raise SDKFileError(f"duplicate archive member: {raw}")
        seen.add(path)
        kinds[path] = kind
        for index in range(1, len(parts) + 1):
            parent = "/".join(parts[:index])
            folded = parent.casefold()
            if folded in spelling and spelling[folded] != parent:
                raise SDKFileError(f"case-colliding archive member: {raw}")
            spelling[folded] = parent
    for path in seen:
        for parent in PurePosixPath(path).parents:
            if str(parent) in kinds and kinds[str(parent)] != stat.S_IFDIR:
                raise SDKFileError(f"archive file used as a directory: {parent}")
    for relative in release["required_members"]:
        path = f"{root}/{relative}"
        if kinds.get(path) != stat.S_IFREG:
            raise SDKFileError(f"required archive file missing: {path}")
    for library in release["libraries"].values():
        base = f"{root}/{release['arch']['lib_subdir']}"
        if f"{base}/{library['link']}" in seen:
            raise SDKFileError(f"archive occupies generated symlink: {base}/{library['link']}")
        path = f"{base}/{library['filename']}"
        data = archive.read(path)
        if hashlib.sha256(data).hexdigest() != library["sha256"]:
            raise SDKFileError(f"library SHA-256 mismatch in archive: {path}")
        _elf_header(data[:20], path, release["arch"])
    return members


def validate_archive(path, release):
    """Check pins and all member metadata before any extraction is permitted."""
    check_archive(path, release)
    with zipfile.ZipFile(path) as archive:
        return _validated_members(archive, release)


def _plain_ancestors(path):
    for part in [path, *path.parents]:
        if part.is_symlink():
            raise SDKFileError(f"symlink in extraction destination: {part}")


def extract_archive(path, destination, release):
    """Extract into a new staging/vendor directory and return receipt inventory.

    The caller records this inventory before publishing any final payload paths.
    Existing destinations are refused, including empty directories.
    """
    destination = Path(destination)
    _plain_ancestors(destination.absolute())
    if destination.exists():
        raise SDKFileError(f"extraction destination already exists: {destination}")
    check_archive(path, release)
    with zipfile.ZipFile(path) as archive:
        members = _validated_members(archive, release)
        destination.mkdir(mode=0o755)
        destination.chmod(0o755)
        dirs = {"downloads", "vendor"}
        files = []
        for info in members:
            relative = info.filename.rstrip("/")
            target = destination / relative
            parent = target if info.is_dir() else target.parent
            missing = []
            while parent != destination:
                missing.append(parent)
                parent = parent.parent
            for directory in reversed(missing):
                directory.mkdir(mode=0o755, exist_ok=True)
                directory.chmod(0o755)
                dirs.add("vendor/" + directory.relative_to(destination).as_posix())
            if not info.is_dir():
                with archive.open(info) as source, target.open("xb") as output:
                    shutil.copyfileobj(source, output)
                    output.flush()
                    os.fchmod(output.fileno(), 0o644)
                    os.fsync(output.fileno())
                files.append({"path": "vendor/" + relative, "size": info.file_size,
                              "sha256": sha256_file(target)})
        root = release["archive"]["top_level_dir"]
        symlinks = []
        for library in release["libraries"].values():
            relative = f"{root}/{release['arch']['lib_subdir']}/{library['link']}"
            (destination / relative).symlink_to(library["filename"])
            symlinks.append({"path": "vendor/" + relative, "target": library["filename"]})
        return {"root": "vendor/" + root, "dirs": sorted(dirs),
                "files": sorted(files, key=lambda item: item["path"]),
                "symlinks": sorted(symlinks, key=lambda item: item["path"])}


def setup_bash(prefix, tool_version, template_version=1):
    """Render Appendix D, with the shellcheck declaration required by section 13."""
    prefix = str(prefix)
    if (not prefix.startswith("/") or ":" in prefix
            or any(ord(c) < 32 or ord(c) == 127 for c in prefix)):
        raise SDKFileError(f"invalid activation prefix: {prefix!r}")
    if template_version != 1 or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", tool_version):
        raise SDKFileError("unsupported activation template or tool version")
    quoted = prefix.replace("'", "'\\''")
    text = r'''# Generated by bootstrap-epos-sdk <VERSION>. Do not edit.
# Template version: 1
# Source this file; do not execute it:  source setup.bash
# shellcheck shell=bash
# Paths below are literal data, including quotes and shell metacharacters.
# shellcheck disable=SC2016,SC2089,SC2090

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
  printf 'setup.bash must be sourced, not executed: source %s\n' "${BASH_SOURCE[0]}" >&2
  exit 1
fi

__epos_root='<PREFIX>'
__epos_lib='<PREFIX>/vendor/EPOS_Linux_Library/lib/intel/x86_64'

if [ ! -r "${__epos_lib}/libEposCmd.so.6.8.1.0" ]; then
  printf 'EPOS SDK not found at %s; run: bootstrap-epos-sdk install\n' "${__epos_root}" >&2
  unset __epos_root __epos_lib
  return 1
fi

case ":${LD_LIBRARY_PATH-}:" in
  *":${__epos_lib}:"*) : ;;
  *) LD_LIBRARY_PATH="${__epos_lib}${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}" ;;
esac

EPOS_SDK_DIR="${__epos_root}"
EPOS_LIB_DIR="${__epos_lib}"
export EPOS_SDK_DIR EPOS_LIB_DIR LD_LIBRARY_PATH
unset __epos_root __epos_lib
'''
    return text.replace("<VERSION>", tool_version).replace("<PREFIX>", quoted).encode("utf-8")
