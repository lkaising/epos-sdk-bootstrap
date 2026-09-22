#!/usr/bin/python3
"""Locked, durable EPOS registration and account changes.

This file deliberately imports no project modules: sudo runs it with -I -B.
Fixture state is caller-owned fixture-state.json. No fixture action calls an
account command, sudo, apt, or udev. See tests/test_system_config.py for examples.
"""
import argparse
import contextlib
import fcntl
import grp
import json
import os
from pathlib import Path
import pwd
import re
import stat
import subprocess
import sys
import tempfile
import time
import uuid

RULE_NAME = '99-epos-sdk-bootstrap.rules'
RULE_DIR = Path('/etc/udev/rules.d')
STATE_NAME = 'fixture-state.json'
MARKER = '# epos-sdk-bootstrap-registration: '
COMMENTS = '# Managed by bootstrap-epos-sdk. Do not edit.\n# Remove it with: bootstrap-epos-sdk uninstall\n'
USB_RULES = ('SUBSYSTEMS=="usb", ATTRS{idVendor}=="0403", ATTRS{idProduct}=="a8b0", GROUP="epos", MODE="0660"\n'
             'SUBSYSTEMS=="usb", ATTRS{idVendor}=="24e7", ATTRS{idProduct}=="3b01", GROUP="epos", MODE="0660"\n')
IDENTITY = ('installation_uuid', 'prefix', 'uid', 'username', 'sdk_version')
PROVENANCE = ('group', 'group_existed_before', 'membership_existed_before')
REG_KEYS = set(IDENTITY + PROVENANCE + ('schema_version', 'state', 'reload_pending'))
STATES = {'installing': True, 'installed': False, 'removing': True, 'removed': False}
TEMP_PATTERN = re.compile(r'^\.epos-sdk-bootstrap-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}-[A-Za-z0-9_-]+\.tmp$')
ENV = {'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LC_ALL': 'C'}


class ConfigError(ValueError):
    """Invalid input, conflicting ownership, or incomplete operation."""


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ConfigError('duplicate JSON key: ' + key)
        result[key] = value
    return result


def parse_json(text):
    try:
        return json.loads(text, object_pairs_hook=_pairs)
    except (ValueError, UnicodeError) as exc:
        raise ConfigError('invalid JSON: ' + str(exc)) from exc


def release_version():
    path = Path(__file__).resolve().parent.parent / 'config/sdk-release.json'
    data = parse_json(path.read_text(encoding='utf-8'))
    if type(data) is not dict or type(data.get('sdk_version')) is not str or data.get('schema_version') != 1:
        raise ConfigError(f'invalid release manifest: {path}')
    return data['sdk_version']


def _prefix(value, account):
    if not isinstance(value, str) or not value or not os.path.isabs(value):
        raise ConfigError('prefix must be an absolute path')
    if ':' in value or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ConfigError('prefix contains a colon or control character')
    p = Path(value)
    if str(p) != value or str(p.resolve()) != value or p.is_symlink():
        raise ConfigError(f'prefix is not canonical or is a symlink: {value}')
    home = Path(account.pw_dir).resolve()
    project = Path(__file__).resolve().parent.parent
    if p == Path('/') or p == home or p in home.parents or p == project or p in project.parents:
        raise ConfigError(f'unsafe prefix: {value}')
    for root in ('/etc', '/usr', '/bin', '/sbin', '/lib', '/lib64', '/boot', '/dev', '/proc', '/sys', '/run', '/var'):
        if p == Path(root) or Path(root) in p.parents:
            raise ConfigError(f'system directory cannot be a prefix: {value}')
    if p.exists() and (not p.is_dir() or p.stat().st_uid != account.pw_uid):
        raise ConfigError(f'prefix must be a directory owned by UID {account.pw_uid}: {value}')


