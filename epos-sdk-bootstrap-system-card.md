# EPOS SDK Bootstrap — implementation handoff

Version: 2.1 · Revised: 2026-09-22 · Target: Ubuntu 24.04 amd64

A standalone specification for an implementing agent: product scope, resolved defaults, researched vendor facts, the exact content of every file the tool generates, and acceptance tests. The original conversation is not required. Nothing here has been implemented or tested on Ubuntu yet.

Sections 1–17 are the specification; Appendices A–E are the artifacts the tool reads and writes, and where a section and an appendix disagree the appendix wins, because it is the thing that gets hashed. Appendix F is a suggested build order. Version history is in git.

**Evidence status.** The §16 blob hashes were re-verified on 2026-09-22 and all three match. The §4 vendor facts were measured on 2026-09-21 and could not be re-confirmed, because the revising environment cannot reach `www.maxongroup.com`. Nothing has been executed on Ubuntu. Step 1 of Appendix F is therefore to re-download the archive and confirm the pins before writing installer logic against them; if a pin differs, stop and follow §17 rather than adjusting the pin to match.

## 1. Product intent and success criterion

Build a small command-line tool named `bootstrap-epos-sdk`, in a project named `epos-sdk-bootstrap`.

The user has an Intel/AMD Ubuntu 24.04 computer and wants maxon's EPOS Linux SDK installed in a user-owned upstream directory. A later Python application will use that SDK to operate motors. The user has previously built similar Bash bootstraps for ROS 2 and Allied Vision cameras and wants the same understandable, inspectable approach with a smaller scope.

The complete public command set is:

```text
install
verify
uninstall
```

`install` downloads and configures the native SDK. `verify` checks the software installation without requiring or testing a controller. `uninstall` removes the installation and the configuration owned by this tool.

The success statement is: **"The specified EPOS SDK is installed, its native libraries load on this Ubuntu system, and its persistent USB access configuration is in place."**

It does not mean that a controller has been found, USB communication works, a motor is correctly configured, or motion is safe. Software verification must succeed on a supported Ubuntu host with no controller attached.

## 2. Agreed scope and explicit defaults

The user explicitly requested downloading into an upstream location, configuration, uninstall, and installation-only verification. A chosen directory and ordinary-user operation are required. Keep these requirements even if reference repositories or vendor instructions suggest a broader installation.

The following defaults resolve implementation details without requiring another planning conversation. They are recommendations for this first version, not requirements previously supplied by the user.

| Decision | v1 default |
|---|---|
| Operating system | Ubuntu `ID=ubuntu`, `VERSION_ID=24.04` (§7.1) |
| Architecture | `uname -m` = `x86_64`, Debian architecture = `amd64`, 64-bit system Python |
| SDK version | Pinned `6.8.1.0`, using Appendix A |
| Default destination | `$HOME/workspace/upstream/epos-sdk` |
| Destination overrides | `--sdk-dir PATH` > `EPOS_SDK_DIR` > default |
| Implementation | Bash entry point, small sourced helper modules, Python standard library for structured data, archive handling, and loading checks |
| Python interpreter | `/usr/bin/python3` explicitly, never `python3` from `PATH` |
| Library selection | Local SDK paths and a generated `setup.bash`; no global linker registration |
| USB access | Dedicated `epos` system group and one tool-owned udev rules file |
| Installed hardware families | Rules for both SDK-listed EPOS2 and EPOS4 USB IDs; no model selection or detection |
| Python environment | Prepare system Python/venv capability; application projects create their own venvs |
| Registered installations | One per machine in v1; do not replace a registration at another prefix or owned by another user (§6.5) |
| Version changes | Maintainer changes the pinned release after validation; no automatic upgrades |
| Tool license | MIT, in a `LICENSE` file. The SDK is never redistributed; it is downloaded from maxon under maxon's terms. |
| Output style | House convention: `[ OK ]`, `[INFO]`, `[WARN]`, `[ERROR]`; color only on a terminal with `NO_COLOR` unset |
| Tool version | A `TOOL_VERSION` constant, semver, shown in `--help` and recorded in the receipt |

The exact controller model, motor, encoder, power supply, and wiring are unknown. Those are not blockers for this software-only bootstrap. Do not ask the user for motor parameters while implementing it.

## 3. Boundaries: what not to build

Do not add ROS integration, a Python motor-control package, a GUI, background service, controller discovery, `probe`, `status`, `update`, `clean`, tuning, homing, fault clearing, firmware updates, or motion commands to v1.

Do not install EPOS Studio, Wine, Windows drivers, CAN adapters, or EtherCAT components. Do not recompile the vendor SDK: this package supplies precompiled libraries. Retain the bundled examples as vendor files but do not build or run them during installation or verification.

Do not create an application workspace, `.venv`, `requirements.txt`, editor configuration, global pip packages, shell-startup edits, an executable link in `~/.local/bin`, or system-wide `LD_LIBRARY_PATH` settings. A README can show how a later application uses its own venv.

Never run the vendor `install.sh`, including its uninstall mode. Do not call `VCS_OpenDevice`, `VCS_GetPortNameSelection`, or other SDK functions to inspect or operate controllers. The verification helper may load libraries and resolve exported symbol addresses but must not invoke an EPOS API function.

No `--force`, `--repair`, `--adopt`, `--version-select`, or `--url` flag. The behavior that would motivate `--repair` is part of ordinary `install` (§6.4).

## 4. Vendor facts verified during research

> Measured 2026-09-21; not re-confirmed since. Confirm before building against them.

