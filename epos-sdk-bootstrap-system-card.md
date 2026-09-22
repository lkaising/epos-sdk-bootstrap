# EPOS SDK Bootstrap — implementation handoff

Version: 1.0 · Prepared: 2026-09-21 · Target: Ubuntu 24.04 amd64

This is a standalone specification for an implementing agent. It contains the agreed product scope, proposed defaults for remaining implementation choices, researched vendor facts, and acceptance tests. The original conversation is not required. This card is a design deliverable; the bootstrap has not been implemented or tested on Ubuntu yet.

## 1. Product intent and success criterion

Build a small command-line tool named `bootstrap-epos-sdk`, in a project tentatively named `epos-sdk-bootstrap`.

The user has an Intel/AMD Ubuntu 24.04 computer and wants maxon's EPOS Linux SDK installed in a user-owned upstream directory. A later Python application will use that SDK to operate motors. The user has previously built similar Bash bootstraps for ROS 2 and Allied Vision cameras and wants the same understandable, inspectable approach with a smaller scope.

The complete public command set is:

```text
install
verify
uninstall
```

`install` downloads and configures the native SDK. `verify` checks the software installation without requiring or testing a controller. `uninstall` removes the installation and the configuration owned by this tool.

The success statement is: **“The specified EPOS SDK is installed, its native libraries load on this Ubuntu system, and its persistent USB access configuration is in place.”**

It does not mean that a controller has been found, USB communication works, a motor is correctly configured, or motion is safe. Software verification must succeed on a supported Ubuntu host with no controller attached.

## 2. Agreed scope and explicit defaults

The user explicitly requested downloading into an upstream location, configuration, uninstall, and installation-only verification. A chosen directory and ordinary-user operation are required. Keep these requirements even if reference repositories or vendor instructions suggest a broader installation.

The following defaults resolve implementation details without requiring another planning conversation. They are recommendations for this first version, not additional requirements previously supplied by the user.

| Decision | v1 default |
|---|---|
| Operating system | Ubuntu `ID=ubuntu`, `VERSION_ID=24.04` |
| Architecture | `uname -m` = `x86_64`, Debian architecture = `amd64`, 64-bit system Python |
| SDK version | Pinned `6.8.1.0`, using the archive and hashes below |
| Default destination | `$HOME/workspace/upstream/epos-sdk` |
| Destination overrides | `--sdk-dir PATH` > `EPOS_SDK_DIR` environment variable > default |
| Implementation | Bash entry point, small helper modules where useful, Python standard library for structured data/archive/loading checks |
| Library selection | Local SDK paths and a generated `setup.bash`; no global linker registration |
| USB access | Dedicated `epos` group and one tool-owned udev rules file |
| Installed hardware families | Rules for both SDK-listed EPOS2 and EPOS4 USB IDs; no model selection or detection required |
| Python environment | Prepare system Python/venv capability; application projects create their own venvs |
| Number of registered installations | One managed installation per machine in v1; do not replace a registration at another prefix or owned by another user |
| Version changes | Maintainer changes the pinned release after validation; no automatic upgrades |

The exact controller model, motor, encoder, power supply, and wiring are unknown. Those are not blockers for this software-only bootstrap. Do not ask the user for motor parameters while implementing it.

## 3. Boundaries: what not to build

Do not add ROS integration, a Python motor-control package, a GUI, background service, controller discovery, `probe`, `status`, `update`, `clean`, tuning, homing, fault clearing, firmware updates, or motion commands to v1.

Do not install EPOS Studio, Wine, Windows drivers, CAN adapters, or EtherCAT components. Do not recompile the vendor SDK: this package supplies precompiled libraries. Retain the bundled examples as vendor files but do not build or run them during installation or verification.

Do not create an application workspace, `.venv`, `requirements.txt`, editor configuration, global pip packages, shell-startup edits, an executable link in `~/.local/bin`, or system-wide `LD_LIBRARY_PATH` settings. Those are unnecessary for this small installer. A README can show how a later application uses its own venv.

Never run the vendor `install.sh`, including its uninstall mode. Do not call `VCS_OpenDevice`, `VCS_GetPortNameSelection`, or other SDK functions to inspect or operate controllers. The verification helper may load libraries and resolve exported symbol addresses but must not invoke an EPOS API function.

## 4. Vendor facts verified during research

