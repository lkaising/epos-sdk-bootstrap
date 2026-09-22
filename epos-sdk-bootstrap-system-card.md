# EPOS SDK Bootstrap — implementation handoff

Version: 2.0 · Revised: 2026-09-22 · Supersedes 1.0 (2026-09-21) · Target: Ubuntu 24.04 amd64

This is a standalone specification for an implementing agent. It contains the agreed product scope, resolved defaults for the remaining implementation choices, researched vendor facts, the exact content of every file the tool generates, and acceptance tests. The original conversation is not required. This card is a design deliverable; the bootstrap has not been implemented or tested on Ubuntu yet.

## 0. Document status and how to read it

Sections 1–17 are the specification. Appendices A–E are the exact artifacts the tool reads and writes; where a section and an appendix disagree, the appendix wins, because it is the thing that gets hashed. Appendix F is a suggested build order. Appendix G records what changed from version 1.0 and why.

Evidence status of the claims in this card, as of the 2026-09-22 revision:

| Claim | Status |
|---|---|
| §16 reference blob hashes | **Re-verified 2026-09-22.** All three match the current public repositories. |
| §4 vendor archive facts (URL, byte count, SHA-256, layout, ELF details, installer behavior) | **Recorded 2026-09-21 from a direct download; not re-confirmed since.** The environment used for this revision cannot reach `www.maxongroup.com` (egress policy denial), so these values were carried forward unchanged rather than re-measured. |
| Everything about runtime behavior on Ubuntu | **Never executed.** No Linux binary, controller, or motor has been run. |

Because of the second row, the first implementation step is to re-download the archive and confirm the pins (Appendix F, step 1) before writing installer logic against them. If a pin differs, stop and follow §17 — do not adjust the pin to match what you downloaded.

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

The following defaults resolve implementation details without requiring another planning conversation. They are recommendations for this first version, not additional requirements previously supplied by the user.

| Decision | v1 default |
|---|---|
| Operating system | Ubuntu `ID=ubuntu`, `VERSION_ID=24.04` (see §7.1 for the exact gate) |
| Architecture | `uname -m` = `x86_64`, Debian architecture = `amd64`, 64-bit system Python |
| SDK version | Pinned `6.8.1.0`, using the archive and hashes in Appendix A |
| Default destination | `$HOME/workspace/upstream/epos-sdk` |
| Destination overrides | `--sdk-dir PATH` > `EPOS_SDK_DIR` environment variable > default |
| Implementation | Bash entry point, small sourced helper modules, Python standard library for structured data, archive handling, and loading checks |
| Python interpreter | `/usr/bin/python3` explicitly, never `python3` from `PATH` |
| Library selection | Local SDK paths and a generated `setup.bash`; no global linker registration |
| USB access | Dedicated `epos` system group and one tool-owned udev rules file |
| Installed hardware families | Rules for both SDK-listed EPOS2 and EPOS4 USB IDs; no model selection or detection required |
| Python environment | Prepare system Python/venv capability; application projects create their own venvs |
| Number of registered installations | One managed installation per machine in v1; do not replace a registration at another prefix or owned by another user (see §6.5 for the multi-user workaround) |
| Version changes | Maintainer changes the pinned release after validation; no automatic upgrades |
| Tool license | MIT, in a `LICENSE` file. The SDK itself is never redistributed; it is downloaded from maxon under maxon's terms. |
| Output style | House convention: `[ OK ]`, `[INFO]`, `[WARN]`, `[ERROR]`; color only on a terminal and only when `NO_COLOR` is unset (§5.5) |
| Tool version | A single `TOOL_VERSION` constant, semver, shown in `--help` and recorded in the receipt |

The exact controller model, motor, encoder, power supply, and wiring are unknown. Those are not blockers for this software-only bootstrap. Do not ask the user for motor parameters while implementing it.

## 3. Boundaries: what not to build

Do not add ROS integration, a Python motor-control package, a GUI, background service, controller discovery, `probe`, `status`, `update`, `clean`, tuning, homing, fault clearing, firmware updates, or motion commands to v1.

Do not install EPOS Studio, Wine, Windows drivers, CAN adapters, or EtherCAT components. Do not recompile the vendor SDK: this package supplies precompiled libraries. Retain the bundled examples as vendor files but do not build or run them during installation or verification.

Do not create an application workspace, `.venv`, `requirements.txt`, editor configuration, global pip packages, shell-startup edits, an executable link in `~/.local/bin`, or system-wide `LD_LIBRARY_PATH` settings. Those are unnecessary for this small installer. A README can show how a later application uses its own venv.

Never run the vendor `install.sh`, including its uninstall mode. Do not call `VCS_OpenDevice`, `VCS_GetPortNameSelection`, or other SDK functions to inspect or operate controllers. The verification helper may load libraries and resolve exported symbol addresses but must not invoke an EPOS API function.

Do not add a `--force`, `--repair`, `--adopt`, `--version-select`, or `--url` flag. The repair behavior that would otherwise motivate `--repair` is specified in §6.4 and is part of ordinary `install`.

## 4. Vendor facts verified during research

> These values were measured on 2026-09-21 and could not be re-measured during the 2026-09-22 revision (§0). Confirm them before building against them.

