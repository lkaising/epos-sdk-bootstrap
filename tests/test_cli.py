"""Public CLI checks. Every potentially mutating external command fails closed."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

PROJECT = Path(__file__).resolve().parents[1]
ENTRY = PROJECT / "bootstrap-epos-sdk"


class CliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="epos-cli-tests-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.log = self.root / "forbidden-calls"
        self.prefix = self.root / "SDK directory"
        self.env = dict(os.environ)
        for key in ("EPOS_SDK_DIR", "EPOS_BOOTSTRAP_UDEV_DIR", "WSL_DISTRO_NAME",
                    "PYTHONPATH", "LD_PRELOAD", "LD_LIBRARY_PATH", "LD_AUDIT"):
            self.env.pop(key, None)
        self.env.update(PATH=str(self.bin) + ":/usr/sbin:/usr/bin:/sbin:/bin",
                        NO_COLOR="1", LC_ALL="C", PYTHONDONTWRITEBYTECODE="1",
                        CLI_TEST_LOG=str(self.log))
        for command in ("sudo", "curl", "apt-get", "groupadd", "gpasswd", "udevadm",
                        "flock", "timeout", "python3"):
            self.stub(command, '#!/bin/bash\nprintf "<<< %s" "$0" >> "$CLI_TEST_LOG"\nprintf " <%s>" "$@" >> "$CLI_TEST_LOG"\nprintf " >>>\\n" >> "$CLI_TEST_LOG"\nexit 97\n')

    def stub(self, name, text):
        path = self.bin / name
        path.write_text(text)
        path.chmod(0o755)

    def run_cli(self, *args, extra_env=None, entry=None):
        env = self.env | (extra_env or {})
        before = {str(p.relative_to(self.root)): (p.lstat().st_mode, p.lstat().st_mtime_ns, p.lstat().st_size)
                  for p in self.root.rglob("*")}
        result = subprocess.run(["/bin/bash", str(entry or ENTRY), *map(str, args)],
                                env=env, text=True, capture_output=True, timeout=15,
                                cwd=self.root)
        self.assertFalse(self.log.exists(), self.log.read_text() if self.log.exists() else "")
        self.assertFalse(self.prefix.exists(), "read-only CLI created the destination")
        after = {str(p.relative_to(self.root)): (p.lstat().st_mode, p.lstat().st_mtime_ns, p.lstat().st_size)
                 for p in self.root.rglob("*")}
        self.assertEqual(before, after, "read-only CLI modified its temporary test tree")
        self.assertNotIn("\x1b[", result.stdout + result.stderr)
        return result

    def assert_exit(self, expected, result):
        self.assertEqual(expected, result.returncode, result.stdout + result.stderr)

    def require_supported_host(self):
        info = Path("/etc/os-release").read_text() if Path("/etc/os-release").exists() else ""
        if 'ID=ubuntu' not in info or 'VERSION_ID="24.04"' not in info:
            self.skipTest("full dry-run CLI checks require Ubuntu 24.04; parser tests remain portable")

    def test_help_and_no_arguments_ignore_invalid_environment(self):
        for args in ((), ("--help",), ("-h",), ("install", "--help"), ("--help", "verify")):
            with self.subTest(args=args):
                result = self.run_cli(*args, extra_env={"EPOS_SDK_DIR": " \t", "WSL_DISTRO_NAME": "fixture"})
                self.assert_exit(0, result)
                for word in ("install", "verify", "uninstall", "--sdk-dir", "--yes", "1.0.0"):
                    self.assertIn(word, result.stdout)

    def test_help_does_not_run_host_queries(self):
        for command in ("uname", "id", "dpkg", "dpkg-query", "getent", "systemctl", "systemd-detect-virt"):
            self.stub(command, '#!/bin/bash\nprintf "%s\\n" "$0" >> "$CLI_TEST_LOG"\nexit 97\n')
        self.assert_exit(0, self.run_cli("--help"))
        self.assert_exit(0, self.run_cli())

    def test_invalid_syntax_even_with_help(self):
        cases = [("--bogus",), ("probe",), ("install", "verify"),
                 ("--sdk-dir",), ("--sdk-dir=",), ("--sdk-dir", ""),
                 ("install", "--sdk-dir", "--dry-run"), ("--", "--help"),
                 ("install", "--", "--dry-run"), ("--force",), ("--repair",),
                 ("--url=https://example.invalid/sdk.zip",)]
        for args in cases:
            with self.subTest(args=args):
                self.assert_exit(2, self.run_cli(*args))
                # A trailing help after -- remains positional and still invalid.
                self.assert_exit(2, self.run_cli(*args, "--help"))

    def test_unsupported_architecture_exits_two_for_every_command(self):
        self.stub("uname", '#!/bin/bash\nprintf "aarch64\\n"\n')
        for command in ("install", "verify", "uninstall"):
            with self.subTest(command=command):
                result = self.run_cli(command, "--dry-run", "--sdk-dir", self.prefix)
                self.assert_exit(2, result)
        self.assert_exit(0, self.run_cli("--help"))

    def test_wrong_debian_architecture(self):
        self.stub("dpkg", '#!/bin/bash\nprintf "arm64\\n"\n')
        for command in ("install", "verify", "uninstall"):
            self.assert_exit(2, self.run_cli(command, "--dry-run", "--sdk-dir", self.prefix))

    def test_flag_order_and_both_path_forms(self):
        self.require_supported_host()
        cases = [("--dry-run", "--sdk-dir", self.prefix, "uninstall"),
                 ("uninstall", "--sdk-dir=" + str(self.prefix), "--dry-run"),
                 ("--sdk-dir", self.prefix, "--dry-run", "--", "uninstall"),
                 ("uninstall", "--dry-run", "--sdk-dir", self.prefix, "--"),
                 ("-y", "uninstall", "--dry-run", "--sdk-dir", self.prefix)]
        for args in cases:
            with self.subTest(args=args):
                self.assert_exit(0, self.run_cli(*args))

    def test_empty_environment_is_usage_error(self):
        self.require_supported_host()
        for value in ("", " ", "\t\n"):
            self.assert_exit(2, self.run_cli("uninstall", "--dry-run", extra_env={"EPOS_SDK_DIR": value}))

    def test_explicit_path_overrides_environment(self):
        self.require_supported_host()
        self.assert_exit(0, self.run_cli("uninstall", "--dry-run", "--sdk-dir", self.prefix,
                                       extra_env={"EPOS_SDK_DIR": str(self.root / "different")}))
        result = self.run_cli("install", "--dry-run", "--sdk-dir", self.prefix,
                              extra_env={"EPOS_SDK_DIR": str(self.root / "different")})
        self.assert_exit(0, result)
        self.assertIn(str(self.prefix), result.stdout)
        self.assertNotIn(str(self.root / "different"), result.stdout)

    def test_environment_overrides_default(self):
        self.require_supported_host()
        result = self.run_cli("install", "--dry-run", extra_env={"EPOS_SDK_DIR": str(self.prefix)})
        self.assert_exit(0, result)
        self.assertIn(str(self.prefix), result.stdout)

    def test_metacharacters_are_inert(self):
        self.require_supported_host()
        marker = self.root / "INJECTION"
        path = self.root / "SDK ' $(touch INJECTION) `touch INJECTION` ; &"
        result = self.run_cli("install", "--dry-run", "--sdk-dir", path)
        self.assert_exit(0, result)
        self.assertIn(str(path), result.stdout)
        self.assertFalse(marker.exists())
        self.assertFalse(path.exists())

    def test_verify_yes_is_accepted_and_load_is_skipped(self):
        self.require_supported_host()
        result = self.run_cli("verify", "--dry-run", "--yes", "--sdk-dir", self.prefix)
        self.assert_exit(1, result)  # A missing installation blocks the verification plan.
        self.assertIn("skip", (result.stdout + result.stderr).lower())

    def test_populated_unowned_prefix_is_preserved(self):
        self.require_supported_host()
        foreign = self.root / "foreign"
        foreign.mkdir()
        important = foreign / "important.txt"
        important.write_text("keep me\n")
        before = important.stat()
        for command in ("install", "verify", "uninstall"):
            with self.subTest(command=command):
                result = self.run_cli(command, "--dry-run", "--yes", "--sdk-dir", foreign)
                self.assert_exit(1, result)
                self.assertEqual("keep me\n", important.read_text())
                self.assertEqual(before.st_mtime_ns, important.stat().st_mtime_ns)
        self.assertEqual([important], list(foreign.iterdir()))

    def test_wsl_install_is_refused(self):
        self.require_supported_host()
        for value in ("fixture", ""):
            self.assert_exit(2, self.run_cli("install", "--dry-run", "--sdk-dir", self.prefix,
                                           extra_env={"WSL_DISTRO_NAME": value}))

    def test_entrypoint_symlink_resolves_helpers(self):
        self.require_supported_host()
        link = self.root / "bootstrap link"
        link.symlink_to(ENTRY)
        self.assert_exit(0, self.run_cli("uninstall", "--dry-run", "--sdk-dir", self.prefix, entry=link))


class HostAndPathTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import sys
        sys.path.insert(0, str(PROJECT / 'lib'))
        import bootstrap
        cls.bootstrap = bootstrap

    def test_os_release_parser_accepts_ubuntu_point_release(self):
        values = self.bootstrap.parse_os_release('# comment\nID=ubuntu\nVERSION_ID="24.04"\nPRETTY_NAME="Ubuntu 24.04.5 LTS"\n')
        self.assertEqual('ubuntu', values['ID'])
        self.assertEqual('24.04', values['VERSION_ID'])
        self.assertEqual('Ubuntu 24.04.5 LTS', values['PRETTY_NAME'])
        self.bootstrap.validate_host(values, 'x86_64', 'amd64', 64, 1000, 'install', False, False)

    def test_os_release_contents_are_data(self):
        text = 'ID=ubuntu\nVERSION_ID=24.04\nMALICIOUS="$(touch /tmp/never-executed)"\n'
        values = self.bootstrap.parse_os_release(text)
        self.assertEqual('$(touch /tmp/never-executed)', values['MALICIOUS'])
        with self.assertRaises(self.bootstrap.HostError):
            self.bootstrap.parse_os_release('ID="unterminated')

    def test_host_failures_and_command_specific_root_rules(self):
        good = dict(os_info={'ID': 'ubuntu', 'VERSION_ID': '24.04'}, machine='x86_64',
                    deb_arch='amd64', bits=64, uid=1000, command='install', dry=False, wsl=False)
        for changes in ({'os_info': {'ID': 'linuxmint', 'ID_LIKE': 'ubuntu', 'VERSION_ID': '24.04'}},
                        {'os_info': {'ID': 'ubuntu', 'VERSION_ID': '22.04'}},
                        {'os_info': {}}, {'machine': 'Darwin'}, {'machine': 'aarch64'},
                        {'deb_arch': 'arm64'}, {'bits': 32}, {'wsl': True}, {'uid': 0}):
            with self.subTest(changes=changes), self.assertRaises(self.bootstrap.HostError):
                self.bootstrap.validate_host(**(good | changes))
        for changes in ({'uid': 0, 'dry': True}, {'uid': 0, 'command': 'verify'},
                        {'wsl': True, 'command': 'verify'}, {'wsl': True, 'command': 'uninstall'}):
            self.bootstrap.validate_host(**(good | changes))
        with self.assertRaises(self.bootstrap.HostError):
            self.bootstrap.validate_host(**(good | {'uid': 0, 'command': 'uninstall'}))

    def test_path_protection_and_canonicalization(self):
        with tempfile.TemporaryDirectory(prefix='epos-path-test-') as directory:
            root = Path(directory)
            actual = root / 'actual'
            actual.mkdir()
            link = root / 'link'
            link.symlink_to(actual, target_is_directory=True)
            self.assertEqual(actual / 'new sdk', self.bootstrap.resolve_prefix(str(link / 'new sdk')))
            with self.assertRaises(self.bootstrap.Failure):
                self.bootstrap.resolve_prefix(str(link))
            for raw in ('/', str(Path.home()), str(PROJECT), '/etc/epos-sdk', '/usr/local/epos-sdk',
                        str(root / 'a:b'), str(root / 'a\nb'), str(root / 'a\x01b')):
                with self.subTest(raw=raw), self.assertRaises(self.bootstrap.Failure):
                    self.bootstrap.resolve_prefix(raw)


if __name__ == "__main__":
    unittest.main()
