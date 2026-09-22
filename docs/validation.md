# Validation record

The implementation follows the [archived system card, version 2.2](archive/system-card-v2.2.md), with the approved ZIP format exception below. Development used isolated fixtures. The user subsequently ran the normal installation and removal sequence on `ws01` and supplied the terminal output. This record distinguishes those reported host results from automated fixture tests and checks still pending.

## Research and static inspection

On 2026-09-22 a fresh download matched all three release hashes and the archive size in `config/sdk-release.json`:

| Artifact | SHA-256 |
|---|---|
| ZIP, 8,001,401 bytes | `467df7a69d67ae02d976c23a807e6bc4c00e4635e06d1330d29637868aa335b5` |
| `libEposCmd.so.6.8.1.0` | `02478aa383eefd5f39458d4c75183ae04fb765c49d75a989e4d71e6a3a10ec2a` |
| `libftd2xx.so.1.4.8` | `a6b2a5eacea47aa3b8fc5ab8d49a05abf2ba1e65db8f5b174b9486e92b73c94f` |

The ZIP directory lists 21 regular files and 13 directories, with 27,134,657 uncompressed file bytes. These counts come from archive metadata, without executing or installing the payload.

Static inspection confirmed the EPOS binary uses `DT_RPATH`. That inspection did not load either library. The later host verification reported successful loading using the FTDI preload, empty working directory, and mapped-path checks.

## Approved ZIP format exception

The freshly downloaded pinned archive contains 34 entries with zero Unix file-type bits. The archived system card's section 8.3 requirement to accept only explicit Unix regular-file and directory bits would reject the pinned vendor release itself.

The user approved a narrow exception during implementation. Absent Unix type bits are accepted only when the ZIP creator and DOS attributes identify an ordinary file or directory consistently. Explicit symlinks, devices, sockets, and other special types remain refused. No archive or library pin changed. Path traversal, root, duplicate, and case-collision checks still apply before extraction.

## Isolated checks

Run `./tests/run-tests.sh` for the suite, `bash -n`, `shellcheck -x`, and Python `ast.parse` checks. The runner uses `-B` and creates no bytecode. Fixtures use caller-owned temporary directories and simulated account and reload records. Root ownership is simulated only in fixtures; production ownership checks are tested separately.

On 2026-09-22, `./tests/run-tests.sh` passed 117 tests with no skips, plus `bash -n`, `shellcheck -x`, and AST parsing of all 10 Python files. The environment was an Ubuntu 24.04.5 container, x86_64 and Debian amd64, with `/usr/bin/python3` 3.12.3 and ShellCheck 0.9.0. `git diff --check` also passed.

The tests cover:

- CLI parsing, destination precedence, unsupported hosts, path protections, and read-only dry runs.
- Archive pins, rejected member types and paths, the approved DOS exception, ELF identity, payload modes, and activation quoting.
- Receipt schema and phase requirements, intent before apt or publication, restoration of missing files, conflicts, and unchanged healthy reruns.
- Canonical registration states, immutable provenance, two-prefix contention, same-prefix locking, publication and reload failures, and removal recovery.
- Local-only cleanup after a competing registration or an interrupted release, preexisting memberships, primary-group refusal, and retained packages/groups.
- Native child success, error, timeout and signal reporting, environment isolation, mapping checks, and temporary cleanup.

The full CLI lifecycle used synthetic shared objects in a test-owned checkout with a synthetic manifest. The exported test functions abort if invoked. Install, verify, repeat install, uninstall, and repeat uninstall passed with one stubbed download and no sudo invocation. A separate synthetic EPOS library depended on the synthetic FTDI SONAME, exercising the preload through the real isolated child. The suite uses an already installed C compiler for these two tests and skips them if none exists. It never installs a compiler or recompiles the vendor SDK.

Production apt dispatch was checked with recording mocks. HTTPS-only and redirect bounds were checked as curl arguments with no test network requests. Fixtures alone do not establish live repository/server behavior, actual account and udev effects, or vendor loading on a supported host. The reported host run below supplies additional evidence for the normal lifecycle.

## Reported host lifecycle

The user supplied transcripts from `ws01` on branch `impl/mvp`. The host gate reported Ubuntu 24.04 x86_64, and verification reported `/usr/bin/python3` 3.12.3, 64-bit. A separate `systemctl is-active systemd-udevd.service` command returned `active`. The prefix was `/home/labuser/workspace/upstream/epos-sdk`.

| Step | Reported result |
|---|---|
| `install --dry-run` | No conflicts; missing `python3-venv`; proposed the dedicated group, membership, and canonical rules. |
| `install` | Installed the missing dependency, retained the pinned archive, validated 21 payload files, configured USB access, loaded both libraries from the managed prefix, and resolved exports without calls. Verification passed. |
| Standalone `verify` | Receipt phase `complete`, zero missing owned entries, native loading and all required checks passed. This preceded sourcing `setup.bash`. |
| Repeat `install` | No missing packages; reported `installation already satisfied; no changes`. No confirmation or privileged operation appeared in the output. |
| Source `setup.bash` | Returned silently, as designed. Environment values were not separately captured. |
| `uninstall --dry-run` | Previewed removal of managed content, registration, and the membership added by the installation. |
| `uninstall` | After confirmation, reported `uninstall complete` and the intended retention of packages and the group. |
| Repeat `uninstall` | Reported `not installed; nothing to remove`, without confirmation or a privileged operation in the output. |

The session-membership warning was expected because the running shell had not picked up the new `epos` group. The final reported state has the SDK removed. Packages and the group are retained by design.

These are user-supplied command results. No independent syscall/process audit, before-and-after file snapshot, or post-removal account listing was supplied. The verifier checked rule ownership and mode internally, but a separate `stat` result was not recorded. Controller attachment state was not explicitly recorded. The output establishes a successful normal lifecycle at the default prefix, not completion of every acceptance criterion.

## Remaining acceptance checks

Use a disposable Ubuntu 24.04 amd64 host with unrestricted sudo and functioning `systemd-udevd` for interruption and concurrency experiments. Keep controllers disconnected. These tests require explicit approval before an agent runs them.

1. Repeat the lifecycle with a custom prefix containing a space.
2. Record rule ownership and `0644` mode separately, and verify configured membership and effective groups after a fresh login.
3. Audit a healthy rerun for unchanged artifact hashes and timestamps, zero sudo calls, and no reload, download, or apt invocation.
4. Observe vendor initialization effects and check for unexpected persistent files and temporary-directory cleanup.
5. Exercise competing prefixes and interrupted system operations under the production directory lock. Confirm reload retry when rule bytes already match and when operative rules have already been removed.
6. After removal, separately verify absent managed files, registration and publication temporaries, removed tool-added membership, and retained packages, group, and preexisting memberships.

Fixtures cover these branches, but the corresponding production checks remain pending. A container cannot establish host udev acceptance. Controller communication, USB permissions on actual hardware, commissioning, and motor operation remain outside this project's acceptance criteria.
