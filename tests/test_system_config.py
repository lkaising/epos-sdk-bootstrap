"""Unprivileged fixtures for the exact production registration state machine."""
import copy
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import pwd
import stat
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock
import uuid

SPEC = importlib.util.spec_from_file_location('epos_system_config', Path(__file__).resolve().parents[1] / 'lib/system_config.py')
sc = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sc)
VERSION = '6.8.1.0'


@unittest.skipIf(os.geteuid() == 0, 'fixture backend deliberately rejects root')
class SystemFixtureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='epos-system-test-')
        self.root = Path(self.tmp.name)
        self.rules = self.root / 'rules'
        self.rules.mkdir()
        self.user = pwd.getpwuid(os.getuid()).pw_name
        self.request = dict(installation_uuid=str(uuid.uuid4()), prefix=str(self.root / 'sdk'),
                            uid=os.getuid(), username=self.user, sdk_version=VERSION, prior_registration=None)
        self.state = dict(group_exists=False, members=[], primary_members=[], service_active=True,
                          reload_ok=True, events=[])
        self.write_state(self.state)
        self.backend = sc.Backend(self.rules)

    def tearDown(self):
        self.tmp.cleanup()

    def write_state(self, state):
        (self.rules / sc.STATE_NAME).write_text(json.dumps(state), encoding='utf-8')

    def read_state(self):
        return json.loads((self.rules / sc.STATE_NAME).read_text())

    def operation(self, name='configure', prior=None):
        request = dict(self.request, prior_registration=prior)
        # A forbidden subprocess fails even if a future fixture implementation
        # accidentally adds a real command.
        with mock.patch.object(sc.subprocess, 'run', side_effect=AssertionError('external command in fixture')):
            return sc.operate(name, request, self.backend, VERSION)

    def registration(self):
        return sc.read_registration(self.backend.target, True, VERSION)

    def test_install_idempotence_remove_release(self):
        result = self.operation()
        reg = result['registration']
        self.assertEqual(reg['state'], 'installed')
        self.assertFalse(reg['group_existed_before'])
        self.assertFalse(reg['membership_existed_before'])
        events = self.read_state()['events']
        self.assertLess(events.index('installing.after_dir_fsync'), events.index('before_group_add'))
        self.assertLess(events.index('after_reload'), events.index('installed.before_write'))
        before = self.backend.target.stat().st_mtime_ns
        self.assertFalse(self.operation(prior=reg)['changed'])
        self.assertEqual(self.backend.target.stat().st_mtime_ns, before)
        self.assertEqual(self.read_state()['events'], events)
        removed = self.operation('remove', reg)['registration']
        self.assertEqual(removed['state'], 'removed')
        self.assertNotIn('SUBSYSTEMS', self.backend.target.read_text())
        state = self.read_state()
        self.assertTrue(state['group_exists'])
        self.assertNotIn(self.user, state['members'])
        self.assertTrue(self.operation('release', removed)['changed'])
        self.assertIsNone(self.registration())
        self.assertFalse(self.operation('release', removed)['changed'])
        self.assertFalse(self.operation('remove', removed)['changed'])

    def test_preexisting_membership_retained(self):
        self.state.update(group_exists=True, members=[self.user])
        self.write_state(self.state)
        reg = self.operation()['registration']
        self.assertTrue(reg['membership_existed_before'])
        self.operation('remove', reg)
        self.assertIn(self.user, self.read_state()['members'])

    def test_primary_preexisting_retained(self):
        self.state.update(group_exists=True, primary_members=[self.user])
        self.write_state(self.state)
        reg = self.operation()['registration']
        self.assertTrue(reg['membership_existed_before'])
        self.operation('remove', reg)
        self.assertNotIn('before_membership_remove', self.read_state()['events'])

    def test_primary_group_conflict_after_install(self):
        reg = self.operation()['registration']
        state = self.read_state()
        state['primary_members'] = [self.user]
        self.write_state(state)
        with self.assertRaisesRegex(sc.ConfigError, 'primary group'):
            self.operation('remove', reg)
        self.assertEqual(self.registration()['state'], 'removing')
        self.assertIn(self.user, self.read_state()['members'])

    def test_missing_rules_reconstructs_original_provenance(self):
        reg = self.operation()['registration']
        self.backend.target.unlink()
        recovered = self.operation(prior=reg)['registration']
        self.assertFalse(recovered['membership_existed_before'])
        self.backend.target.unlink()
        removed = self.operation('remove', recovered)['registration']
        self.assertEqual(removed['state'], 'removed')
        self.assertNotIn(self.user, self.read_state()['members'])

    def test_missing_rules_removed_snapshot_never_recreates_or_deletes_membership(self):
        reg = self.operation()['registration']
        removed = self.operation('remove', reg)['registration']
        self.operation('release', removed)
        state = self.read_state()
        state['members'] = [self.user]
        self.write_state(state)
        self.assertFalse(self.operation('remove', removed)['changed'])
        self.assertIsNone(self.registration())
        self.assertIn(self.user, self.read_state()['members'])

    def test_acknowledged_removal_never_deletes_later_membership(self):
        reg = self.operation()['registration']
        removed = self.operation('remove', reg)['registration']
        state = self.read_state()
        state['members'] = [self.user]
        self.write_state(state)
        self.assertFalse(self.operation('remove', removed)['changed'])
        self.assertIn(self.user, self.read_state()['members'])

    def test_removed_prior_rejects_regression(self):
        reg = self.operation()['registration']
        removed = sc._with_state(reg, 'removed')
        with self.assertRaisesRegex(sc.ConfigError, 'regressed'):
            self.operation('remove', removed)
        self.assertEqual(self.registration(), reg)

    def test_removal_is_terminal_for_configure(self):
        reg = self.operation()['registration']
        removed = self.operation('remove', reg)['registration']
        with self.assertRaisesRegex(sc.ConfigError, 'finish uninstall'):
            self.operation(prior=removed)
        self.backend.target.unlink()
        with self.assertRaisesRegex(sc.ConfigError, 'finish uninstall'):
            self.operation(prior=removed)

    def test_unclaimed_removal_has_no_effect(self):
        self.assertEqual(self.operation('remove'), {'ok': True, 'changed': False, 'registration': None})
        self.assertEqual(self.read_state(), self.state)

    def test_missing_membership_repair_preserves_provenance(self):
        reg = self.operation()['registration']
        state = self.read_state()
        state['members'] = []
        self.write_state(state)
        repaired = self.operation(prior=reg)['registration']
        self.assertEqual(repaired, reg)
        self.assertIn(self.user, self.read_state()['members'])

    def test_other_uuid_and_provenance_refused_before_mutation(self):
        reg = self.operation()['registration']
        state = self.read_state()
        self.request['installation_uuid'] = str(uuid.uuid4())
        with self.assertRaisesRegex(sc.ConfigError, 'belongs to'):
            self.operation()
        self.assertEqual(self.read_state(), state)
        self.request['installation_uuid'] = reg['installation_uuid']
        prior = dict(reg, group_existed_before=True)
        with self.assertRaisesRegex(sc.ConfigError, 'provenance conflict'):
            self.operation(prior=prior)
        self.assertEqual(self.read_state(), state)

    def test_replacement_registration_survives_stale_release(self):
        reg = self.operation()['registration']
        removed = self.operation('remove', reg)['registration']
        self.operation('release', removed)
        old_request = self.request
        self.request = dict(old_request, installation_uuid=str(uuid.uuid4()), prefix=str(self.root / 'new-sdk'))
        new_reg = self.operation()['registration']
        self.request = old_request
        with self.assertRaisesRegex(sc.ConfigError, 'belongs to'):
            self.operation('release', removed)
        self.assertEqual(self.registration(), new_reg)
        self.assertIn(self.user, self.read_state()['members'])

    def test_foreign_rules_same_uuid_and_metadata_refused(self):
        self.operation()
        original = self.backend.target.read_bytes()
        for data in (original + b'# extra\n', original.replace(b'0660', b'0666'), b'# foreign\n'):
            self.backend.target.write_bytes(data)
            with self.assertRaises(sc.ConfigError):
                self.operation()
            self.assertEqual(self.backend.target.read_bytes(), data)
        self.backend.target.write_bytes(original)
        self.backend.target.chmod(0o600)
        with self.assertRaisesRegex(sc.ConfigError, '0644'):
            self.operation()

    def test_symlink_hardlink_and_fifo_registration_refused(self):
        self.operation()
        saved = self.root / 'saved'
        self.backend.target.rename(saved)
        self.backend.target.symlink_to(saved)
        with self.assertRaises(sc.ConfigError):
            self.operation()
        self.backend.target.unlink()
        os.link(saved, self.backend.target)
        with self.assertRaisesRegex(sc.ConfigError, 'link count'):
            self.operation()
        self.backend.target.unlink()
        os.mkfifo(self.backend.target)
        with self.assertRaises(sc.ConfigError):
            self.operation()

    def test_publication_faults_never_mutate_accounts_before_durability(self):
        points = ['before_write', 'after_write', 'after_file_fsync', 'before_replace', 'after_replace', 'after_dir_fsync']
        for point in points:
            with self.subTest(point=point):
                if self.backend.target.exists():
                    self.backend.target.unlink()
                state = copy.deepcopy(self.state)
                state['fail_at'] = 'installing.' + point
                self.write_state(state)
                with self.assertRaisesRegex(sc.ConfigError, 'injected failure'):
                    self.operation()
                self.assertFalse(self.read_state()['group_exists'])
                current = self.registration()
                self.assertTrue(current is None or current['state'] == 'installing')
                self.assertFalse(list(self.rules.glob('.epos-sdk-bootstrap-*.tmp')))
                state = self.read_state()
                state.pop('fail_at')
                self.write_state(state)
                self.assertEqual(self.operation()['registration']['state'], 'installed')

    def test_account_reload_and_acknowledgement_faults_resume(self):
        points = ['before_group_add', 'after_group_add', 'before_membership_add', 'after_membership_add',
                  'before_reload', 'after_reload', 'installed.before_write', 'installed.after_write',
                  'installed.after_replace', 'installed.after_dir_fsync']
        for point in points:
            with self.subTest(point=point):
                if self.backend.target.exists():
                    self.backend.target.unlink()
                state = copy.deepcopy(self.state)
                state['fail_at'] = point
                self.write_state(state)
                with self.assertRaisesRegex(sc.ConfigError, 'injected failure'):
                    self.operation()
                reg = self.registration()
                self.assertIsNotNone(reg)
                self.assertFalse(reg['membership_existed_before'])
                state = self.read_state()
                state.pop('fail_at')
                self.write_state(state)
                self.assertEqual(self.operation(prior=reg)['registration']['state'], 'installed')

    def test_remove_faults_resume_without_losing_provenance(self):
        for point in ['removing.before_write', 'removing.after_replace', 'removing.after_dir_fsync',
                      'before_membership_remove', 'after_membership_remove', 'before_reload', 'after_reload',
                      'removed.before_write', 'removed.after_replace']:
            with self.subTest(point=point):
                if self.backend.target.exists():
                    self.backend.target.unlink()
                self.write_state(copy.deepcopy(self.state))
                reg = self.operation()['registration']
                state = self.read_state()
                state['fail_at'] = point
                self.write_state(state)
                with self.assertRaisesRegex(sc.ConfigError, 'injected failure'):
                    self.operation('remove', reg)
                self.assertIsNotNone(self.registration())
                state = self.read_state()
                state.pop('fail_at')
                self.write_state(state)
                result = self.operation('remove', reg)
                self.assertEqual(result['registration']['state'], 'removed')
                self.assertNotIn(self.user, self.read_state()['members'])

    def test_failed_reload_retries_identical_install_and_removal_rules(self):
        self.state['reload_ok'] = False
        self.write_state(self.state)
        with self.assertRaisesRegex(sc.ConfigError, 'reload failed'):
            self.operation()
        reg = self.registration()
        self.assertEqual(reg['state'], 'installing')
        state = self.read_state()
        state['reload_ok'] = True
        self.write_state(state)
        installed = self.operation(prior=reg)['registration']
        state = self.read_state()
        state['reload_ok'] = False
        self.write_state(state)
        with self.assertRaisesRegex(sc.ConfigError, 'reload failed'):
            self.operation('remove', installed)
        removing = self.registration()
        self.assertEqual(removing['state'], 'removing')
        state = self.read_state()
        state['reload_ok'] = True
        self.write_state(state)
        self.assertEqual(self.operation('remove', removing)['registration']['state'], 'removed')
        self.assertEqual(self.read_state()['events'].count('before_reload'), 4)

    def test_safe_abandoned_temporary_cleanup_and_suspicious_refusal(self):
        temp = self.rules / ('.epos-sdk-bootstrap-' + self.request['installation_uuid'] + '-abc.tmp')
        temp.write_text('interrupted')
        self.operation()
        self.assertFalse(temp.exists())
        temp.symlink_to(self.backend.target)
        with self.assertRaisesRegex(sc.ConfigError, 'suspicious registration temporary'):
            self.operation()
        self.assertTrue(temp.is_symlink())

    def test_lock_timeout_no_shared_mutation(self):
        state = self.read_state()
        state['lock_timeout'] = 0.05
        self.write_state(state)
        fd = os.open(self.rules, os.O_RDONLY | os.O_DIRECTORY)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaisesRegex(sc.ConfigError, 'timed out'):
                self.operation()
        finally:
            os.close(fd)
        self.assertEqual(self.read_state(), state)
        self.assertIsNone(self.registration())

    def test_two_prefix_contenders_only_one_mutates(self):
        requests = [self.request, dict(self.request, installation_uuid=str(uuid.uuid4()), prefix=str(self.root / 'sdk two'))]
        command = ['/usr/bin/python3', '-I', '-B', str(Path(sc.__file__))]
        # subprocesses execute only the explicitly unprivileged adapter.
        processes = [subprocess.Popen(command + ['configure', '--fixture-dir', str(self.rules), '--request-json', json.dumps(req)],
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for req in requests]
        outputs = [p.communicate(timeout=10) for p in processes]
        self.assertEqual(sorted(p.returncode for p in processes), [0, 1], outputs)
        state = self.read_state()
        self.assertEqual(state['events'].count('before_group_add'), 1)
        self.assertEqual(state['events'].count('before_membership_add'), 1)
        self.assertEqual(state['events'].count('before_reload'), 1)
        self.assertEqual(self.registration()['state'], 'installed')

    def test_directory_identity_rechecked_after_lock(self):
        original_flock = sc.fcntl.flock

        def replace_after_lock(fd, flags):
            original_flock(fd, flags)
            self.rules.rename(self.root / 'old-rules')
            self.rules.mkdir()

        with mock.patch.object(sc.fcntl, 'flock', side_effect=replace_after_lock):
            with self.assertRaisesRegex(sc.ConfigError, 'changed after locking'):
                self.operation()
        self.assertFalse(self.backend.target.exists())

    def test_release_interruption_is_repeatable(self):
        for point in ('before_release', 'after_release'):
            with self.subTest(point=point):
                self.write_state(copy.deepcopy(self.state))
                reg = self.operation()['registration']
                removed = self.operation('remove', reg)['registration']
                state = self.read_state()
                state['fail_at'] = point
                self.write_state(state)
                with self.assertRaisesRegex(sc.ConfigError, 'injected failure'):
                    self.operation('release', removed)
                state = self.read_state()
                state.pop('fail_at')
                self.write_state(state)
                self.operation('release', removed)
                self.assertIsNone(self.registration())

    def test_install_versus_uninstall_serialized(self):
        reg = self.operation()['registration']
        request = dict(self.request, prior_registration=reg)
        command = ['/usr/bin/python3', '-I', '-B', str(Path(sc.__file__))]
        processes = [subprocess.Popen(command + [operation, '--fixture-dir', str(self.rules),
                                                '--request-json', json.dumps(request)],
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                     for operation in ('configure', 'remove')]
        outputs = [p.communicate(timeout=10) for p in processes]
        self.assertEqual(processes[1].returncode, 0, outputs)
        self.assertIn(processes[0].returncode, (0, 1), outputs)
        self.assertEqual(self.registration()['state'], 'removed')
        self.assertNotIn(self.user, self.read_state()['members'])
        self.assertEqual(self.read_state()['events'].count('before_membership_remove'), 1)

    def test_fixture_directory_and_state_symlinks_refused(self):
        alias = self.root / 'alias'
        alias.symlink_to(self.rules, target_is_directory=True)
        with self.assertRaisesRegex(sc.ConfigError, 'symlink'):
            sc.validate_fixture_dir(alias)
        source = self.rules / sc.STATE_NAME
        source.rename(self.root / 'state')
        source.symlink_to(self.root / 'state')
        with self.assertRaises(sc.ConfigError):
            self.operation()

    def test_production_backend_cannot_be_used_unprivileged(self):
        with self.assertRaisesRegex(sc.ConfigError, 'effective UID 0'):
            sc.Backend()
        with mock.patch.object(sc.os, 'geteuid', return_value=0):
            with self.assertRaisesRegex(sc.ConfigError, 'rejects fixture'):
                sc.Backend(self.rules)

    def test_registration_schema_types_uuid_and_prefix(self):
        reg = self.operation()['registration']
        alterations = {'schema_version': True, 'uid': True, 'username': 'no-such-epos-account',
                       'installation_uuid': 'invalid', 'group': 'root', 'group_existed_before': 1,
                       'membership_existed_before': 'no', 'reload_pending': True, 'state': 'other',
                       'sdk_version': 'latest', 'prefix': '/etc/sdk'}
        for key, value in alterations.items():
            with self.subTest(key=key), self.assertRaises(sc.ConfigError):
                sc.validate_registration(dict(reg, **{key: value}), VERSION)
        for prefix in ('/', str(Path.home()), str(self.root) + '/a/../sdk', str(self.root / 'sdk:other'),
                       str(self.root / 'sdk\nother'), str(Path(sc.__file__).resolve().parents[1])):
            with self.subTest(prefix=prefix), self.assertRaises(sc.ConfigError):
                sc.validate_registration(dict(reg, prefix=prefix), VERSION)
        with self.assertRaises(sc.ConfigError):
            sc.validate_registration(dict(reg, extra='unknown'), VERSION)
        duplicate = sc.canonical_rules(reg).replace(b'"group":"epos"', b'"group":"epos","group":"epos"')
        for raw in (duplicate, sc.canonical_rules(reg) + (sc.MARKER + '{}\n').encode(), b'{}', b'\xff'):
            with self.assertRaises(sc.ConfigError):
                sc.parse_rules(raw, VERSION)

    def test_request_rejects_extra_missing_duplicate_and_mismatched_identity(self):
        for request in (dict(self.request, shell='echo unsafe'),
                        {key: value for key, value in self.request.items() if key != 'uid'},
                        dict(self.request, uid=True), dict(self.request, prior_registration=[])):
            with self.assertRaises(sc.ConfigError):
                sc.validate_request(request, VERSION)
        with self.assertRaisesRegex(sc.ConfigError, 'duplicate JSON key'):
            sc.parse_json('{"uid":1000,"uid":1001}')
        reg = self.operation()['registration']
        with self.assertRaisesRegex(sc.ConfigError, 'identities conflict'):
            sc.validate_request(dict(self.request, installation_uuid=str(uuid.uuid4()), prior_registration=reg), VERSION)

    def test_release_requires_exact_removed_snapshot(self):
        reg = self.operation()['registration']
        with self.assertRaisesRegex(sc.ConfigError, 'requires acknowledged'):
            self.operation('release', reg)
        removed = sc._with_state(reg, 'removed')
        with self.assertRaisesRegex(sc.ConfigError, 'differs'):
            self.operation('release', removed)


class ProductionPredicateTests(unittest.TestCase):
    def test_uid_gid_mode_type_link_count(self):
        metadata = dict(st_mode=stat.S_IFREG | 0o644, st_uid=0, st_gid=0, st_nlink=1)
        self.assertTrue(sc.valid_file_metadata(types.SimpleNamespace(**metadata)))
        for key, value in [('st_mode', stat.S_IFLNK | 0o644), ('st_mode', stat.S_IFREG | 0o666),
                           ('st_uid', 1000), ('st_gid', 1000), ('st_nlink', 2)]:
            self.assertFalse(sc.valid_file_metadata(types.SimpleNamespace(**dict(metadata, **{key: value}))))


if __name__ == '__main__':
    unittest.main()
