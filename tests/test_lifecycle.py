"""Full caller lifecycle in private fixtures. Synthetic archives, no host mutation."""
import contextlib
import copy
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import pwd
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
import bootstrap as b
import system_config as sc
import sdk_files as sdk
from test_sdk_files import make_fixture


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='epos-lifecycle-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.prefix = self.root / "SDK ' dollar$ tick` ; directory"
        self.rulesdir = self.root / 'rules'; self.rulesdir.mkdir()
        self.archive = self.root / 'fixture.zip'
        self.release = make_fixture(self.archive)
        self.account = pwd.getpwuid(os.getuid())
        self.state = self.rulesdir / sc.STATE_NAME
        self.write_state(dict(group_exists=False,members=[],primary_members=[],service_active=True,reload_ok=True,events=[]))
        self.env_patch = mock.patch.dict(os.environ,EPOS_BOOTSTRAP_UDEV_DIR=str(self.rulesdir))
        self.env_patch.start(); self.addCleanup(self.env_patch.stop)
        self.pin_patch = mock.patch.object(sdk,'load_release',return_value=self.release)
        self.pin_patch.start(); self.addCleanup(self.pin_patch.stop)
        self.pkg_patch = mock.patch.object(b.Context,'missing_packages',return_value=[])
        self.pkg_patch.start(); self.addCleanup(self.pkg_patch.stop)
        self.native_patch = mock.patch.object(b,'native_verify')
        self.native = self.native_patch.start(); self.addCleanup(self.native_patch.stop)
        self.output = io.StringIO()
        for stream in ('stdout','stderr'):
            patch = getattr(contextlib,'redirect_'+stream)(self.output)
            patch.__enter__(); self.addCleanup(patch.__exit__,None,None,None)
        self.calls = []
        original_run = b.run
        def fake_run(args, **kwargs):
            self.calls.append(list(args))
            if args[0] == 'curl':
                target = Path(args[args.index('--output')+1])
                # The first durable receipt must exist before networking.
                r = json.loads((self.prefix / b.RECEIPT).read_text())
                self.assertEqual(r['phase'],'download')
                shutil.copyfile(self.archive,target)
                return subprocess.CompletedProcess(args,0,'','')
            if args[0] in ('sudo','apt-get','groupadd','gpasswd','udevadm'):
                self.fail('unexpected real external action: '+repr(args))
            return original_run(args,**kwargs)
        patch = mock.patch.object(b,'run',side_effect=fake_run)
        patch.start(); self.addCleanup(patch.stop)

    def write_state(self, data):
        self.state.write_text(json.dumps(data)); self.state.chmod(0o644)

    def get_state(self): return json.loads(self.state.read_text())
    def receipt(self): return json.loads((self.prefix / b.RECEIPT).read_text())
    def put_receipt(self, r): b.save_receipt(self.prefix,r)
    def ctx(self,command='install',dry=False,prefix=None):
        return b.Context(command,prefix or self.prefix,dry,True,'1.0.0',os.getuid(),self.account.pw_name).inspect()
    def install(self): b.install(self.ctx())
    def uninstall(self): b.uninstall(self.ctx('uninstall'))
    def snapshot(self):
        result = {}
        for root in (self.prefix,self.rulesdir):
            if root.exists():
                for p in [root]+sorted(root.rglob('*')):
                    st = p.lstat()
                    result[str(p)] = (st.st_ino,st.st_mtime_ns,stat.S_IMODE(st.st_mode),os.readlink(p) if p.is_symlink() else p.read_bytes() if p.is_file() else None)
        return result

    def test_fresh_healthy_verify_rerun_remove_repeat(self):
        self.install()
        r = self.receipt(); self.assertEqual(r['phase'],'complete')
        self.assertEqual(r['system']['registration']['state'],'installed')
        self.assertFalse(r['system']['registration']['membership_existed_before'])
        for event in ('after_group_add','after_membership_add','after_reload'):
            self.assertIn(event,self.get_state()['events'])
        before = self.snapshot(); calls = len(self.calls)
        with mock.patch.object(b,'host_gate',return_value=(os.getuid(),self.account.pw_name)):
            self.assertEqual(b.main(['install',str(self.prefix),'0','1','1.0.0']),0)
        self.assertEqual(before,self.snapshot())
        self.assertFalse(any(c[0]=='curl' or 'system_config.py' in ' '.join(c) for c in self.calls[calls:]))
        b.verify(self.ctx('verify'))
        self.uninstall(); self.assertFalse(self.prefix.exists())
        self.assertFalse((self.rulesdir / b.RULES).exists())
        self.assertTrue(self.get_state()['group_exists'])
        self.assertNotIn(self.account.pw_name,self.get_state()['members'])
        calls = len(self.calls)
        with mock.patch.object(b,'host_gate',return_value=(os.getuid(),self.account.pw_name)):
            self.assertEqual(b.main(['uninstall',str(self.prefix),'0','1','1.0.0']),0)
        self.assertEqual(calls,len(self.calls))

    def test_missing_files_restore_without_rewriting_healthy_items(self):
        self.install(); original = self.receipt(); setup = self.prefix/'setup.bash'; setup.unlink()
        preserved = self.prefix/'vendor/EPOS_Linux_Library/EULA.txt'; inode = preserved.stat().st_ino
        self.install(); self.assertEqual(preserved.stat().st_ino,inode)
        self.assertEqual(self.receipt()['installation_uuid'],original['installation_uuid'])
        self.assertEqual(self.receipt()['tool'],original['tool'])
        archive = self.prefix / b.archive_meta(self.release)['path']; archive.unlink()
        self.install(); self.assertTrue(archive.exists())
        self.assertEqual(preserved.stat().st_ino,inode)

    def test_modified_and_extra_files_refused_without_mutation(self):
        self.install(); p=self.prefix/'vendor/EPOS_Linux_Library/EULA.txt'; old=p.read_bytes(); p.write_bytes(b'user edit')
        before=self.snapshot()
        for command in ('install','verify','uninstall'):
            with self.subTest(command=command),self.assertRaisesRegex(ValueError,'conflict'): self.ctx(command)
            self.assertEqual(before,self.snapshot())
        p.write_bytes(old); extra=self.prefix/'mine'; extra.write_text('keep')
        before=self.snapshot()
        for command in ('install','uninstall'):
            with self.assertRaisesRegex(ValueError,'unexpected content'): self.ctx(command)
        b.verify(self.ctx('verify')); self.assertEqual(before,self.snapshot())

    def test_corrupt_retained_archive_never_downloaded_again(self):
        self.install(); archive=self.prefix/b.archive_meta(self.release)['path']; archive.write_bytes(b'HTML')
        calls=len(self.calls)
        for command in ('install','uninstall','verify'):
            with self.assertRaises(ValueError): self.ctx(command)
        self.assertEqual(calls,len(self.calls)); self.assertEqual(archive.read_bytes(),b'HTML')

    def test_missing_payload_can_be_uninstalled_without_native_load(self):
        self.install(); shutil.rmtree(self.prefix/'vendor'); self.native.reset_mock()
        self.uninstall(); self.native.assert_not_called(); self.assertFalse(self.prefix.exists())

    def test_registration_only_recovery_reuses_uuid_or_removes(self):
        self.install(); ident=self.receipt()['installation_uuid']; shutil.rmtree(self.prefix)
        with self.assertRaisesRegex(ValueError,'missing'): self.ctx('verify')
        self.install(); self.assertEqual(self.receipt()['installation_uuid'],ident)
        shutil.rmtree(self.prefix); self.uninstall(); self.assertFalse(self.prefix.exists())
        self.assertFalse((self.rulesdir/b.RULES).exists())

    def test_all_install_phases_resume_and_public_verify_refuses(self):
        self.install(); complete=self.receipt()
        for phase in ('initialised','deps','download','payload','system','verify'):
            with self.subTest(phase=phase):
                r=copy.deepcopy(complete); r['phase']=phase
                r['system']['request']='configure' if phase=='system' else None
                self.put_receipt(r)
                with self.assertRaisesRegex(ValueError,'phase'): b.verify(self.ctx('verify'))
                self.install(); self.assertEqual(self.receipt()['phase'],'complete')
                self.assertEqual(self.receipt()['installation_uuid'],complete['installation_uuid'])

    def test_resume_after_initial_receipt_and_partial_download(self):
        self.prefix.mkdir(); self.prefix.chmod(0o755)
        r=b.new_receipt(self.prefix,os.getuid(),self.account.pw_name,'1.0.0',self.release)
        self.put_receipt(r); (self.prefix/'.staging').mkdir(); (self.prefix/'.staging/unfinished.part').write_bytes(b'partial')
        self.install(); self.assertEqual(self.receipt()['phase'],'complete'); self.assertFalse((self.prefix/'.staging').exists())

    def test_empty_prefix_recoverable_but_unknown_startup_temp_is_not(self):
        self.prefix.mkdir(); self.install(); self.uninstall(); self.prefix.mkdir()
        tmp=self.prefix/(b.RECEIPT+'.tmp'); tmp.write_text('{partial')
        for command in ('install','uninstall'):
            with self.assertRaisesRegex(ValueError,'json.tmp'): self.ctx(command)
        self.assertTrue(tmp.exists())

    def test_inventory_durable_before_publication_and_resume_every_file(self):
        self.install(); self.uninstall()
        publish=b.durable_publish; count=0
        def stop_after(source,target):
            nonlocal count
            r=self.receipt()
            if target.name != self.release['archive']['filename']:
                self.assertIsNotNone(r['payload']); self.assertIsNotNone(r['generated']['setup_bash'])
            else: self.assertIsNotNone(r['generated']['archive'])
            publish(source,target); count+=1
            if count==3: raise OSError('injected partial publication')
        with mock.patch.object(b,'durable_publish',side_effect=stop_after):
            with self.assertRaisesRegex(OSError,'injected'): self.install()
        self.assertEqual(self.receipt()['phase'],'payload')
        self.install(); b.verify(self.ctx('verify'))

    def test_failed_reload_resume_original_provenance(self):
        state=self.get_state(); state['reload_ok']=False; self.write_state(state)
        with self.assertRaises(ValueError): self.install()
        r=self.receipt(); self.assertEqual(r['phase'],'system'); self.assertEqual(r['system']['request'],'configure')
        reg=sc.read_registration(self.rulesdir/b.RULES,fixture=True); self.assertEqual(reg['state'],'installing')
        self.assertFalse(reg['membership_existed_before'])
        state=self.get_state(); state['reload_ok']=True; self.write_state(state)
        self.install(); self.assertFalse(self.receipt()['system']['registration']['membership_existed_before'])
        self.uninstall(); self.assertNotIn(self.account.pw_name,self.get_state()['members'])

    def test_root_ahead_of_receipt_reconciles_and_removal_blocks_install(self):
        self.install(); r=self.receipt(); prior=copy.deepcopy(r['system']['registration']); prior.update(state='installing',reload_pending=True)
        r['phase']='system'; r['system']['request']='configure'; r['system']['registration']=prior; r['system']['udev_sha256']=b.digest(sc.canonical_rules(prior)); self.put_receipt(r)
        self.install()
        ctx=self.ctx('uninstall'); ctx.phase('uninstall_system','remove'); ctx.helper('remove')
        with self.assertRaisesRegex(ValueError,'finish uninstall'): self.ctx('install')
        self.uninstall(); self.assertFalse(self.prefix.exists())

    def test_uninstall_failure_keeps_provenance_and_resumes(self):
        self.install(); state=self.get_state(); state['reload_ok']=False; self.write_state(state)
        with self.assertRaises(ValueError): self.uninstall()
        self.assertEqual(self.receipt()['phase'],'uninstall_system')
        self.assertEqual(sc.read_registration(self.rulesdir/b.RULES,fixture=True)['state'],'removing')
        state=self.get_state(); state['reload_ok']=True; self.write_state(state)
        self.uninstall(); self.assertFalse(self.prefix.exists())

    def test_released_then_replacement_registration_survives_local_cleanup(self):
        self.install(); ctx=self.ctx('uninstall'); ctx.phase('uninstall_system','remove'); removed=ctx.helper('remove'); ctx.acknowledge(removed,'uninstall_local'); ctx.helper('release',removed)
        newprefix=self.root/'replacement'; newprefix.mkdir()
        req=dict(installation_uuid=str(uuid.uuid4()),prefix=str(newprefix),uid=os.getuid(),username=self.account.pw_name,sdk_version='6.8.1.0',prior_registration=None)
        result=subprocess.run(['/usr/bin/python3','-I','-B',str(b.PROJECT/'lib/system_config.py'),'configure','--request-json',json.dumps(req),'--fixture-dir',str(self.rulesdir)],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        before=(self.rulesdir/b.RULES).read_bytes(); events=self.get_state()['events'][:]
        self.uninstall(); self.assertEqual((self.rulesdir/b.RULES).read_bytes(),before)
        self.assertEqual(self.get_state()['events'],events)

    def test_never_registered_loser_can_remove_only_local_content(self):
        self.install(); other=self.root/'loser'; other.mkdir(); other.chmod(0o755)
        r=b.new_receipt(other,os.getuid(),self.account.pw_name,'1.0.0',self.release); b.save_receipt(other,r)
        before=(self.rulesdir/b.RULES).read_bytes(); events=self.get_state()['events'][:]
        with self.assertRaisesRegex(ValueError,'registration conflict'): self.ctx(prefix=other)
        b.uninstall(self.ctx('uninstall',prefix=other)); self.assertFalse(other.exists())
        self.assertEqual((self.rulesdir/b.RULES).read_bytes(),before); self.assertEqual(self.get_state()['events'],events)

    def test_preexisting_membership_retained(self):
        state=self.get_state(); state.update(group_exists=True,members=[self.account.pw_name]); self.write_state(state)
        self.install(); self.uninstall(); self.assertIn(self.account.pw_name,self.get_state()['members'])

    def test_primary_group_conflict_blocks_dry_run(self):
        self.install(); state=self.get_state(); state['primary_members']=[self.account.pw_name]; self.write_state(state)
        before=self.snapshot()
        with self.assertRaisesRegex(ValueError,'primary group'): b.plan(self.ctx('uninstall',dry=True),[])
        self.assertEqual(before,self.snapshot())

    def test_same_prefix_lock_fails_fast(self):
        self.install(); fd=os.open(self.prefix,os.O_RDONLY|os.O_DIRECTORY)
        try:
            fcntl.flock(fd,fcntl.LOCK_EX)
            with self.assertRaisesRegex(ValueError,'locked'):
                with b.prefix_lock(self.ctx()): self.fail('lock acquired')
        finally: os.close(fd)

    def test_dry_runs_never_lock_load_or_write(self):
        self.install(); before=self.snapshot(); self.native.reset_mock()
        for command in ('install','verify','uninstall'):
            with mock.patch.object(b,'host_gate',return_value=(os.getuid(),self.account.pw_name)),mock.patch.object(b,'prefix_lock',side_effect=AssertionError('dry lock')),mock.patch.object(b,'run_privileged',side_effect=AssertionError('dry sudo')):
                self.assertEqual(b.main([command,str(self.prefix),'1','0','1.0.0']),0)
        self.native.assert_not_called(); self.assertEqual(before,self.snapshot())

    def test_verify_detects_concurrent_receipt_change(self):
        self.install()
        def change(*args):
            r=self.receipt(); r['phase']='verify'; self.put_receipt(r)
        self.native.side_effect=change
        with self.assertRaisesRegex(ValueError,'concurrent'): b.verify(self.ctx('verify'))

    def test_receipt_rejects_schema_types_paths_and_immutable_changes(self):
        self.install(); original=self.receipt()
        mutations=[lambda r:r.update(schema_version=2),lambda r:r.update(schema_version=True),lambda r:r.update(owner=dict(uid=0,username='root')),lambda r:r['payload']['files'][0].update(path='../outside'),lambda r:r['payload']['symlinks'][0].update(target='/etc/passwd'),lambda r:r['payload'].update(symlinks=[1]),lambda r:r['generated']['archive'].update(size=True),lambda r:r['tool_artifacts'].append('/etc/passwd'),lambda r:r.update(phase='unknown'),lambda r:r['system'].update(udev_sha256='0'*64),lambda r:r['generated']['setup_bash'].update(sha256='0'*64)]
        for mutation in mutations:
            r=copy.deepcopy(original); mutation(r)
            with self.subTest(r=r),self.assertRaises(ValueError): b.validate_receipt(r,self.prefix,os.getuid(),self.account.pw_name,self.release)

    def test_symlink_and_temp_type_conflicts_preserve_everything(self):
        self.install(); path=self.prefix/'vendor/EPOS_Linux_Library/EULA.txt'; data=path.read_bytes(); path.unlink(); path.symlink_to('/etc/passwd')
        with self.assertRaisesRegex(ValueError,'conflict'): self.ctx('uninstall')
        path.unlink(); path.write_bytes(data)
        stage=self.prefix/'.staging'; stage.write_bytes(b'wrong type')
        with self.assertRaisesRegex(ValueError,'temporary type'): self.ctx('uninstall')
        stage.unlink(); temp=self.prefix/(b.RECEIPT+'.tmp'); temp.mkdir()
        with self.assertRaisesRegex(ValueError,'temporary type'): self.ctx('uninstall')

    def test_no_confirmation_in_noninteractive_session(self):
        ctx=self.ctx(); ctx.yes=False
        with mock.patch.object(sys.stdin,'isatty',return_value=False),self.assertRaisesRegex(ValueError,'interactive terminal'): b.confirm(ctx)

    def test_dependency_dispatch_is_exact_and_receipt_precedes_apt(self):
        ctx=self.ctx(); ctx.fixture=None
        commands=[]
        def privileged(args):
            commands.append(args)
            self.assertEqual(self.receipt()['phase'],'deps')
            self.assertIsNone(self.receipt()['payload'])
            if 'install' in args: ctx.fixture=self.rulesdir
            return subprocess.CompletedProcess(args,0,'','')
        with mock.patch.object(b.Context,'missing_packages',side_effect=[['python3-venv'],[],[]]), mock.patch.object(b,'run_privileged',side_effect=privileged):
            b.install(ctx)
        self.assertEqual(commands,[['DEBIAN_FRONTEND=noninteractive','apt-get','update'],['DEBIAN_FRONTEND=noninteractive','apt-get','install','-y','--no-install-recommends','python3-venv']])
        self.assertEqual(self.receipt()['system']['apt'],dict(packages_installed=['python3-venv'],apt_get_update_run=True))

    def test_apt_failure_leaves_valid_initial_receipt(self):
        ctx=self.ctx(); ctx.fixture=None
        with mock.patch.object(b.Context,'missing_packages',return_value=['python3-venv']),mock.patch.object(b,'run_privileged',side_effect=b.Failure('sudo denied')):
            with self.assertRaisesRegex(ValueError,'sudo denied'): b.install(ctx)
        r=self.receipt(); self.assertEqual(r['phase'],'deps'); self.assertIsNone(r['payload'])
        b.validate_receipt(r,self.prefix,os.getuid(),self.account.pw_name,self.release)
        self.assertFalse((self.prefix/'.staging').exists())

    def test_download_policy_and_partial_failure_resume(self):
        self.install()
        curl=next(c for c in self.calls if c[0]=='curl')
        self.assertEqual(curl[:18],['curl','--disable','--proto','=https','--proto-redir','=https','--tlsv1.2','--location','--max-redirs','5','--fail-with-body','--connect-timeout','15','--max-time','600','--retry','3','--retry-delay'])
        self.assertIn('--retry-connrefused',curl); self.assertEqual(curl[-1],self.release['archive']['url'])
        self.uninstall()
        previous=b.run
        def fail_download(args,**kwargs):
            if args[0]=='curl':
                Path(args[args.index('--output')+1]).write_bytes(b'partial')
                raise b.Failure('interrupted download')
            return previous(args,**kwargs)
        with mock.patch.object(b,'run',side_effect=fail_download):
            with self.assertRaisesRegex(ValueError,'interrupted download'): self.install()
        self.assertFalse((self.prefix/b.archive_meta(self.release)['path']).exists())
        self.assertEqual(self.receipt()['phase'],'download')
        self.install(); self.assertFalse((self.prefix/'.staging').exists())

    def test_local_cleanup_interruption_keeps_receipt_and_resumes(self):
        self.install(); original=Path.unlink
        def interrupted(path,*args,**kwargs):
            if path==self.prefix/'setup.bash': raise OSError('interrupted local cleanup')
            return original(path,*args,**kwargs)
        with mock.patch.object(Path,'unlink',interrupted):
            with self.assertRaisesRegex(OSError,'interrupted local cleanup'): self.uninstall()
        self.assertEqual(self.receipt()['phase'],'uninstall_local')
        self.assertFalse((self.rulesdir/b.RULES).exists())
        with self.assertRaisesRegex(ValueError,'finish uninstall'): self.ctx('install')
        self.uninstall(); self.assertFalse(self.prefix.exists())

    def test_removed_snapshot_absent_rules_never_removes_later_membership(self):
        self.install(); ctx=self.ctx('uninstall'); ctx.phase('uninstall_system','remove'); removed=ctx.helper('remove'); ctx.acknowledge(removed,'uninstall_local'); ctx.helper('release',removed)
        r=self.receipt(); r['phase']='uninstall_system'; r['system']['request']='remove'; self.put_receipt(r)
        state=self.get_state(); state['members']=[self.account.pw_name]; self.write_state(state)
        events=state['events'][:]
        self.uninstall(); self.assertIn(self.account.pw_name,self.get_state()['members'])
        self.assertEqual(events,self.get_state()['events'])

    def test_directory_identity_rechecked_after_prefix_lock(self):
        self.install(); original=fcntl.flock
        moved=self.root/'moved-sdk'
        def swapped(fd,flags):
            original(fd,flags)
            self.prefix.rename(moved); self.prefix.mkdir()
        with mock.patch.object(fcntl,'flock',side_effect=swapped):
            with self.assertRaisesRegex(ValueError,'changed while locking'):
                with b.prefix_lock(self.ctx()): self.fail('changed prefix accepted')
        self.assertTrue((moved/b.RECEIPT).exists()); self.assertEqual(list(self.prefix.iterdir()),[])

    def test_receipt_phase_nullability_and_bad_nested_types(self):
        self.install(); complete=self.receipt()
        initial=b.new_receipt(self.prefix,os.getuid(),self.account.pw_name,'1.0.0',self.release)
        for phase in ('initialised','deps','download','uninstall_system','uninstall_local'):
            r=copy.deepcopy(initial); r['phase']=phase
            if phase=='uninstall_system': r['system']['request']='remove'
            b.validate_receipt(r,self.prefix,os.getuid(),self.account.pw_name,self.release)
        for phase in ('payload','system','verify','complete'):
            r=copy.deepcopy(initial); r['phase']=phase
            with self.assertRaises(ValueError): b.validate_receipt(r,self.prefix,os.getuid(),self.account.pw_name,self.release)
        for field,value in [('phase',[]),('owner',None),('payload',[]),('system',None),('tool',[]),('generated',False),('created_utc',12)]:
            r=copy.deepcopy(complete); r[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError): b.validate_receipt(r,self.prefix,os.getuid(),self.account.pw_name,self.release)

    def test_run_privileged_closed_vocabulary(self):
        with self.assertRaisesRegex(ValueError,'vocabulary'): b.run_privileged(['gpasswd','-a',self.account.pw_name,'epos'])
        with mock.patch.object(b,'run',return_value=subprocess.CompletedProcess([],0,'','')) as run:
            b.run_privileged(['DEBIAN_FRONTEND=noninteractive','apt-get','update'])
            self.assertEqual(run.call_args.args[0],['sudo','DEBIAN_FRONTEND=noninteractive','apt-get','update'])


if __name__=='__main__': unittest.main()