The [official EPOS product download page](https://www.maxongroup.com/maxon/view/product/380264) offered Linux Library 6.8.1.0. The product page is a download source, not a claim that the user's controller is product 380264.

```text
URL:       https://www.maxongroup.com/medias/sys_master/root/9443687202846/EPOS-Linux-Library-En.zip
Filename:  EPOS-Linux-Library-En.zip
Bytes:     8001401
SHA-256:   467df7a69d67ae02d976c23a807e6bc4c00e4635e06d1330d29637868aa335b5
Top level: EPOS_Linux_Library
```

These are reproducibility pins, not vendor signatures. A different hash must fail installation; do not replace the expected hash automatically or fall back to a mirror. If maxon changes the archive, investigate and deliberately update the release specification.

Relevant paths inside the extracted archive:

```text
EPOS_Linux_Library/
  EULA.txt
  install.sh
  include/Definitions.h
  lib/intel/x86_64/libEposCmd.so.6.8.1.0
  lib/intel/x86_64/libftd2xx.so.1.4.8
  lib/intel/x86/...
  lib/arm/v6/...  lib/arm/v7/...  lib/arm/v8/...
  misc/99-ftdi.rules
  misc/99-epos4.rules
  examples/HelloEposCmd/...
```

Retain the complete extracted package, including its license and other architecture directories. Select only `lib/intel/x86_64` for runtime configuration. The archive does not include the separately downloadable Command Library manual; link to it in the README rather than expanding the download scope.

| File | SHA-256 | ELF identity |
|---|---|---|
| `libEposCmd.so.6.8.1.0` | `02478aa383eefd5f39458d4c75183ae04fb765c49d75a989e4d71e6a3a10ec2a` | 64-bit little-endian x86-64; SONAME `libEposCmd.so` |
| `libftd2xx.so.1.4.8` | `a6b2a5eacea47aa3b8fc5ab8d49a05abf2ba1e65db8f5b174b9486e92b73c94f` | 64-bit little-endian x86-64; SONAME `libftd2xx.so` |

`libEposCmd` directly depends on `libftd2xx.so`, `libpthread.so.0`, `librt.so.1`, `libstdc++.so.6`, `libm.so.6`, `libgcc_s.so.1`, and `libc.so.6`. The FTDI library depends on `libpthread.so.0`, `librt.so.1`, and `libc.so.6`. Keep the bundled FTDI library available even for an EPOS4, because it is a dependency of the EPOS binary itself.

The FTDI SONAME is load-bearing: §11.3 preloads `libftd2xx.so.1.4.8` with `RTLD_GLOBAL` so that `libEposCmd`'s `DT_NEEDED` entry for `libftd2xx.so` is satisfied by the already-loaded object rather than by a search. The `/proc/self/maps` assertion is what proves it happened, so a wrong SONAME surfaces as a clear failure instead of a silent fallback to some other FTDI library.

The EPOS binary's build-machine run-path ends in a colon. An empty run-path entry means the process working directory, so a directory containing a file named `libftd2xx.so` could satisfy the dependency. Rather than patch the binary, the design preloads by absolute path, runs the load check in a fresh empty directory, and confirms the loaded paths afterwards. Record whether the tag is `DT_RPATH` or `DT_RUNPATH` during Ubuntu validation.

The vendor installer hard-codes `/opt/EposCmdLib_6.8.1.0`, creates `/usr/lib` links, installs USB rules with `0666`, makes examples broadly writable, and adds passwordless `/bin/ip` access. It offers no custom-prefix option. This bootstrap replaces those mechanics with the footprint below.

## 5. Public interface

### 5.1 Usage and flags

```bash
./bootstrap-epos-sdk install --dry-run
./bootstrap-epos-sdk install
./bootstrap-epos-sdk verify
./bootstrap-epos-sdk uninstall --dry-run
./bootstrap-epos-sdk uninstall

# Chosen location: repeat the override for subsequent commands.
./bootstrap-epos-sdk install --sdk-dir "$HOME/workspace/upstream/epos-sdk"
./bootstrap-epos-sdk verify  --sdk-dir "$HOME/workspace/upstream/epos-sdk"
```

| Flag | Meaning |
|---|---|
| `--sdk-dir PATH`, `--sdk-dir=PATH` | Managed installation root; support spaces and metacharacters through correct quoting |
| `--dry-run` | Print the command's plan and locally observable state; no network, sudo, writes, locks, or library loading |
| `--yes`, `-y` | Skip the install/uninstall confirmation; never override ownership or integrity refusals |
| `--help`, `-h` | Print help without performing checks that can mutate anything |

Both `--sdk-dir` forms are accepted, matching the existing `bootstrap-vimbax-sdk`. A bare `--` ends option parsing. Accept flags before or after the command. Reject conflicting commands, unknown flags, empty path values, and missing flag values. No arguments displays help and exits 0, avoiding an accidental installation.

`--yes` on `verify` is accepted and ignored, since `verify` never prompts. An empty or whitespace-only `EPOS_SDK_DIR` is an error (exit 2), not a silent fallback to the default.

### 5.2 Dry run

`--dry-run` is valid for all three commands and is strictly read-only: no sudo, apt, dpkg, network, locks, file or directory creation or removal, and no vendor library loaded.

| Command | Reports |
|---|---|
| `install` | Resolved prefix, release pin, which stages are already satisfied, missing packages, the exact udev content, the exact group change, and the exact sudo commands a real run would invoke |
| `verify` | The checks that would run and the state observable without loading libraries; states explicitly that the native-load and export checks were skipped |
| `uninstall` | The exact local content, rules file, and membership change that would be removed, plus what is deliberately retained |

The load-check exclusion is the point of `verify --dry-run`: loading a vendor library executes vendor initialization code, so there must be a way to ask what would be checked without doing that.

### 5.3 Confirmation

Before a real install or uninstall, show the resolved prefix and exact intended changes, then ask once. `--yes` skips it. An already satisfied installation or fully absent uninstallation finishes without confirmation and without sudo. A dry run never prompts. Sudo authentication is separate from this confirmation.

The install confirmation carries the license acknowledgement, because the tool downloads vendor software on the user's behalf:

```text
[INFO] This downloads and installs maxon's EPOS Linux Library 6.8.1.0 under
       maxon's license terms. The EULA ships inside the archive and is retained
       at <prefix>/vendor/EPOS_Linux_Library/EULA.txt.
Proceed? [y/N]
```

`--help` must state that `--yes` also accepts that acknowledgement. Confirmation requires an interactive terminal; if stdin is not a terminal and `--yes` was not given, fail with exit 1 rather than reading EOF as a refusal.

### 5.4 Exit statuses

| Exit | Meaning |
|---|---|
| 0 | Succeeded, was already satisfied or absent, or a dry run whose plan can be executed |
| 1 | Operation or verification failed: ownership or registration conflict, hash mismatch, declined confirmation, missing installation, unsupported receipt schema, or a dry run whose plan is blocked |
| 2 | Invalid arguments, or an unsupported host, for any command including `--dry-run` |

A dry run that discovers a blocking conflict exits 1, so `install --dry-run` is usable as a precondition check. An unsupported host is exit 2 for every command including `verify`, because host support is a property of the machine rather than a failed check.

Warnings alone never change a successful exit status. Name the failed check and path in every error. Stdout and stderr are enough; v1 has no persistent run-log infrastructure.

### 5.5 Output conventions

Follow the existing bootstraps. Results and progress go to stdout as `[ OK ]` and `[INFO]`; `[WARN]` and `[ERROR]` go to stderr. Color is decided once at startup, only when the stream is a terminal and `NO_COLOR` is unset. Every subprocess whose output is parsed runs under `LC_ALL=C`.

## 6. Managed files and ownership

### 6.1 Layout

```text
<sdk-dir>/
  .epos-sdk-bootstrap.json        receipt (Appendix B)
  .epos-sdk-bootstrap.lock        advisory lock, tool-owned, empty
  setup.bash                      generated activation file (Appendix D)
  downloads/
    EPOS-Linux-Library-En.zip     retained, hash-pinned
  vendor/
    EPOS_Linux_Library/
      ...complete vendor package...
      lib/intel/x86_64/
        libEposCmd.so.6.8.1.0
        libftd2xx.so.1.4.8
        libEposCmd.so -> libEposCmd.so.6.8.1.0
        libftd2xx.so -> libftd2xx.so.1.4.8
```

`<sdk-dir>/.staging/` exists only during an install. Finding it at the start of a run means a previous run was interrupted; remove and rebuild it rather than reusing it.

The two unversioned symlinks are generated by the bootstrap with relative targets. Everything stays owned by the ordinary user. Set modes explicitly rather than inheriting the caller's umask: directories `0755`, files `0644`, no executable bits anywhere in the payload.

That has a deliberate side effect. Python's `zipfile` does not restore recorded permissions, and this design does not add them back, so `vendor/EPOS_Linux_Library/install.sh` lands non-executable. Since §3 forbids ever running it, that is the desired outcome; say so in the README rather than treating it as a defect.

The only persistent root-owned file is:

```text
/etc/udev/rules.d/99-epos-sdk-bootstrap.rules
```

Package installation and group membership are additional system changes and must be listed separately; do not describe the footprint as "only one change."

The tool contacts exactly one network host, `www.maxongroup.com`, only during `install`, and only when the pinned archive is not already present and valid. State that in the README.

### 6.2 The receipt and the registration

The local JSON receipt is data, never shell-sourceable code. Appendix B gives its schema. Reject a `schema_version` the tool does not implement — including a newer one, which exits 1 with "this installation was created by a newer bootstrap; upgrade the tool."

Do not include the receipt's own hash in its managed-file list; validate it through its schema, identity, allowed paths, and agreement with the root registration instead. The release manifest's pinned archive and library hashes stay independent of the receipt.

The root-owned udev file carries a one-line JSON registration comment (Appendix C) holding the installation UUID, canonical prefix, UID, username, and group provenance. It is the machine-wide registration and identifies the installation if the local directory goes missing. Generate it with JSON serialization. Never execute or source metadata from either file.

The trust chain: the release manifest pins the *archive* hash, the archive hash is checked before anything is extracted, and the per-file inventory in the receipt is computed from that validated extraction. The manifest separately pins the two libraries that actually get loaded, so those are checked against a maintainer-controlled value and not only a self-generated one.

Neither the registration comment nor `setup.bash` contains a timestamp. Both must be byte-identical when regenerated from the same inputs, or the idempotency contract in §7.4 is unimplementable.

Validate receipt entries before using them as paths: only expected relative paths within the prefix, no traversal or absolute paths, no following unexpected symlinks. A user-writable receipt is not authority to delete arbitrary files or elevate arbitrary commands.

### 6.3 Provenance is recorded before the change

`install` records whether the `epos` group and this user's membership existed beforehand, and `uninstall` removes membership only if this installation added it. Recording that *after* the change loses it: a run interrupted between `gpasswd` and the receipt write leaves membership present and provenance unwritten, the next `install` concludes the membership predated the tool, and the user can never get back to a clean machine.

So, for the group and the udev file alike:

1. Observe the current state.
2. Write it to the receipt as an intent record — what was observed, what is about to happen — and flush to disk.
3. Perform the system change.
4. Update the receipt to mark it complete.

Provenance fields are write-once. A rerun that finds `membership_existed_before` already recorded never overwrites it, whatever the machine currently looks like. If step 2 completed and step 4 did not, the recorded intent tells the next run what to re-check.

### 6.4 State matrix

"Ours" means a registration matching the receipt's UUID, prefix, and UID. Where no receipt exists (rows 2 and 3), there is no UUID to match, so it means only that the registration's UID is the invoking user's; its prefix then decides between the two rows. A registration naming a different UID is never ours — all three commands refuse and name the owner. That distinction is why the UID is recorded, since row 2 is the one case where the tool acts on registration metadata alone.

| # | Prefix | Receipt | Registration | `install` | `verify` | `uninstall` |
|---|---|---|---|---|---|---|
| 1 | empty | absent | absent | Fresh install | Fail 1, "not installed" | Nothing to do, exit 0, no sudo |
| 2 | empty | absent | ours, this prefix | Re-install payload, reusing its UUID | Fail 1, payload missing | Remove rule and recorded membership, exit 0 |
| 3 | empty | absent | ours, another prefix `P` | Refuse 1, name `P` | Fail 1, name `P` and the `--sdk-dir P` retry | Refuse 1, name `P` |
| 4 | populated | valid, ours, `complete` | ours | Idempotent rerun; recreate only missing owned items | Run all checks | Remove |
| 5 | populated | valid, ours | absent, or phase incomplete | Repair the missing part, or resume from the recorded phase | Fail 1, naming what is missing | Remove what is recorded |
| 6 | anything else | | | Refuse 1, change nothing | Fail 1 | Refuse 1, delete nothing |

Row 6 covers: a populated prefix with no valid receipt, a receipt owned by another UID, an unparsable or foreign file at the rules path, a registration disagreeing with the receipt, an unsupported schema version, and any managed file whose hash does not match. In every case name the specific conflict so the user can move the file aside and retry.

Rows 2 and 5 are what replaces a `--repair` flag: `install` recreates owned content that is *missing* and refuses only when content is *conflicting*.

Unexpected extra files in the prefix are a warning for `verify` (§11.4) and a refusal for `uninstall` (§12). `.epos-sdk-bootstrap.lock` and, mid-run, `.staging/` are tool artifacts and never count as unexpected.

### 6.5 Multi-user machines

v1 registers one installation per machine, so a second user is refused by rows 3 and 6. The refusal must not leave them stuck: a second user needing controller access does not need a second installation, only membership in the existing `epos` group, which an administrator grants with `sudo gpasswd -a <user> epos`. Say that in the refusal and the README.

### 6.6 Locking

Two scopes, because a per-prefix lock alone cannot serialize two installs at *different* prefixes competing for the single machine-wide registration:

- **Per-prefix.** An exclusive non-blocking `flock` on `<sdk-dir>/.epos-sdk-bootstrap.lock`, created right after the prefix directory, held for the whole mutating run. A second invocation at the same prefix fails fast with exit 1 and names the holder's PID.
- **Machine-wide.** The registration step is a single privileged call under `flock` on the rules directory:

  ```bash
  sudo flock --exclusive --timeout 60 /etc/udev/rules.d \
    "${PROJECT_DIR}/lib/privileged-udev.sh" publish <staged-file> <uuid>
  ```

  `flock(1)` accepts a directory, so this needs no extra lock file and no world-writable path. The helper re-reads the target *inside* the lock, so check and write cannot be split by another process (Appendix C.2).

`verify` and every dry run take no lock. The rules directory is overridable by one test-only variable, `EPOS_BOOTSTRAP_UDEV_DIR` (§14.1), absent from `--help`; when set, neither lock nor sudo is used because nothing privileged remains to serialize.

This assumes ordinary unrestricted `sudo`, since the helper runs as root from the user's own checkout. That is not an escalation — the caller already has full sudo — but a narrowed sudoers policy is unsupported. State it in the README's prerequisites.

## 7. Installation behavior

Implement a small series of check/action stages. Check real state on every run; the receipt's phase alone is not evidence that a stage succeeded.

### 7.1 Host gate

Runs before anything else; failure is exit 2 for every command. Parse `/etc/os-release` as `KEY=value` lines, as `lib/checks.sh` already does in the reference repositories; do not source it into the tool's own shell.

| Condition | Rule |
|---|---|
| `ID=ubuntu` | Required. Derivatives setting `ID_LIKE=ubuntu` are refused; their package sets and udev behavior were not validated. |
| `VERSION_ID=24.04` | Required exactly. Point releases such as 24.04.3 keep `VERSION_ID=24.04` and are accepted. |
| `uname -m` | Must be `x86_64`. |
| `/usr/bin/python3` | Must exist and be 64-bit (`sys.maxsize > 2**32`). |
| Effective UID | A real `install` or `uninstall` refuses to run as root. Get identity from `id -u` and `id -un`, not a trusted `$USER` or `$SUDO_USER`. |
| WSL | Refuse `install`: `microsoft` or `WSL` in `/proc/sys/kernel/osrelease`, or a set `WSL_DISTRO_NAME`. WSL2 has no working udev by default, so the USB stage would silently produce nothing. |
| Container | Detect via `systemd-detect-virt --container`, `/run/.containerenv`, or `/.dockerenv`. Do not refuse — containers are a legitimate fixture environment — but state it in the plan and expect §11's udev-service check to fail there. |

There is no override flag or environment escape hatch. Widening host support is a maintainer change: edit the gate, validate on the new release, update this card.

### 7.2 Stages

1. **Parse and inspect.** Resolve destination precedence, run the §7.1 gate, detect conflicts (§6.4) before changing the machine.
2. **Plan.** Show version and URL, resolved prefix, missing packages, local files, udev content, group changes, and the exact sudo commands. Handle dry run and confirmation before any mutation.
3. **Dependencies.** Install only missing required packages (§8.1).
4. **Download and validate.** Fetch as the ordinary user into `<prefix>/.staging/` (§8.2). Check size, then the pinned hash, before extraction or reading anything out of the archive.
5. **Prepare.** Validate archive member paths, extract into staging, check required files and ELF identity, create the two relative symlinks and `setup.bash`, publish into the prefix, write the receipt. A partial download must never look like a completed SDK.
6. **Configure USB access.** Create the group if missing, add the user if needed, install the owned udev file. Record intent and provenance before each system change (§6.3). Publish atomically, root-owned, `0644`. Reload rules if the rule changed.
7. **Verify.** Run the §11 checks. Mark the receipt `complete` only after they pass. Print the prefix, activation command, and any session-refresh note.

### 7.3 Phases and resume

`phase` takes exactly these values, each written *before* entering the stage it names, so an interrupted run is identifiable.

| Phase | Reached when | A resumed run does |
|---|---|---|
| `initialised` | Receipt created, prefix locked | Re-run from stage 3 |
| `deps` | About to touch apt | Re-check packages; skip apt if now satisfied |
| `download` | About to fetch | Reuse `downloads/` archive if its hash still matches, else re-fetch |
| `payload` | About to extract and publish | Discard `.staging/`, rebuild, republish |
| `system` | About to make the first privileged change | Read the intent records, finish or undo the partial change (§6.3) |
| `verify` | Local and system work done | Re-run verification |
| `complete` | Verification passed | Idempotent no-op (row 4) |

The retained archive can supply missing payload during a resumed install if its hash still matches. Leave previously healthy content intact if a new preparation stage fails.

### 7.4 Idempotency contract

A healthy rerun does not download again, invoke apt or sudo, rewrite matching files, add duplicate group memberships or environment entries, or change its installation ID. Read-only verification may always be repeated.

Sudo is invoked only when a system change is actually required. On a healthy machine — packages present, group exists, user is a member, rules file already byte-identical — `install` completes without calling sudo at all, and therefore without a password prompt. Compute the full set of needed system changes first and skip the privileged section entirely when it is empty. This is also a test assertion (§14.2).

Modified managed files and unexpected content are conflicts, not permission to overwrite user changes.

Do not promise a transaction covering apt: if later work fails, installed packages remain. Keep recovery information, report what completed, and allow a rerun or uninstall to recover.

## 8. Dependencies, downloads, and path handling

### 8.1 Packages

```text
python3   python3-venv   curl   ca-certificates
libc6     libstdc++6     libgcc-s1   udev
```

Most are present on a standard Ubuntu machine. Detect each with `dpkg-query -W -f='${db:Status-Status}' <pkg>`; treat `installed` as satisfied and anything else, including a nonzero exit, as missing. Install only the missing set:

```bash
sudo DEBIAN_FRONTEND=noninteractive apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends <missing...>
```

Run `apt-get update` only when at least one package is missing, and only once per run — without it, `install` fails on any host with an empty or stale package index, including a fresh container. Refreshing the index before an install that is already happening is not an upgrade and changes no installed package. `apt upgrade`, `dist-upgrade`, external repositories, PPAs, source builds, and global pip remain forbidden.

If the user has no sudo rights, fail with exit 1 and print the exact `apt-get install` line an administrator should run, rather than prompting repeatedly.

The tool may use Python's standard-library `zipfile`, avoiding an unzip dependency. `sudo`, Bash 5, apt/dpkg, coreutils, `flock`, `getent`, `gpasswd`, `groupadd`, and a working udev service are host prerequisites, not things the tool installs. Report missing prerequisites clearly. Do not install a sudo policy or try to grant the account administrative rights.

Do not add `build-essential`, CMake, ROS, `libftdi1`, a separate FTDI SDK, libusb headers, `pythonnet`, `pyserial`, or third-party Python packages. Note specifically that `file(1)` and `binutils` are *not* dependencies: §8.4 parses the ELF header directly, as `bootstrap-vimbax-sdk` already does. If Ubuntu loading reveals an unobserved dependency, identify it, update the requirement deliberately, and test it; do not install guessed packages.

### 8.2 Download

```bash
curl --proto '=https' --proto-redir '=https' --tlsv1.2 \
     --location --max-redirs 5 --fail-with-body \
     --connect-timeout 15 --max-time 600 \
     --retry 3 --retry-delay 2 --retry-connrefused \
     --output "<prefix>/.staging/EPOS-Linux-Library-En.zip.part" \
     "<pinned url>"
```

Never use sudo to download. On success check the byte count first — a cheap failure that catches an HTML error page — then the SHA-256, and only then rename `.part` to its final name. An interrupted transfer leaves only `.part`, which the next run deletes; nothing that looks like a complete archive is left behind.

Pin URL, version, size, and hashes together in `config/sdk-release.json` (Appendix A): maintainer-controlled data, parsed with Python's `json` module, never sourced as shell.

### 8.3 Archive handling

Reject, before extracting anything:

- absolute member paths, and any member whose normalized path escapes the archive root (`..`);
- any top-level entry other than `EPOS_Linux_Library/`;
- any member that is not a regular file or directory, from the entry's own mode bits: `(zinfo.external_attr >> 16) & 0o170000` must be `0o100000` or `0o040000`, so symlink members (`0o120000`), devices, and sockets are refused;
- duplicate or case-colliding member paths.

Extract to `<prefix>/.staging/vendor/`, then set modes explicitly per §6.1. The internal symlinks are created by this tool afterwards, never taken from the archive. Preserve `EULA.txt`. Link to vendor downloads and terms in the README; do not commit SDK binaries to this repository.

### 8.4 ELF identity check

Read the first 20 bytes of the header directly — no `file`, no `readelf`, no `binutils`:

| Offset | Field | Required |
|---|---|---|
| 0–3 | magic | `7f 45 4c 46` |
| 4 | `EI_CLASS` | `2` (ELF64) |
| 5 | `EI_DATA` | `1` (little-endian) |
| 18–19 | `e_machine`, LE | `0x3e` (62, x86-64) |

A file shorter than 20 bytes is a truncated-ELF failure, not a mismatch. Report a mismatch by naming the file, the machine found, and the host architecture.

SONAME is not part of the required check; parsing `.dynamic` is more machinery than the guarantee is worth, and the `/proc/self/maps` assertion in §11.3 catches a SONAME problem by its effect.

### 8.5 Path rules

- Use an explicit absolute destination, or resolve a relative one consistently, and display it before modification.
- Canonicalize existing ancestors. Reject a symlink at the destination itself and unexpected symlinks inside managed paths.
- Reject `/`, the home directory, the bootstrap checkout, ancestors of either, and system configuration directories. The destination must be a user-owned SDK directory with a writable parent; do not use sudo to create it.
- Accept a nonexistent or genuinely empty destination. Refuse a populated one without this tool's valid receipt.
- Support spaces and safely quoted metacharacters. Reject newlines, other control characters, and `:` — the last because the path goes into a colon-delimited library path. Never evaluate user input as shell code.
- Do not infer the prefix from whichever SDK happens to be on the current library path. Commands use their resolved prefix consistently.

The tool locates its own `lib/` by resolving `BASH_SOURCE[0]` through symlinks, using the `resolve_project_dir` idiom in `bootstrap-vimbax-sdk`, so invocation through a symlink still finds its helpers.

## 9. USB configuration and its limits

Appendix C.1 gives the file byte for byte. It carries the two SDK-listed IDs with group-restricted access:

```udev
SUBSYSTEMS=="usb", ATTRS{idVendor}=="0403", ATTRS{idProduct}=="a8b0", GROUP="epos", MODE="0660"
SUBSYSTEMS=="usb", ATTRS{idVendor}=="24e7", ATTRS{idProduct}=="3b01", GROUP="epos", MODE="0660"
```

The first is the SDK's EPOS2 FTDI ID, the second its EPOS4 ID; preserve the distinction. They are not an exhaustive catalog of every future controller. No vendor-wide or all-USB `0666` rule is allowed.

### 9.1 Group management

```bash
getent group epos                      # existence and the authoritative member list
sudo groupadd --system epos            # create; tolerate exit 9 (already exists)
sudo gpasswd -a "$username" epos       # add this user
sudo gpasswd -d "$username" epos       # uninstall, only if this install added it
```

`gpasswd -a` is preferred over `usermod -aG`, which rewrites the whole group entry from a snapshot and can drop a concurrent addition. A system group (GID below 1000) matches `dialout` and `plugdev`.

Determine membership from two distinct sources and never conflate them:

- **Configured**: the member list from `getent group epos`, plus the case where `epos` is the user's primary group per `getent passwd`.
- **Effective for this process**: `id -nG` with no operand.

### 9.2 Applying, and its limits

After a real rules change, run `udevadm control --reload-rules` with sudo, inside the same privileged helper invocation that wrote the file. Do not trigger all USB devices or restart the service. Applying permissions to an already attached device is outside the installation test; explain that a later hardware session may require reconnection per the controller's documented power-off USB procedure.

Adding membership does not change already running processes. Compare configured membership against this process's effective groups. If configured membership is correct but the process is stale, verification passes with a prominent advisory to start a new login or SSH session. Do not launch `newgrp`, change the user's shell, or reboot.

If legacy `/opt` installations, global EPOS or FTDI links, or vendor rules exist, report them. Do not invoke the vendor uninstaller, remove foreign rules, or silently migrate an existing installation. The access granted by all other udev rules cannot be proved without examining their combined behavior on hardware; do not claim this tool guarantees exclusive permissions.

EPOS2 can hit an `ftdi_sio`/D2XX conflict. Mention it as later troubleshooting only. Never blacklist drivers, unload modules, detach devices, or probe for a conflict during verification. [FTDI explanation](https://ftdichip.com/faq/can-i-just-load-the-d2xx-drivers-and-run-a-d2xx-application-on-a-newly-installed-linux-system/), [maxon USB distinctions](https://support.maxongroup.com/hc/en-us/articles/360014218020-EPOS4-IDX-Action-steps-in-case-of-failing-USB-connection).

## 10. Local activation and Python consumption

Appendix D gives `setup.bash` byte for byte. Sourced, it sets `EPOS_SDK_DIR` and `EPOS_LIB_DIR` and prepends the library directory to `LD_LIBRARY_PATH` exactly once. Three properties are requirements, not style:

- **Sourced, never executed**, signalling failure with `return` — an `exit` in a sourced file terminates the user's interactive shell. The file detects direct execution and refuses.
- **Never introduces an empty `LD_LIBRARY_PATH` entry**, which would mean the working directory (the exposure described in §4). Use the `${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}` guard, not bare concatenation.
- **Deterministic** given the prefix and template version, so `verify` can compare it against the hash recorded at install time.

Do not source it automatically or edit `.bashrc`, `.profile`, `/etc/profile.d`, `/etc/ld.so.conf*`, or `/usr/lib`.

One deliberate interaction to document: `setup.bash` exports `EPOS_SDK_DIR`, which is also the tool's destination override, so after sourcing it a later `bootstrap-epos-sdk verify` with no `--sdk-dir` targets that same prefix. That keeps an activated shell and the tool in agreement, but nobody should be surprised by it.

For the README, an application may instead load the two files explicitly from `EPOS_LIB_DIR`. This shows the load order without contacting hardware:

```python
import ctypes
import os
from pathlib import Path

lib_dir = Path(os.environ["EPOS_LIB_DIR"])
ftdi = ctypes.CDLL(str(lib_dir / "libftd2xx.so.1.4.8"), mode=ctypes.RTLD_GLOBAL)
epos = ctypes.CDLL(str(lib_dir / "libEposCmd.so.6.8.1.0"))
# Keep both objects alive. No controller is opened here.
```

`ctypes` is part of Python, not a pip dependency. Maxon recommends this approach but provides no supported native Python SDK. A later application owns its venv, dependencies, motor configuration, and C bindings. [maxon's Python guidance](https://support.maxongroup.com/hc/en-us/articles/360012695739-EPOS2-EPOS4-IDX-Commanding-by-Python-ctypes).

That application must match `argtypes` and `restype` to the shipped Linux `include/Definitions.h`. In this release handles are `void*`; `VCS_GetPositionIs` takes `int*`, while `VCS_MoveToPosition` takes a C `long`. These facts are why the bootstrap should not copy an arbitrary Windows Python wrapper. Implementing those bindings is out of scope.

## 11. Exact verification contract

`verify` uses no sudo and makes no repairs, downloads, package changes, group changes, device calls, locks, or persistent logs. It must not require the caller to have sourced `setup.bash`. If prerequisites are absent it fails with instructions to run `install`.

### 11.1 Required checks

| Check | Passing condition |
|---|---|
| Host | §7.1 gate satisfied (failure is exit 2, not a failed check) |
| Installation identity | Valid supported receipt schema; matching prefix, owner, release, and registration per §6.4 |
| Archive | Retained archive matches pinned size and SHA-256 |
| Payload | Every managed file matches its recorded hash; required files, `EULA.txt`, and `include/Definitions.h` present |
| Selected libraries | Both match the manifest's pinned hashes, pass §8.4, and the two relative links resolve to them |
| Activation | `setup.bash` matches the hash recorded at install time and points inside the resolved prefix |
| Python | `/usr/bin/python3` imports `ctypes`, is 64-bit, and `python3-venv` reports installed |
| Native dependencies | Both libraries load in a bounded child process and every native dependency resolves (§11.3) |
| Expected exports | Addresses resolve for `VCS_OpenDevice`, `VCS_CloseDevice`, `VCS_GetDriverInfo`; none is called |
| USB configuration | Owned rules file has expected content, `root:root`, `0644`, and a parsable registration comment; `epos` exists and configured membership is present |
| Udev service | `systemctl is-active systemd-udevd.service` reports `active` |

The udev-service check fails inside a container, which is correct: a container cannot establish the host acceptance criteria (§14.3). Say so explicitly rather than letting it look like a broken installation.

### 11.2 Locating an installation the caller did not name

If the resolved prefix holds nothing but the registration names a different prefix, do not silently follow it — §8.5 requires commands to use their resolved prefix. Say where it is instead:

```text
[ERROR] No EPOS SDK installation at /home/lk/workspace/upstream/epos-sdk
[INFO]  An installation is registered at /opt/lab/epos-sdk (owner: lk).
[INFO]  Re-run with: bootstrap-epos-sdk verify --sdk-dir /opt/lab/epos-sdk
```

### 11.3 The native load check

```bash
cd "$empty_tmpdir" && env -i \
  PATH=/usr/bin:/bin HOME="$empty_tmpdir" LC_ALL=C PYTHONDONTWRITEBYTECODE=1 \
  timeout --signal=TERM --kill-after=2 10 \
  /usr/bin/python3 -I -B "$PROJECT_DIR/lib/check_load.py" \
    --lib-dir "$lib_dir" --json
```

`env -i` drops `LD_PRELOAD`, `LD_LIBRARY_PATH`, `LD_AUDIT`, `PYTHONPATH`, and anything else that could substitute a foreign library, in the child only. The empty working directory neutralizes the run-path exposure in §4, which an environment scrub alone does not cover. `-I` isolates Python, which also means `check_load.py` cannot import siblings and must be self-contained; `-I -B` plus `PYTHONDONTWRITEBYTECODE=1` keeps the check from leaving `__pycache__` anywhere.

Verify both hashes *before* loading. Load by absolute path, FTDI first with `RTLD_GLOBAL`, and retain both handles. Then confirm from the child's own `/proc/self/maps` that the loaded objects are the files inside the managed prefix — a matching filename is not sufficient evidence. Do not hard-code system libc paths; successful loading resolves those.

| Child exit | Meaning |
|---|---|
| 0, `"ok": true` | Pass |
| 0, `"ok": false` | Fail; report the child's `error` |
| 124 | Fail: load timed out after 10 s |
| 128+N | Fail: loader or vendor initialization died on signal N |
| anything else | Fail: report exit status and captured stderr |

Resolving an export address is allowed; invoking it is not. Loading executes vendor initialization code, and this research did not establish every internal side effect, so do not advertise "zero USB syscalls" or "no vendor initialization." The promise is no explicit controller enumeration, connection, data request, state change, or hardware test by this tool. Characterize any initialization side effects during Ubuntu validation. If a supposedly software-only check turns out to need a controller, it does not belong in default verification.

Verification must leave no cache files or bytecode in the SDK or application folders, and must clean the temporary directory it created. If the vendor loader creates unavoidable persistent state, document the observed behavior and adjust the check deliberately rather than silently violating the contract.

### 11.4 Output

Unexpected extra files in the prefix are a warning when all required files remain valid. Modified managed files are failures. Uninstall is stricter (§12).

```text
[ OK ] host: Ubuntu 24.04 (x86_64), running as lk
[ OK ] installation: 6.8.1.0 at /home/lk/workspace/upstream/epos-sdk
[ OK ] archive: EPOS-Linux-Library-En.zip matches the pinned SHA-256
[ OK ] payload: 218 managed files match; EULA.txt and Definitions.h present
[ OK ] libraries: libEposCmd 6.8.1.0 + libftd2xx 1.4.8, ELF64 LSB x86-64, links resolve
[ OK ] activation: setup.bash matches its recorded hash
[ OK ] python: /usr/bin/python3 3.12.3 (64-bit), ctypes available, python3-venv installed
[ OK ] native load: both libraries loaded from the managed prefix
[ OK ] exports: VCS_OpenDevice, VCS_CloseDevice, VCS_GetDriverInfo resolved (none called)
[ OK ] usb access: 99-epos-sdk-bootstrap.rules root:root 0644; group 'epos' configured for lk
[ OK ] udev service: systemd-udevd active
[WARN] this shell does not yet carry the 'epos' group; start a new login session
[ OK ] verify PASSED — SDK installation verified
[INFO] controller communication and motor operation were not tested
```

Do not show a "missing controller" warning; no controller is expected. The success wording must not overstate Ubuntu hardware compatibility or active-session USB permissions.

## 12. Uninstall and recovery

Uninstall must work when the download server is unavailable or the native libraries are missing or unloadable. It uses validated ownership records and static inspection, never SDK execution.

Before removing anything:

1. Resolve and validate the prefix and registration against §6.4.
2. Confirm the invoking UID owns that registration and the IDs match.
3. Inventory every expected file and link, and every actual prefix entry, without following symlinks.
4. Refuse if a managed file changed, a generated link points elsewhere, an unrecognized file is present, or foreign configuration occupies the owned rules filename. Name the exact conflict so the user can move it aside and retry. Missing owned files are allowed, so a partial installation stays cleanable.
5. Print what will be removed and what is retained. Confirm once unless `--yes`.

Remove only recorded managed content and the matching owned rule. Remove this user's `epos` membership only if this installation added it, per the write-once provenance in §6.3. Retain the group itself even if this tool created it — other users may depend on it, and §6.5 makes it the supported path for a second user.

Retain installed apt packages, other users' memberships, foreign configuration, application projects, all venvs, motor parameter backups, and vendor data outside the managed prefix. State these in the completion message.

Reload udev rules after removing the owned rule. Do not revoke running sessions' supplementary groups or alter connected devices. Explain that future USB permission behavior changes when rules are reapplied. An already sourced shell may still hold an obsolete `EPOS_LIB_DIR` and library-path entry; recommend a fresh shell rather than editing startup files.

Remove directories only when empty after deleting validated owned contents. Keep the receipt until the last practical step; release and unlink the lock last of all. Preserve enough phase information to resume after a partial failure; return nonzero instead of claiming success. Repeating uninstall after a successful removal exits 0 without sudo.

Row 2 of §6.4 is the important recovery case: prefix manually deleted, matching registration still present — use its validated metadata to remove only that rule and any recorded tool-added membership. Row 6 is its mirror: a populated prefix whose receipt is missing or invalid is never deleted. `--yes` bypasses neither.

## 13. Repository organization

```text
epos-sdk-bootstrap/
  README.md
  LICENSE                     MIT, for this tool only
  bootstrap-epos-sdk          entry point: CLI, dispatch, confirmation
  config/sdk-release.json     Appendix A — maintainer-controlled release pin
  lib/log.sh                  house logging, color, confirmation helpers
  lib/common.sh               host gate, path rules, receipt I/O, locking
  lib/install.sh              stages 3-7
  lib/verify.sh               the §11 checks
  lib/uninstall.sh            §12
  lib/privileged-udev.sh      Appendix C.2 — the only code that runs as root
  lib/sdk_files.py            archive validation, extraction, hashing, ELF header
  lib/check_load.py           Appendix E — the isolated load check
  tests/run-tests.sh          fixture tests
  .gitignore
```

Merge helpers if that improves clarity. Use a small number of direct functions; no plugin or stage framework, daemon, database, package manager, or reusable SDK abstraction. Add a test dependency only if the standard library and shell fixtures prove insufficient.

Two deliberate departures from the prior repositories, each worth a code comment: the release pin is JSON rather than a `config/defaults.conf` shell file, because it holds hashes the tool parses but must never source; and there is no `logs/` directory, since v1 has no run-log infrastructure.

Every shell file carries `# shellcheck shell=bash` and the tree passes `shellcheck -x`. Use `set -Eeuo pipefail` in the entry point with an `ERR` trap naming the current stage, as `ros2-jazzy-bootstrap/lib/log.sh` already does.

Do not run installer scripts from the reference repositories. They are design references, not dependencies.

## 14. Required tests and acceptance criteria

Tests are justified because the tool downloads binaries and modifies system access configuration. Fixture tests redirect all filesystem and privileged operations into controlled temporaries or mocks; never mutate the developer's real `/etc`, accounts, or upstream directories.

### 14.1 How privileged behavior is tested

**Privileged actions are stubbed at `PATH`.** Every one goes through a single `run_privileged` wrapper invoking `sudo` with a fixed, small vocabulary — and nothing else:

```text
sudo DEBIAN_FRONTEND=noninteractive apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends ...
sudo groupadd --system epos
sudo gpasswd -a <user> epos
sudo gpasswd -d <user> epos
sudo flock --exclusive --timeout 60 /etc/udev/rules.d <project>/lib/privileged-udev.sh publish|remove ...
```

Fixture tests prepend a recording `sudo` stub in the `<<< args >>>` block style of `vimbax-ros2-driver-bootstrap/tests/run-tests.sh`, asserting on both arguments and invocation count. The closed vocabulary is itself an assertion: any other `sudo` shape is a bug.

**Reading the registration is de-escalated, never escalated.** A fixture cannot create a file in `/etc`, so the rules directory is overridable by one variable, `EPOS_BOOTSTRAP_UDEV_DIR`, constrained so it can only ever point somewhere the caller already owns:

- the value must be an existing directory owned by the invoking UID, and must not be `/etc` or under it — otherwise exit 2;
- when set, the registration step runs in place, without sudo and without the machine-wide lock;
- every run prints `[WARN] TEST MODE: udev directory overridden to <path>; not a supported installation`;
- no ownership, hash, receipt, conflict, or host check is relaxed by it.

Because it cannot reach a privileged destination and grants nothing the caller lacks, it removes privilege rather than adding it — which is what keeps it compatible with the rule that production interfaces must not expose privileged destinations for testing convenience.

### 14.2 Required cases

| Area | Required cases |
|---|---|
| CLI | Three commands, no-argument help, flags before/after commands, both `--sdk-dir` forms, `--`, unknown/conflicting options, empty values, empty `EPOS_SDK_DIR`, precedence, paths with spaces and metacharacters |
| Exit codes | Each row of §5.4, including a blocked dry run exiting 1 and an unsupported host exiting 2 for all three commands |
| Read-only behavior | Help and every dry run make no writes, network calls, sudo calls, or locks, and load no vendor library; `verify --dry-run` skips the load check; `verify` makes no deliberate persistent change and no EPOS API or device call; temporaries are cleaned |
| Host checks | Ubuntu 24.04 amd64 and a point release accepted; macOS, ARM, an `ID_LIKE=ubuntu` derivative, 32-bit Python, WSL, and real root execution each refused with the right status |
| Download/extraction | Correct pin accepted; wrong size, wrong hash, HTML error response, interrupted transfer leaving only `.part`, traversal, absolute member, duplicate entries, non-regular members, unexpected top-level root all rejected |
| Installation | Fresh install creates exactly the §6.1 footprint; healthy rerun mutates nothing and calls sudo zero times; each §7.3 phase can be interrupted and resumed; every §6.4 row behaves as specified |
| Permissions | Sudo used only for the §14.1 vocabulary; native files user-owned `0644`/`0755` with no executable bits in the payload; root rule `0644`; no world-writable device rule, sudoers edit, or global library registration |
| Receipt | Provenance written before the mutation and unchanged across reruns; an interrupted run between intent and completion recovers correctly; invalid schema, newer schema, traversal, and symlink targets never authorize deletions |
| Activation | Correct custom path; repeated sourcing does not duplicate entries; unset `LD_LIBRARY_PATH` produces no empty entry; direct execution refused; a failed source returns rather than exiting; no shell-startup file changed |
| Verification | Missing, modified, wrong-architecture, and missing-dependency cases fail; load success, failure, crash, and timeout each map to the right §11.3 outcome; a substituted foreign library is caught via `/proc/self/maps`; no attached hardware still passes; a wrong prefix produces the §11.2 pointer |
| USB/session state | Missing group, missing configured membership, and missing or foreign rules each fail; stale effective groups give the advisory and still exit 0; no USB enumeration, module unload, or device trigger |
| Uninstall | Exact owned content removed; packages, group, and preexisting membership retained; added membership removed; unknown or modified files preserved through refusal; missing payload still cleanable; repeat is a no-op; partial failures recoverable |
| Concurrency | Two installs at the same prefix: the second fails fast on the per-prefix lock. Two at *different* prefixes: exactly one registration exists afterwards and neither corrupts the rules file |
| Static analysis | `shellcheck -x` and `bash -n` clean on every shell file; both Python helpers parse clean via `ast.parse` (not `py_compile`, which writes `__pycache__` even under `-B`) |

Mocks prove bootstrap logic, not that maxon's binary works.

### 14.3 Integration test

Run a real test in a disposable Ubuntu 24.04 amd64 system with sudo and a functioning udev service, without a controller: `install` → `verify` → `install` again → `uninstall` → `uninstall` again, including a custom path containing a space. The second `install` must call sudo zero times; the second `uninstall` must exit 0 without sudo.

A container can test file and loading behavior but cannot establish the host acceptance criteria; the `systemd-udevd` check is expected to fail there.

Use the official pinned archive and `/usr/bin/python3`. Record OS, architecture, Python version, SDK hash, whether the run-path tag is `DT_RPATH` or `DT_RUNPATH`, and any observable side effect of vendor initialization. Fixture tests may be developed on macOS, but the stubs assume GNU tooling, so Linux is where they are supported; mark Ubuntu integration pending until actually run. Do not claim vendor certification from your own successful test.

### 14.4 Definition of done

- Every §14.2 case passes, and §14.3 has been run on Ubuntu 24.04 rather than deferred.
- `shellcheck -x` and `bash -n` clean.
- Appendix A's pins re-confirmed against a fresh download.
- README covers install, custom paths, what `verify` does and does not prove, uninstall scope, Python consumption, the `EPOS_SDK_DIR` interaction (§10), the multi-user note (§6.5), the single network host (§6.1), the full-sudo assumption (§6.6), and known limitations.
- `LICENSE` exists, and the README states the SDK is downloaded from maxon under maxon's terms, not redistributed here.

## 15. Known limits and research evidence

The [Command Library manual, section 9.2](https://www.maxongroup.com/medias/sys_master/root/9157360353310/EPOS-Command-Library-En.pdf) lists older Intel Ubuntu versions in its tested-platform table. It does not establish Ubuntu 24.04 support. Library loading and installation behavior need real Ubuntu validation. Controller communication is outside v1 acceptance.

EPOS Studio is the Windows commissioning tool. Configuration, tuning, and persistent parameter backups belong to the later hardware workflow; the Linux library does not reproduce all Studio GUI or parameter import/export features. [Commissioning guidance](https://support.maxongroup.com/hc/en-us/articles/6719969220380-EPOS4-IDX-Important-steps-during-initial-commissioning), [parameter backups](https://support.maxongroup.com/hc/en-us/articles/360005421674-EPOS-IDX-Export-of-parameter-configuration-in-a-dcf-file).

The vendor `HelloEposCmd` source defaults to a motion demonstration that can clear faults and enable the drive. It must never be the bootstrap smoke test. Losing USB communication also does not inherently stop EPOS2/EPOS4 motion; that is context for excluding motor tests, not a problem for this installer to solve. [Communication-loss behavior](https://support.maxongroup.com/hc/en-us/articles/360012982439-EPOS4-Motor-stop-at-communication-lost).

Research completed: archive download, hash and structure inspection, installer inspection, static x86_64 ELF and dependency inspection, header inspection, and review of the user's prior bootstrap code. No Linux binary, controller, or motor was run. The earlier read-status Python example from the conversation opens a controller and is intentionally not part of this tool.

Left to Ubuntu validation rather than guessed at now: whether the run-path tag is `DT_RPATH` or `DT_RUNPATH`; what side effects vendor initialization has at load time; the extracted payload's file count and size; and whether any dependency beyond §8.1 appears in practice.

## 16. Prior projects to consult

References for style and behavior, not prerequisites. Inspect current files before adapting code; the repositories may evolve. These are **Git blob hashes of the named files**, not commit IDs, and all three were re-verified on 2026-09-22.

| Reference | Relevant patterns | Reviewed entry-point blob |
|---|---|---|
| [vimbax-sdk-bootstrap](https://github.com/lkaising/vimbax-sdk-bootstrap/blob/main/bootstrap-vimbax-sdk) | SDK directory override, `--sdk-dir=` parsing, ELF header checks without `file(1)`, `resolve_project_dir`, exact system-file previews, idempotency | `b44d0cdc8845082a926ca222ccfe1411a3aea616` |
| [ros2-jazzy-bootstrap](https://github.com/lkaising/ros2-jazzy-bootstrap/blob/main/bootstrap-ros2-jazzy) | Check/action stages, strictly read-only dry runs, `lib/log.sh` conventions, `require_not_root`, workspace ownership | `492b4fe993e5675f3a7098546b4631f28029c94e` |
| [vimbax-ros2-driver-bootstrap](https://github.com/lkaising/vimbax-ros2-driver-bootstrap/blob/main/bootstrap-vimbax-ros2-driver) | Small entry point, dependency ownership boundaries, `PATH`-stub fixture tests, `NO_COLOR` handling | `9353ff91a37d80c5c0df9a19c417c28364604195` |

Also useful: [workspace ownership](https://github.com/lkaising/ros2-jazzy-bootstrap/blob/main/lib/workspace.sh), [guarded cleanup](https://github.com/lkaising/ros2-jazzy-bootstrap/blob/main/lib/clean.sh), [logging and prompts](https://github.com/lkaising/ros2-jazzy-bootstrap/blob/main/lib/log.sh), and [driver fixture tests](https://github.com/lkaising/vimbax-ros2-driver-bootstrap/blob/main/tests/run-tests.sh) — the model for §14.1's stub strategy. The [driver's own specification](https://github.com/lkaising/vimbax-ros2-driver-bootstrap/blob/main/vimbax-ros2-driver-bootstrap-spec.md) is the closest precedent for this document's shape.

The Vimba X SDK tool assumes an already extracted SDK and registers a global GenTL path; this design includes download and extraction and uses local library paths. Its camera simulator test does not transfer.

## 17. Deliverables and remaining questions

Deliverables: a runnable bootstrap, its helpers and release manifest, a `LICENSE`, tests, and a README covering §14.4. Include exact test results and any pending Ubuntu validation in the final implementation report.

There are no blocking product questions. The defaults in §2, the command UX in §5, the multi-user policy in §6.5, and the group retention policy in §12 are explicit design choices the user can revise. Do not expand scope to resolve the unknown controller or motor.

Ask for a decision only if a concrete new fact invalidates the design — the pinned archive becomes unavailable or its hash changed, the library fails on Ubuntu 24.04, the run-path or SONAME facts in §4 prove wrong in a way the preload depends on, or the machine has a conflicting registration the ownership rules cannot handle. Present the evidence and a specific alternative. Do not silently change versions, remove foreign installations, or declare hardware compatibility.

This card specifies the project. Creating or publishing a repository, pushing commits, or installing on a real host follows the instructions of the task in which the implementing agent receives it; possession of this card alone is not an instruction to publish or modify a host.

---

# Appendices — exact artifacts

The files the tool reads and writes. Specified rather than described, because three are hashed and two are parsed.

## Appendix A — `config/sdk-release.json`

Maintainer-controlled. Parsed with Python's `json` module; never sourced. Changing the pinned release means editing this file, validating on a real host, and updating §4.

```json
{
  "schema_version": 1,
  "sdk_version": "6.8.1.0",
  "archive": {
    "url": "https://www.maxongroup.com/medias/sys_master/root/9443687202846/EPOS-Linux-Library-En.zip",
    "filename": "EPOS-Linux-Library-En.zip",
    "size_bytes": 8001401,
    "sha256": "467df7a69d67ae02d976c23a807e6bc4c00e4635e06d1330d29637868aa335b5",
    "top_level_dir": "EPOS_Linux_Library"
  },
  "arch": {
    "uname_m": "x86_64",
    "lib_subdir": "lib/intel/x86_64",
    "elf_class": 2,
    "elf_data": 1,
    "elf_machine": 62
  },
  "libraries": {
    "ftdi": {
      "filename": "libftd2xx.so.1.4.8",
      "link": "libftd2xx.so",
      "soname": "libftd2xx.so",
      "sha256": "a6b2a5eacea47aa3b8fc5ab8d49a05abf2ba1e65db8f5b174b9486e92b73c94f"
    },
    "epos": {
      "filename": "libEposCmd.so.6.8.1.0",
      "link": "libEposCmd.so",
      "soname": "libEposCmd.so",
      "sha256": "02478aa383eefd5f39458d4c75183ae04fb765c49d75a989e4d71e6a3a10ec2a"
    }
  },
  "required_members": [
    "EULA.txt",
    "include/Definitions.h",
    "lib/intel/x86_64/libEposCmd.so.6.8.1.0",
    "lib/intel/x86_64/libftd2xx.so.1.4.8"
  ],
  "expected_symbols": ["VCS_OpenDevice", "VCS_CloseDevice", "VCS_GetDriverInfo"],
  "udev_rules": [
    { "label": "EPOS2 (FTDI)", "id_vendor": "0403", "id_product": "a8b0" },
    { "label": "EPOS4",        "id_vendor": "24e7", "id_product": "3b01" }
  ]
}
```

`libraries.ftdi` is listed first deliberately: that is the load order in §11.3, so the pin reads in the order the preload requires.

## Appendix B — `<sdk-dir>/.epos-sdk-bootstrap.json`

Mode `0644`, owned by the installing user. Written with `json.dump(..., sort_keys=True, indent=2)` and published by atomic rename, so an interrupted write never leaves a half-parsed receipt.

```json
{
  "schema_version": 1,
  "tool": { "name": "bootstrap-epos-sdk", "version": "1.0.0" },
  "installation_uuid": "3f2b9c1e-6d84-4a77-9d2f-1c0b5a8e4471",
  "created_utc": "2026-09-22T10:14:03Z",
  "updated_utc": "2026-09-22T10:14:51Z",
  "phase": "complete",
  "prefix": "/home/lk/workspace/upstream/epos-sdk",
  "owner": { "uid": 1000, "username": "lk" },
  "release": {
    "sdk_version": "6.8.1.0",
    "archive_url": "https://www.maxongroup.com/medias/sys_master/root/9443687202846/EPOS-Linux-Library-En.zip",
    "archive_sha256": "467df7a69d67ae02d976c23a807e6bc4c00e4635e06d1330d29637868aa335b5",
    "archive_size_bytes": 8001401,
    "lib_subdir": "lib/intel/x86_64"
  },
  "payload": {
    "root": "vendor/EPOS_Linux_Library",
    "dirs": ["downloads", "vendor", "vendor/EPOS_Linux_Library"],
    "files": [
      { "path": "vendor/EPOS_Linux_Library/EULA.txt", "size": 14211, "sha256": "…" },
      { "path": "vendor/EPOS_Linux_Library/include/Definitions.h", "size": 71234, "sha256": "…" }
    ],
    "symlinks": [
      { "path": "vendor/EPOS_Linux_Library/lib/intel/x86_64/libEposCmd.so", "target": "libEposCmd.so.6.8.1.0" },
      { "path": "vendor/EPOS_Linux_Library/lib/intel/x86_64/libftd2xx.so",  "target": "libftd2xx.so.1.4.8" }
    ]
  },
  "generated": {
    "archive":    { "path": "downloads/EPOS-Linux-Library-En.zip", "size": 8001401, "sha256": "467df7…" },
    "setup_bash": { "path": "setup.bash", "template_version": 1, "sha256": "…" }
  },
  "tool_artifacts": [".epos-sdk-bootstrap.json", ".epos-sdk-bootstrap.lock"],
  "system": {
    "udev": {
      "path": "/etc/udev/rules.d/99-epos-sdk-bootstrap.rules",
      "sha256": "…",
      "preexisting": false,
      "intent_recorded_utc": "2026-09-22T10:14:44Z",
      "published": true
    },
    "group": {
      "name": "epos",
      "existed_before": false,
      "created_by_this_install": true,
      "membership_existed_before": false,
      "membership_added_by_this_install": true,
      "intent_recorded_utc": "2026-09-22T10:14:41Z"
    },
    "apt": { "packages_installed": ["python3-venv"], "apt_get_update_run": true }
  }
}
```

`payload.files` lists every regular file extracted, not only the required four; the two shown are an elision, and the list is the bulk of the file.

- **Write-once provenance.** `udev.preexisting`, `group.existed_before`, and `group.membership_existed_before` are set once, with `intent_recorded_utc`, *before* the corresponding change (§6.3), and never rewritten.
- **Intent versus completion.** `intent_recorded_utc` present with `published` false, or `membership_added_by_this_install` unset, marks a run interrupted mid-change — what phase `system` exists to recover.
- **Paths are relative to `prefix`** and validated before use: no absolute paths, no `..`, no symlink traversal out of the prefix.
- **`tool_artifacts`** names the two legitimately unhashed files, so `verify` and `uninstall` can tell them from unexpected content.

## Appendix C — the machine-wide registration

### C.1 `/etc/udev/rules.d/99-epos-sdk-bootstrap.rules`

`root:root`, mode `0644`, byte-identical whenever regenerated — hence no timestamp.

```text
# Managed by bootstrap-epos-sdk. Do not edit.
# Remove it with: bootstrap-epos-sdk uninstall
# epos-sdk-bootstrap-registration: {"group":"epos","group_existed_before":false,"installation_uuid":"3f2b9c1e-6d84-4a77-9d2f-1c0b5a8e4471","membership_existed_before":false,"prefix":"/home/lk/workspace/upstream/epos-sdk","schema_version":1,"sdk_version":"6.8.1.0","uid":1000,"username":"lk"}
SUBSYSTEMS=="usb", ATTRS{idVendor}=="0403", ATTRS{idProduct}=="a8b0", GROUP="epos", MODE="0660"
SUBSYSTEMS=="usb", ATTRS{idVendor}=="24e7", ATTRS{idProduct}=="3b01", GROUP="epos", MODE="0660"
```

The registration line is `json.dumps(obj, sort_keys=True, separators=(",", ":"))` on one line, prefixed with `# epos-sdk-bootstrap-registration: `. Sorted keys and no spaces make it reproducible.

Parsing accepts **exactly one** such line. Zero, two or more, a non-object, or invalid JSON each make the file foreign (§6.4 row 6) and the tool refuses rather than guessing. The parsed object is data: never executed, sourced, or used as a command argument without §8.5 validation. A file at this path with no registration line is someone else's; leave it alone and name it in the error.

### C.2 `lib/privileged-udev.sh`

The only code in the project that runs as root:

```bash
sudo flock --exclusive --timeout 60 /etc/udev/rules.d \
  "${PROJECT_DIR}/lib/privileged-udev.sh" publish <staged-file> <expected-uuid>

sudo flock --exclusive --timeout 60 /etc/udev/rules.d \
  "${PROJECT_DIR}/lib/privileged-udev.sh" remove <expected-uuid>
```

1. `set -Eeuo pipefail`. Read **only** its positional arguments; ignore the environment, which it inherits across a `sudo` boundary.
2. Hard-code the target path. Refuse any argument that would write outside `/etc/udev/rules.d/99-epos-sdk-bootstrap.rules`.
3. Re-read the target *inside* the lock and check it against `<expected-uuid>`: absent is fine for `publish`, a matching registration is fine for both, anything else exits nonzero untouched. This re-check is what makes check-then-act atomic, and why the privileged step is one call rather than several.
4. `publish`: `install -m 0644 -o root -g root -T -- <staged-file> <target>` — writes and renames atomically with the final mode already set.
5. `remove`: unlink only after the UUID matches.
6. On an actual change, run `udevadm control --reload-rules`. Never `udevadm trigger`, never restart the service.
7. Print what it did on stdout so the unprivileged caller can report it without re-reading as root.

Keep it under about 60 lines. It is the piece a reviewer will read most carefully.

## Appendix D — `<sdk-dir>/setup.bash`

Mode `0644`, deliberately **not** executable. Deterministic given the prefix and `template_version`, so §11 can compare it to the hash recorded at install time.

```bash
# Generated by bootstrap-epos-sdk <TOOL_VERSION>. Do not edit.
# Template version: 1
# Source this file; do not execute it:  source setup.bash

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
  printf 'setup.bash must be sourced, not executed: source %s\n' "${BASH_SOURCE[0]}" >&2
  exit 1
fi

__epos_root='<PREFIX>'
__epos_lib='<PREFIX>/vendor/EPOS_Linux_Library/lib/intel/x86_64'

if [ ! -r "${__epos_lib}/libEposCmd.so.6.8.1.0" ]; then
  printf 'EPOS SDK not found at %s; run: bootstrap-epos-sdk install\n' "${__epos_root}" >&2
  unset __epos_root __epos_lib
  return 1
fi

case ":${LD_LIBRARY_PATH-}:" in
  *":${__epos_lib}:"*) : ;;
  *) LD_LIBRARY_PATH="${__epos_lib}${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}" ;;
esac

EPOS_SDK_DIR="${__epos_root}"
EPOS_LIB_DIR="${__epos_lib}"
export EPOS_SDK_DIR EPOS_LIB_DIR LD_LIBRARY_PATH
unset __epos_root __epos_lib
```

`<PREFIX>` is substituted with single-quote escaping — every `'` becomes `'\''` — so a path with spaces or metacharacters is inert. §8.5 already rejects `:`, newlines, and control characters, leaving quoting and the empty-entry case, both handled above. `return 1` rather than `exit` on the missing-installation path; `${LD_LIBRARY_PATH:+…}` rather than bare concatenation, since the naive form yields a trailing empty entry the loader reads as the working directory; the `case` guard makes repeated sourcing idempotent. Quiet on success.

## Appendix E — `lib/check_load.py`

Run under §11.3's isolated invocation, so it must be one self-contained file importing only the standard library — `-I` puts its own directory off `sys.path`.

Arguments: `--lib-dir PATH`, the two expected filenames, each expected SHA-256, the symbol names, and `--json`. In order:

1. Re-hash both libraries against the pins. A mismatch stops before loading anything — the check never loads a file it has not just verified.
2. `ctypes.CDLL(<abs libftd2xx.so.1.4.8>, mode=ctypes.RTLD_GLOBAL)`.
3. `ctypes.CDLL(<abs libEposCmd.so.6.8.1.0>)`.
4. Keep both handles referenced for the rest of the process.
5. Read `/proc/self/maps` and confirm the mapped EPOS and FTDI objects are exactly the two absolute paths just loaded. A different path — a system-wide FTDI library, or one from the working directory — is a failure naming the path actually mapped.
6. Resolve each expected symbol via `getattr(handle, name)`, which performs `dlsym` without calling the function. **No EPOS API function is ever invoked.**
7. Print one JSON object to stdout and exit 0. Reserve nonzero exits for conditions that prevent producing a report at all.

```json
{
  "ok": true,
  "ftdi_path": "/home/lk/workspace/upstream/epos-sdk/vendor/EPOS_Linux_Library/lib/intel/x86_64/libftd2xx.so.1.4.8",
  "epos_path": "/home/lk/workspace/upstream/epos-sdk/vendor/EPOS_Linux_Library/lib/intel/x86_64/libEposCmd.so.6.8.1.0",
  "maps_confirmed": true,
  "symbols": { "VCS_OpenDevice": true, "VCS_CloseDevice": true, "VCS_GetDriverInfo": true },
  "python": { "version": "3.12.3", "bits": 64 },
  "error": null
}
```

On failure, `"ok": false` with `error` naming the failing step. Symbol addresses may be recorded but not printed as raw pointers; they are meaningless to the user and vary per run.

## Appendix F — Suggested build order

Each step is independently testable, and the risky external facts come first.

1. **Confirm the pins** — size, SHA-256, layout, library hashes, ELF fields, run-path tag. Everything downstream assumes them.
2. **Skeleton and CLI** — entry point, `lib/log.sh`, parsing, `--help`, exit codes, the §7.1 gate. Test before writing anything that mutates.
3. **Path rules and the receipt** — §8.5, Appendix B, schema refusal, path validation.
4. **Download and extraction** — §8.2–§8.4, against a fixture archive first and the real one second.
5. **Local install** — staging, publication, symlinks, `setup.bash`, receipt completion. `install` now works with the USB stage stubbed.
6. **Verification** — `check_load.py` and the §11 checks; the first real exercise on Ubuntu.
7. **The privileged stage** — `privileged-udev.sh`, group management, locking, §6.3 ordering. After verification exists, so there is a way to tell whether it worked.
8. **Uninstall**, then **concurrency and the full §6.4 matrix**, then the **integration run and README**.
