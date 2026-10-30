# Development and releases

## Code map

```text
src/mcyard/
  __main__.py             # Library / manager / backup-worker entry point
  hub.py                  # Server library and creation wizard
  catalog.py              # Publisher catalogs and compatible loader versions
  import_existing.py      # In-place import with launcher detection and preview
  mods.py                 # Bounded mod metadata and reversible toggles
  provision.py            # Validated downloads and transactional folder setup
  java_runtime.py         # Java detection and version checks
  runtime_install.py      # Verified, per-user Temurin runtime installation
  registry.py             # Per-user server catalog
  paths.py                # Resource and runtime locations
  preferences.py          # Cached, watched appearance settings shared across windows
  backgrounds.py          # Private installed-game asset import and original fallback
  backup.py               # Verified offline snapshots
  backup_budget.py        # Shared per-server storage policy
  manager/                # UI, history, world/player data and local commands
bridge/                   # Original Fabric bridge source and build tool
resources/                # Original icons, bridge JAR, preset and license texts
installer/                # Inno Setup source for the per-user Windows installer
```

The library launches each server manager as its own process. A per-server lock
prevents duplicate manager windows. The enhanced preset uses local
files under `manager/data` for telemetry and bridge commands. Other setups send
commands to the owned Java process through stdin. No administration network
listener is opened.

App state defaults to `%LOCALAPPDATA%\MCyard Server`. `MCYARD_DATA_DIR` overrides
it for tests or a separate installation. Keep runtime data outside this source
tree. `MCYARD_REDUCED_MOTION=1` disables interface animation. The UI switch persists
in `preferences.json`; file watching keeps separate manager processes in sync.
Panorama frames use cached pixels with a 30 fps ceiling. World time comes from
the bridge, owned console queries, or bounded cached NBT reads when offline.

## Development

The [custom license](../LICENSE) permits building the unmodified app for personal,
non-commercial use. Obtain the author's permission before modifying or
redistributing original project code, subject to the license's exceptions.

Create a Windows Python 3.14 virtual environment and run `python -m pip install
-e ".[build]"`. Run the app with `python -m mcyard`.

The public repository contains the app and build inputs. Maintainer tests,
temporary servers and local validation output are excluded. Check a build with
a disposable server folder, keeping your live worlds separate.

## Rebuilding the bridge

The repository includes the original bridge JAR used by the preset. To rebuild
it, prepare a Fabric 26.3 server with the preset dependencies and start it once
so its dependency JARs exist. Stop it, then run:

```powershell
python bridge/build.py --server-dir "D:\Servers\disposable-build-server"
```

Java 25's `javac` must be available, or pass `--javac` with its path. The build
reads that server's dependencies but does not modify its world or libraries.
Only `dev/mcyard/bridge` classes, mod metadata and the project license are written
to `resources/mcyard-bridge-0.1.0.jar`; Minecraft or dependency classes must
never be bundled into it. Update the version pins and rerun live integration
checks together when supporting another Minecraft release.

## Packaging

`python scripts/build_windows.py` builds the portable folder with PyInstaller.
Python and the selected Qt runtime components are included; Java, Minecraft and
third-party server mods are not. Preserve the Qt DLLs as replaceable dynamic
libraries and include all bundled license notices.

The build uses a restricted dependency search path so unrelated developer-tool
DLLs cannot enter the application. Test the packaged EXE as well as the Python
source; startup diagnostics are written to the app data folder.

With Inno Setup 6 installed, run `python scripts/build_installer.py` after the
portable build. It creates `MCyard Server Setup.exe` in the project root and a
versioned installer in `release`, then updates the release checksums. Installer
source and testing options are described in [Windows setup](INSTALLER.md).

Before uploading a source archive, check that it contains code/docs, original
resources and build inputs only. Exclude tests, `dist`, `build`, virtual environments, test
output, downloaded server files, worlds, logs, backups, player data, secrets and
personal images. `.gitignore` is useful for Git but is not a ZIP packaging rule.

For a Windows release, distribute the complete generated app folder with the
README, app license and third-party notices. Test extraction and startup on a
clean Windows account without Python, then test each server type with its required Java version.
GitHub Actions produces a build artifact for review; publishing a release is a
separate maintainer action.

Qt attribution files are pinned to Qt 6.11.1 under `resources/licenses`. To refresh
them deliberately, run `python scripts/collect_qt_licenses.py`; the collector
records official source URLs and file hashes. Review changes before a release.
