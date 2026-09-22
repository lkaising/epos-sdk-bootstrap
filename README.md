# EPOS SDK bootstrap

`bootstrap-epos-sdk` installs maxon's pinned EPOS Linux Library 6.8.1.0 in a user-owned directory on Ubuntu 24.04 amd64. It configures restricted USB permissions and checks the software without opening a controller or calling an EPOS API function.

Real installation and Ubuntu integration testing are pending explicit user approval. Isolated tests do not establish that the vendor libraries work on a host with running udev. See [validation status](docs/validation.md).

## Requirements

Use Ubuntu with `ID=ubuntu`, `VERSION_ID=24.04`, `uname -m` reporting `x86_64`, Debian architecture `amd64`, and a 64-bit `/usr/bin/python3`. Derivatives and other releases are unsupported. WSL installation is refused. Containers can run fixtures but cannot establish host udev acceptance.

Run as an ordinary user with unrestricted sudo. Bash 5, apt/dpkg, coreutils, `flock`, `getent`, `gpasswd`, `groupadd`, sudo, and working udev are prerequisites. The helper runs from your checkout with full sudo. A restricted sudoers policy is unsupported.

The installer checks and installs only missing packages:

```text
python3 python3-venv curl ca-certificates libc6 libstdc++6 libgcc-s1 udev
```

It runs `apt-get update` only when packages are missing. It performs no upgrade, adds no repository, and installs no pip package, compiler, or separate FTDI SDK.

## Commands

Start with the read-only plan:

```bash
./bootstrap-epos-sdk install --dry-run
./bootstrap-epos-sdk install
./bootstrap-epos-sdk verify
./bootstrap-epos-sdk uninstall --dry-run
./bootstrap-epos-sdk uninstall
```

Installation and removal ask once for confirmation. `--yes` or `-y` skips the prompt. For installation it also accepts the acknowledgement that the SDK is downloaded under maxon's license terms. Noninteractive installation or removal requires `--yes`. A satisfied installation or absent uninstallation does not prompt or use sudo.

The default prefix is `$HOME/workspace/upstream/epos-sdk`. `--sdk-dir PATH` and `--sdk-dir=PATH` override `EPOS_SDK_DIR`, which overrides the default. Repeat a chosen path for later commands:

```bash
./bootstrap-epos-sdk install --sdk-dir "$HOME/workspace/upstream/EPOS SDK" --dry-run
./bootstrap-epos-sdk install --sdk-dir "$HOME/workspace/upstream/EPOS SDK"
./bootstrap-epos-sdk verify --sdk-dir "$HOME/workspace/upstream/EPOS SDK"
```

Quote spaces and shell metacharacters. Colons, control characters, the home directory itself, system configuration paths, and the checkout itself are refused. Existing ancestors are canonicalized. The destination must be empty or hold a valid installation owned by the invoking user. Empty or whitespace-only `EPOS_SDK_DIR` is an error.

Flags can precede or follow the command. A bare `--` ends option parsing. No arguments, `--help`, and `-h` display help. The only commands are `install`, `verify`, and `uninstall`.

Every `--dry-run` is read-only, with no network, sudo, lock, file creation, or native library load. It reports local state and planned changes. `verify --dry-run` skips native loading and export checks. Exit 0 means success or an executable plan, exit 1 means a failed operation or blocked plan, and exit 2 means invalid arguments or an unsupported host. `NO_COLOR` disables terminal colors.

## Files and system changes

The prefix contains:

```text
.epos-sdk-bootstrap.json
setup.bash
downloads/EPOS-Linux-Library-En.zip
vendor/EPOS_Linux_Library/
```

The complete vendor package remains, including the EULA, headers, examples, and other architecture directories. Runtime configuration selects `lib/intel/x86_64`, where the tool adds relative `libEposCmd.so` and `libftd2xx.so` links. Files have mode `0644`; directories have mode `0755`. Vendor `install.sh` deliberately has no executable bit. The bootstrap never runs it, builds examples, or runs `HelloEposCmd`, whose demonstration can operate a drive.

