"""Synthetic ZIPs only. No vendor download, library load, or host mutation."""

import copy
import hashlib
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
import warnings
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import sdk_files as sdk


def elf(machine=62):
    return b"\x7fELF\x02\x01" + bytes(12) + machine.to_bytes(2, "little") + b"fixture only"


def entry(name, kind=stat.S_IFREG, creator=3, attrs=None):
    item = zipfile.ZipInfo(name)
    item.create_system = creator
    item.external_attr = attrs if attrs is not None else (kind | 0o777) << 16
    return item


def make_fixture(path, extra=(), dos=False):
    release = copy.deepcopy(sdk.load_release())
    root = release["archive"]["top_level_dir"]
    items = [(root + "/EULA.txt", b"test terms"),
             (root + "/include/Definitions.h", b"test header"),
             (root + "/install.sh", b"never execute"),
             (root + "/lib/arm/v8/keep.txt", b"retain other architectures")]
    for library in release["libraries"].values():
        data = elf() + library["filename"].encode()
        library["sha256"] = hashlib.sha256(data).hexdigest()
        items.append((f"{root}/{release['arch']['lib_subdir']}/{library['filename']}", data))
    with warnings.catch_warnings(), zipfile.ZipFile(path, "w") as archive:
        warnings.simplefilter("ignore", UserWarning)
        archive.writestr(entry(root + "/", stat.S_IFDIR, 0 if dos else 3,
                              0x10 if dos else None), b"")
        for name, data in items:
            archive.writestr(entry(name, creator=0 if dos else 3,
                                  attrs=0x20 if dos else None), data)
        for item, data in extra:
            archive.writestr(item, data)
    release["archive"]["size_bytes"] = path.stat().st_size
    release["archive"]["sha256"] = sdk.sha256_file(path)
    return release


class SDKFilesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.archive = self.root / "fixture.zip"
        self.release = make_fixture(self.archive)

    def reject_members(self, extra):
        release = make_fixture(self.archive, extra)
        destination = self.root / "vendor"
        with self.assertRaises(sdk.SDKFileError):
            sdk.extract_archive(self.archive, destination, release)
        self.assertFalse(destination.exists(), "rejection must precede extraction")

    def test_pin_and_inventory_and_modes(self):
        original_umask = os.umask(0o077)
        self.addCleanup(os.umask, original_umask)
        payload = sdk.extract_archive(self.archive, self.root / "vendor", self.release)
        self.assertEqual(len(payload["files"]), 6)
        self.assertEqual(len(payload["symlinks"]), 2)
        for item in payload["files"]:
            path = self.root / item["path"]
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644)
            self.assertEqual(item["sha256"], sdk.sha256_file(path))
        for relative in payload["dirs"]:
            if relative != "downloads":
                self.assertEqual(stat.S_IMODE((self.root / relative).stat().st_mode), 0o755)
        for item in payload["symlinks"]:
            self.assertEqual(os.readlink(self.root / item["path"]), item["target"])
            self.assertTrue((self.root / item["path"]).is_file())

    def test_dos_creator_exception(self):
        release = make_fixture(self.archive, dos=True)
        self.assertEqual(len(sdk.validate_archive(self.archive, release)), 7)

    def test_dos_readonly_file_exception(self):
        release = make_fixture(self.archive, [(entry("EPOS_Linux_Library/readonly", creator=0, attrs=0x21), b"x")])
        sdk.validate_archive(self.archive, release)

    def test_dos_exception_is_narrow(self):
        for creator, attrs, name in [(3, 0x20, "file"), (0, 0x28, "volume"),
                                      (0, 0x400, "device"), (0, 0x10, "file"),
                                      (0, 0x20, "dir/"), (0, 0x22, "hidden")]:
            with self.subTest(creator=creator, attrs=attrs):
                self.reject_members([(entry("EPOS_Linux_Library/" + name, creator=creator, attrs=attrs), b"")])

    def test_path_rejections(self):
        for path in ("/tmp/escape", "EPOS_Linux_Library/../escape", "OTHER/file",
                     "EPOS_Linux_Library//file", "EPOS_Linux_Library/./file",
                     "EPOS_Linux_Library/dir\\file", "EPOS_Linux_Library/a\nfile"):
            with self.subTest(path=path):
                self.reject_members([(entry(path), b"x")])

    def test_special_types(self):
        for kind in (stat.S_IFLNK, stat.S_IFIFO, stat.S_IFSOCK, stat.S_IFCHR, stat.S_IFBLK):
            with self.subTest(kind=kind):
                self.reject_members([(entry("EPOS_Linux_Library/special", kind), b"x")])

    def test_duplicate_and_case_collision(self):
        for name in ("EULA.txt", "eula.TXT", "Include/other.h"):
            with self.subTest(name=name):
                self.reject_members([(entry("EPOS_Linux_Library/" + name), b"x")])

    def test_file_as_parent(self):
        self.reject_members([(entry("EPOS_Linux_Library/parent"), b"x"),
                             (entry("EPOS_Linux_Library/parent/child"), b"x")])

    def test_archive_cannot_supply_generated_link(self):
        self.reject_members([(entry("EPOS_Linux_Library/lib/intel/x86_64/libEposCmd.so"), b"x")])

    def test_directory_payload_rejected(self):
        self.reject_members([(entry("EPOS_Linux_Library/data/", stat.S_IFDIR), b"x")])

    def test_size_hash_and_html_rejected(self):
        bad = copy.deepcopy(self.release)
        bad["archive"]["size_bytes"] += 1
        with self.assertRaisesRegex(sdk.SDKFileError, "size mismatch"):
            sdk.check_archive(self.archive, bad)
        bad["archive"]["size_bytes"] -= 1
        bad["archive"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(sdk.SDKFileError, "SHA-256 mismatch"):
            sdk.check_archive(self.archive, bad)
        self.archive.write_bytes(b"<html>error</html>")
        with self.assertRaisesRegex(sdk.SDKFileError, "size mismatch"):
            sdk.extract_archive(self.archive, self.root / "vendor", self.release)
        self.assertFalse((self.root / "vendor").exists())

    def test_library_hash_before_extraction(self):
        self.release["libraries"]["epos"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(sdk.SDKFileError, "library SHA-256"):
            sdk.extract_archive(self.archive, self.root / "vendor", self.release)
        self.assertFalse((self.root / "vendor").exists())

    def test_required_file(self):
        self.release["required_members"].append("not-present")
        with self.assertRaisesRegex(sdk.SDKFileError, "required archive file"):
            sdk.validate_archive(self.archive, self.release)

    def test_elf_identity(self):
        native = self.root / "fake.so"
        native.write_bytes(elf())
        sdk.check_elf(native)
        native.write_bytes(elf(183))
        with self.assertRaisesRegex(sdk.SDKFileError, "machine=183.*x86_64"):
            sdk.check_elf(native)
        native.write_bytes(b"short")
        with self.assertRaisesRegex(sdk.SDKFileError, "truncated ELF"):
            sdk.check_elf(native)

    def test_destination_and_archive_links(self):
        destination = self.root / "vendor"
        destination.symlink_to(self.root / "outside", target_is_directory=True)
        with self.assertRaisesRegex(sdk.SDKFileError, "symlink"):
            sdk.extract_archive(self.archive, destination, self.release)
        alias = self.root / "alias.zip"
        alias.symlink_to(self.archive)
        with self.assertRaisesRegex(sdk.SDKFileError, "regular file"):
            sdk.check_archive(alias, self.release)


class ActivationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "SDK spaces ' $(touch INJECTED) `touch INJECTED2`"
        self.lib = self.root / "vendor/EPOS_Linux_Library/lib/intel/x86_64"
        self.lib.mkdir(parents=True)
        (self.lib / "libEposCmd.so.6.8.1.0").write_text("synthetic")
        self.setup = self.root / "setup.bash"
        self.setup.write_bytes(sdk.setup_bash(self.root, "1.0.0"))

    def bash(self, command, *args, **kwargs):
        return subprocess.run(["/bin/bash", "-c", command, "test", str(self.setup), *args],
                              cwd=self.temp.name, text=True, capture_output=True, check=False, **kwargs)

    def test_safe_repeat_and_no_empty_entry(self):
        result = self.bash('unset LD_LIBRARY_PATH; source "$1"; source "$1"; printf "%s\\n%s\\n%s\\n" "$EPOS_SDK_DIR" "$EPOS_LIB_DIR" "$LD_LIBRARY_PATH"')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), [str(self.root), str(self.lib), str(self.lib)])
        self.assertFalse((Path(self.temp.name) / "INJECTED").exists())
        self.assertFalse((Path(self.temp.name) / "INJECTED2").exists())

    def test_preserves_nonempty_path(self):
        result = self.bash('LD_LIBRARY_PATH=/somewhere; source "$1"; source "$1"; printf "%s" "$LD_LIBRARY_PATH"')
        self.assertEqual(result.stdout, str(self.lib) + ":/somewhere")

    def test_direct_execution_refused(self):
        result = subprocess.run(["/bin/bash", str(self.setup)], capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 1)
        self.assertIn("must be sourced", result.stderr)

    def test_missing_library_returns_without_exit(self):
        (self.lib / "libEposCmd.so.6.8.1.0").unlink()
        result = self.bash('source "$1"; status=$?; printf "survived %s" "$status"')
        self.assertEqual(result.stdout, "survived 1")

    def test_deterministic_and_version_preserved(self):
        self.assertEqual(self.setup.read_bytes(), sdk.setup_bash(self.root, "1.0.0"))
        self.assertNotEqual(self.setup.read_bytes(), sdk.setup_bash(self.root, "1.1.0"))

    def test_invalid_prefix_and_template(self):
        for path in ("/some:where", "/some\nwhere", "relative"):
            with self.assertRaises(sdk.SDKFileError):
                sdk.setup_bash(path, "1.0.0")
        with self.assertRaises(sdk.SDKFileError):
            sdk.setup_bash(self.root, "1.0.0", 2)

    def test_shell_static_checks(self):
        result = subprocess.run(["/bin/bash", "-n", str(self.setup)], capture_output=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        import shutil
        if shutil.which("shellcheck"):
            result = subprocess.run(["shellcheck", "-x", str(self.setup)], capture_output=True, check=False)
            self.assertEqual(result.returncode, 0, result.stdout)


if __name__ == "__main__":
    unittest.main()
