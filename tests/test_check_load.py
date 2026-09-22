"""Exercise the checker with mock native handles, never vendor libraries."""

import argparse
import builtins
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import check_load


class NativeCheckTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "SDK with spaces"
        self.root.mkdir()
        self.args = argparse.Namespace(lib_dir=str(self.root), symbol=list(check_load.SYMBOLS), json=True)
        for kind in ("epos", "ftdi"):
            filename = check_load.DEFAULTS[kind + "_filename"]
            data = f"synthetic {kind}, never native code".encode()
            (self.root / filename).write_bytes(data)
            setattr(self.args, kind + "_filename", filename)
            setattr(self.args, kind + "_sha256", hashlib.sha256(data).hexdigest())
        self.epos = str(self.root / self.args.epos_filename)
        self.ftdi = str(self.root / self.args.ftdi_filename)
        self.maps = self.map_line(self.ftdi) + self.map_line(self.epos)
        self.real_open = builtins.open

    @staticmethod
    def map_line(path):
        return f"7000-8000 r-xp 00000000 08:01 123 {path}\n"

    def fake_open(self, path, *args, **kwargs):
        if str(path) == "/proc/self/maps":
            return io.StringIO(self.maps)
        return self.real_open(path, *args, **kwargs)

    def test_load_order_and_resolve_without_calls(self):
        ftdi = mock.Mock()
        epos = mock.Mock()
        with mock.patch.object(check_load.ctypes, "CDLL", side_effect=[ftdi, epos]) as load, \
                mock.patch("builtins.open", side_effect=self.fake_open):
            report = check_load.check(self.args)
        self.assertTrue(report["ok"], report)
        self.assertEqual(load.call_args_list, [mock.call(self.ftdi, mode=check_load.ctypes.RTLD_GLOBAL),
                                              mock.call(self.epos)])
        self.assertTrue(report["maps_confirmed"])
        for name in self.args.symbol:
            getattr(epos, name).assert_not_called()
            self.assertTrue(report["symbols"][name])

    def test_both_hashes_precede_any_load(self):
        for kind in ("epos", "ftdi"):
            with self.subTest(kind=kind):
                original = getattr(self.args, kind + "_sha256")
                setattr(self.args, kind + "_sha256", "0" * 64)
                with mock.patch.object(check_load.ctypes, "CDLL") as load:
                    report = check_load.check(self.args)
                self.assertFalse(report["ok"])
                self.assertIn("SHA-256 mismatch", report["error"])
                load.assert_not_called()
                setattr(self.args, kind + "_sha256", original)

    def test_load_errors_are_json_failures(self):
        with mock.patch.object(check_load.ctypes, "CDLL", side_effect=OSError("missing dependency")):
            report = check_load.check(self.args)
        self.assertFalse(report["ok"])
        self.assertIn("load FTDI", report["error"])
        self.assertIn("missing dependency", report["error"])

    def test_wrong_mapped_path_names_actual_path(self):
        foreign = "/usr/lib/libftd2xx.so.1.4.8"
        self.maps = self.map_line(foreign) + self.map_line(self.epos)
        with mock.patch.object(check_load.ctypes, "CDLL"), \
                mock.patch("builtins.open", side_effect=self.fake_open):
            report = check_load.check(self.args)
        self.assertFalse(report["ok"])
        self.assertIn(foreign, report["error"])

    def test_extra_foreign_library_fails(self):
        self.maps += self.map_line("/cwd/libftd2xx.so")
        with self.assertRaisesRegex(ValueError, "/cwd/libftd2xx.so"):
            check_load.mapped_paths(self.maps, self.epos, self.ftdi)

    def test_missing_mapping_fails(self):
        with self.assertRaisesRegex(ValueError, "expected library not mapped"):
            check_load.mapped_paths(self.map_line(self.epos), self.epos, self.ftdi)

    def test_deleted_mapping_fails(self):
        with self.assertRaisesRegex(ValueError, "deleted"):
            check_load.mapped_paths(self.map_line(self.epos) + self.map_line(self.ftdi + " (deleted)"),
                                    self.epos, self.ftdi)

    def test_missing_export(self):
        epos = mock.Mock(spec=["VCS_OpenDevice"])
        with mock.patch.object(check_load.ctypes, "CDLL", side_effect=[mock.Mock(), epos]), \
                mock.patch("builtins.open", side_effect=self.fake_open):
            report = check_load.check(self.args)
        self.assertFalse(report["ok"])
        self.assertIn("VCS_CloseDevice", report["error"])
        epos.VCS_OpenDevice.assert_not_called()

    def test_missing_file_report(self):
        Path(self.epos).unlink()
        with mock.patch.object(check_load.ctypes, "CDLL") as load:
            report = check_load.check(self.args)
        self.assertFalse(report["ok"])
        self.assertIn(self.epos, report["error"])
        load.assert_not_called()

    def test_symlink_file_refused(self):
        Path(self.epos).unlink()
        Path(self.epos).symlink_to(self.ftdi)
        with mock.patch.object(check_load.ctypes, "CDLL") as load:
            report = check_load.check(self.args)
        self.assertFalse(report["ok"])
        self.assertIn("regular file", report["error"])
        load.assert_not_called()

    def test_bad_arguments_do_not_load(self):
        self.args.ftdi_filename = "../outside.so"
        with mock.patch.object(check_load.ctypes, "CDLL") as load:
            report = check_load.check(self.args)
        self.assertFalse(report["ok"])
        self.assertIn("invalid ftdi filename", report["error"])
        load.assert_not_called()

    def test_isolated_helper_reports_failure_without_cache(self):
        helper = Path(check_load.__file__).resolve()
        before = set(self.root.iterdir())
        result = subprocess.run(["/usr/bin/python3", "-I", "-B", str(helper),
                                 "--lib-dir", str(self.root), "--json"],
                                env={"PATH": "/usr/bin:/bin", "HOME": self.temp.name,
                                     "LC_ALL": "C", "PYTHONDONTWRITEBYTECODE": "1"},
                                cwd=self.temp.name, capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertFalse(report["ok"])
        self.assertIn("SHA-256 mismatch", report["error"])
        self.assertEqual(set(self.root.iterdir()), before)


if __name__ == "__main__":
    unittest.main()