The tool manages `/etc/udev/rules.d/99-epos-sdk-bootstrap.rules`, the dedicated `epos` system group, and the installing user's configured membership. Its operative rules are exactly:

```udev
SUBSYSTEMS=="usb", ATTRS{idVendor}=="0403", ATTRS{idProduct}=="a8b0", GROUP="epos", MODE="0660"
SUBSYSTEMS=="usb", ATTRS{idVendor}=="24e7", ATTRS{idProduct}=="3b01", GROUP="epos", MODE="0660"
```

The first ID is the SDK-listed EPOS2 FTDI device; the second is EPOS4. The root-owned rules file also records ownership and recovery state. It has mode `0644`. The helper reloads rules without triggering devices or restarting udev.

Package installation and group membership are separate system changes. The tool creates no global linker entries, `/usr/lib` links, sudoers entries, shell-startup edits, application environments, or persistent run logs.

Only one installation can register per machine. A different prefix or owner is a conflict. For another user, an administrator can run `sudo gpasswd -a <user> epos` and arrange read/traverse access to the existing SDK. Group membership alone does not grant access through another user's home directory.

## Download and integrity

`config/sdk-release.json` pins the version, starting HTTPS URL, archive size and SHA-256, and both selected library hashes. Installation downloads from [maxon's official SDK URL](https://www.maxongroup.com/medias/sys_master/root/9443687202846/EPOS-Linux-Library-En.zip) only when the retained archive is missing. It permits at most five HTTPS redirects, including to other hosts, and disables the user's default curl configuration. Final bytes must match the pins. These hashes provide reproducibility, not a vendor signature.

A missing archive may be downloaded again. Unexpected bytes in an existing archive or managed file cause a refusal. The tool does not overwrite them. Missing packages cause apt to contact the machine's configured repositories. `verify` and `uninstall` use no network.

ZIP validation rejects traversal, other roots, duplicate and case-colliding paths, symlinks, and special files before extraction. The approved exception to system-card section 8.3 accepts absent Unix type bits only for ordinary DOS/Windows file or directory entries with consistent attributes. The pinned vendor ZIP uses that format. Explicit Unix special-file types remain refused. See [the recorded decision](docs/validation.md#approved-zip-format-exception).

## What verification proves

`verify` checks receipt and registration identity, the archive, complete recorded payload, ELF architecture, selected library pins and links, activation file, Python and venv package availability, configured membership, owned rules, and active `systemd-udevd.service`.

A bounded child process uses `/usr/bin/python3 -I -B` with an empty environment and fresh empty working directory. It rehashes both libraries, loads FTDI by absolute path with `RTLD_GLOBAL`, then loads EPOS. It checks `/proc/self/maps` for the exact files and resolves `VCS_OpenDevice`, `VCS_CloseDevice`, and `VCS_GetDriverInfo` without calling them. Timeout is 10 seconds with a two-second kill grace period. The check needs no sourced activation file and cleans its temporary directory.

Loading executes vendor initialization code. Its effects still need observation during approved Ubuntu validation. The tool makes no explicit controller enumeration, connection, data request, or motor command. Verification does not prove controller communication, motor configuration, safe motion, or vendor certification for Ubuntu 24.04.

Configured membership and effective process groups differ. A new membership may require a new login or SSH session. Verification passes with an advisory when configuration is correct but this session is stale. An already attached controller may require reconnection using its documented power-off USB procedure during the later hardware workflow. Other udev rules may grant additional access.

## Activate and use from Python

```bash
source "$HOME/workspace/upstream/epos-sdk/setup.bash"
```

The file sets `EPOS_SDK_DIR` and `EPOS_LIB_DIR`, and prepends the library directory to `LD_LIBRARY_PATH` once without adding an empty entry. Source it; direct execution is refused. It changes only the current shell and its children.

`EPOS_SDK_DIR` also overrides the CLI destination. A later `bootstrap-epos-sdk verify` in this shell targets the activated installation unless `--sdk-dir` overrides it.

Your later application owns its environment and dependencies:

```bash
/usr/bin/python3 -m venv /path/to/application/.venv
source /path/to/application/.venv/bin/activate
```

After SDK activation, this example shows the load order. It executes vendor initialization but opens no controller:

```python
import ctypes
import os
from pathlib import Path

lib_dir = Path(os.environ["EPOS_LIB_DIR"])
ftdi = ctypes.CDLL(str(lib_dir / "libftd2xx.so.1.4.8"), mode=ctypes.RTLD_GLOBAL)
epos = ctypes.CDLL(str(lib_dir / "libEposCmd.so.6.8.1.0"))
# Keep both objects alive. No controller is opened here.
```

`ctypes` ships with Python. Maxon describes it in its [Python guidance](https://support.maxongroup.com/hc/en-us/articles/360012695739-EPOS2-EPOS4-IDX-Commanding-by-Python-ctypes), but provides no supported native Python SDK. Application bindings must match `argtypes` and `restype` to the shipped Linux `include/Definitions.h`. Handles are `void*`; `VCS_GetPositionIs` takes `int*`, while `VCS_MoveToPosition` takes a C `long`. Check these declarations before copying Windows bindings. Implementing bindings and motor control is outside this project.

## Recovery and removal

Rerun ordinary `install` to restore missing owned files or resume an interrupted installation. Healthy reruns preserve files and identity and use no sudo. The receipt and root registration preserve intent before changes, including whether membership existed beforehand. Prefix and rules-directory locks serialize changes. Rerun the corresponding command to resume interrupted registration states. Once removal begins, finish `uninstall` before installing again.

Uninstall checks all remaining managed files and actual prefix entries before deletion. It refuses changed files, unknown files, unexpected links, invalid receipts, and foreign rules. Inspect and move the named conflict aside, then retry. `--yes` never overrides these checks.

Missing payload remains removable. If the prefix was deleted but its matching root registration remains, `uninstall --sdk-dir <original-prefix>` completes shared cleanup from that record. An interrupted attempt that never registered, or whose shared removal was acknowledged, may remove only its own validated local files while leaving another valid registration untouched.

Uninstall removes the user's membership only if this installation added it. It retains the `epos` group, installed packages, preexisting membership, other users' memberships, foreign configuration, application projects, venvs, parameter backups, and vendor data outside the prefix. Running processes retain supplementary groups. Rules take effect when reapplied; uninstall does not change connected devices. Use a fresh shell to discard an obsolete activation environment.

## Tests and remaining validation

```bash
./tests/run-tests.sh
```

Tests use temporary directories, synthetic payloads, simulated accounts and reloads, and recording command stubs. They do not install host packages, change groups, or modify host udev configuration. Python syntax checks use `ast.parse` to avoid bytecode files. Shell checks require `shellcheck`; missing tooling is reported.

The first real installation requires approval and a disposable Ubuntu 24.04 amd64 host with sudo and working udev. See [pending validation](docs/validation.md).

The [Command Library manual](https://www.maxongroup.com/medias/sys_master/root/9157360353310/EPOS-Command-Library-En.pdf) lists older Ubuntu releases, not Ubuntu 24.04 certification. EPOS Studio commissioning, tuning, backups, USB communication, and motor operation remain outside this project. EPOS2's possible `ftdi_sio`/D2XX conflict belongs to later hardware troubleshooting. The tool never blacklists or unloads drivers, detaches devices, or probes that conflict. See [FTDI's explanation](https://ftdichip.com/faq/can-i-just-load-the-d2xx-drivers-and-run-a-d2xx-application-on-a-newly-installed-linux-system/).

## License

The bootstrap is [MIT licensed](LICENSE). The SDK is downloaded from maxon under maxon's terms and is not redistributed here. Its EULA remains at `<prefix>/vendor/EPOS_Linux_Library/EULA.txt`. See [maxon's download page](https://www.maxongroup.com/maxon/view/product/380264) for the package and associated license information.