def _identity(obj, sdk_version=None):
    if type(obj.get('uid')) is not int or obj['uid'] <= 0:
        raise ConfigError('uid must be a nonzero integer')
    if type(obj.get('username')) is not str:
        raise ConfigError('username must be a string')
    try:
        account = pwd.getpwnam(obj['username'])
    except KeyError as exc:
        raise ConfigError('unknown account: ' + obj['username']) from exc
    if account.pw_uid != obj['uid'] or pwd.getpwuid(obj['uid']).pw_name != obj['username']:
        raise ConfigError('UID and username do not match the account database')
    ident = obj.get('installation_uuid')
    try:
        if type(ident) is not str or str(uuid.UUID(ident)) != ident:
            raise ValueError('noncanonical UUID')
    except (ValueError, AttributeError) as exc:
        raise ConfigError('invalid installation UUID') from exc
    if obj.get('sdk_version') != (sdk_version or release_version()):
        raise ConfigError('unsupported SDK release')
    _prefix(obj.get('prefix'), account)


def validate_registration(obj, sdk_version=None):
    if type(obj) is not dict or set(obj) != REG_KEYS:
        raise ConfigError('registration must contain exactly the Appendix C keys')
    if type(obj['schema_version']) is not int or obj['schema_version'] != 1:
        raise ConfigError('unsupported registration schema; upgrade the tool')
    _identity(obj, sdk_version)
    if obj['group'] != 'epos':
        raise ConfigError('registration group must be epos')
    for key in ('group_existed_before', 'membership_existed_before', 'reload_pending'):
        if type(obj[key]) is not bool:
            raise ConfigError(key + ' must be boolean')
    if obj['membership_existed_before'] and not obj['group_existed_before']:
        raise ConfigError('membership provenance requires a preexisting group')
    if type(obj['state']) is not str or obj['state'] not in STATES or obj['reload_pending'] != STATES[obj['state']]:
        raise ConfigError('invalid registration state/reload_pending combination')
    return obj


def same_identity(a, b):
    return all(a[k] == b[k] for k in IDENTITY)


def same_provenance(a, b):
    return all(a[k] == b[k] for k in PROVENANCE)


def validate_request(obj, sdk_version=None):
    if type(obj) is not dict or set(obj) != set(IDENTITY) | {'prior_registration'}:
        raise ConfigError('request must contain exactly identity and prior_registration')
    _identity(obj, sdk_version)
    prior = obj['prior_registration']
    if prior is not None:
        validate_registration(prior, sdk_version)
        if not same_identity(obj, prior):
            raise ConfigError('request and saved registration identities conflict')
    return obj


def canonical_rules(reg):
    value = COMMENTS + MARKER + json.dumps(reg, sort_keys=True, separators=(',', ':')) + '\n'
    if reg['state'] in ('installing', 'installed'):
        value += USB_RULES
    return value.encode('utf-8')


def parse_rules(data, sdk_version=None):
    try:
        content = data.decode('utf-8') if isinstance(data, bytes) else data
        lines = [line for line in content.splitlines() if line.startswith(MARKER)]
        if len(lines) != 1:
            raise ConfigError('expected exactly one registration line')
        reg = validate_registration(parse_json(lines[0][len(MARKER):]), sdk_version)
        if content.encode('utf-8') != canonical_rules(reg):
            raise ConfigError('rules content differs from the canonical registration')
        return reg
    except UnicodeError as exc:
        raise ConfigError('rules must be UTF-8') from exc


def valid_file_metadata(info, uid=0, gid=0):
    return (stat.S_ISREG(info.st_mode) and info.st_uid == uid and info.st_gid == gid
            and stat.S_IMODE(info.st_mode) == 0o644 and info.st_nlink == 1)


def _read_regular(path, uid, gid=None, exact_mode=True):
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise ConfigError(f'cannot safely read {path}: {exc}') from exc
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != uid:
            raise ConfigError(f'foreign file type, owner, or link count: {path}')
        if gid is not None and info.st_gid != gid:
            raise ConfigError(f'foreign group owner: {path}')
        if exact_mode and stat.S_IMODE(info.st_mode) != 0o644:
            raise ConfigError(f'expected mode 0644: {path}')
        return stream.read()


