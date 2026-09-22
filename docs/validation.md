# Validation record

The implementation targets system-card version 2.2. No real SDK installation, native vendor load, host package change, group change, or host udev configuration change is authorized by the implementation task. Real installation and integration validation require explicit approval.

## Research and static inspection

On 2026-09-22 a fresh download matched all three release hashes and the archive size in Appendix A:

| Artifact | SHA-256 |
|---|---|
| ZIP, 8,001,401 bytes | `467df7a69d67ae02d976c23a807e6bc4c00e4635e06d1330d29637868aa335b5` |
| `libEposCmd.so.6.8.1.0` | `02478aa383eefd5f39458d4c75183ae04fb765c49d75a989e4d71e6a3a10ec2a` |
| `libftd2xx.so.1.4.8` | `a6b2a5eacea47aa3b8fc5ab8d49a05abf2ba1e65db8f5b174b9486e92b73c94f` |

The ZIP directory lists 21 regular files and 13 directories, with 27,134,657 uncompressed file bytes. These counts come from archive metadata, without executing or installing the payload.

Static inspection confirmed the EPOS binary uses `DT_RPATH`, not `DT_RUNPATH`. No binary was loaded. The bootstrap retains the specified FTDI preload, empty working directory, and mapped-path checks.

## Approved ZIP format exception

The freshly downloaded pinned archive contains 34 entries with zero Unix file-type bits. Section 8.3's original requirement to accept only explicit Unix regular-file and directory bits would reject the pinned vendor release itself.

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

Production apt dispatch was checked with recording mocks. HTTPS-only and redirect bounds were checked as curl arguments with no test network requests. Fixtures do not establish live repository/server behavior, actual account and udev effects, or vendor loading on a supported host. Those remain part of the approved installation sequence below.

## Pending first installation

After explicit approval, use a disposable Ubuntu 24.04 amd64 host with unrestricted sudo and functioning `systemd-udevd`. Keep controllers disconnected. Record OS, machine and Debian architectures, `/usr/bin/python3` version and bitness, manifest hashes, and the `DT_RPATH` observation.

1. Run `install --dry-run` and review the prefix, packages, group changes, rules, and sudo commands.
2. Run `install`, then `verify`, with a custom prefix containing a space.
3. Observe native initialization effects. Confirm mapped library paths, export resolution without calls, absence of unexpected persistent state, and temporary-directory cleanup.
4. Repeat `install`. Confirm unchanged artifacts and identity, zero sudo calls, no reload, and no download or apt invocation.
5. Check actual root ownership and `0644` mode of the rules file, configured membership, effective-session advice, and active udev service.
6. Test competing prefixes under the production rules-directory lock and interruption recovery with durable registration intent. Confirm a failed or interrupted reload retries even when rule bytes already match.
7. Run `uninstall`, then `uninstall` again. Confirm the second run exits 0 without sudo, that the owned rule and publication temporaries are absent, and that package, group, and preexisting membership retention matches recorded provenance.

These integration checks remain pending. A container cannot establish host udev acceptance. Controller communication, USB permissions on actual hardware, commissioning, and motor operation remain outside v1 acceptance even after this sequence passes.
