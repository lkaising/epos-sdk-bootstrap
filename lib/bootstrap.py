"""Ordinary-user operations. No root writes and no shell evaluation of metadata."""
import contextlib
import copy
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import pwd
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import uuid

import sdk_files
import system_config as system

PROJECT = Path(__file__).resolve().parent.parent
RECEIPT = '.epos-sdk-bootstrap.json'
RULES = '99-epos-sdk-bootstrap.rules'
PACKAGES = ['python3', 'python3-venv', 'curl', 'ca-certificates', 'libc6', 'libstdc++6', 'libgcc-s1', 'udev']
PHASES = {'initialised', 'deps', 'download', 'payload', 'system', 'verify', 'complete', 'uninstall_system', 'uninstall_local'}
ENV = dict(os.environ, LC_ALL='C', PYTHONDONTWRITEBYTECODE='1')
COLORS = {stream: stream.isatty() and 'NO_COLOR' not in os.environ for stream in (sys.stdout, sys.stderr)}

class Failure(ValueError):
    pass

class HostError(Failure):
    pass


def log(kind, message):
    stream = sys.stderr if kind in ('WARN', 'ERROR') else sys.stdout
    label = '[ OK ]' if kind == 'OK' else '[' + kind + ']'
    if COLORS.get(stream, False):
        label = '\033[' + ('31' if kind == 'ERROR' else '33' if kind == 'WARN' else '32') + 'm' + label + '\033[0m'
    print(label, message, file=stream)


def run(args, check=True, **kwargs):
    try:
        result = subprocess.run([str(a) for a in args], env=ENV, text=True,
                                capture_output=True, **kwargs)
    except OSError as exc:
        raise Failure(f'{args[0]}: {exc}') from exc
    if check and result.returncode:
        raise Failure(f'{shlex.join([str(a) for a in args])}: exit {result.returncode}: {result.stderr.strip()}')
    return result


def parse_os_release(text):
    result = {}
    for line in text.splitlines():
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        if not re.fullmatch('[A-Z_]+', key):
            continue
        try:
            words = shlex.split(value, comments=False)
        except ValueError as exc:
            raise HostError('/etc/os-release: invalid value') from exc
        result[key] = words[0] if len(words) == 1 else ''
    return result


def validate_host(os_info, machine, deb_arch, bits, uid, command, dry, wsl):
    if os_info.get('ID') != 'ubuntu' or os_info.get('VERSION_ID') != '24.04':
        raise HostError('host: requires Ubuntu ID=ubuntu VERSION_ID=24.04 in /etc/os-release')
    if machine != 'x86_64' or deb_arch != 'amd64' or bits != 64:
        raise HostError(f'host: requires x86_64, Debian amd64, 64-bit /usr/bin/python3; found {machine}, {deb_arch}, {bits}')
    if command == 'install' and wsl:
        raise HostError('host: WSL install is unsupported because a working udev service is required')
    if not dry and command in ('install', 'uninstall') and uid == 0:
        raise HostError('host: install/uninstall must run as an ordinary user, not root')


def host_gate(command, dry):
    try:
        os_info = parse_os_release(Path('/etc/os-release').read_text())
        machine = run(['uname', '-m']).stdout.strip()
        deb_arch = run(['dpkg', '--print-architecture']).stdout.strip()
        uid = int(run(['id', '-u']).stdout.strip())
        username = run(['id', '-un']).stdout.strip()
        kernel = Path('/proc/sys/kernel/osrelease').read_text()
    except (OSError, ValueError) as exc:
        raise HostError(f'host: {exc}') from exc
    validate_host(os_info, machine, deb_arch, 64 if sys.maxsize > 2**32 else 32, uid,
                  command, dry, 'WSL_DISTRO_NAME' in os.environ or bool(re.search('microsoft|wsl', kernel, re.I)))
    container = Path('/.dockerenv').exists() or Path('/run/.containerenv').exists()
    if shutil.which('systemd-detect-virt'):
        container |= run(['systemd-detect-virt', '--container'], check=False).returncode == 0
    log('OK', f'host: Ubuntu 24.04 x86_64, running as {username}')
    if container:
        log('WARN', 'container detected; production verification requires the host systemd-udevd service')
    return uid, username


def resolve_prefix(raw):
    if not raw.strip() or any(ord(c) < 32 or ord(c) == 127 or c == ':' for c in raw):
        raise HostError(f'destination: invalid path {raw!r}; control characters and colons are forbidden')
    path = Path(os.path.abspath(raw))
    if path.is_symlink():
        raise Failure(f'destination: symlink refused: {path}')
    path = path.resolve()
    home = Path.home().resolve()
    if path == Path('/') or path in (home, PROJECT) or path in home.parents or path in PROJECT.parents:
        raise Failure(f'destination: protected directory {path}')
    if any(path == root or root in path.parents for root in map(Path, ['/etc','/usr','/bin','/sbin','/lib','/lib64','/boot','/dev','/proc','/sys','/run','/var'])):
        raise Failure(f'destination: system directory refused: {path}')
    if path.exists() and (not path.is_dir() or path.stat().st_uid != os.getuid()):
        raise Failure(f'destination: expected user-owned directory: {path}')
    parent = path.parent
    while not parent.exists():
        parent = parent.parent
    if not parent.is_dir() or not os.access(parent, os.W_OK | os.X_OK):
        raise Failure(f'destination: parent is not writable: {parent}')
    return path