def read_registration(path, fixture=False, sdk_version=None):
    data = _read_regular(path, os.getuid() if fixture else 0, None if fixture else 0)
    if data is None:
        return None
    try:
        return parse_rules(data, sdk_version)
    except ConfigError as exc:
        raise ConfigError(f'foreign registration at {path}: {exc}') from exc


def validate_fixture_dir(path):
    if os.geteuid() == 0:
        raise ConfigError('root backend rejects fixture destinations')
    raw = Path(os.path.abspath(path))
    if raw != raw.resolve() or raw == Path('/etc') or Path('/etc') in raw.parents:
        raise ConfigError(f'fixture directory must have no symlink traversal and be outside /etc: {path}')
    try:
        info = raw.lstat()
    except OSError as exc:
        raise ConfigError(f'fixture directory unavailable: {path}') from exc
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
        raise ConfigError(f'fixture directory must be caller-owned: {path}')
    return raw


def fixture_state(directory):
    path = Path(directory) / STATE_NAME
    raw = _read_regular(path, os.getuid(), exact_mode=False)
    if raw is None:
        raise ConfigError(f'missing fixture account/reload data: {path}')
    data = parse_json(raw)
    required = {'group_exists', 'members', 'primary_members', 'service_active', 'reload_ok', 'events'}
    if type(data) is not dict or not required <= set(data):
        raise ConfigError(f'incomplete fixture state: {path}')
    if set(data) - required - {'fail_at', 'lock_timeout'}:
        raise ConfigError(f'unknown fixture state fields: {path}')
    for key in ('group_exists', 'service_active', 'reload_ok'):
        if type(data[key]) is not bool:
            raise ConfigError(f'{path}: {key} must be boolean')
    for key in ('members', 'primary_members', 'events'):
        if type(data[key]) is not list or any(type(x) is not str for x in data[key]):
            raise ConfigError(f'{path}: {key} must be a string list')
    if not data['group_exists'] and (data['members'] or data['primary_members']):
        raise ConfigError(f'{path}: membership requires an existing group')
    return data