The [official EPOS product download page](https://www.maxongroup.com/maxon/view/product/380264) offered Linux Library 6.8.1.0. The specific product page is a download source, not a claim that the user's controller is product 380264.

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

These SHA-256 values are reproducibility pins, not vendor signatures. A different hash must fail installation; do not automatically replace the expected hash or fall back to a mirror. If maxon changes the archive, investigate it and deliberately update the release specification.

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

The recorded FTDI SONAME is load-bearing, not trivia. The verification helper loads `libftd2xx.so.1.4.8` first with `RTLD_GLOBAL`, so that when `libEposCmd` is loaded its `DT_NEEDED` entry for `libftd2xx.so` is satisfied by the already-loaded object instead of by a search. That only works if the SONAME matches the `DT_NEEDED` string. The `/proc/self/maps` assertion in §11.3 is what proves it actually happened, so a wrong SONAME becomes a clear verification failure rather than a silent fallback to some other FTDI library on the system.

The EPOS binary contains a build-machine run-path ending in a colon. An empty entry in a run-path list means *the process working directory*, so a working directory containing a file named `libftd2xx.so` could satisfy the dependency. Whether the recorded tag is `DT_RPATH` (searched before `LD_LIBRARY_PATH`) or `DT_RUNPATH` (searched after) changes how early that happens but not the exposure. The design therefore does three things rather than patch the binary: preload the intended FTDI library by absolute path, run the load check in a freshly created empty directory, and confirm the loaded paths afterwards. Record which tag it actually is during Ubuntu validation.

The vendor installer hard-codes `/opt/EposCmdLib_6.8.1.0`, creates `/usr/lib` links, installs USB rules with `0666`, makes examples broadly writable, and adds passwordless `/bin/ip` access. It offers no custom-prefix option. These findings come from direct inspection of the SDK archive. The new bootstrap replaces those installation mechanics with the explicitly defined footprint below.

## 5. Public interface

### 5.1 Usage

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
| `--sdk-dir PATH`, `--sdk-dir=PATH` | Managed installation root; support spaces and shell metacharacters through correct quoting |
| `--dry-run` | Print the chosen command's plan and locally observable state; no network, sudo, writes, locks, or library loading |
| `--yes`, `-y` | Skip the install/uninstall summary confirmation; never override ownership or integrity refusals |
| `--help`, `-h` | Print help without performing checks that can mutate anything |

Both `--sdk-dir PATH` and `--sdk-dir=PATH` are accepted, matching the existing `bootstrap-vimbax-sdk`. A bare `--` ends option parsing. Accept flags before or after the command. Reject conflicting commands, unknown flags, empty path values, and missing flag values. No arguments displays help and exits 0, avoiding an accidental installation.

`--yes` on `verify` is accepted and ignored, because `verify` never prompts. An empty or whitespace-only `EPOS_SDK_DIR` is an error (exit 2), not a silent fallback to the default: a user who exported it wrongly should be told, not quietly redirected.

### 5.2 Dry run, per command

`--dry-run` is valid for all three commands, and every dry run is strictly read-only. It must not invoke or validate sudo, run apt or dpkg, touch the network, create or remove any file, directory, symlink, lock, or temporary file, load a vendor library, or edit anything.

| Command | Dry run reports |
|---|---|
| `install` | Resolved prefix, release pin, which stages are already satisfied, each missing package, the exact udev file content, the exact group change, and the exact sudo commands a real run would invoke |
| `verify` | The list of checks that would run and the state observable without loading libraries; explicitly states that the native-load and export checks were skipped |
| `uninstall` | The exact local content, rules file, and membership change that would be removed, and the resources deliberately retained |

The load-check exclusion for `verify --dry-run` is the point of the flag: loading a vendor library executes vendor initialization code, so there has to be a way to ask "what would you check?" without doing that.

### 5.3 Confirmation

Before an actual install or uninstall, show the resolved prefix and exact intended changes. A single ordinary yes/no confirmation is sufficient; `--yes` supports automation. An already satisfied installation or fully absent uninstallation finishes without confirmation and without sudo. A dry run never prompts. Normal sudo authentication is separate from the tool's confirmation.

The install confirmation must also carry the license acknowledgement, because the tool downloads vendor software on the user's behalf:

```text
[INFO] This downloads and installs maxon's EPOS Linux Library 6.8.1.0 under
       maxon's license terms. The EULA ships inside the archive and is retained
       at <prefix>/vendor/EPOS_Linux_Library/EULA.txt.
Proceed? [y/N]
```

`--help` must state that `--yes` also accepts that acknowledgement.

Confirmation requires an interactive terminal. If stdin is not a terminal and `--yes` was not given, fail with exit 1 and say so, rather than reading EOF as a refusal.

### 5.4 Exit statuses

| Exit | Meaning |
|---|---|
| 0 | Command succeeded, was already satisfied/absent, or a dry run whose plan can be executed completed |
| 1 | Operation or verification failed: ownership or registration conflict, hash mismatch, declined confirmation, missing installation, unsupported receipt schema, or a dry run whose plan is blocked |
| 2 | Invalid arguments, or an unsupported host, for any command including `--dry-run` |

Two consequences worth stating explicitly, because v1.0 left them ambiguous:

- A dry run that discovers a blocking conflict exits 1, not 0. `install --dry-run` is then usable as a precondition check in a script.
- An unsupported host is exit 2 for every command, including `verify`. Host support is a property of the machine, not a failed check.

Warnings do not alone change a successful exit status. Make error messages actionable and name the failed check and path. Standard output and standard error are enough; persistent run-log infrastructure is not required for v1.

### 5.5 Output conventions

Follow the existing bootstraps. Result and progress lines go to stdout with `[ OK ]` and `[INFO]`; `[WARN]` and `[ERROR]` go to stderr. Colour is enabled only when the stream is a terminal and `NO_COLOR` is unset, decided once at startup. Every subprocess whose output is parsed runs under `LC_ALL=C` so parsing is stable under any user locale.

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

`<sdk-dir>/.staging/` exists only during an install and must be absent afterwards; its presence at the start of a run means a previous run was interrupted, and it is removed and rebuilt rather than reused.

The two unversioned symlinks are generated by the bootstrap and use relative targets. The libraries, archive, generated files, and directories remain owned by the ordinary user. Do not reproduce the vendor's broad write permissions. Set modes explicitly rather than inheriting whatever the caller's umask happens to be: directories `0755`, regular files `0644`, and no executable bits anywhere in the payload.

That last point has a deliberate side effect. Python's `zipfile` does not restore recorded permissions on extraction, and this design does not add them back, so `vendor/EPOS_Linux_Library/install.sh` lands non-executable. Given that §3 forbids ever running it, that is the desired outcome and should be stated in the README rather than treated as a defect.

The only persistent root-owned file created by the tool is:

```text
/etc/udev/rules.d/99-epos-sdk-bootstrap.rules
```

System package installation and group membership are additional system changes and must be listed separately; do not describe the footprint as "only one change."

The tool contacts exactly one network host, `www.maxongroup.com`, and only during `install`, and only when the pinned archive is not already present and valid. Say this in the README for anyone who has to justify it to a network policy.

### 6.2 The receipt and the registration

The local JSON receipt is data, never shell-sourceable code. Appendix B gives its exact schema, and the tool must reject a receipt whose `schema_version` it does not implement rather than guessing at the fields — including a *newer* schema, which exits 1 with "this installation was created by a newer bootstrap; upgrade the tool."

Do not include the receipt's own hash in its managed-file hash list. Validate the receipt through its schema, identity, allowed paths, and agreement with the root registration; hashing it inside itself would be circular. The release manifest's pinned archive and selected-binary hashes remain independent of the receipt.

The root-owned udev file carries a one-line JSON registration comment (Appendix C) holding the installation UUID, canonical prefix, UID, username, and group provenance. This is the machine-wide registration and enables identification if the local directory goes missing. Generate it with JSON serialization. Do not execute or source metadata from either file.

The trust chain is worth stating once, because it is what makes the payload inventory safe to generate rather than ship: the release manifest pins the *archive* hash, the archive hash is checked before anything is extracted, and the per-file inventory in the receipt is then computed from that validated extraction. The manifest additionally pins the two selected libraries, so the files that actually get loaded are checked against a maintainer-controlled value and not only against a self-generated one.

The registration comment contains no timestamps, and neither does `setup.bash`. Both files must be byte-identical when regenerated from the same inputs, or the idempotency contract in §7.4 ("a healthy rerun does not rewrite matching files") is unimplementable.

Validate receipt entries before using them as filesystem paths: allow only expected relative paths within the prefix, reject traversal and absolute paths, and do not follow unexpected symlinks. A user-writable receipt is not authority to delete arbitrary files or elevate arbitrary commands.

### 6.3 Provenance must be recorded before the change, not after

This is the one place where v1.0's ordering was wrong, and it produces a real data-loss bug.

`install` records whether the `epos` group and this user's membership existed beforehand, and `uninstall` removes membership only if this installation added it. If the provenance is written *after* the `gpasswd` call, a run interrupted between the two leaves membership present and provenance unrecorded. The next `install` observes existing membership, concludes it predated the tool, and `uninstall` then leaves the user in a group the tool created. The user can never get back to a clean machine.

The required ordering, for the group and for the udev file alike:

1. Observe the current state.
2. Write it to the receipt as an *intent* record — what was observed, and what is about to be done — and flush the receipt to disk.
3. Perform the system change.
4. Update the receipt to mark the change completed.

Provenance fields are write-once. A rerun that finds `membership_existed_before` already recorded must never overwrite it, whatever the current state of the system is. If step 2 completed but step 4 did not, the recorded intent tells the next run exactly what to re-check and lets it finish or roll back correctly.

### 6.4 State matrix

These are the combinations the three commands must handle.

"Ours" is defined against whatever identity evidence exists. When a valid receipt is present, a registration is ours only if its UUID, prefix, and UID all match that receipt. When no receipt is present — rows 2, 3, and 4 — there is no UUID to match, so a registration is ours only if its recorded UID equals the invoking user's UID; its prefix then decides between rows 2 and 3. A registration naming a different UID is never ours: all three commands refuse and name the owner, never row 3's recovery. That distinction is the whole point of recording the UID in the registration, since row 3 is the one case where the tool acts on registration metadata alone, with no local receipt to corroborate it.

| # | Prefix | Receipt | Registration at `/etc` | `install` | `verify` | `uninstall` |
|---|---|---|---|---|---|---|
| 1 | absent or empty | absent | absent | Fresh install | Fail 1, "no installation at `<prefix>`; run install" | Nothing to do, exit 0, no sudo |
| 2 | absent or empty | absent | ours, different prefix `P` | Refuse 1: an installation is registered at `P` | Fail 1, and name `P` with the `--sdk-dir P` retry | Refuse 1, and name `P` |
| 3 | absent or empty | absent | ours, this prefix | Re-install the payload, reusing the registration's UUID | Fail 1, payload missing | Remove the rule and any recorded membership, exit 0 |
| 4 | absent or empty | absent | foreign or unparsable file at our path | Refuse 1, name the file, change nothing | Fail 1 | Refuse 1, leave the file untouched |
| 5 | populated | absent or invalid | any | Refuse 1, delete nothing | Fail 1 | Refuse 1, delete nothing |
| 6 | populated | valid, another UID | any | Refuse 1 | Fail 1, name the owner | Refuse 1 |
| 7 | populated | valid, ours, phase `complete` | ours, matching | Idempotent rerun; recreate only missing owned items | Run all checks | Remove |
| 8 | populated | valid, ours, phase incomplete | ours or absent | Resume from the recorded phase | Fail 1, "installation incomplete (phase `<p>`); run install" | Remove what is recorded, exit 0 |
| 9 | populated | valid, ours | absent | Repair: re-publish the rule and re-check membership | Fail 1, "USB configuration missing; run install" | Remove local content and recorded membership; note that no rule was found |
| 10 | populated | valid, ours | ours, different UUID, prefix, or UID | Refuse 1, explain which installation must be uninstalled first | Fail 1 | Refuse 1 |
| 11 | any | schema newer than this tool | any | Refuse 1 | Fail 1 | Refuse 1 |

Rows 3 and 9 are what replaces a `--repair` flag: `install` recreates owned content that is *missing*, and refuses only when content is *conflicting*. A managed file that exists but whose hash does not match the receipt is a conflict in every row — `install`, `verify`, and `uninstall` all refuse, and the message names the file so the user can move it aside and retry.

Unexpected extra files in the prefix are a warning for `verify` (§11.4) and a refusal for `uninstall` (§12). `.epos-sdk-bootstrap.lock` and, mid-run, `.staging/` are tool artifacts and never count as unexpected.

### 6.5 Multi-user machines

v1 registers one installation per machine, so a second user on the same host is refused by rows 2 and 10 rather than given a second registration. That is the intended v1 behavior, but the refusal message must not leave them stuck: a second user who needs controller access does not need a second installation, only membership in the existing `epos` group, which an administrator grants with `sudo gpasswd -a <user> epos`. Say that in the refusal and in the README.

### 6.6 Locking

v1.0 called for "one advisory lock on a mutating path", which cannot serialize two installs at *different* prefixes competing for the single machine-wide registration — yet §14 requires exactly that to be impossible. Two locks are needed, at two scopes:

- **Per-prefix.** `flock` an exclusive, non-blocking lock on `<sdk-dir>/.epos-sdk-bootstrap.lock`, created immediately after the prefix directory itself. Held for the whole mutating run. A second invocation at the same prefix fails fast with exit 1 and names the holder's PID.
- **Machine-wide.** The registration section runs as a single privileged call under `flock` on the rules directory:

  ```bash
  sudo flock --exclusive --timeout 60 /etc/udev/rules.d \
    "${PROJECT_DIR}/lib/privileged-udev.sh" publish <staged-file> <uuid>
  ```

  `flock(1)` accepts a directory, so this needs no extra lock file and no world-writable path. The helper re-reads the target *inside* the lock, so the check and the write cannot be split by another process, then installs the file atomically and reloads rules. Appendix C.2 specifies the helper.

`verify` and every dry run take no lock of either kind.

The rules directory is overridable by one test-only variable, `EPOS_BOOTSTRAP_UDEV_DIR`, which is constrained so that it can only ever point somewhere the caller already owns; §14.1 specifies it. It is deliberately absent from `--help`, and when it is set neither lock nor sudo is used, because there is nothing privileged left to serialize.

This design assumes ordinary unrestricted `sudo` (the `%sudo` group), because the helper runs as root from the user's own checkout. That is not an escalation — the invoking user already has full sudo — but it does mean a narrowed sudoers policy is unsupported. State that in the README's prerequisites.

## 7. Installation behavior

Implement a small series of check/action stages. Check real state on every run; the receipt's phase alone is not evidence that a stage succeeded.

### 7.1 Host gate

The host check runs before anything else and produces exit 2 on failure, for every command. Read `/etc/os-release` by parsing `KEY=value` lines, as `lib/checks.sh` already does in the reference repositories; do not source it into the tool's own shell.

| Condition | Rule |
|---|---|
| `ID=ubuntu` | Required. Ubuntu derivatives that set `ID_LIKE=ubuntu` are refused: their package sets and udev behavior were not validated. |
| `VERSION_ID=24.04` | Required, exactly. Point releases such as 24.04.3 keep `VERSION_ID=24.04` and are accepted automatically. |
| `uname -m` | Must be `x86_64`. |
| `/usr/bin/python3` | Must exist and report a 64-bit interpreter (`sys.maxsize > 2**32`). |
| Effective UID | A real `install` or `uninstall` refuses to run as root. Obtain identity with `id -u` and `id -un`, not a blindly trusted `$USER` or `$SUDO_USER`. |
| WSL | Refuse `install` under WSL: detect `microsoft` or `WSL` in `/proc/sys/kernel/osrelease`, or a set `WSL_DISTRO_NAME`. WSL2 has no working udev by default, so the USB stage would silently produce nothing. |
| Container | Detect with `systemd-detect-virt --container` or the presence of `/run/.containerenv` or `/.dockerenv`. Do not refuse — containers are a legitimate fixture environment — but state it in the plan, and expect the udev service check in §11 to fail there. |

There is no override flag and no environment escape hatch. Widening host support is a maintainer change: edit the gate, validate on the new release, and update this card. That is the same discipline §4 applies to the archive pin, and it is the reason a user cannot accidentally "succeed" on an untested platform.

### 7.2 Stages

1. **Parse and inspect.** Resolve destination precedence. Run the §7.1 gate. Detect destination and udev ownership conflicts (§6.4) before changing the machine.
2. **Plan.** Show SDK version and URL, resolved prefix, missing packages, local files, udev content, group changes, and the exact sudo commands. Handle dry run and confirmation before any mutation.
3. **Dependencies.** Install only missing required Ubuntu packages (§8.1).
4. **Download and validate.** Download as the ordinary user into `<prefix>/.staging/` (§8.2). Verify size then pinned hash before extraction or reading anything else out of the archive.
5. **Prepare the local installation.** Validate archive member paths, extract into staging, check required files and ELF identity, create the two relative symlinks and `setup.bash`, then publish into the managed prefix and write the receipt. A partial download must never appear to be a completed SDK.
6. **Configure USB access.** Create the group if missing, add the installing user if needed, and install the owned udev file. Record intent and provenance before each system change (§6.3). Publish the root file atomically with root ownership and mode `0644`. Reload udev rules if the rule changed.
7. **Verify.** Run the same installation-only checks as `verify`, including native library loading as the ordinary user. Mark the receipt `complete` only after the required checks pass. Print the prefix, activation command, and any session-refresh note.

### 7.3 Phases and resume

The receipt's `phase` field takes exactly these values, in order. Each is written *before* entering the stage it names, so an interrupted run is identifiable.

| Phase | Reached when | A resumed run does |
|---|---|---|
| `initialised` | Receipt created, prefix locked | Re-run from stage 3 |
| `deps` | About to touch apt | Re-check packages; skip apt if now satisfied |
| `download` | About to fetch | Reuse `downloads/` archive if its hash still matches, else re-fetch |
| `payload` | About to extract and publish | Discard `.staging/`, rebuild it, republish |
| `system` | About to make the first privileged change | Read the intent records, finish or undo the partial change (§6.3) |
| `verify` | Local and system work done | Re-run verification |
| `complete` | Verification passed | Idempotent no-op run (row 7) |

The retained archive can supply missing payload during a resumed install if its hash still matches. Leave previously healthy content intact if a new preparation stage fails.

### 7.4 Idempotency contract

A healthy rerun does not download again, invoke apt or sudo, rewrite matching files, add duplicate group memberships or environment entries, or change its installation ID. Running read-only verification again is always acceptable.

Sudo is invoked only when a system change is actually required. On a healthy machine where the packages are present, the group exists, the user is a member, and the rules file already matches byte for byte, `install` completes without ever calling sudo and therefore without a password prompt. Implement this by computing the full set of needed system changes first and skipping the privileged section entirely when it is empty. It is also a test assertion (§14).

Modified managed files and unexpected content are conflicts, not permission to overwrite user changes.

Do not promise a transaction covering apt. If later work fails, already installed Ubuntu packages remain. Keep owned recovery information, report what completed, and allow a rerun or uninstall to recover.

## 8. Dependencies, downloads, and path handling

### 8.1 Packages

Runtime and setup packages:

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

Most are present on a standard Ubuntu machine. Detect each with `dpkg-query -W -f='${db:Status-Status}' <pkg>` and treat `installed` as satisfied; anything else, including a nonzero exit, means missing. Install only the missing set:

```bash
sudo DEBIAN_FRONTEND=noninteractive apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends <missing...>
```

`apt-get update` runs only when at least one package is missing, and only once per run. v1.0 omitted this and forbade `apt upgrade`, which reads as "never touch apt metadata" — but on a fresh container or a machine with an empty package index, `apt-get install` then fails outright, which would break the integration test this card requires. Refreshing the index before an install that is already happening is not an upgrade and does not change any installed package.

`apt upgrade`, `dist-upgrade`, external package repositories, PPAs, source builds, and global pip remain forbidden.

The tool may use Python's standard-library `zipfile` module, avoiding an extra unzip dependency. `sudo`, Bash 5, apt/dpkg, coreutils, `flock`, `getent`, `gpasswd`, `groupadd`, and a working udev service are host prerequisites, not things the tool installs. Report missing prerequisites clearly. Do not install a sudo policy or attempt to grant the invoking account administrative rights.

Two apt failure modes need explicit handling rather than a raw apt error:

- **The dpkg/apt lock is held.** Detect a nonzero exit whose output names `/var/lib/dpkg/lock` or `Could not get lock`, and report that another package manager (often unattended-upgrades) is running and that the run should be retried shortly. Do not wait in a loop and do not remove a lock file.
- **The user has no sudo rights.** Fail with exit 1 and print the exact `apt-get install` line an administrator should run, then exit rather than prompting repeatedly.

Do not add `build-essential`, CMake, ROS, `libftdi1`, a separately downloaded FTDI SDK, libusb development headers, `pythonnet`, `pyserial`, or third-party Python packages. No application compilation is required. Note specifically that `file(1)` and `binutils` are *not* dependencies: the ELF identity check in §8.4 parses the header directly, the way `bootstrap-vimbax-sdk` already does. If actual Ubuntu loading reveals a previously unobserved dependency, identify it, update the documented requirement deliberately, and test it; do not install a collection of guessed packages.

### 8.2 Download

```bash
curl --proto '=https' --proto-redir '=https' --tlsv1.2 \
     --location --max-redirs 5 \
     --fail-with-body \
     --connect-timeout 15 --max-time 600 \
     --retry 3 --retry-delay 2 --retry-connrefused \
     --output "<prefix>/.staging/EPOS-Linux-Library-En.zip.part" \
     "<pinned url>"
```

Downloading never uses sudo. On success, check the byte count against the pin first (a cheap fast failure that catches an HTML error page), then the SHA-256, and only then rename `.part` to its final name. An interrupted transfer leaves only the `.part` file, which the next run deletes; nothing that looks like a completed archive is ever left behind.

Before downloading, require free space on the destination filesystem (`df --output=avail -k`) of at least the value in the release manifest's `min_free_bytes`. Set it to 150 MB for now and tighten it once the extracted size is measured during Ubuntu validation.

Pin URL, version, size, and hashes together in `config/sdk-release.json` (Appendix A), which is maintainer-controlled data, parsed with Python's `json` module, and never sourced as shell.

### 8.3 Archive handling

Reject, before extracting anything:

- absolute member paths, and any member whose normalized path escapes the archive root (`..`);
- any top-level entry other than `EPOS_Linux_Library/`;
- any member that is not a regular file or a directory. Detect this from the Zip entry's own mode bits: `(zinfo.external_attr >> 16) & 0o170000` must be `0o100000` or `0o040000`. Symlink members (`0o120000`), devices, and sockets are refused;
- duplicate or case-colliding member paths;
- a member count or total uncompressed size wildly outside the recorded release (a compression-bomb guard).

Extract to `<prefix>/.staging/vendor/`, then set modes explicitly per §6.1. The internal symlinks in the installed layout are created by this tool afterwards, never taken from the archive. Preserve `EULA.txt`. Link to vendor downloads and terms in the README; do not commit the SDK binaries to the bootstrap repository.

### 8.4 ELF identity check

Required files are checked by reading the first 20 bytes of the ELF header directly — no `file`, no `readelf`, no `binutils`:

| Offset | Field | Required value |
|---|---|---|
| 0–3 | magic | `7f 45 4c 46` |
| 4 | `EI_CLASS` | `2` (ELF64) |
| 5 | `EI_DATA` | `1` (little-endian) |
| 18–19 | `e_machine`, LE | `0x3e` (62, x86-64) |

A file shorter than 20 bytes is a truncated-ELF failure, not a mismatch. Report a mismatch in terms the user can act on: name the file, the machine found, and the host architecture.

SONAME is not part of the required check — parsing `.dynamic` is more machinery than the guarantee is worth, and the `/proc/self/maps` assertion in §11.3 catches a SONAME problem by its actual effect. Keep the recorded SONAMEs in §4 as documentation of why the preload works.

### 8.5 Path rules

- Use an explicit absolute destination, or expand and resolve a supplied relative path consistently, and display it before modification.
- Canonicalize existing ancestors. Reject a symlink at the destination itself and unexpected symlinks inside managed paths.
- Reject `/`, the user's home directory, the bootstrap checkout, ancestors of the home directory or checkout, and system configuration directories as installation roots. The destination must be a suitable user-owned SDK directory with a writable parent; do not use sudo to create it.
- Accept a nonexistent or genuinely empty destination. Refuse a populated destination without this tool's valid receipt.
- Support spaces and safely quoted shell metacharacters. Reject newlines and other control characters, and reject `:` in the prefix because it is used in a colon-delimited library path. Do not evaluate user input as shell code.
- Do not infer the custom prefix from whichever SDK happens to be on the current library path. Commands use their resolved `--sdk-dir`, environment variable, or default consistently.

The tool locates its own `lib/` directory by resolving `BASH_SOURCE[0]` through any symlinks, using the `resolve_project_dir` idiom already present in `bootstrap-vimbax-sdk`, so an invocation through a symlink still finds its helpers.

## 9. USB configuration and its limits

The rules file content is specified byte for byte in Appendix C. It carries the two SDK-listed IDs with group-restricted access:

```udev
SUBSYSTEMS=="usb", ATTRS{idVendor}=="0403", ATTRS{idProduct}=="a8b0", GROUP="epos", MODE="0660"
SUBSYSTEMS=="usb", ATTRS{idVendor}=="24e7", ATTRS{idProduct}=="3b01", GROUP="epos", MODE="0660"
```

The first is the SDK's EPOS2 FTDI ID; the second is its EPOS4 ID. Preserve the distinction. These are not an exhaustive catalog of every future controller. No vendor-wide or all-USB `0666` rule is allowed.

### 9.1 Group management

Use targeted commands that modify one membership rather than rewriting the group line:

```bash
getent group epos                      # existence, and the authoritative member list
sudo groupadd --system epos            # create; tolerate exit 9 (already exists)
sudo gpasswd -a "$username" epos       # add this user
sudo gpasswd -d "$username" epos       # uninstall, only if this install added it
```

`gpasswd -a` is preferred over `usermod -aG` because `usermod` rewrites the whole group entry from a snapshot and can drop a concurrent addition. A system group (GID below 1000) matches the convention of `dialout` and `plugdev`.

Determine membership from two distinct sources and do not conflate them:

- **Configured**: the member list from `getent group epos`, plus the case where `epos` is the user's primary group per `getent passwd`.
- **Effective for this process**: `id -nG` with no operand.

If `getent group epos` resolves but `epos` is absent from `/etc/group`, the group comes from a directory service such as LDAP or SSSD. Do not attempt `gpasswd` against it: refuse with exit 1 and tell the user their administrator must manage that group. This is rare but produces a confusing failure if unhandled.

### 9.2 Applying and its limits

After an actual rules-file change, run `udevadm control --reload-rules` with sudo, inside the same privileged helper invocation that wrote the file. Do not trigger all USB devices or restart the udev service. Applying permissions to an already attached device is outside the installation test; explain that a later hardware session may require reconnection according to the controller's documented power-off USB procedure.

Adding group membership does not change already running processes. Compare configured membership with the effective groups of the current process. If configured membership is correct but the process is stale, installation verification passes with a prominent advisory to start a new login or SSH session. Do not launch `newgrp`, change the user's shell, or reboot automatically.

If legacy `/opt` installations, global EPOS or FTDI links, or vendor rules exist, report them. Do not invoke the vendor uninstaller, remove foreign rules, or silently migrate an existing installation. The exact access granted by all other udev rules cannot be proved without examining their combined behavior on hardware; do not claim this tool guarantees exclusive permissions.

EPOS2 can encounter an `ftdi_sio`/D2XX conflict. Mention it as later troubleshooting only. Never blacklist drivers, unload modules, detach devices, or probe for a conflict during bootstrap verification. [FTDI explanation](https://ftdichip.com/faq/can-i-just-load-the-d2xx-drivers-and-run-a-d2xx-application-on-a-newly-installed-linux-system/), [maxon USB distinctions](https://support.maxongroup.com/hc/en-us/articles/360014218020-EPOS4-IDX-Action-steps-in-case-of-failing-USB-connection).

## 10. Local activation and Python consumption

`<sdk-dir>/setup.bash` is specified byte for byte in Appendix D. Sourced, it sets `EPOS_SDK_DIR` and `EPOS_LIB_DIR` and prepends the library directory to `LD_LIBRARY_PATH` exactly once.

Three properties are requirements, not style:

- It is **sourced, never executed**, and signals failure with `return`, never `exit` — an `exit` in a sourced file terminates the user's interactive shell. The file detects direct execution and refuses.
- It **never introduces an empty entry** in `LD_LIBRARY_PATH`. An empty entry means the working directory, which is the same exposure described in §4. Use the `${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}` guard, not bare concatenation.
- It is **deterministic** given the prefix and template version, so `verify` can compare it against the hash recorded at install time.

Do not source it automatically or edit `.bashrc`, `.profile`, `/etc/profile.d`, `/etc/ld.so.conf*`, or `/usr/lib`.

Note one deliberate interaction: `setup.bash` exports `EPOS_SDK_DIR`, which is also the tool's own destination override. After sourcing it, a later `bootstrap-epos-sdk verify` with no `--sdk-dir` targets that same prefix. That is the desired behavior — it keeps an activated shell and the tool in agreement — but it should be documented in the README so nobody is surprised that sourcing an activation file changed where a later command looked.

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

A future application must match `argtypes` and `restype` to the shipped Linux `include/Definitions.h`. In this release, handles are `void*`; `VCS_GetPositionIs` takes `int*`, while `VCS_MoveToPosition` takes a C `long` target. These facts explain why the bootstrap should not copy an arbitrary Windows Python wrapper. Implementing those motor API bindings is out of scope here.

## 11. Exact verification contract

`verify` uses no sudo and makes no repairs, downloads, package changes, group changes, device calls, locks, or persistent run logs. It must not require the caller to have sourced `setup.bash`. If prerequisites are absent it fails with instructions to run `install`.

### 11.1 Required checks

| Check | Passing condition |
|---|---|
| Host | §7.1 gate satisfied (failure is exit 2, not a failed check) |
| Installation identity | Valid supported receipt schema; matching prefix, owner, release, and registration per §6.4 |
| Archive | Retained archive matches pinned size and SHA-256 |
| Payload | Every managed regular file matches its recorded hash; required files, `EULA.txt`, and `include/Definitions.h` present |
| Selected libraries | Both match the manifest's pinned hashes, pass the §8.4 ELF check, and the two relative links resolve to them |
| Activation | `setup.bash` matches the hash recorded at install time and points inside the resolved prefix |
| Python | `/usr/bin/python3` imports `ctypes`, is 64-bit, and `python3-venv` reports installed |
| Native dependencies | The intended EPOS and FTDI libraries load in a bounded child process and every native dependency resolves (§11.3) |
| Expected exports | Addresses resolve for `VCS_OpenDevice`, `VCS_CloseDevice`, and `VCS_GetDriverInfo`; none is called |
| USB configuration | Owned rules file has expected content, `root:root`, mode `0644`, and a parsable registration comment; `epos` exists and configured membership is present |
| Udev service | `systemctl is-active systemd-udevd.service` reports `active`; no device permissions are tested |

The udev-service check fails inside a container, which is correct and expected: a container cannot establish the host acceptance criteria (§14). The failure message should say so explicitly rather than looking like a broken installation.

### 11.2 Locating an installation the caller did not name

If the resolved prefix holds nothing but the machine-wide registration names a different prefix, do not silently follow it — §8.5 requires commands to use their resolved prefix consistently. Instead, read the registration and say so:

```text
[ERROR] No EPOS SDK installation at /home/lk/workspace/upstream/epos-sdk
[INFO]  An installation is registered at /opt/lab/epos-sdk (owner: lk).
[INFO]  Re-run with: bootstrap-epos-sdk verify --sdk-dir /opt/lab/epos-sdk
```

The registration already holds this information; not using it would make a recoverable situation look like a broken one.

### 11.3 The native load check

Run the load check in a separate process with a short deadline, so a native crash or hang becomes a clear verification failure rather than a stuck command:

```bash
cd "$empty_tmpdir" && env -i \
  PATH=/usr/bin:/bin \
  HOME="$empty_tmpdir" \
  LC_ALL=C \
  PYTHONDONTWRITEBYTECODE=1 \
  timeout --signal=TERM --kill-after=2 10 \
  /usr/bin/python3 -I -B "$PROJECT_DIR/lib/check_load.py" \
    --lib-dir "$lib_dir" --json
```

Each part is load-bearing:

- `env -i` drops `LD_PRELOAD`, `LD_LIBRARY_PATH`, `LD_AUDIT`, `PYTHONPATH`, `PYTHONHOME`, and everything else that could substitute a foreign library. Scrubbing happens only in the child; the user's shell is never modified.
- `cd "$empty_tmpdir"` neutralizes the working-directory exposure created by the run-path trailing colon (§4). An env scrub alone does not cover it.
- `-I` runs Python isolated, which also means `check_load.py` cannot import sibling modules and must be self-contained. `-B` plus `PYTHONDONTWRITEBYTECODE=1` keeps the check from leaving `__pycache__` anywhere.
- `timeout` maps cleanly onto distinguishable outcomes.

Verify the two libraries' hashes *before* loading them. Load by explicit absolute path, FTDI first with `RTLD_GLOBAL`, and retain both handles. Then confirm from the child's own `/proc/self/maps` that the loaded EPOS and FTDI objects are the files inside the managed prefix — a matching filename is not sufficient evidence. Do not hard-code system libc paths; successful loading resolves those dependencies.

Map the child's exit status as follows:

| Child exit | Meaning |
|---|---|
| 0 and `"ok": true` in its JSON | Pass |
| 0 and `"ok": false` | Fail, report the child's `error` field |
| 124 | Fail: load timed out after 10 s |
| 128+N | Fail: the loader or vendor initialization died on signal N |
| anything else | Fail: report exit status and captured stderr |

Appendix E specifies the child's contract.

Resolving an export address is allowed; invoking it is not. Native library loading executes vendor initialization code. This research did not establish every internal side effect of that initialization, so do not advertise "zero USB syscalls" or "no vendor initialization." The promised behavior is no explicit controller enumeration, connection, data request, state change, or hardware test by this tool. Characterize any initialization side effects during Ubuntu validation. If a supposedly software-only check turns out to require a controller to succeed, that check does not belong in default verification.

Verification must not intentionally leave cache files or bytecode in the SDK or application folders, and must clean the temporary directory it created. If the vendor loader creates unavoidable persistent state, document the observed behavior and adjust the check deliberately rather than silently violating the contract.

### 11.4 Output

Unexpected extra files in the SDK prefix are reported as a warning when all required files remain valid. Modified managed files are failures. Uninstall has the stricter preservation behavior in §12.

Successful output, in the house style:

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

Do not show a "missing controller" warning; no controller is expected for this command. The final success wording must not overstate Ubuntu hardware compatibility or active-session USB permissions.

## 12. Uninstall and recovery

Uninstall must work when the download server is unavailable or the native libraries are missing or unloadable. It uses validated ownership records and static inspection, not SDK execution.

Before removing anything:

1. Resolve and validate the prefix and machine-wide registration against §6.4.
2. Confirm the invoking UID owns that registration and that the IDs match.
3. Inventory every expected file and link, and every actual prefix entry, without following symlinks.
4. Refuse if a managed file has changed, a generated link points elsewhere, an unrecognized file is present, or foreign configuration occupies the owned rules filename. Explain the exact conflict so the user can preserve or move it and retry. Missing owned files are allowed, so a partial installation stays cleanable.
5. Print the exact local installation, rules file, and membership change to be removed, plus the resources deliberately retained. Confirm once unless `--yes` was supplied.

Remove only recorded managed content and the matching owned udev rule. Remove this user's `epos` membership only if this installation originally added it, per the write-once provenance in §6.3; preserve preexisting membership. Retain the named group itself as a shared system resource, even if this tool originally created it — other users may already depend on it, and §6.5 makes it the supported path for a second user.

Retain installed apt packages, other users' memberships, foreign configuration, application projects, all venvs, motor parameter backups, and any vendor data outside the managed prefix. State these retained resources in the completion message.

Reload udev rules after removing the owned rule. Do not try to revoke already running sessions' supplementary groups or alter connected devices. Explain that future USB permission behavior changes when rules are reapplied. An already sourced shell may still contain an obsolete `EPOS_LIB_DIR` and library-path entry; recommend a fresh shell rather than editing startup files.

Remove directories only when empty after deleting the validated owned contents. Keep the receipt until the last practical step; the lock file is released and unlinked last of all, after the receipt. Preserve enough phase information to resume after a partial failure; return nonzero instead of claiming success. Repeating uninstall after a fully successful removal exits 0 without sudo.

Row 3 of §6.4 is the important recovery case: if the prefix was manually deleted but a matching root-owned registration remains, use its validated metadata to remove only that owned rule and any recorded tool-added membership. Row 5 is its mirror: if the prefix is populated but its receipt is missing or invalid, do not delete its contents — report the conflict. `--yes` never bypasses either rule.

## 13. Repository organization

Keep the code smaller than the ROS bootstraps. Sizes are guidance from the existing repositories, not targets to hit.

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

Merge helpers if that improves clarity. Use a small number of direct functions; do not create a general plugin/stage framework, daemon, database, package manager, or reusable SDK abstraction. Only add a test dependency if the standard library and shell fixtures prove insufficient.

Two deliberate departures from the prior repositories, both worth a comment in the code:

- The release pin is JSON, not the `config/defaults.conf` shell file those projects use. It holds hashes and structured data that the tool parses but must never source, and §6.2 makes "data, never shell-sourceable code" a property of the design rather than a preference.
- There is no `logs/` directory. v1 has no persistent run-log infrastructure (§5.4).

Every shell file carries `# shellcheck shell=bash` and the whole tree passes `shellcheck -x`. Use `set -Eeuo pipefail` in the entry point and an `ERR` trap that names the current stage, as `lib/log.sh` in `ros2-jazzy-bootstrap` already does.

Do not run installer scripts from the reference repositories as part of this task. They are design references, not dependencies. Their ROS checks, camera configuration, and source-build workflows are not applicable to this tool.

## 14. Required tests and acceptance criteria

Tests are justified here because the tool downloads binaries and modifies system access configuration. They must verify meaningful behavior and filesystem boundaries. Fixture tests redirect all filesystem and privileged operations into controlled temporary fixtures or mocks; never mutate the developer's real `/etc`, accounts, or upstream directories.

### 14.1 How privileged behavior is tested

v1.0 required that production interfaces not expose arbitrary privileged destinations merely to make testing easier, but gave no way to test writes to `/etc`. Two mechanisms resolve that without weakening the production interface.

**Privileged actions are stubbed at `PATH`.** Every privileged action goes through one `run_privileged` wrapper that invokes `sudo` with a fixed, small command vocabulary — and nothing else:

```text
sudo DEBIAN_FRONTEND=noninteractive apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends ...
sudo groupadd --system epos
sudo gpasswd -a <user> epos
sudo gpasswd -d <user> epos
sudo flock --exclusive --timeout 60 /etc/udev/rules.d <project>/lib/privileged-udev.sh publish|remove ...
```

Fixture tests prepend a recording `sudo` stub, in the `<<< args >>>` block style `vimbax-ros2-driver-bootstrap/tests/run-tests.sh` already uses, and assert on both the arguments and the invocation count. That closed vocabulary is itself a test assertion: any other `sudo` shape is a bug.

**Reading the registration is de-escalated, never escalated.** A fixture cannot create a file in `/etc`, so the rules directory is overridable by exactly one documented variable, `EPOS_BOOTSTRAP_UDEV_DIR`, under these constraints:

- the value must be an existing directory owned by the invoking UID, and must not be `/etc` or under it — otherwise the tool exits 2;
- when it is set, the registration step runs in place, without sudo and without the machine-wide lock;
- every run prints `[WARN] TEST MODE: udev directory overridden to <path>; not a supported installation`;
- no ownership, hash, receipt, conflict, or host check is relaxed by it.

The override can only point somewhere the user already has full access, so it cannot reach a privileged destination and cannot grant anything the caller lacks. It removes privilege rather than adding it, which is what keeps it compatible with the rule it is implementing.

### 14.2 Required cases

| Area | Required cases |
|---|---|
| CLI | Three commands, no-argument help, flags before/after commands, `--sdk-dir=PATH` and `--sdk-dir PATH`, `--`, unknown/conflicting options, empty values, empty `EPOS_SDK_DIR`, precedence, paths containing spaces and metacharacters |
| Exit codes | Each row of the §5.4 table, including a blocked dry run exiting 1 and an unsupported host exiting 2 for all three commands |
| Read-only behavior | Help and every dry run make no writes, network calls, sudo calls, or locks, and load no vendor library; `verify --dry-run` explicitly skips the load check; `verify` makes no deliberate persistent change and no EPOS API or device call; owned temporary resources are cleaned |
| Host checks | Ubuntu 24.04 amd64 accepted; a point release accepted; macOS, ARM, an `ID_LIKE=ubuntu` derivative, 32-bit Python, WSL, and real root execution each refused with the right status |
| Download/extraction | Correct pin accepted; wrong size, wrong hash, HTML error response, interrupted transfer leaving only `.part`, traversal, absolute member, duplicate entries, non-regular members, and unexpected top-level root all rejected |
| Installation | Fresh install creates exactly the §6.1 footprint; healthy rerun mutates nothing and calls sudo zero times; each phase in §7.3 can be interrupted and resumed; every row of the §6.4 matrix behaves as specified |
| Permissions | Sudo used only for the §14.1 vocabulary; native files owned by the user, `0644`/`0755`, no executable bits in the payload; root rule `0644`; no world-writable device rule, sudoers edit, or global library registration |
| Receipt | Provenance is written before the mutation and survives reruns unchanged; an interrupted run between intent and completion recovers correctly; invalid schema, newer schema, path traversal, and symlink targets never authorize deletions |
| Activation | Correct custom path; repeated sourcing does not duplicate entries; unset `LD_LIBRARY_PATH` does not produce an empty entry; executing `setup.bash` directly is refused; a failed source returns rather than exiting; no shell-startup file changed |
| Verification | Missing, modified, wrong-architecture, and missing-dependency cases fail; load success, failure, crash, and timeout each map to the right §11.3 outcome; a foreign library substituted on the path is detected via `/proc/self/maps`; no attached hardware still passes; a wrong prefix produces the §11.2 pointer |
| USB/session state | Missing group, missing configured membership, and missing or foreign rules each fail; stale effective groups produce the advisory and still exit 0; a directory-service `epos` group is refused cleanly; no USB enumeration, module unload, or device trigger |
| Uninstall | Exact owned content removed; packages, group, and preexisting membership retained; added membership removed; unknown or modified files preserved through refusal; missing payload still cleanable; repeat is a no-op; partial failures recoverable |
| Concurrency | Two installs at the same prefix: the second fails fast on the per-prefix lock. Two installs at *different* prefixes: exactly one registration exists afterwards and neither corrupts the rules file |
| Static analysis | `shellcheck -x` clean, `bash -n` clean on every shell file, and both Python helpers parse clean via `ast.parse` |

Use `ast.parse` rather than `py_compile` for the Python syntax check: `py_compile` writes `__pycache__` even under `-B`, which would violate this project's own no-bytecode rule from inside its test suite.

Use mocked downloads and commands for deterministic fixture tests. Mocks prove bootstrap logic, not that maxon's binary works.

### 14.3 Integration test

Also perform a real integration test in a disposable Ubuntu 24.04 amd64 system with sudo and a functioning udev service, without an EPOS controller. Exercise `install` → `verify` → `install` again → `uninstall` → `uninstall` again, including a custom path with a space in it. The second `install` must call sudo zero times, and the second `uninstall` must exit 0 without sudo.

A container without a real udev service can test file and loading behavior but cannot establish the complete host acceptance criteria; the `systemd-udevd` check is expected to fail there, and that is the difference between the two environments rather than a defect.

The real verification test uses the official pinned archive and Ubuntu's `/usr/bin/python3`. Record OS, architecture, Python version, SDK hash, the observed extracted size (to tighten `min_free_bytes`), whether the recorded run-path tag is `DT_RPATH` or `DT_RUNPATH`, and any observable side effect of vendor initialization. It is acceptable to develop and run fixture tests on macOS, but the stubs assume GNU tooling, so Linux is the supported place to run them; clearly mark Ubuntu integration as pending until it is run. Do not claim vendor certification from your own successful test.

### 14.4 Definition of done

- Every case in §14.2 passes, and §14.3 has actually been run on Ubuntu 24.04 rather than deferred.
- `shellcheck -x` and `bash -n` are clean.
- Appendix A's pins have been re-confirmed against a fresh download (§0).
- The README covers install, custom paths, what `verify` does and does not prove, uninstall scope, Python consumption, the `EPOS_SDK_DIR` interaction in §10, the multi-user note in §6.5, the single network host in §6.1, the full-sudo assumption in §6.6, and known limitations.
- `LICENSE` exists and the README states the SDK is downloaded from maxon under maxon's terms, not redistributed here.

## 15. Known limits and research evidence

The [Command Library manual, section 9.2](https://www.maxongroup.com/medias/sys_master/root/9157360353310/EPOS-Command-Library-En.pdf) lists older Intel Ubuntu versions in its tested-platform table. It does not establish Ubuntu 24.04 support. Library loading and installation behavior need actual Ubuntu validation. Controller communication remains outside v1 acceptance.

EPOS Studio is the Windows commissioning tool. Configuration, tuning, and persistent parameter backups belong to the later hardware workflow; the Linux library does not reproduce all Studio GUI or parameter import/export features. [Commissioning guidance](https://support.maxongroup.com/hc/en-us/articles/6719969220380-EPOS4-IDX-Important-steps-during-initial-commissioning), [parameter backups](https://support.maxongroup.com/hc/en-us/articles/360005421674-EPOS-IDX-Export-of-parameter-configuration-in-a-dcf-file).

The vendor `HelloEposCmd` source defaults to a motion demonstration that can clear faults and enable the drive. It must never be the bootstrap smoke test. Losing USB communication also does not inherently stop EPOS2/EPOS4 motion; this is context for excluding motor tests, not a feature for this installer to solve. [Communication-loss behavior](https://support.maxongroup.com/hc/en-us/articles/360012982439-EPOS4-Motor-stop-at-communication-lost).

Research already completed: official archive download, archive hash and structure inspection, installer inspection, static x86_64 binary and ELF dependency inspection, header inspection, and review of the user's prior bootstrap code. No Linux binary, controller, or motor was run during that research. The earlier read-status Python example from the conversation opens a controller; it is intentionally not part of this tool.

Open questions this design deliberately leaves to Ubuntu validation rather than guessing at now: whether the run-path tag is `DT_RPATH` or `DT_RUNPATH`; what side effects vendor initialization has at load time; the extracted payload's file count and size; and whether any dependency beyond §8.1 appears in practice.

## 16. Prior projects to consult

These are references for style and behavior, not prerequisites. The implementing agent should inspect current files before adapting code; the repositories may evolve. The hashes below are **Git blob hashes of the named files**, not commit IDs or clone refs, and all three were re-verified against the live repositories on 2026-09-22.

| Reference | Relevant patterns | Reviewed entry-point blob |
|---|---|---|
| [vimbax-sdk-bootstrap](https://github.com/lkaising/vimbax-sdk-bootstrap/blob/main/bootstrap-vimbax-sdk) | SDK directory override, `--sdk-dir=` parsing, ELF header checks without `file(1)`, `resolve_project_dir`, exact system-file previews, idempotency | `b44d0cdc8845082a926ca222ccfe1411a3aea616` |
| [ros2-jazzy-bootstrap](https://github.com/lkaising/ros2-jazzy-bootstrap/blob/main/bootstrap-ros2-jazzy) | Check/action stages, strictly read-only dry runs, `lib/log.sh` conventions, `require_not_root`, workspace ownership | `492b4fe993e5675f3a7098546b4631f28029c94e` |
| [vimbax-ros2-driver-bootstrap](https://github.com/lkaising/vimbax-ros2-driver-bootstrap/blob/main/bootstrap-vimbax-ros2-driver) | Small entry point, dependency ownership boundaries, `PATH`-stub fixture tests, `NO_COLOR` handling | `9353ff91a37d80c5c0df9a19c417c28364604195` |

Particularly useful supporting files are [ROS workspace ownership](https://github.com/lkaising/ros2-jazzy-bootstrap/blob/main/lib/workspace.sh), [guarded cleanup](https://github.com/lkaising/ros2-jazzy-bootstrap/blob/main/lib/clean.sh), [logging and prompts](https://github.com/lkaising/ros2-jazzy-bootstrap/blob/main/lib/log.sh), and [driver fixture tests](https://github.com/lkaising/vimbax-ros2-driver-bootstrap/blob/main/tests/run-tests.sh). That last file is the model for §14.1's stub strategy. The [driver's own specification](https://github.com/lkaising/vimbax-ros2-driver-bootstrap/blob/main/vimbax-ros2-driver-bootstrap-spec.md) is the closest precedent for this document's shape.

The Vimba X SDK tool assumes an already extracted SDK and registers a global GenTL path; this EPOS design deliberately includes download and extraction and uses local library paths. The camera simulator test does not transfer to EPOS.

## 17. Deliverables and remaining questions

The implementation deliverables are a runnable bootstrap, its helpers and release manifest, a `LICENSE`, tests, and a README covering everything listed in §14.4. Include exact test results and any pending Ubuntu validation in the final implementation report.

There are no blocking product questions for implementing this v1. The defaults in §2, the command UX in §5, the multi-user policy in §6.5, and the group retention policy in §12 are explicit design choices the user can revise. Do not expand scope to resolve the unknown controller or motor.

Ask for a decision only if a concrete new fact invalidates the design — for example, the official pinned archive becomes unavailable or its hash has changed, the real Linux library fails on Ubuntu 24.04, the run-path or SONAME facts in §4 turn out to be wrong in a way the preload design depends on, or the destination machine has a conflicting registration that cannot be handled within the ownership rules. Present the evidence and a specific alternative. Do not silently change versions, remove foreign installations, or declare hardware compatibility.

This handoff specifies the project to implement. Creating or publishing a GitHub repository, pushing commits, or installing on a real host follows the instructions of the task in which the implementing agent receives it; possession of this card alone is not an instruction to publish or modify a host.

---

# Appendices — exact artifacts

These are the files the tool reads and writes. They are specified here rather than described, because three of them are hashed and two are parsed, and a prose description is not a stable enough contract for either.

## Appendix A — `config/sdk-release.json`

Maintainer-controlled. Parsed with Python's `json` module; never sourced as shell. Changing the pinned release means editing this file, validating on a real host, and updating §4.

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
  ],
  "min_free_bytes": 157286400
}
```

`libraries.ftdi` is listed first deliberately: that is the load order in §11.3, and keeping the file in load order makes the preload requirement visible to anyone reading the pin.

## Appendix B — `<sdk-dir>/.epos-sdk-bootstrap.json`

Mode `0644`, owned by the installing user. Written with `json.dump(..., sort_keys=True, indent=2)` and published by atomic rename, so an interrupted write never leaves a half-parsed receipt. Never sourced, never executed.

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

`payload.files` lists every regular file extracted from the archive, not only the required four; the two shown are an elision. Expect it to be the bulk of the file. If it exceeds roughly 1 MB, something has gone wrong with extraction and the run should stop rather than write it.

Rules that are not obvious from the shape:

- **Write-once provenance.** `system.udev.preexisting`, `system.group.existed_before`, and `system.group.membership_existed_before` are set exactly once, alongside `intent_recorded_utc`, *before* the corresponding system change (§6.3). A rerun never rewrites them, whatever the machine currently looks like.
- **Intent versus completion.** `intent_recorded_utc` present with `published` false, or with `membership_added_by_this_install` unset, identifies a run interrupted mid-change. That is the state phase `system` exists to recover.
- **The receipt does not hash itself.** `payload` and `generated` cover everything else in the prefix; `tool_artifacts` names the two files that are legitimately unhashed, so `verify` and `uninstall` can tell them apart from unexpected content.
- **Paths are relative to `prefix`** and validated before use: no absolute paths, no `..`, no symlink traversal out of the prefix.
- **Unknown `schema_version`**, higher or lower, is a refusal (row 11 of §6.4), not a best-effort read.

## Appendix C — the machine-wide registration

### C.1 `/etc/udev/rules.d/99-epos-sdk-bootstrap.rules`

Owner `root:root`, mode `0644`. Byte-identical whenever regenerated from the same installation, which is why it carries no timestamp.

```text
# Managed by bootstrap-epos-sdk. Do not edit.
# Remove it with: bootstrap-epos-sdk uninstall
# epos-sdk-bootstrap-registration: {"group":"epos","group_existed_before":false,"installation_uuid":"3f2b9c1e-6d84-4a77-9d2f-1c0b5a8e4471","membership_existed_before":false,"prefix":"/home/lk/workspace/upstream/epos-sdk","schema_version":1,"sdk_version":"6.8.1.0","uid":1000,"username":"lk"}
SUBSYSTEMS=="usb", ATTRS{idVendor}=="0403", ATTRS{idProduct}=="a8b0", GROUP="epos", MODE="0660"
SUBSYSTEMS=="usb", ATTRS{idVendor}=="24e7", ATTRS{idProduct}=="3b01", GROUP="epos", MODE="0660"
```

Generation and parsing:

- The registration line is produced by `json.dumps(obj, sort_keys=True, separators=(",", ":"))` on one line, prefixed with `# epos-sdk-bootstrap-registration: `. Sorted keys and no spaces make it reproducible.
- Parsing accepts **exactly one** line with that prefix. Zero, two or more, a non-object, or invalid JSON each make the file foreign — row 4 of §6.4 — and the tool refuses rather than guessing.
- The parsed object is data. Nothing in it is ever executed, sourced, or used as a command argument without the §8.5 path validation.
- A file at this path with no registration line is someone else's file. Leave it alone and name it in the error.

### C.2 `lib/privileged-udev.sh`

The only code in the project that runs as root. Invoked exactly as:

```bash
sudo flock --exclusive --timeout 60 /etc/udev/rules.d \
  "${PROJECT_DIR}/lib/privileged-udev.sh" publish <staged-file> <expected-uuid>

sudo flock --exclusive --timeout 60 /etc/udev/rules.d \
  "${PROJECT_DIR}/lib/privileged-udev.sh" remove <expected-uuid>
```

Contract:

1. `set -Eeuo pipefail`. Read **only** its positional arguments; ignore the environment entirely, since it inherits one across a `sudo` boundary.
2. Hard-code the target path. Refuse any argument that would write outside `/etc/udev/rules.d/99-epos-sdk-bootstrap.rules`.
3. Re-read the target *inside* the lock and re-check it against `<expected-uuid>`: absent is fine for `publish`; a matching registration is fine for both; anything else exits nonzero without touching it. This re-check inside the lock is what makes the check-then-act sequence atomic, and it is the reason the privileged step is one call rather than several.
4. `publish`: `install -m 0644 -o root -g root -T -- <staged-file> <target>`, which writes and renames atomically with the final mode already set.
5. `remove`: unlink the target only after the UUID matches.
6. Either way, on an actual change, run `udevadm control --reload-rules`. Never `udevadm trigger`, never restart the service.
7. Print what it did on stdout so the unprivileged caller can report it without re-reading as root.

Keep it under about 60 lines. It is the piece a reviewer will read most carefully, so it should be readable in one sitting.

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

`<PREFIX>` is substituted with single-quote escaping — every `'` in the path becomes `'\''` — so a path containing spaces or shell metacharacters is inert. §8.5 already rejects `:`, newlines, and control characters, so the two remaining hazards are quoting and the empty-entry case, and both are handled above.

Four details that are requirements rather than taste:

- `return 1`, never `exit`, on the missing-installation path. An `exit` here closes the user's interactive shell.
- `${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}` rather than `:${LD_LIBRARY_PATH}`. With the variable unset, the naive form yields a trailing empty entry, which the dynamic loader reads as the working directory.
- The `case` guard makes repeated sourcing idempotent and removes only this SDK's own entry from consideration; it does not rewrite anything else on the path.
- Quiet on success. It prints nothing when it works.

## Appendix E — `lib/check_load.py`

Run under the isolated invocation in §11.3, so it must be a single self-contained file that imports only the standard library — `-I` puts its own directory off `sys.path`, so a sibling import would fail.

Arguments: `--lib-dir PATH`, the two expected filenames, the expected SHA-256 of each, the symbol names to resolve, and `--json`.

Behaviour, in order:

1. Re-hash both libraries and compare to the pins. Mismatch means stop before loading anything — the check never loads a file it has not just verified.
2. `ctypes.CDLL(<abs path to libftd2xx.so.1.4.8>, mode=ctypes.RTLD_GLOBAL)`.
3. `ctypes.CDLL(<abs path to libEposCmd.so.6.8.1.0>)`.
4. Keep both handles referenced for the rest of the process.
5. Read `/proc/self/maps` and confirm that the mapped EPOS and FTDI objects are exactly the two absolute paths just loaded. A different path — a system-wide FTDI library, or one picked up from the working directory — is a failure, and the report names the path that was actually mapped.
6. For each expected symbol, resolve its address via `getattr(handle, name)` and record it. Resolving performs `dlsym`; it does not call the function. **No EPOS API function is ever invoked.**
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

On failure, `"ok": false` with `error` naming the failing step. The parent maps exit status per the table in §11.3, so a crash inside vendor initialization and a clean "could not load" are reported differently rather than both surfacing as "verify failed".

Symbol addresses may be recorded but must not be printed as raw pointers in normal output; they are meaningless to the user and vary per run.

## Appendix F — Suggested build order

Each step is independently testable, and the risky external facts are confronted first rather than last.

1. **Confirm the pins.** Download the archive, check size and SHA-256 against Appendix A, re-inspect the layout, the two library hashes, the ELF header fields, and the run-path tag. Everything downstream assumes these. If any differ, stop and follow §17.
2. **Skeleton and CLI.** Entry point, `lib/log.sh`, argument parsing, `--help`, exit codes, the §7.1 host gate. Test §14.2's CLI, exit-code, and host rows before writing anything that mutates.
3. **Path rules and the receipt.** §8.5, Appendix B read/write, schema refusal, path validation. Still no mutation outside a fixture prefix.
4. **Download and extraction.** §8.2–§8.4 and `lib/sdk_files.py`, against a local fixture archive first and the real one second.
5. **Local install.** Staging, publication, symlinks, `setup.bash`, receipt completion. At this point `install` works with the USB stage stubbed out.
6. **Verification.** `lib/check_load.py` and the §11 checks. This is where the real archive first gets exercised on Ubuntu.
7. **The privileged stage.** `lib/privileged-udev.sh`, group management, locking, and the §6.3 intent ordering. Do this after verification exists, so there is already a way to tell whether it worked.
8. **Uninstall.** §12 and the §6.4 matrix rows it owns.
9. **Concurrency, then the full matrix.** Both locks, and every remaining row of §6.4.
10. **Integration run and README.** §14.3, then §14.4's documentation list.

## Appendix G — Changes from version 1.0

Version 1.0 was sound in scope, boundaries, and safety posture; almost all of it survives unchanged. This revision fixes defects, resolves contradictions, and supplies the artifacts that were described but not specified.

**Defects fixed**

| | Problem in v1.0 | Fix |
|---|---|---|
| 1 | Group provenance was recorded after the change, so a run interrupted between `gpasswd` and the receipt write made the addition look preexisting, and `uninstall` would then never remove it | §6.3: observe, record intent, change, confirm — with write-once provenance fields |
| 2 | "One advisory lock on a mutating path" cannot serialize two installs at different prefixes contending for the single machine-wide registration, which §14 required to be impossible | §6.6: a per-prefix lock plus a machine-wide `flock` on the rules directory, with the check-then-act re-validated inside the lock (Appendix C.2) |
| 3 | Nothing forbade a timestamp in the generated files, which would make every rerun rewrite them and break the idempotency contract | §6.2: registration comment and `setup.bash` are byte-stable by construction |
| 4 | `setup.bash` was to "fail clearly", but an `exit` in a sourced file kills the user's shell | §10 and Appendix D: `return 1`, plus a direct-execution guard |
| 5 | ELF architecture checks were required, but `file`/`binutils` were correctly excluded from dependencies and no mechanism was given | §8.4: parse the ELF header directly, as `bootstrap-vimbax-sdk` already does |
| 6 | No `apt-get update` policy, so `install` fails on any host with a stale or empty package index — including the fresh container §14 requires for integration testing | §8.1: one `apt-get update`, only when a package is actually missing |
| 7 | "System Python" was required but unqualified, so a pyenv or conda `python3` on `PATH` would be used instead | §2 and §7.1: `/usr/bin/python3` explicitly |

**Contradictions and ambiguities resolved**

- `verify --dry-run` and `--yes` on `verify` were undefined, although §14 already implied a dry run for every command — §5.2 defines them, and the load-check exclusion is what makes `verify --dry-run` meaningful.
- A dry run that found a blocking conflict still exited 0 — §5.4 makes it exit 1, so `install --dry-run` is usable as a precondition check.
- `verify` on an unsupported host had no defined status — §5.4 makes an unsupported host exit 2 for all three commands.
- `--sdk-dir=PATH`, `--`, and an empty `EPOS_SDK_DIR` were unspecified, though the existing tool already supports the `=` form — §5.1.
- "Does not rewrite matching files" never said what happens to *missing* owned files — §6.4 rows 3 and 9 make `install` the repair path, which is why no `--repair` flag is needed.

**Specified rather than described**

Appendix A (release manifest), B (receipt schema), C (registration file and the privileged helper), D (`setup.bash`), E (the load-check child contract); §7.3 (phase values and resume semantics); §6.4 (the eleven-row state matrix); §14.1 (how privileged behavior is tested without exposing a privileged destination); and exact commands throughout for apt, group management, curl, zip member validation, and the isolated load check.

**Added**

Host-gate specifics including WSL and container handling (§7.1); the EULA acknowledgement in the install confirmation (§5.3); a `LICENSE` for the tool (§2, §13); the multi-user workaround (§6.5); the "no system change means no sudo prompt" rule (§7.4); free-space, dpkg-lock, and no-sudo-rights handling (§8); the directory-service group case (§9.1); the `/proc/self/maps` and empty-working-directory hardening rationale (§4, §11.3); the pointer to a registered installation at a different prefix (§11.2); the single-network-host statement (§6.1); house-style output (§5.5, §11.4); shellcheck and the definition of done (§13, §14.4).

**Corrected**

§16's blob hashes were re-verified against the live repositories and all three match. §4's vendor facts could not be re-verified because the revising environment cannot reach `www.maxongroup.com`; §0 records that, and step 1 of Appendix F confronts it first.