def unique_object(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise Failure(f'JSON: duplicate key {key}')
        obj[key] = value
    return obj


def json_read(path):
    try:
        return json.loads(path.read_text(), object_pairs_hook=unique_object)
    except (OSError, ValueError) as exc:
        raise Failure(f'JSON {path}: {exc}') from exc


def digest(data):
    return hashlib.sha256(data).hexdigest()


def keys(obj, expected, name):
    if not isinstance(obj, dict) or set(obj) != set(expected.split()):
        raise Failure(f'{name}: invalid object keys')


def relative(path, vendor_only=False):
    if not isinstance(path, str) or not path or '\\' in path or any(ord(c) < 32 or ord(c) == 127 for c in path):
        raise Failure(f'receipt: invalid relative path {path!r}')
    p = PurePosixPath(path)
    if p.is_absolute() or str(p) != path or any(s in ('', '.', '..') for s in path.split('/')):
        raise Failure(f'receipt: unsafe path {path!r}')
    if vendor_only and not path.startswith('vendor/EPOS_Linux_Library/'):
        raise Failure(f'receipt: path outside vendor payload: {path}')
    return path


def hash_meta(item, path=None, size=True):
    keys(item, 'path sha256' + (' size' if size else ''), 'file metadata')
    relative(item['path'])
    if path is not None and item['path'] != path:
        raise Failure(f'receipt: unexpected file {item["path"]}')
    if not isinstance(item['sha256'], str) or not re.fullmatch('[0-9a-f]{64}', item['sha256']):
        raise Failure('receipt: invalid SHA-256')
    if size and (type(item['size']) is not int or item['size'] < 0):
        raise Failure('receipt: invalid size')


def expected_release(release):
    a = release['archive']
    return dict(sdk_version=release['sdk_version'], archive_url=a['url'], archive_sha256=a['sha256'],
                archive_size_bytes=a['size_bytes'], lib_subdir=release['arch']['lib_subdir'])


def archive_meta(release):
    a = release['archive']
    return dict(path='downloads/' + a['filename'], size=a['size_bytes'], sha256=a['sha256'])


def _validate_receipt(r, prefix, uid, username, release):
    keys(r, 'schema_version tool installation_uuid created_utc updated_utc phase prefix owner release payload generated tool_artifacts system', 'receipt')
    if type(r['schema_version']) is not int or r['schema_version'] != 1:
        raise Failure('receipt: this installation was created by a newer bootstrap; upgrade the tool' if isinstance(r['schema_version'], int) and r['schema_version'] > 1 else 'receipt: unsupported schema_version')
    keys(r['tool'], 'name version', 'tool')
    if r['tool']['name'] != 'bootstrap-epos-sdk' or not isinstance(r['tool']['version'], str) or not re.fullmatch(r'\d+\.\d+\.\d+', r['tool']['version']):
        raise Failure('receipt: invalid tool identity/version')
    try:
        if str(uuid.UUID(r['installation_uuid'])) != r['installation_uuid']:
            raise ValueError('noncanonical UUID')
        for field in ('created_utc','updated_utc'):
            datetime.datetime.strptime(r[field], '%Y-%m-%dT%H:%M:%SZ')
    except (ValueError, TypeError, AttributeError) as exc:
        raise Failure('receipt: invalid UUID/timestamp') from exc
    if r['prefix'] != str(prefix) or r['owner'] != dict(uid=uid, username=username) or type(r['owner'].get('uid')) is not int:
        raise Failure(f'receipt: identity/owner mismatch at {prefix}')
    if r['phase'] not in PHASES or r['release'] != expected_release(release):
        raise Failure('receipt: unknown phase or release mismatch')
    if r['tool_artifacts'] != [RECEIPT]:
        raise Failure('receipt: invalid tool_artifacts')
    keys(r['generated'], 'archive setup_bash', 'generated')
    a, setup = r['generated']['archive'], r['generated']['setup_bash']
    if a is not None:
        hash_meta(a, archive_meta(release)['path'])
        if a != archive_meta(release): raise Failure('receipt: archive pin mismatch')
    if setup is not None:
        keys(setup, 'path template_version sha256', 'setup_bash')
        if setup['path'] != 'setup.bash' or type(setup['template_version']) is not int or setup['template_version'] != 1 or setup['sha256'] != digest(sdk_files.setup_bash(str(prefix), r['tool']['version'])):
            raise Failure('receipt: activation metadata mismatch')
    payload = r['payload']
    if payload is not None:
        keys(payload, 'root dirs files symlinks', 'payload')
        if payload['root'] != 'vendor/EPOS_Linux_Library' or any(not isinstance(payload[k], list) for k in ('dirs','files','symlinks')):
            raise Failure('receipt: invalid payload inventory')
        paths = set()
        for path in payload['dirs']:
            relative(path)
            if path not in ('downloads','vendor','vendor/EPOS_Linux_Library'):
                relative(path, vendor_only=True)
            if path in paths: raise Failure(f'receipt: duplicate path {path}')
            paths.add(path)
        dirs = set(paths)
        if not {'downloads','vendor','vendor/EPOS_Linux_Library'} <= dirs:
            raise Failure('receipt: incomplete directory inventory')
        file_paths = set()
        for item in payload['files']:
            hash_meta(item); relative(item['path'], vendor_only=True)
            if item['path'] in paths: raise Failure(f'receipt: duplicate path {item["path"]}')
            paths.add(item['path']); file_paths.add(item['path'])
        expected_links = [dict(path='vendor/EPOS_Linux_Library/' + release['arch']['lib_subdir'] + '/' + lib['link'], target=lib['filename']) for lib in release['libraries'].values()]
        if any(not isinstance(item, dict) for item in payload['symlinks']):
            raise Failure('receipt: malformed symlink entry')
        if sorted(payload['symlinks'], key=lambda x: x.get('path','')) != sorted(expected_links, key=lambda x: x['path']):
            raise Failure('receipt: invalid library symlinks')
        for item in payload['symlinks']:
            if item['path'] in paths: raise Failure('receipt: file/link collision')
            paths.add(item['path'])
        if len({p.casefold() for p in paths}) != len(paths):
            raise Failure('receipt: case-colliding paths')
        for path in paths:
            parent = str(PurePosixPath(path).parent)
            if parent != '.' and parent not in dirs:
                raise Failure(f'receipt: missing parent inventory for {path}')
        if not {'vendor/EPOS_Linux_Library/' + p for p in release['required_members']} <= file_paths:
            raise Failure('receipt: required payload member missing from inventory')
        for lib in release['libraries'].values():
            item = next(f for f in payload['files'] if f['path'] == 'vendor/EPOS_Linux_Library/' + release['arch']['lib_subdir'] + '/' + lib['filename'])
            if item['sha256'] != lib['sha256']: raise Failure('receipt: library hash differs from manifest')
    s = r['system']; keys(s, 'request registration udev_sha256 apt', 'system')
    if s['request'] not in (None, 'configure', 'remove'): raise Failure('receipt: invalid system request')
    keys(s['apt'], 'packages_installed apt_get_update_run', 'apt')
    packages = s['apt']['packages_installed']
    if not isinstance(packages, list) or any(p not in PACKAGES for p in packages) or len(set(packages)) != len(packages) or type(s['apt']['apt_get_update_run']) is not bool:
        raise Failure('receipt: invalid apt record')
    reg = s['registration']
    if reg is not None:
        system.validate_registration(reg, release['sdk_version'])
        if not identity_matches(r, reg): raise Failure('receipt: registration identity mismatch')
        if s['udev_sha256'] != digest(system.canonical_rules(reg)):
            raise Failure('receipt: registration hash mismatch')
    elif s['udev_sha256'] is not None:
        raise Failure('receipt: registration hash without registration')
    phase = r['phase']
    if phase in ('payload','system','verify','complete') and a is None:
        raise Failure(f'receipt: {phase} requires archive metadata')
    if phase in ('system','verify','complete') and (payload is None or setup is None):
        raise Failure(f'receipt: {phase} requires complete inventory')
    if phase == 'system' and s['request'] != 'configure': raise Failure('receipt: system phase requires configure intent')
    if phase in ('verify','complete') and (reg is None or reg['state'] != 'installed' or s['request'] is not None):
        raise Failure(f'receipt: {phase} requires acknowledged installed registration')
    if phase == 'uninstall_system' and s['request'] != 'remove': raise Failure('receipt: removal intent missing')
    if phase == 'uninstall_local' and (s['request'] is not None or reg is not None and reg['state'] != 'removed'):
        raise Failure('receipt: local cleanup lacks removal acknowledgement')
    return r


def validate_receipt(r, prefix, uid, username, release):
    try:
        return _validate_receipt(r, prefix, uid, username, release)
    except (ValueError, TypeError, KeyError, AttributeError, IndexError) as exc:
        raise Failure(f'receipt validation at {prefix / RECEIPT}: {exc}') from exc


def identity_matches(receipt, reg):
    return all((receipt['installation_uuid'] == reg['installation_uuid'], receipt['prefix'] == reg['prefix'],
                receipt['owner']['uid'] == reg['uid'], receipt['owner']['username'] == reg['username'],
                receipt['release']['sdk_version'] == reg['sdk_version']))


def fsync_dir(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try: os.fsync(fd)
    finally: os.close(fd)


def now():
    return datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def save_receipt(prefix, receipt):
    receipt['updated_utc'] = now()
    tmp = prefix / (RECEIPT + '.tmp')
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
    try:
        with os.fdopen(fd, 'w') as out:
            os.fchmod(out.fileno(), 0o644)
            json.dump(receipt, out, sort_keys=True, indent=2); out.write('\n'); out.flush(); os.fsync(out.fileno())
        os.replace(tmp, prefix / RECEIPT); fsync_dir(prefix)
    finally:
        if tmp.exists(): tmp.unlink()


def new_receipt(prefix, uid, username, version, release, reg=None):
    return dict(schema_version=1, tool=dict(name='bootstrap-epos-sdk', version=version),
                installation_uuid=reg['installation_uuid'] if reg else str(uuid.uuid4()),
                created_utc=now(), updated_utc=now(), phase='initialised', prefix=str(prefix),
                owner=dict(uid=uid,username=username), release=expected_release(release), payload=None,
                generated=dict(archive=None,setup_bash=None), tool_artifacts=[RECEIPT],
                system=dict(request=None,registration=reg,udev_sha256=digest(system.canonical_rules(reg)) if reg else None,
                            apt=dict(packages_installed=[],apt_get_update_run=False)))


def safe_stat(path, uid, mode, directory=False):
    st = path.lstat()
    expected = stat.S_ISDIR(st.st_mode) if directory else stat.S_ISREG(st.st_mode)
    if not expected or st.st_uid != uid or stat.S_IMODE(st.st_mode) != mode or not directory and st.st_nlink != 1:
        raise Failure(f'ownership/type/mode conflict: {path}')
    return st


def inventory(receipt):
    dirs = {'downloads','vendor'}
    files = {}; links = {}
    if receipt['payload']:
        dirs.update(receipt['payload']['dirs'])
        files.update({f['path']:f for f in receipt['payload']['files']})
        links.update({f['path']:f['target'] for f in receipt['payload']['symlinks']})
    for metadata in receipt['generated'].values():
        if metadata: files[metadata['path']] = metadata
    return dirs, files, links


def inspect_contents(prefix, receipt, uid, release, command):
    dirs, files, links = inventory(receipt)
    expected = dirs | set(files) | set(links) | {RECEIPT}
    missing, extras = [], []
    # Walk without following links. Validate parents before hashing any descendant.
    for base, subdirs, names in os.walk(prefix, followlinks=False):
        for name in subdirs[:] + names:
            path = Path(base) / name; rel = str(path.relative_to(prefix))
            if rel == '.staging' or rel.startswith('.staging/') or rel == RECEIPT + '.tmp':
                st = path.lstat()
                if rel == '.staging' and not stat.S_ISDIR(st.st_mode) or rel == RECEIPT + '.tmp' and not stat.S_ISREG(st.st_mode):
                    raise Failure(f'unsafe interrupted temporary type: {path}')
                # Only the two tool-generated staged links are allowed, never arbitrary links.
                staged_links = {'.staging/vendor/EPOS_Linux_Library/' + release['arch']['lib_subdir'] + '/' + lib['link']: lib['filename'] for lib in release['libraries'].values()}
                known_link = stat.S_ISLNK(st.st_mode) and rel in staged_links and os.readlink(path) == staged_links[rel]
                if st.st_uid != uid or not (stat.S_ISREG(st.st_mode) or stat.S_ISDIR(st.st_mode) or known_link) or stat.S_ISREG(st.st_mode) and st.st_nlink != 1:
                    raise Failure(f'unsafe interrupted temporary: {path}')
                continue
            if rel not in expected:
                extras.append(str(path))
                if name in subdirs: subdirs.remove(name)
                continue
            if rel in links:
                if not path.is_symlink() or path.lstat().st_uid != uid or os.readlink(path) != links[rel]:
                    raise Failure(f'library symlink conflict: {path}')
            elif rel in dirs:
                safe_stat(path, uid, 0o755, directory=True)
            else:
                safe_stat(path, uid, 0o644)
                if rel in files:
                    info = files[rel]
                    if 'size' in info and path.stat().st_size != info['size'] or sdk_files.sha256_file(path) != info['sha256']:
                        raise Failure(f'managed file hash/size conflict: {path}')
    for rel in sorted(set(files) | set(links) | dirs):
        if not os.path.lexists(prefix / rel): missing.append(rel)
    # A retained corrupt archive is never overwritten even in incomplete phases.
    archive = prefix / archive_meta(release)['path']
    if os.path.lexists(archive): sdk_files.check_archive(archive, release)
    if extras:
        if command == 'verify':
            for item in extras: log('WARN', f'unexpected content retained: {item}')
        else: raise Failure('unexpected content; move it aside before retrying: ' + ', '.join(extras))
    return missing


def registration_for(ctx):
    return system.read_registration(ctx.rules, fixture=ctx.fixture is not None, sdk_version=ctx.release['sdk_version'])


def reconcile(receipt, reg):
    if reg is None or not identity_matches(receipt, reg): return
    prior = receipt['system']['registration']
    if prior is None: return
    for key in ('group_existed_before','membership_existed_before','group'):
        if prior[key] != reg[key]: raise Failure('registration: immutable provenance differs from receipt')
    old, new = prior['state'], reg['state']
    if old == new: return
    request = receipt['system']['request']
    allowed = (old, new) in {('installing','installed'),('removing','removed')}
    allowed |= old == 'installed' and new == 'installing' and request == 'configure'
    # A root removal state always prevents installation, including a stale caller.
    allowed |= old in ('installing','installed') and new in ('removing','removed')
    if not allowed: raise Failure(f'registration: invalid state transition {old} -> {new}')


class Context:
    def __init__(self, command, prefix, dry, yes, version, uid, username):
        self.command, self.prefix, self.dry, self.yes = command, prefix, dry, yes
        self.version, self.uid, self.username = version, uid, username
        self.release = sdk_files.load_release(PROJECT / 'config/sdk-release.json')
        fixture_raw = os.environ.get('EPOS_BOOTSTRAP_UDEV_DIR')
        self.fixture = None
        if fixture_raw is not None:
            try: self.fixture = system.validate_fixture_dir(fixture_raw)
            except (ValueError, OSError) as exc: raise HostError(f'fixture directory: {exc}') from exc
            log('WARN', f'TEST MODE: udev directory overridden to {self.fixture}; not a supported installation')
        self.rules = (self.fixture or Path('/etc/udev/rules.d')) / RULES
        self.receipt = None; self.reg = None; self.missing = []
        self.local_only = False

    def inspect(self):
        self.receipt = None; self.missing = []; self.local_only = False
        if self.prefix.is_symlink(): raise Failure(f'destination symlink: {self.prefix}')
        if self.prefix.exists():
            st = self.prefix.stat()
            if not stat.S_ISDIR(st.st_mode) or st.st_uid != self.uid:
                raise Failure(f'prefix owner/type conflict: {self.prefix}')
            rp = self.prefix / RECEIPT
            if os.path.lexists(rp):
                safe_stat(self.prefix, self.uid, 0o755, directory=True)
                safe_stat(rp, self.uid, 0o644)
                self.receipt = validate_receipt(json_read(rp), self.prefix, self.uid, self.username, self.release)
                self.missing = inspect_contents(self.prefix, self.receipt, self.uid, self.release, self.command)
            elif any(self.prefix.iterdir()):
                offender = next(self.prefix.iterdir())
                raise Failure(f'populated prefix without valid receipt: {self.prefix}; conflict: {offender}')
        self.reg = registration_for(self)
        r, reg = self.receipt, self.reg
        matches = reg is not None and (identity_matches(r, reg) if r else reg['prefix'] == str(self.prefix) and reg['uid'] == self.uid and reg['username'] == self.username)
        if matches and r: reconcile(r, reg)
        if reg is not None and not matches:
            # A saved removed snapshot authorizes local cleanup only. Never touch a new reservation.
            self.local_only = bool(r and (r['system']['registration'] is None or r['phase'] == 'uninstall_local'))
            if not (self.command == 'uninstall' and self.local_only):
                raise Failure(f'registration conflict at {self.rules}: owned by {reg["username"]} at {reg["prefix"]}. Re-run with: bootstrap-epos-sdk {self.command} --sdk-dir {shlex.quote(reg["prefix"])}. A second user needs administrator-granted epos membership and read/traverse access to that SDK; only one installation is supported.')
            log('INFO', f'local-only cleanup; leaving registration at {reg["prefix"]} untouched')
        if self.command == 'install' and (matches and reg['state'] in ('removing','removed') or r and (r['phase'].startswith('uninstall_') or r['system']['request'] == 'remove' or r['system']['registration'] and r['system']['registration']['state'] in ('removing','removed'))):
            raise Failure(f'uninstall incomplete at {self.prefix}; finish uninstall first')
        if self.command == 'verify' and r is None:
            raise Failure(f'not installed: payload/receipt missing at {self.prefix}')
        return self

    def observe(self):
        return system.observations(self.username, self.fixture)

    def missing_packages(self):
        return [p for p in PACKAGES if run(['dpkg-query','-W','-f=${db:Status-Status}',p],check=False).stdout.strip() != 'installed']

    def request(self, prior=None):
        r = self.receipt
        if r:
            reg = self.reg if self.reg and identity_matches(r, self.reg) else r['system']['registration']
            data = dict(installation_uuid=r['installation_uuid'],prefix=str(self.prefix),uid=self.uid,username=self.username,sdk_version=self.release['sdk_version'])
        else:
            reg = self.reg
            if reg is None: raise Failure('system request: no registration identity')
            data = {k:reg[k] for k in ('installation_uuid','prefix','uid','username','sdk_version')}
        data['prior_registration'] = prior if prior is not None else reg
        return data

    def helper_args(self, operation, request):
        args = ['/usr/bin/python3','-I','-B',str(PROJECT / 'lib/system_config.py'),operation,'--request-json',json.dumps(request,sort_keys=True,separators=(',',':'))]
        if self.fixture: args += ['--fixture-dir',str(self.fixture)]
        return args

    def helper(self, operation, prior=None):
        args = self.helper_args(operation, self.request(prior))
        result = run(args) if self.fixture else run_privileged(args)
        try:
            reply = json.loads(result.stdout, object_pairs_hook=unique_object)
            if reply['ok'] is not True or type(reply['changed']) is not bool: raise ValueError('invalid helper acknowledgement')
            reg = reply['registration']
            if reg is not None: system.validate_registration(reg,self.release['sdk_version'])
        except (ValueError, KeyError, TypeError) as exc:
            raise Failure(f'system helper {operation}: invalid response') from exc
        actual = registration_for(self)
        if actual != reg and not (operation == 'remove' and actual is None and reg is not None and reg['state'] == 'removed'):
            raise Failure(f'system helper {operation}: registration changed; retry')
        self.reg = reg
        return reg

    def acknowledge(self, reg, phase):
        self.receipt['system']['registration'] = reg
        self.receipt['system']['udev_sha256'] = digest(system.canonical_rules(reg)) if reg else None
        self.receipt['system']['request'] = None
        self.receipt['phase'] = phase
        save_receipt(self.prefix,self.receipt)

    def phase(self, phase, request=None):
        self.receipt['phase'] = phase
        if request is not None: self.receipt['system']['request'] = request
        save_receipt(self.prefix,self.receipt)


def run_privileged(args):
    apt = args[:2] == ['DEBIAN_FRONTEND=noninteractive','apt-get'] and (args[2:] == ['update'] or args[2:5] == ['install','-y','--no-install-recommends'] and bool(args[5:]) and all(p in PACKAGES for p in args[5:]))
    helper = len(args) == 7 and args[:4] == ['/usr/bin/python3','-I','-B',str(PROJECT / 'lib/system_config.py')] and args[4] in ('configure','remove','release') and args[5] == '--request-json'
    if not (apt or helper): raise Failure('internal error: privileged command is outside the allowed vocabulary')
    try: return run(['sudo'] + args)
    except Failure as exc:
        raise Failure(f'{exc}. Full sudo is required. Administrator command: {shlex.join(args)}') from exc


def cleanup_temporaries(ctx):
    # inspect_contents has already rejected symlinks and foreign owners anywhere below staging.
    stage = ctx.prefix / '.staging'
    if stage.exists(): shutil.rmtree(stage); fsync_dir(ctx.prefix)
    temp = ctx.prefix / (RECEIPT + '.tmp')
    if temp.exists(): temp.unlink(); fsync_dir(ctx.prefix)


@contextlib.contextmanager
def prefix_lock(ctx, create=False):
    if create and not ctx.prefix.exists():
        # User-owned ancestors only; no sudo. Explicit modes defeat restrictive umasks.
        chain = []; p = ctx.prefix
        while not p.exists(): chain.append(p); p = p.parent
        for directory in reversed(chain):
            try: directory.mkdir(mode=0o755)
            except FileExistsError: pass
            if directory.is_symlink() or not directory.is_dir() or directory.stat().st_uid != ctx.uid:
                raise Failure(f'prefix creation conflict: {directory}')
            directory.chmod(0o755); fsync_dir(directory.parent)
    fd = os.open(ctx.prefix, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        try: fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc: raise Failure(f'prefix locked by another operation: {ctx.prefix}') from exc
        a, b = os.fstat(fd), ctx.prefix.stat(follow_symlinks=False)
        if (a.st_dev,a.st_ino) != (b.st_dev,b.st_ino): raise Failure(f'prefix changed while locking: {ctx.prefix}')
        ctx.inspect()
        yield
    finally: os.close(fd)


def system_satisfied(ctx):
    obs = ctx.observe()
    return ctx.reg is not None and ctx.reg['state'] == 'installed' and obs['group_exists'] and obs['membership']


def check_prerequisites(ctx, needs_system, needs_apt):
    names = ['bash','dpkg','dpkg-query','getent','id','uname','timeout','flock']
    if needs_apt: names += ['sudo','apt-get']
    if needs_system and not ctx.fixture: names += ['sudo','groupadd','gpasswd','udevadm','systemctl']
    for name in names:
        if not shutil.which(name): raise Failure(f'prerequisite missing: {name}')


def legacy_warnings():
    patterns = ['/opt/EposCmdLib*','/usr/lib/libEposCmd*','/usr/lib/libftd2xx*','/usr/local/lib/libEposCmd*','/usr/local/lib/libftd2xx*', '/etc/udev/rules.d/*ftdi*.rules','/etc/udev/rules.d/*epos*.rules']
    import glob
    for pattern in patterns:
        for path in glob.glob(pattern):
            if Path(path).name != RULES: log('WARN', f'legacy or foreign configuration retained: {path}')


def plan(ctx, missing_packages):
    log('INFO', f'{ctx.command}: SDK {ctx.release["sdk_version"]} at {ctx.prefix}')
    legacy_warnings()
    r = ctx.receipt
    if r: log('INFO', f'local phase: {r["phase"]}; missing owned entries: {len(ctx.missing)}')
    if ctx.command == 'verify':
        log('INFO','checks: receipt/registration, archive, every payload file, selected library pins/ELF/links, activation, Python/venv, group membership and udev service')
        if ctx.dry: log('INFO','native-load and export checks skipped by --dry-run')
        return
    if ctx.command == 'install':
        log('INFO', f'archive URL: {ctx.release["archive"]["url"]}')
        log('INFO', f'archive pin: {ctx.release["archive"]["size_bytes"]} bytes, SHA-256 {ctx.release["archive"]["sha256"]}')
        log('INFO', 'missing packages: ' + (', '.join(missing_packages) or 'none'))
        if missing_packages:
            for args in (['sudo','DEBIAN_FRONTEND=noninteractive','apt-get','update'],['sudo','DEBIAN_FRONTEND=noninteractive','apt-get','install','-y','--no-install-recommends'] + missing_packages):
                log('INFO', shlex.join(args))
        log('INFO', 'local content: receipt, retained archive, complete vendor package, two relative library links, setup.bash')
        if r:
            for path in ctx.missing: log('INFO', 'restore missing: ' + str(ctx.prefix / path))
        if not system_satisfied(ctx):
            obs = ctx.observe()
            log('INFO', 'group change: ' + ('retain existing epos group' if obs['group_exists'] else 'groupadd --system epos'))
            log('INFO', 'membership change: ' + ('already configured' if obs['membership'] else shlex.join(['gpasswd','-a',ctx.username,'epos'])))
            # Reserve identity for this proposed run without writing or taking a lock.
            if r is None:
                ctx.receipt = new_receipt(ctx.prefix,ctx.uid,ctx.username,ctx.version,ctx.release,ctx.reg)
                ctx.planned_uuid = ctx.receipt['installation_uuid']
            req = ctx.request()
            preview = dict(req); preview.pop('prior_registration')
            prior = req['prior_registration']
            preview.update(group='epos', schema_version=1, group_existed_before=prior['group_existed_before'] if prior else obs['group_exists'],membership_existed_before=prior['membership_existed_before'] if prior else obs['membership'], state='installed',reload_pending=False)
            log('INFO', f'final udev content at {ctx.rules}:\n' + system.canonical_rules(preview).decode())
            log('INFO', shlex.join(([] if ctx.fixture else ['sudo']) + ctx.helper_args('configure',req)))
            log('INFO', 'helper records installing intent, then changes group/membership and runs udevadm control --reload-rules')
            ctx.receipt = r
    else:
        if r:
            dirs, files, links = inventory(r)
            for path in sorted(set(files) | set(links) | dirs | {RECEIPT}): log('INFO', 'remove if present: ' + str(ctx.prefix / path))
            log('INFO', f'remove validated interrupted staging and receipt temporaries, then empty prefix: {ctx.prefix}')
        reg = ctx.reg if ctx.reg and (not r or identity_matches(r,ctx.reg)) else r['system']['registration'] if r else None
        if not ctx.local_only and reg:
            if not reg['membership_existed_before'] and reg['state'] != 'removed' and ctx.observe()['primary']:
                raise Failure(f'membership conflict: epos is now the primary group of {ctx.username}; account identity will not be changed')
            log('INFO', f'remove matching registration: {ctx.rules}')
            log('INFO', 'membership change: ' + ('retain preexisting membership' if reg['membership_existed_before'] or reg['state']=='removed' else shlex.join(['gpasswd','-d',ctx.username,'epos'])))
            for operation in ('remove','release'):
                req = ctx.request()
                if operation == 'release':
                    req['prior_registration'] = dict(reg,state='removed',reload_pending=False)
                log('INFO', shlex.join(([] if ctx.fixture else ['sudo']) + ctx.helper_args(operation,req)))
        log('INFO','retain apt packages, epos group, other memberships, foreign configuration, applications, venvs, parameter backups and vendor data outside this prefix')


def confirm(ctx):
    if ctx.command == 'install':
        log('INFO', f"This downloads and installs maxon's EPOS Linux Library {ctx.release['sdk_version']} under maxon's license terms. The EULA ships inside the archive and is retained at {ctx.prefix}/vendor/EPOS_Linux_Library/EULA.txt.")
    if ctx.yes: return
    if not sys.stdin.isatty(): raise Failure('confirmation requires an interactive terminal; use --yes to accept the displayed changes')
    if input('Proceed? [y/N] ').lower() not in ('y','yes'): raise Failure('confirmation declined')


def static_verify(ctx, internal=False):
    r = ctx.receipt
    required_phase = 'verify' if internal else 'complete'
    if r is None or r['phase'] != required_phase:
        raise Failure(f'installation: {ctx.prefix} requires phase {required_phase}; run install or finish uninstall')
    if ctx.missing: raise Failure(f'installation missing: {ctx.prefix / ctx.missing[0]}; run install')
    if ctx.reg != r['system']['registration'] or ctx.reg is None or ctx.reg['state'] != 'installed' or r['system']['request'] is not None:
        raise Failure(f'USB registration missing, changed or incomplete: {ctx.rules}; run install')
    if ctx.missing_packages(): raise Failure('required packages missing; run install')
    libdir = ctx.prefix / 'vendor/EPOS_Linux_Library' / ctx.release['arch']['lib_subdir']
    for lib in ctx.release['libraries'].values():
        path = libdir / lib['filename']
        if sdk_files.sha256_file(path) != lib['sha256']: raise Failure(f'library manifest hash mismatch: {path}')
        sdk_files.check_elf(path,ctx.release['arch'])
        if os.readlink(libdir / lib['link']) != lib['filename']: raise Failure(f'library link mismatch: {libdir / lib["link"]}')
    obs = ctx.observe()
    if not obs['group_exists'] or not obs['membership']: raise Failure('USB access: epos group/configured membership missing; run install')
    if not obs['service_active']: raise Failure('udev service: systemd-udevd.service is not active; containers cannot establish host acceptance')
    import ctypes  # standard-library import only, no SDK loaded here
    del ctypes
    for text in (f'installation: {ctx.release["sdk_version"]} at {ctx.prefix}', 'archive: retained archive matches pinned size and SHA-256', f'payload: {len(r["payload"]["files"])} managed files match; EULA.txt and Definitions.h present', 'libraries: pinned hashes, ELF64 LSB x86-64 and relative links valid', 'activation: setup.bash matches recorded generator and hash', f'python: /usr/bin/python3 {platform.python_version()}, 64-bit; ctypes and python3-venv available', 'usb access: canonical registration and epos configured membership valid', 'udev service: systemd-udevd active'):
        log('OK', text)
    if 'epos' not in run(['id','-nG']).stdout.split(): log('WARN', "this shell does not yet carry the 'epos' group; start a new login or SSH session")
    return libdir


def native_verify(ctx, libdir):
    with tempfile.TemporaryDirectory(prefix='epos-load-') as empty:
        args = ['timeout','--signal=TERM','--kill-after=2','10','/usr/bin/python3','-I','-B',str(PROJECT / 'lib/check_load.py'),'--lib-dir',str(libdir),'--json']
        for kind in ('ftdi','epos'):
            lib = ctx.release['libraries'][kind]
            args += ['--'+kind+'-filename',lib['filename'],'--'+kind+'-sha256',lib['sha256']]
        for symbol in ctx.release['expected_symbols']: args += ['--symbol',symbol]
        env = dict(PATH='/usr/bin:/bin',HOME=empty,LC_ALL='C',PYTHONDONTWRITEBYTECODE='1')
        child = subprocess.run(args,env=env,cwd=empty,capture_output=True,text=True)
        if child.returncode == 124: raise Failure('native load: timed out after 10 s')
        if child.returncode < 0 or child.returncode >= 128:
            signal = -child.returncode if child.returncode < 0 else child.returncode - 128
            raise Failure(f'native load: loader/vendor initialization died on signal {signal}')
        if child.returncode: raise Failure(f'native load: exit {child.returncode}: {child.stderr.strip()}')
        try: report = json.loads(child.stdout)
        except ValueError as exc: raise Failure('native load: invalid child JSON') from exc
        if report.get('ok') is not True: raise Failure(f'native load: {report.get("error", "invalid report")}')
        if report.get('maps_confirmed') is not True or any(report.get('symbols',{}).get(s) is not True for s in ctx.release['expected_symbols']): raise Failure('native load: incomplete maps/export report')
        for kind in ('ftdi','epos'):
            if report.get(kind+'_path') != str(libdir / ctx.release['libraries'][kind]['filename']): raise Failure('native load: child reported foreign library path')
    log('OK','native load: both libraries loaded from the managed prefix')
    log('OK','exports: ' + ', '.join(ctx.release['expected_symbols']) + ' resolved; none called')


def verify(ctx, internal=False):
    before = copy.deepcopy((ctx.receipt,ctx.reg))
    libdir = static_verify(ctx,internal)
    if not ctx.dry: native_verify(ctx,libdir)
    # Lock-free public checks must detect changed identity/state before success.
    ctx.inspect()
    if (ctx.receipt,ctx.reg) != before: raise Failure('verification: concurrent installation change detected; retry')
    if not ctx.dry:
        log('OK', 'fixture verification passed; not a supported installation' if ctx.fixture else 'verify PASSED: SDK installation verified')
        log('INFO','controller communication and motor operation were not tested')


def durable_publish(source, target):
    if os.path.lexists(target): raise Failure(f'publication destination appeared: {target}')
    if not source.is_symlink():
        fd = os.open(source,os.O_RDONLY | os.O_NOFOLLOW)
        try: os.fsync(fd)
        finally: os.close(fd)
    os.rename(source,target)
    fsync_dir(target.parent)
    if source.parent != target.parent: fsync_dir(source.parent)


def ensure_directory(path, uid):
    if os.path.lexists(path): safe_stat(path,uid,0o755,directory=True)
    else:
        path.mkdir(mode=0o755); path.chmod(0o755); fsync_dir(path); fsync_dir(path.parent)


def install(ctx):
    planned_uuid = ctx.receipt['installation_uuid'] if ctx.receipt else None
    with prefix_lock(ctx,create=True):
        if planned_uuid and ctx.receipt and planned_uuid != ctx.receipt['installation_uuid']:
            raise Failure(f'installation changed after confirmation: {ctx.prefix}; retry')
        if ctx.receipt is None:
            ctx.prefix.chmod(0o755); fsync_dir(ctx.prefix)
            ctx.receipt = new_receipt(ctx.prefix,ctx.uid,ctx.username,ctx.version,ctx.release,ctx.reg)
            if getattr(ctx, 'planned_uuid', None): ctx.receipt['installation_uuid'] = ctx.planned_uuid
            save_receipt(ctx.prefix,ctx.receipt)
        cleanup_temporaries(ctx)
        r = ctx.receipt
        missing_packages = ctx.missing_packages()
        if missing_packages:
            ctx.phase('deps')
            if ctx.fixture:
                raise Failure('fixture isolation: required packages missing; use recording package-query stubs, never apt in fixture mode')
            run_privileged(['DEBIAN_FRONTEND=noninteractive','apt-get','update'])
            r['system']['apt']['apt_get_update_run'] = True; save_receipt(ctx.prefix,r)
            run_privileged(['DEBIAN_FRONTEND=noninteractive','apt-get','install','-y','--no-install-recommends']+missing_packages)
            r['system']['apt']['packages_installed'] = sorted(set(r['system']['apt']['packages_installed']) | set(missing_packages))
            save_receipt(ctx.prefix,r)
            if ctx.missing_packages(): raise Failure('dependencies: apt returned success but packages are still missing')
            log('OK', 'dependencies installed: ' + ', '.join(missing_packages) + '; these packages remain if a later stage fails')
        stage = ctx.prefix / '.staging'
        archive = ctx.prefix / archive_meta(ctx.release)['path']
        need_payload = r['payload'] is None or r['generated']['setup_bash'] is None or any(p != archive_meta(ctx.release)['path'] for p in ctx.missing)
        if not archive.exists() or need_payload:
            ensure_directory(stage,ctx.uid)
        if not archive.exists():
            ctx.phase('download')
            part = stage / (ctx.release['archive']['filename'] + '.part')
            args = ['curl','--disable','--proto','=https','--proto-redir','=https','--tlsv1.2','--location','--max-redirs','5','--fail-with-body','--connect-timeout','15','--max-time','600','--retry','3','--retry-delay','2','--retry-connrefused','--output',str(part),ctx.release['archive']['url']]
            run(args)
            safe_stat_download(part,ctx.uid)
            sdk_files.check_archive(part,ctx.release)
            part.chmod(0o644)
            r['generated']['archive'] = archive_meta(ctx.release); save_receipt(ctx.prefix,r)
            ensure_directory(ctx.prefix / 'downloads',ctx.uid)
            durable_publish(part,archive)
            log('OK', f'archive validated and retained: {archive}')
        else:
            sdk_files.check_archive(archive,ctx.release)
        if need_payload:
            ctx.phase('payload')
            payload = sdk_files.extract_archive(archive,stage / 'vendor',ctx.release)
            setup = sdk_files.setup_bash(str(ctx.prefix),r['tool']['version'])
            setup_meta = dict(path='setup.bash',template_version=1,sha256=digest(setup))
            if r['payload'] is not None and r['payload'] != payload:
                raise Failure('payload: validated archive inventory differs from saved inventory')
            if r['generated']['setup_bash'] is not None and r['generated']['setup_bash'] != setup_meta:
                raise Failure('activation: regenerated setup differs from saved metadata')
            (stage / 'setup.bash').write_bytes(setup); (stage / 'setup.bash').chmod(0o644)
            r['payload'] = payload; r['generated']['setup_bash'] = setup_meta
            save_receipt(ctx.prefix,r)  # Inventory is durable before any final payload path appears.
            inspect_contents(ctx.prefix,r,ctx.uid,ctx.release,'install')
            for rel in sorted(payload['dirs'],key=lambda p:(len(PurePosixPath(p).parts),p)):
                ensure_directory(ctx.prefix / rel,ctx.uid)
            for entry in payload['files'] + payload['symlinks'] + [setup_meta]:
                target = ctx.prefix / entry['path']
                if not os.path.lexists(target): durable_publish(stage / entry['path'],target)
        cleanup_temporaries(ctx)
        log('OK', f'payload prepared at {ctx.prefix}; recovery receipt retained until completion')
        ctx.inspect(); r = ctx.receipt
        if not system_satisfied(ctx) or r['system']['request'] is not None:
            ctx.phase('system','configure')
            reg = ctx.helper('configure')
            ctx.acknowledge(reg,'verify')
        else:
            ctx.acknowledge(ctx.reg,'verify')
        ctx.inspect()
        verify(ctx,internal=True)
        ctx.phase('complete')
        log('INFO', 'activate with: source ' + shlex.quote(str(ctx.prefix / 'setup.bash')))
        log('INFO','future hardware use may require reconnection following the controller documented power-off USB procedure')


def safe_stat_download(path, uid):
    st = path.lstat()
    if not stat.S_ISREG(st.st_mode) or st.st_uid != uid or st.st_nlink != 1:
        raise Failure(f'download: unsafe staging file {path}')


def local_cleanup(ctx):
    # Revalidate after shared cleanup, before deleting a single local file.
    inspect_contents(ctx.prefix,ctx.receipt,ctx.uid,ctx.release,'uninstall')
    cleanup_temporaries(ctx)
    dirs, files, links = inventory(ctx.receipt)
    for rel in sorted(set(files) | set(links)):
        path = ctx.prefix / rel
        if os.path.lexists(path): path.unlink(); fsync_dir(path.parent)
    for rel in sorted(dirs,key=lambda p:(len(PurePosixPath(p).parts),p),reverse=True):
        path = ctx.prefix / rel
        if path.exists(): path.rmdir(); fsync_dir(path.parent)
    (ctx.prefix / RECEIPT).unlink(); fsync_dir(ctx.prefix)
    ctx.prefix.rmdir(); fsync_dir(ctx.prefix.parent)


def uninstall_locked(ctx):
    r = ctx.receipt
    if r is None:
        if ctx.reg:
            removed = ctx.helper('remove')
            if removed: ctx.helper('release',removed)
        if ctx.prefix.exists(): ctx.prefix.rmdir(); fsync_dir(ctx.prefix.parent)
        return
    cleanup_temporaries(ctx)
    prior = r['system']['registration']
    matching = ctx.reg is not None and identity_matches(r,ctx.reg)
    if ctx.local_only or (not matching and prior is None):
        r['system']['request'] = None
        ctx.phase('uninstall_local')
    elif not matching and r['phase'] == 'uninstall_local':
        # Released or replaced registration. Saved removed provenance is terminal.
        pass
    else:
        ctx.phase('uninstall_system','remove')
        removed = ctx.helper('remove')
        ctx.acknowledge(removed,'uninstall_local')
        if removed: ctx.helper('release',removed)
    local_cleanup(ctx)


def uninstall(ctx):
    if ctx.prefix.exists():
        with prefix_lock(ctx): uninstall_locked(ctx)
    else:
        # No replacement prefix: the machine registration holds all recovery intent.
        ctx.inspect()
        if ctx.reg:
            removed = ctx.helper('remove')
            if removed: ctx.helper('release',removed)
    log('OK','uninstall complete')
    log('INFO','retained apt packages, epos group, preexisting/other memberships, foreign configuration, applications, venvs, parameter backups and vendor data outside the prefix')
    log('INFO','running sessions keep their groups; USB permissions change when rules are reapplied. Start a fresh shell to discard obsolete EPOS_LIB_DIR and library-path entries')


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 5: raise HostError('internal invocation: expected command, prefix, dry-run, yes, version')
    command, raw, dry_raw, yes_raw, version = args
    if command not in ('install','verify','uninstall') or dry_raw not in ('0','1') or yes_raw not in ('0','1'):
        raise HostError('internal invocation: invalid arguments')
    dry = dry_raw == '1'
    uid, username = host_gate(command,dry)
    prefix = resolve_prefix(raw)
    ctx = Context(command,prefix,dry,yes_raw == '1',version,uid,username)
    if command == 'verify' and dry: log('INFO','native-load and export checks skipped by --dry-run')
    ctx.inspect()
    packages = ctx.missing_packages() if command == 'install' else []
    plan(ctx,packages)
    if command == 'verify':
        verify(ctx)
        return 0
    if command == 'uninstall' and ctx.receipt is None and ctx.reg is None and (not prefix.exists() or not any(prefix.iterdir())):
        log('OK','not installed; nothing to remove')
        return 0
    if command == 'install' and ctx.receipt and ctx.receipt['phase'] == 'complete' and not ctx.missing and not packages and system_satisfied(ctx) and ctx.receipt['system']['registration'] == ctx.reg and not (prefix / '.staging').exists() and not (prefix / (RECEIPT + '.tmp')).exists():
        verify(ctx)
        log('OK','installation already satisfied; no changes')
        return 0
    needs_system = command == 'install' and not system_satisfied(ctx) or command == 'uninstall' and not ctx.local_only and (ctx.reg is not None or ctx.receipt and ctx.receipt['system']['registration'] is not None)
    check_prerequisites(ctx,needs_system,bool(packages))
    if dry: return 0
    confirm(ctx)
    if command == 'install': install(ctx)
    else: uninstall(ctx)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except HostError as exc:
        log('ERROR',str(exc)); sys.exit(2)
    except (ValueError, OSError, KeyError, TypeError, EOFError) as exc:
        log('ERROR',str(exc)); sys.exit(1)