def observations(username, fixture_dir=None):
    if fixture_dir is not None:
        state = fixture_state(validate_fixture_dir(fixture_dir))
        return {'group_exists': state['group_exists'], 'membership': username in state['members'] or username in state['primary_members'],
                'primary': username in state['primary_members'], 'service_active': state['service_active']}
    try:
        group = grp.getgrnam('epos')
    except KeyError:
        group = None
    account = pwd.getpwnam(username)
    primary = group is not None and account.pw_gid == group.gr_gid
    result = subprocess.run(['/usr/bin/systemctl', 'is-active', '--quiet', 'systemd-udevd.service'], env=ENV,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    return {'group_exists': group is not None, 'membership': bool(group and (primary or username in group.gr_mem)),
            'primary': primary, 'service_active': result.returncode == 0}


class Backend:
    def __init__(self, directory=None):
        self.fixture = directory is not None
        if self.fixture:
            self.directory = validate_fixture_dir(directory)
        else:
            if os.geteuid() != 0:
                raise ConfigError('production backend requires effective UID 0')
            self.directory = RULE_DIR
        self.target = self.directory / RULE_NAME
        self.fd = None

    def state(self):
        return fixture_state(self.directory)

    def save_state(self, state):
        fd, name = tempfile.mkstemp(prefix='.fixture-state-', dir=self.directory)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                json.dump(state, stream, sort_keys=True)
                stream.write('\n')
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, self.directory / STATE_NAME)
            os.fsync(self.fd)
        finally:
            if os.path.exists(name):
                os.unlink(name)

    def event(self, name):
        if self.fixture:
            state = self.state()
            state['events'].append(name)
            self.save_state(state)
            if state.get('fail_at') == name:
                raise ConfigError('injected failure: ' + name)

    @contextlib.contextmanager
    def locked(self):
        fd = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        self.fd = fd
        try:
            info = os.fstat(fd)
            path_info = self.directory.lstat()
            if (info.st_dev, info.st_ino) != (path_info.st_dev, path_info.st_ino):
                raise ConfigError(f'rules directory changed: {self.directory}')
            if not self.fixture and (info.st_uid != 0 or stat.S_IMODE(info.st_mode) & 0o022):
                raise ConfigError(f'unsafe production rules directory: {self.directory}')
            timeout = self.state().get('lock_timeout', 60) if self.fixture else 60
            if type(timeout) not in (int, float) or not 0 <= timeout <= 60:
                raise ConfigError('fixture lock_timeout must be between 0 and 60 seconds')
            deadline = time.monotonic() + timeout
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise ConfigError(f'timed out waiting for rules directory lock: {self.directory}')
                    time.sleep(min(0.05, max(0, deadline - time.monotonic())))
            current = self.directory.lstat()
            if (info.st_dev, info.st_ino) != (current.st_dev, current.st_ino):
                raise ConfigError(f'rules directory changed after locking: {self.directory}')
            yield
        finally:
            os.close(fd)
            self.fd = None

    def clean_temporaries(self):
        for path in self.directory.iterdir():
            if not TEMP_PATTERN.fullmatch(path.name):
                continue
            info = path.lstat()
            expected_uid = os.getuid() if self.fixture else 0
            if not stat.S_ISREG(info.st_mode) or info.st_uid != expected_uid or info.st_nlink != 1:
                raise ConfigError(f'suspicious registration temporary: {path}')
            path.unlink()
            os.fsync(self.fd)

    def publish(self, reg):
        state = reg['state']
        self.event(state + '.before_write')
        fd, name = tempfile.mkstemp(prefix='.epos-sdk-bootstrap-' + reg['installation_uuid'] + '-', suffix='.tmp', dir=self.directory)
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(canonical_rules(reg))
                if not self.fixture:
                    os.fchown(stream.fileno(), 0, 0)
                os.fchmod(stream.fileno(), 0o644)
                stream.flush()
                self.event(state + '.after_write')
                os.fsync(stream.fileno())
                self.event(state + '.after_file_fsync')
            self.event(state + '.before_replace')
            os.replace(name, self.target)
            self.event(state + '.after_replace')
            os.fsync(self.fd)
            self.event(state + '.after_dir_fsync')
        finally:
            if os.path.exists(name):
                os.unlink(name)

    def observe(self, username):
        return observations(username, self.directory if self.fixture else None)

    def account(self, action, username):
        self.event('before_' + action)
        if self.fixture:
            state = self.state()
            if action == 'group_add':
                state['group_exists'] = True
            elif action == 'membership_add':
                if username not in state['members']:
                    state['members'].append(username)
            elif action == 'membership_remove':
                state['members'] = [x for x in state['members'] if x != username]
            self.save_state(state)
        else:
            args = {'group_add': ['/usr/sbin/groupadd', '--system', 'epos'],
                    'membership_add': ['/usr/bin/gpasswd', '-a', username, 'epos'],
                    'membership_remove': ['/usr/bin/gpasswd', '-d', username, 'epos']}[action]
            result = subprocess.run(args, env=ENV, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
            if result.returncode and not (action == 'group_add' and result.returncode == 9 and self.observe(username)['group_exists']):
                raise ConfigError(f'{action} failed at {self.target}: {result.stderr.strip()}')
        self.event('after_' + action)
        current = self.observe(username)
        expected = current['group_exists'] if action == 'group_add' else current['membership'] == (action == 'membership_add')
        if not expected:
            raise ConfigError(f'{action} configured state did not change at {self.target}')

    def reload(self):
        self.event('before_reload')
        if self.fixture:
            state = self.state()
            if not state['reload_ok'] or not state['service_active']:
                raise ConfigError(f'udev reload failed at {self.target}')
        else:
            result = subprocess.run(['/usr/bin/udevadm', 'control', '--reload-rules'], env=ENV,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
            if result.returncode:
                raise ConfigError(f'udev reload failed at {self.target}: {result.stderr.strip()}')
        self.event('after_reload')


def _with_state(reg, state):
    return dict(reg, state=state, reload_pending=STATES[state])


def operate(operation, request, backend, sdk_version=None):
    request = validate_request(request, sdk_version)
    prior = request['prior_registration']
    with backend.locked():
        current = read_registration(backend.target, backend.fixture, sdk_version)
        if current is not None:
            if not same_identity(current, request):
                raise ConfigError(f'registration at {backend.target} belongs to {current["username"]} at {current["prefix"]}; use that prefix to uninstall')
            if prior is not None and not same_provenance(current, prior):
                raise ConfigError(f'registration provenance conflict: {backend.target}')
        # Do not even clean temporaries until the authoritative conflict check.
        backend.clean_temporaries()
        if operation == 'release':
            if prior is None or prior['state'] != 'removed':
                raise ConfigError(f'release requires acknowledged removed registration: {backend.target}')
            if current is None:
                return {'ok': True, 'changed': False, 'registration': None}
            if current != prior:
                raise ConfigError(f'release target differs from acknowledged removed registration: {backend.target}')
            backend.event('before_release')
            backend.target.unlink()
            os.fsync(backend.fd)
            backend.event('after_release')
            return {'ok': True, 'changed': True, 'registration': None}
        if operation not in ('configure', 'remove'):
            raise ConfigError('unknown operation: ' + operation)
        if operation == 'configure':
            if any(reg is not None and reg['state'] in ('removing', 'removed') for reg in (current, prior)):
                raise ConfigError(f'removal has begun at {backend.target}; finish uninstall first')
            if current is not None and current['state'] == 'installed':
                observed = backend.observe(request['username'])
                if observed['group_exists'] and observed['membership']:
                    return {'ok': True, 'changed': False, 'registration': current}
            reg = current or prior
            if reg is None:
                observed = backend.observe(request['username'])
                reg = {key: request[key] for key in IDENTITY}
                reg.update(group='epos', group_existed_before=observed['group_exists'],
                           membership_existed_before=observed['membership'], schema_version=1)
            reg = _with_state(reg, 'installing')
            if current != reg:
                backend.publish(reg)
            else:
                # A previous replacement may have reached disk before its
                # directory flush failed. Establish durability before accounts.
                os.fsync(backend.fd)
            observed = backend.observe(request['username'])
            if not observed['group_exists']:
                backend.account('group_add', request['username'])
            if not backend.observe(request['username'])['membership']:
                backend.account('membership_add', request['username'])
            backend.reload()
            reg = _with_state(reg, 'installed')
            backend.publish(reg)
        else:
            if prior is not None and prior['state'] == 'removed':
                if current is not None and current != prior:
                    raise ConfigError(f'removed snapshot cannot resume a regressed registration: {backend.target}')
                return {'ok': True, 'changed': False, 'registration': current or prior}
            reg = current or prior
            if reg is None:
                return {'ok': True, 'changed': False, 'registration': None}
            if reg['state'] == 'removed':
                return {'ok': True, 'changed': False, 'registration': reg}
            reg = _with_state(reg, 'removing')
            if current != reg:
                backend.publish(reg)
            else:
                # A previous replacement may have reached disk before its
                # directory flush failed. Establish durability before accounts.
                os.fsync(backend.fd)
            observed = backend.observe(request['username'])
            if not reg['membership_existed_before'] and observed['membership']:
                if observed['primary']:
                    raise ConfigError(f'cannot remove epos membership because it is the primary group for {request["username"]}: {backend.target}')
                backend.account('membership_remove', request['username'])
            backend.reload()
            reg = _with_state(reg, 'removed')
            backend.publish(reg)
        return {'ok': True, 'changed': True, 'registration': reg}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('configure', 'remove', 'release'))
    parser.add_argument('--request-json', required=True)
    parser.add_argument('--fixture-dir')
    args = parser.parse_args(argv)
    path = RULE_DIR / RULE_NAME
    try:
        backend = Backend(args.fixture_dir)
        path = backend.target
        if backend.fixture:
            print(f'[WARN] TEST MODE: udev directory overridden to {backend.directory}; not a supported installation', file=sys.stderr)
        result = operate(args.operation, parse_json(args.request_json), backend)
        print(json.dumps(result, sort_keys=True, separators=(',', ':')))
        return 0
    except (ConfigError, OSError, KeyError) as exc:
        print(f'[ERROR] {args.operation} failed at {path}: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
