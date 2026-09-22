"""Native child contract using synthetic libraries only, never the vendor SDK."""
import contextlib
import copy
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'lib'))
import bootstrap as b
import sdk_files as sdk


class NativeProcessTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='epos-native-tests-'); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.libdir=self.root/'libraries with space'; self.libdir.mkdir()
        self.release=copy.deepcopy(sdk.load_release())
        self.ctx=types.SimpleNamespace(release=self.release)

    def test_child_result_mapping_environment_and_cleanup(self):
        report=dict(ok=True,maps_confirmed=True,symbols={s:True for s in self.release['expected_symbols']},error=None)
        for kind in ('ftdi','epos'): report[kind+'_path']=str(self.libdir/self.release['libraries'][kind]['filename'])
        cases=[(0,json.dumps(report),'',None),(0,json.dumps(dict(report,ok=False,error='missing dependency')),'','missing dependency'),(0,'garbage','','invalid child JSON'),(124,'','','timed out'),(139,'','','signal 11'),(-11,'','','signal 11'),(7,'','bad stderr','exit 7')]
        for rc,out,err,expected in cases:
            with self.subTest(rc=rc,out=out):
                cwd=[]
                def child(args,**kwargs):
                    cwd.append(kwargs['cwd']); self.assertEqual(list(Path(kwargs['cwd']).iterdir()),[])
                    self.assertEqual(set(kwargs['env']),{'PATH','HOME','LC_ALL','PYTHONDONTWRITEBYTECODE'})
                    self.assertIn('-I',args); self.assertIn('-B',args); self.assertEqual(args[:4],['timeout','--signal=TERM','--kill-after=2','10'])
                    return subprocess.CompletedProcess(args,rc,out,err)
                with mock.patch.object(subprocess,'run',side_effect=child):
                    if expected:
                        with self.assertRaisesRegex(ValueError,expected): b.native_verify(self.ctx,self.libdir)
                    else:
                        with contextlib.redirect_stdout(io.StringIO()): b.native_verify(self.ctx,self.libdir)
                self.assertFalse(Path(cwd[0]).exists())

    @unittest.skipUnless(shutil.which('gcc'),'optional synthetic ELF test requires an already installed compiler')
    def test_real_child_with_synthetic_sonames_exports_and_no_api_calls(self):
        # API bodies abort if the checker ever invokes one instead of resolving it.
        sources={
            'ftdi':'int fixture_ftdi(void) { return 123; }\n',
            'epos':'#include <stdlib.h>\nextern int fixture_ftdi(void);\nint fixture_dep(void) { return fixture_ftdi(); }\nvoid VCS_OpenDevice(void) { abort(); }\nvoid VCS_CloseDevice(void) { abort(); }\nvoid VCS_GetDriverInfo(void) { abort(); }\n'}
        for kind in ('ftdi','epos'):
            lib=self.release['libraries'][kind]
            source=self.root/(kind+'.c'); source.write_text(sources[kind])
            args=['gcc','-shared','-fPIC',str(source),'-Wl,-soname,'+lib['soname'],'-o',str(self.libdir/lib['filename'])]
            if kind=='epos': args += ['-L'+str(self.libdir),'-l:libftd2xx.so.1.4.8']
            subprocess.run(args,check=True,capture_output=True)
            lib['sha256']=sdk.sha256_file(self.libdir/lib['filename'])
        with contextlib.redirect_stdout(io.StringIO()): b.native_verify(self.ctx,self.libdir)
        self.assertFalse(list(self.root.rglob('__pycache__')))
        # The EPOS dependency cannot resolve without the absolute FTDI preload.
        (self.libdir/self.release['libraries']['ftdi']['filename']).unlink()
        with self.assertRaisesRegex(ValueError,'hash'): b.native_verify(self.ctx,self.libdir)

    @unittest.skipUnless(shutil.which('gcc'),'optional CLI fixture requires an already installed compiler')
    def test_cli_fixture_lifecycle_with_synthetic_shared_objects(self):
        # A test-owned checkout is the only place whose manifest is changed.
        project=self.root/'checkout'; project.mkdir()
        shutil.copytree(b.PROJECT/'lib',project/'lib')
        shutil.copytree(b.PROJECT/'config',project/'config')
        shutil.copy2(b.PROJECT/'bootstrap-epos-sdk',project/'bootstrap-epos-sdk')
        for kind in ('ftdi','epos'):
            lib=self.release['libraries'][kind]
            source=self.root/(kind+'.c')
            source.write_text('void fixture_ftdi(void) {}\n' if kind=='ftdi' else '#include <stdlib.h>\nvoid VCS_OpenDevice(void){abort();}\nvoid VCS_CloseDevice(void){abort();}\nvoid VCS_GetDriverInfo(void){abort();}\n')
            subprocess.run(['gcc','-shared','-fPIC',str(source),'-Wl,-soname,'+lib['soname'],'-o',str(self.libdir/lib['filename'])],check=True,capture_output=True)
            lib['sha256']=sdk.sha256_file(self.libdir/lib['filename'])
        archive=self.root/'synthetic.zip'
        with zipfile.ZipFile(archive,'w') as z:
            for relative,data in [('EULA.txt',b'fixture'),('include/Definitions.h',b'fixture'),('install.sh',b'never run')]+[(self.release['arch']['lib_subdir']+'/'+lib['filename'],(self.libdir/lib['filename']).read_bytes()) for lib in self.release['libraries'].values()]:
                entry=zipfile.ZipInfo('EPOS_Linux_Library/'+relative); entry.create_system=3; entry.external_attr=0o100644 << 16; z.writestr(entry,data)
        self.release['archive']['size_bytes']=archive.stat().st_size; self.release['archive']['sha256']=sdk.sha256_file(archive)
        (project/'config/sdk-release.json').write_text(json.dumps(self.release))
        bindir=self.root/'bin'; bindir.mkdir(); record=self.root/'external-actions'; rules=self.root/'rules'; rules.mkdir()
        (rules/'fixture-state.json').write_text(json.dumps(dict(group_exists=False,members=[],primary_members=[],service_active=True,reload_ok=True,events=[])))
        for name in ('sudo','apt-get','groupadd','gpasswd','udevadm'):
            script=bindir/name; script.write_text('#!/bin/bash\nprintf "unexpected %s\\n" "$0" >> "$FIXTURE_RECORD"\nexit 99\n'); script.chmod(0o755)
        query=bindir/'dpkg-query'; query.write_text('#!/bin/bash\nprintf installed\n'); query.chmod(0o755)
        curl=bindir/'curl'; curl.write_text('#!/bin/bash\nset -eu\n[[ $1 == --disable ]] || exit 99\nprintf "curl\\n" >> "$FIXTURE_RECORD"\nwhile (($#)); do if [[ $1 == --output ]]; then shift; /bin/cp -- "$FIXTURE_ARCHIVE" "$1"; exit; fi; shift; done\nexit 99\n'); curl.chmod(0o755)
        prefix=self.root/"CLI SDK ' $ semicolon;"
        env=dict(os.environ,PATH=str(bindir)+':'+os.environ['PATH'],EPOS_BOOTSTRAP_UDEV_DIR=str(rules),FIXTURE_ARCHIVE=str(archive),FIXTURE_RECORD=str(record),PYTHONDONTWRITEBYTECODE='1')
        env.pop('EPOS_SDK_DIR',None); env.pop('WSL_DISTRO_NAME',None)
        for command in ('install','verify','install','uninstall','uninstall'):
            result=subprocess.run([str(project/'bootstrap-epos-sdk'),command,'--sdk-dir',str(prefix),'--yes'],env=env,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertIn('TEST MODE',result.stderr)
        self.assertEqual(record.read_text(),'curl\n')
        self.assertFalse(prefix.exists()); self.assertFalse((rules/b.RULES).exists())
        self.assertFalse(list(project.rglob('__pycache__')))


if __name__=='__main__': unittest.main()