The [official EPOS product download page](https://www.maxongroup.com/maxon/view/product/380264) currently offers Linux Library 6.8.1.0. The specific product page is a download source, not a claim that the user's controller is product 380264.

Download specification:

```text
URL:
https://www.maxongroup.com/medias/sys_master/root/9443687202846/EPOS-Linux-Library-En.zip

Archive filename:
EPOS-Linux-Library-En.zip

Archive bytes observed:
8001401

Archive SHA-256:
467df7a69d67ae02d976c23a807e6bc4c00e4635e06d1330d29637868aa335b5

Archive top-level directory:
EPOS_Linux_Library
```

These SHA-256 values were calculated from the official download on 2026-09-21. They are reproducibility pins, not vendor signatures. A different hash must fail installation; do not automatically replace the expected hash or fall back to a mirror. If maxon changes the archive, investigate it and deliberately update the release specification.

Relevant paths inside the extracted archive:

```text
EPOS_Linux_Library/
  EULA.txt
  install.sh
  include/Definitions.h
  lib/intel/x86_64/libEposCmd.so.6.8.1.0
  lib/intel/x86_64/libftd2xx.so.1.4.8
  lib/intel/x86/...
  lib/arm/v6/...
  lib/arm/v7/...
  lib/arm/v8/...
  misc/99-ftdi.rules
  misc/99-epos4.rules
  examples/HelloEposCmd/...
```

Retain the complete extracted package, including its license and other architecture directories. Select only `lib/intel/x86_64` for this tool's runtime configuration. The archive does not include the separately downloadable Command Library manual; link to it in the README rather than expanding the download scope.

Binary details, inspected statically:

| File | SHA-256 | ELF identity |
|---|---|---|
| `libEposCmd.so.6.8.1.0` | `02478aa383eefd5f39458d4c75183ae04fb765c49d75a989e4d71e6a3a10ec2a` | 64-bit little-endian x86-64; SONAME `libEposCmd.so` |
| `libftd2xx.so.1.4.8` | `a6b2a5eacea47aa3b8fc5ab8d49a05abf2ba1e65db8f5b174b9486e92b73c94f` | 64-bit little-endian x86-64; SONAME `libftd2xx.so` |

`libEposCmd` directly depends on `libftd2xx.so`, `libpthread.so.0`, `librt.so.1`, `libstdc++.so.6`, `libm.so.6`, `libgcc_s.so.1`, and `libc.so.6`. The FTDI library directly depends on `libpthread.so.0`, `librt.so.1`, and `libc.so.6`. Keep the bundled FTDI library available even when the eventual controller is an EPOS4, because this is a dependency of the EPOS binary itself.

The EPOS binary contains a build-machine RPATH ending in a colon. Do not depend on that path or the working directory for loading. Explicitly preload the bundled FTDI library and verify that the intended EPOS/FTDI files are the ones loaded. No binary patching is required by this design.

The vendor installer hard-codes `/opt/EposCmdLib_6.8.1.0`, creates `/usr/lib` links, installs USB rules with `0666`, makes examples broadly writable, and adds passwordless `/bin/ip` access. It offers no custom-prefix option. These findings come from direct inspection of [the SDK archive](https://www.maxongroup.com/medias/sys_master/root/9443687202846/EPOS-Linux-Library-En.zip). The new bootstrap replaces those installation mechanics with the explicitly defined footprint below.

## 5. Public interface

Proposed usage:

```bash
./bootstrap-epos-sdk install --dry-run
./bootstrap-epos-sdk install
./bootstrap-epos-sdk verify
./bootstrap-epos-sdk uninstall --dry-run
./bootstrap-epos-sdk uninstall

# Chosen location: repeat the override for subsequent commands.
./bootstrap-epos-sdk install --sdk-dir "$HOME/workspace/upstream/epos-sdk"
./bootstrap-epos-sdk verify --sdk-dir "$HOME/workspace/upstream/epos-sdk"
```

Supported flags only:

| Flag | Meaning |
|---|---|
| `--sdk-dir PATH` | Managed installation root; support spaces and shell metacharacters through correct quoting |
| `--dry-run` | Print the chosen operation's plan and locally observable state; no network, sudo, writes, logs, or library execution |
| `--yes`, `-y` | Skip the normal install/uninstall summary confirmation; never override ownership or integrity refusals |
| `--help`, `-h` | Print help without performing checks that can mutate anything |

Accept flags before or after the command. Reject conflicting commands, unknown flags, empty path values, and missing flag values. No arguments should display help and exit 0, avoiding an accidental installation. There is no version-selection, arbitrary download URL, archive-input, force, or repair flag in v1.

Before an actual install or uninstall, show the resolved prefix and exact intended changes. A single ordinary yes/no confirmation is sufficient; `--yes` supports automation. An already satisfied installation or fully absent uninstallation should finish without confirmation or sudo. A dry run never prompts. Normal sudo authentication is separate from the tool's confirmation.

Use these stable exit statuses:

| Exit | Meaning |
|---|---|
| 0 | Command succeeded, already satisfied/absent, or a valid dry run completed |
| 1 | Operation or verification failed, including ownership conflicts, hash mismatch, declined confirmation, or missing install |
| 2 | Invalid arguments or unsupported host for a real operation |

Warnings do not alone change a successful exit status. Make error messages actionable and name the failed check and path. Standard output/error is enough; persistent run-log infrastructure is not required for v1.

## 6. Managed files and ownership

Recommended installed layout:

```text
<sdk-dir>/
  .epos-sdk-bootstrap.json
  setup.bash
  downloads/
    EPOS-Linux-Library-En.zip
  vendor/
    EPOS_Linux_Library/
      ...complete vendor package...
      lib/intel/x86_64/
        libEposCmd.so.6.8.1.0
        libftd2xx.so.1.4.8
        libEposCmd.so -> libEposCmd.so.6.8.1.0
        libftd2xx.so -> libftd2xx.so.1.4.8
```

The two unversioned symlinks are generated by the bootstrap and use relative targets. The libraries, archive, generated files, and directories remain owned by the ordinary user. Do not reproduce the vendor's broad write permissions. Use normal user-owned directory/file permissions; group/world write access is unnecessary.

The only persistent root-owned file created by the tool is:

```text
/etc/udev/rules.d/99-epos-sdk-bootstrap.rules
```

System package installations and group membership are additional system changes and must be listed separately; do not describe the footprint as “only one change.”

The local JSON receipt is data, never shell-sourceable code. At minimum record:

- Schema version, tool identity, installation UUID, canonical prefix, installing UID and username.
- SDK version, archive URL and hash, selected architecture, installation phase.
- Managed regular files and expected SHA-256 values; generated symlinks and exact link targets; managed directories.
- Udev path and exact expected content or hash.
- Whether the `epos` group and this user's membership existed before this installation.
- Relevant completed/intended system actions for recovery from interruption.

Store original group-membership provenance before modifying it. Never overwrite that provenance on a rerun just because the membership now exists.

Do not include the receipt's own hash in its managed-file hash list. Validate the receipt through its schema, identity, allowed paths, and agreement with the root registration; hashing it inside itself would be circular. The release manifest's pinned archive and selected-binary hashes remain independent of the receipt.

Include a machine-readable JSON comment in the root-owned udev file carrying the installation UUID, canonical prefix, UID, username, and whether membership predated the tool. Generate it with JSON serialization, on one comment line. This acts as the machine-wide registration and enables identification if the local directory goes missing. Do not execute or source metadata from either file.

A matching root registration permits a rerun at the same prefix by its owner. A different prefix, UUID, owner, or unrecognized existing rules file is a conflict: leave it untouched and explain which installation must be uninstalled first. There is no v1 adoption or forced overwrite mode.

Validate receipt entries before using them as filesystem paths: allow only expected relative paths within the prefix, reject traversal/absolute paths, and do not follow unexpected symlinks. A user-writable receipt is not authority to delete arbitrary files or elevate arbitrary commands.

## 7. Installation behavior

Implement a small series of check/action stages. Check real state on every run; the receipt's phase alone is not evidence that a stage succeeded.

1. **Parse and inspect.** Resolve destination precedence. Validate the host and effective user. Refuse a real operation running as root; obtain the identity with `id`, not a blindly trusted `$USER`/`$SUDO_USER` value. Detect destination and udev ownership conflicts before changing the machine.
2. **Plan.** Show SDK version/URL, resolved prefix, missing packages, local files, udev content, and group changes. Handle dry run and confirmation before mutations.
3. **Dependencies.** Install only missing required Ubuntu packages, using sudo for apt. No `apt upgrade`, external package repositories, source builds, or global pip. Skip apt and sudo when packages are already satisfied.
4. **Download and validate.** Download as the ordinary user into a controlled staging area. Verify the pinned hash before extraction or executing anything from the archive.
5. **Prepare the local installation.** Validate archive member paths, extract into staging, check required files and ELF architectures, create the two relative symlinks and activation file, and write a receipt. Publish only validated payload into the managed prefix; a partial download must not appear to be a completed SDK.
6. **Configure USB access.** Create the group if missing, add the installing user if needed, and install the owned udev file. Record intended/provenance state before system changes so a failed run can resume. Publish the root file atomically with root ownership and mode `0644`. Reload udev rules if the rule changed.
7. **Verify.** Run the same installation-only checks as `verify`, including native library loading as the ordinary user. Mark the receipt complete only after required checks pass. Print the prefix, activation command, and any session-refresh note.

Idempotency contract: a healthy rerun does not download again, invoke apt/sudo, rewrite matching files, add duplicate group memberships or environment entries, or change its installation ID. Running read-only verification again is acceptable. The retained archive can supply missing payload during a resumed install if its hash still matches. Modified managed files or unexpected content are conflicts, not permission to overwrite user changes.

Do not promise a transaction covering apt. If later work fails, already installed Ubuntu packages remain. Keep owned recovery information, report what completed, and allow a rerun or uninstall to recover. Leave previously healthy content intact if a new preparation stage fails. Prevent overlapping install/uninstall operations from corrupting the same prefix or machine-wide registration; one advisory lock on a mutating path is sufficient, and dry run/verify must not create it.

## 8. Dependencies, downloads, and path handling

Runtime/setup packages:

```text
python3
python3-venv
curl
ca-certificates
libc6
libstdc++6
libgcc-s1
udev
```

Most are present on a standard Ubuntu machine. The tool may use Python's standard-library `zipfile` module, avoiding an extra unzip dependency. `sudo`, Bash, apt/dpkg, coreutils, account-management tools, and a working udev service are host prerequisites. Report missing prerequisites clearly. Do not install a sudo policy or attempt to grant the invoking account administrative rights.

Do not add `build-essential`, CMake, ROS, `libftdi1`, a separately downloaded FTDI SDK, libusb development headers, `pythonnet`, `pyserial`, or third-party Python packages. No application compilation is required. If actual Ubuntu loading reveals a previously unobserved dependency, identify it, update the documented requirement deliberately, and test it; do not install a collection of guessed packages.

Use HTTPS with certificate verification and failure-on-HTTP-error. Limit redirects to HTTPS, use bounded connection/transfer timeouts and a small retry count, and leave no completed-looking archive on interruption. Downloading should never use sudo. Pin URL/version/hash together in a small maintainer-controlled release manifest.

Archive handling must reject absolute paths, `..` traversal, unexpected top-level roots, symlink/special-file members, and duplicate/conflicting member paths. The inspected release contains regular files and directories; internal symlinks are created by this tool afterward. Preserve `EULA.txt`. Link to vendor downloads and terms in the README; do not commit the SDK binaries to the bootstrap repository.

Path rules:

- Use an explicit absolute destination, or expand/resolve a supplied relative path consistently and display it before modification.
- Canonicalize existing ancestors. Reject a symlink at the destination itself and unexpected symlinks inside managed paths.
- Reject `/`, the user's home directory, the bootstrap checkout, ancestors of the home/checkout, and system configuration directories as installation roots. The destination must be a suitable user-owned SDK directory with a writable parent; do not use sudo to create it.
- Accept a nonexistent or genuinely empty destination. Refuse a populated destination without this tool's valid receipt.
- Support spaces and safely quoted shell metacharacters. Reject newlines/control characters and `:` in the prefix because it is used in a colon-delimited library path. Do not evaluate user input as shell code.
- Do not infer the custom prefix from whichever SDK happens to be on the current library path. Commands use their resolved `--sdk-dir`/environment/default consistently.

## 9. USB configuration and its limits

Use the IDs taken from the vendor rules, with group-restricted access:

```udev
# Tool identity and serialized installation metadata go above these lines.
SUBSYSTEMS=="usb", ATTRS{idVendor}=="0403", ATTRS{idProduct}=="a8b0", GROUP="epos", MODE="0660"
SUBSYSTEMS=="usb", ATTRS{idVendor}=="24e7", ATTRS{idProduct}=="3b01", GROUP="epos", MODE="0660"
```

The first is the SDK's EPOS2 FTDI ID; the second is its EPOS4 ID. Preserve the distinction. These are not an exhaustive catalog of every future controller. No vendor-wide or all-USB `0666` rule is allowed.

After an actual rules-file change, run `udevadm control --reload-rules` with sudo. Do not trigger all USB devices or restart the udev service. Applying permissions to an already attached device is outside the installation test; explain that a later hardware session may require reconnection according to the controller's documented power-off USB procedure.

Adding group membership does not change already running processes. Compare configured account membership with effective groups of the current process. If configured membership is correct but the process is stale, installation verification can pass with a prominent advisory to start a new login/SSH session. Do not launch `newgrp`, change the user's shell, or reboot automatically.

If legacy `/opt` installations, global EPOS/FTDI links, or vendor rules exist, report them. Do not invoke the vendor uninstaller, remove foreign rules, or silently migrate an existing installation. Exact access granted by all other udev rules cannot be proved without examining their combined behavior on hardware; do not claim this tool guarantees exclusive permissions.

EPOS2 can encounter an `ftdi_sio`/D2XX conflict. Mention it as later troubleshooting only. Never blacklist drivers, unload modules, detach devices, or probe for a conflict during bootstrap verification. [FTDI explanation](https://ftdichip.com/faq/can-i-just-load-the-d2xx-drivers-and-run-a-d2xx-application-on-a-newly-installed-linux-system/), [maxon USB distinctions](https://support.maxongroup.com/hc/en-us/articles/360014218020-EPOS4-IDX-Action-steps-in-case-of-failing-USB-connection).

## 10. Local activation and Python consumption

Generate `<sdk-dir>/setup.bash` that, when explicitly sourced:

```text
sets EPOS_SDK_DIR to the managed root
sets EPOS_LIB_DIR to <root>/vendor/EPOS_Linux_Library/lib/intel/x86_64
adds that directory once at the front of LD_LIBRARY_PATH
```

Use proper shell escaping when generating paths. Preserve other nonempty library-path entries; do not introduce empty search entries or duplicate this SDK directory on repeated sourcing. The file should be quiet on success, and fail clearly if the expected installation is missing. Do not source it automatically or edit `.bashrc`, `.profile`, `/etc/profile.d`, `/etc/ld.so.conf*`, or `/usr/lib`.

For the README, an application may instead explicitly load the two files from `EPOS_LIB_DIR`. This illustrates the load order without contacting hardware:

```python
import ctypes
import os
from pathlib import Path

lib_dir = Path(os.environ["EPOS_LIB_DIR"])
ftdi = ctypes.CDLL(str(lib_dir / "libftd2xx.so.1.4.8"), mode=ctypes.RTLD_GLOBAL)
epos = ctypes.CDLL(str(lib_dir / "libEposCmd.so.6.8.1.0"))
# Keep both objects alive. No controller is opened here.
```

`ctypes` is part of Python, not a pip dependency. Maxon recommends this approach but does not provide a supported native Python SDK. A later application owns its venv, dependencies, motor configuration, and C function bindings. [maxon's Python guidance](https://support.maxongroup.com/hc/en-us/articles/360012695739-EPOS2-EPOS4-IDX-Commanding-by-Python-ctypes).

A future application must match `argtypes`/`restype` to the shipped Linux `include/Definitions.h`. In this release, handles are `void*`; `VCS_GetPositionIs` takes `int*`, while `VCS_MoveToPosition` takes a C `long` target. These facts explain why the bootstrap should not copy an arbitrary Windows Python wrapper. Implementing those motor API bindings is out of scope here.

## 11. Exact verification contract

`verify` uses no sudo and makes no repairs, downloads, package changes, group changes, device calls, or persistent run logs. It must not require the caller to have sourced `setup.bash`. If prerequisites are absent it fails with instructions to run `install`.

Required checks:

| Check | Passing condition |
|---|---|
| Host | Supported Ubuntu/architecture and non-root execution |
| Installation identity | Valid supported receipt schema; matching prefix, owner, release, and registration |
| Archive | Retained archive matches pinned SHA-256 |
| Payload | Managed regular files match the recorded release contents; required files, license, and header are present |
| Selected libraries | Both match the pinned hashes, are ELF64 little-endian x86-64, and have the expected local links |
| Activation | Generated file matches the expected configuration and points inside the chosen prefix |
| Python | System Python imports `ctypes`; `python3-venv` is installed; interpreter is 64-bit |
| Native dependencies | The intended EPOS/FTDI libraries load successfully in a bounded child process and all their native dependencies resolve |
| Expected exports | Resolve addresses of representative symbols such as `VCS_OpenDevice`, `VCS_CloseDevice`, and `VCS_GetDriverInfo`; call none of them |
| USB configuration | Owned rules file has expected metadata/content, root ownership and mode; `epos` exists and account membership is configured |
| Udev service | The expected host udev service is available/running; no device permissions are tested |

Run the load check in a separate process with a short deadline, for example 10 seconds, so a native crash or hang becomes a clear verification failure. Verify trusted file hashes before loading them. Use explicit absolute library paths and retain the FTDI handle. Isolate the child from inherited Python paths and dynamic-loader overrides that could substitute foreign libraries; do this only in the child, not by changing the user's shell. Confirm selected EPOS/FTDI library paths, for example from the child process's `/proc/self/maps`, rather than assuming a matching filename is sufficient. Do not hard-code system libc paths; successful loading resolves those dependencies.

Resolving an export address is allowed; invoking it is not. Native library loading executes vendor initialization code. This research did not establish every internal side effect of that initialization, so do not advertise “zero USB syscalls” or “no vendor initialization.” The promised behavior is no explicit controller enumeration, connection, data request, state change, or hardware test by this tool. Characterize any initialization side effects during Ubuntu validation. If a supposedly software-only check requires a controller to succeed, that check does not belong in default verification.

Verification must not intentionally leave cache files or bytecode in the SDK or application folders. Avoid Python bytecode writes in the helper; clean any owned temporary resources. If the vendor loader creates unavoidable persistent state, document the observed behavior and adjust the check deliberately rather than silently violating the contract.

Unexpected extra files in the SDK prefix may be reported as a warning when all required files remain valid. Modified managed files are failures. Uninstall has the stricter preservation behavior below.

Suggested successful output:

```text
PASS  supported host: Ubuntu 24.04 amd64
PASS  SDK archive and installed files: 6.8.1.0
PASS  local EPOS and FTDI libraries load
PASS  Python and expected library exports available
PASS  USB access configuration installed
NOTE  new login required for this shell to receive the epos group   [if applicable]
PASS  SDK installation verified
NOTE  controller communication and motor operation were not tested
```

Do not show a “missing controller” warning. No controller is expected for this command. The final success wording must not overstate Ubuntu hardware compatibility or active-session USB permissions.

## 12. Uninstall and recovery

Uninstall must work when the download server is unavailable or native libraries are missing/unloadable. It uses validated ownership records and static inspection, not SDK execution.

Before removing anything:

1. Resolve and validate the prefix and machine-wide registration.
2. Confirm the invoking UID owns that registration and the IDs match.
3. Inventory every expected file/link and actual prefix entry without following symlinks.
4. Refuse if a managed file has changed, a generated link points elsewhere, an unrecognized file is present, or foreign system configuration occupies the owned rules filename. Explain the exact conflict so the user can preserve/move it and retry. Missing owned files are allowed for cleanup of a partial installation.
5. Print the exact local installation, rules file, and membership change to be removed, plus resources deliberately retained. Confirm once unless `--yes` was supplied.

Remove only recorded managed content and the matching owned udev rule. Remove this user's `epos` membership only if this installation originally added it; preserve preexisting membership. Retain the named group itself as a shared system resource, even if originally created here. Retain installed apt packages, other users' memberships, foreign configuration, application projects, all venvs, motor parameter backups, and any vendor data outside the managed prefix. State these retained resources in the completion message.

Reload udev rules after removing the owned rule. Do not try to revoke already running sessions' supplementary groups or alter connected devices. Explain that future USB permission behavior changes when rules are reapplied. An already sourced shell may still contain an obsolete `EPOS_LIB_DIR`/library-path entry; recommend a fresh shell rather than editing startup files.

Remove directories only when empty after deleting the validated owned contents. Keep the receipt until the last practical step. Preserve enough phase information to resume after a partial failure; return nonzero instead of claiming success. Repeating uninstall after a fully successful removal exits 0 without sudo.

If the prefix was manually deleted but a matching root-owned registration remains, use its validated metadata to remove only that owned rule and any recorded tool-added membership. If the prefix is populated but its receipt is missing or invalid, do not delete its contents. Report the conflict. A `--yes` flag never bypasses these checks.

## 13. Suggested repository organization

Keep the code smaller than the ROS bootstraps. This is an organizational suggestion, not a required framework:

```text
epos-sdk-bootstrap/
  README.md
  bootstrap-epos-sdk
  config/sdk-release.json
  lib/common.sh
  lib/install.sh
  lib/verify.sh
  lib/uninstall.sh
  lib/sdk_files.py
  lib/check_load.py
  tests/run-tests.sh
  .gitignore
```

Merge helpers if that improves clarity. Use a small number of direct functions; do not create a general plugin/stage framework, daemon, database, package manager, or reusable SDK abstraction. Only add a test dependency if the standard library and shell fixtures prove insufficient.

Do not run installer scripts from the reference repositories as part of this task. They are design references, not dependencies. Their ROS checks, camera configuration, and source-build workflows are not applicable to this tool.

## 14. Required tests and acceptance criteria

Tests are justified here because the tool downloads binaries and modifies system access configuration. They must verify meaningful behavior and filesystem boundaries. Fixture tests must redirect all filesystem and privileged operations into controlled temporary fixtures or mocks; never mutate the developer's real `/etc`, accounts, or upstream directories. Production interfaces must not expose arbitrary privileged destinations merely to make testing easier.

| Area | Required cases |
|---|---|
| CLI | Three commands, no-argument help, flags before/after commands, unknown/conflicting options, empty values, precedence, paths containing spaces/metacharacters |
| Read-only behavior | Help and every dry run make no writes/network/sudo calls and do not load vendor libraries; verify makes no deliberate persistent changes or EPOS API/device calls; owned temporary resources are cleaned |
| Host checks | Ubuntu 24.04 amd64 accepted; macOS, ARM, 32-bit Python, and real root execution refused appropriately |
| Download/extraction | Correct pin accepted; hash mismatch, HTML error response, interrupted transfer, traversal, duplicate entries, and archive symlinks rejected |
| Installation | Fresh install creates exact footprint; healthy rerun skips mutations; failed stages can resume; foreign/populated prefix and another registered owner/prefix are preserved |
| Permissions | Sudo used only for package/account/udev actions; native files owned by user; root rule `0644`; no world-writable device rule, sudoers edit, or global library registration |
| Receipt | Original membership provenance survives reruns; invalid schema/path traversal/symlink targets never authorize deletions |
| Activation | Correct custom path; repeated sourcing does not duplicate entries; no empty library-path entry introduced; no shell-startup files changed |
| Verification | Missing, modified, wrong-architecture, and missing-dependency cases fail; native load success/failure/crash/timeout handled; foreign library substitution detected; no attached hardware still passes |
| USB/session state | Missing group/configured membership/rules fail; stale effective groups produce advisory; no USB enumeration, module unload, or device trigger |
| Uninstall | Exact owned content removed; packages/group/preexisting membership retained; added membership removed; unknown/modified files preserved through refusal; missing payload cleanable; repeat is a no-op; partial failures recoverable |
| Concurrency | Two mutating invocations cannot both claim or corrupt the same machine registration |

Use mocked downloads/commands for deterministic fixture tests. Mocks prove bootstrap logic, not that maxon's binary works. Also perform a real integration test in a disposable Ubuntu 24.04 amd64 system with sudo and a functioning udev service, without an EPOS controller. Exercise install → verify → install again → uninstall → uninstall again, including a custom path. A container without a real udev service can test file/loading behavior but cannot establish the complete host acceptance criteria.

The real verification test should use the official pinned archive and Ubuntu's system Python. Record OS, architecture, Python version, SDK hash, and actual results. It is acceptable to develop and run fixture/syntax tests on macOS; clearly mark Ubuntu integration as pending until it is run. Do not claim vendor certification from your own successful test.

## 15. Known limits and research evidence

The [Command Library manual, section 9.2](https://www.maxongroup.com/medias/sys_master/root/9157360353310/EPOS-Command-Library-En.pdf) lists older Intel Ubuntu versions in its tested-platform table. It does not establish Ubuntu 24.04 support. Library loading and installation behavior need actual Ubuntu validation. Controller communication remains outside v1 acceptance.

EPOS Studio is the Windows commissioning tool. Configuration/tuning and persistent parameter backups belong to the later hardware workflow; the Linux library does not reproduce all Studio GUI or parameter import/export features. [Commissioning guidance](https://support.maxongroup.com/hc/en-us/articles/6719969220380-EPOS4-IDX-Important-steps-during-initial-commissioning), [parameter backups](https://support.maxongroup.com/hc/en-us/articles/360005421674-EPOS-IDX-Export-of-parameter-configuration-in-a-dcf-file).

The vendor `HelloEposCmd` source defaults to a motion demonstration that can clear faults and enable the drive. It must never be the bootstrap smoke test. Losing USB communication also does not inherently stop EPOS2/EPOS4 motion; this is context for excluding motor tests, not a feature for this installer to solve. [Communication-loss behavior](https://support.maxongroup.com/hc/en-us/articles/360012982439-EPOS4-Motor-stop-at-communication-lost).

Research already completed: official archive download, archive hash and structure inspection, installer inspection, static x86_64 binary/ELF dependency inspection, header inspection, and review of the user's prior bootstrap code. No Linux binary, controller, or motor was run during that research. The earlier read-status Python example from the conversation opens a controller; it is intentionally not part of this tool.

## 16. Prior projects to consult

These are references for style and behavior, not prerequisites. The implementing agent should inspect current files before adapting code; the repositories may evolve. The hashes below are reviewed **Git blob hashes of the named files**, not commit IDs or clone refs.

| Reference | Relevant patterns | Reviewed entry-point blob |
|---|---|---|
| [vimbax-sdk-bootstrap](https://github.com/lkaising/vimbax-sdk-bootstrap/blob/main/bootstrap-vimbax-sdk) | SDK directory override, ELF architecture checks, exact system-file previews, idempotency | `b44d0cdc8845082a926ca222ccfe1411a3aea616` |
| [ros2-jazzy-bootstrap](https://github.com/lkaising/ros2-jazzy-bootstrap/blob/main/bootstrap-ros2-jazzy) | Check/action stages, strictly read-only dry runs, workspace ownership | `492b4fe993e5675f3a7098546b4631f28029c94e` |
| [vimbax-ros2-driver-bootstrap](https://github.com/lkaising/vimbax-ros2-driver-bootstrap/blob/main/bootstrap-vimbax-ros2-driver) | Small entry point, dependency ownership boundaries, fixture tests | `9353ff91a37d80c5c0df9a19c417c28364604195` |

Particularly useful supporting files are [ROS workspace ownership](https://github.com/lkaising/ros2-jazzy-bootstrap/blob/main/lib/workspace.sh), [guarded cleanup](https://github.com/lkaising/ros2-jazzy-bootstrap/blob/main/lib/clean.sh), and [driver fixture tests](https://github.com/lkaising/vimbax-ros2-driver-bootstrap/blob/main/tests/run-tests.sh). The Vimba SDK tool assumes an already extracted SDK and registers a global GenTL path; this EPOS design deliberately includes download/extraction and uses local library paths. The camera simulator test does not transfer to EPOS.

## 17. Deliverables and remaining questions

The implementation deliverables are a runnable bootstrap, its small helpers/release manifest, tests, and a README covering install, custom paths, verify meaning, uninstall scope, Python consumption, and known limitations. Include exact test results and any pending Ubuntu validation in the final implementation report.

There are no blocking product questions for implementing this v1. The defaults in section 2, command UX in section 5, and group retention policy in section 12 are explicit design choices the user can revise. Do not expand scope to resolve the unknown controller or motor.

Ask for a decision only if a concrete new fact invalidates the design—for example, the official pinned archive becomes unavailable, the real Linux library fails on Ubuntu 24.04, or the destination machine has a conflicting registration that cannot be handled within the ownership rules. Present the evidence and a specific alternative. Do not silently change versions, remove foreign installations, or declare hardware compatibility.

This handoff specifies the project to implement. Creating or publishing a GitHub repository, pushing commits, or installing on a real host follows the instructions of the task in which the implementing agent receives it; possession of this card alone is not an instruction to publish or modify a host.
