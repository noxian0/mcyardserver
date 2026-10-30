# Third-party notices

MCyard Server's original source code, original vector icons, forest illustration and original Fabric
bridge are covered by [LICENSE](LICENSE). That license does not replace the
licenses of the following components.

## Included in the Windows application

- **CPython** — Python Software Foundation License and the additional notices
  shipped with Python. [License](https://docs.python.org/3/license.html) ·
  [Source](https://www.python.org/downloads/source/).
- **PySide6, Shiboken6 and Qt 6 runtime libraries** — the distributed community
  packages offer open-source licensing options. MCyard Server uses their LGPLv3
  option for the runtime modules it loads. Qt may include additional third-party
  components under their own notices. [Qt for Python licensing](https://doc.qt.io/qtforpython-6/index.html)
  · [Qt source archive](https://download.qt.io/archive/qt/)
  · [Qt for Python source archive](https://download.qt.io/official_releases/QtForPython/).
- **PyInstaller bootloader** — GPLv2-or-later with the PyInstaller bootloader
  exception, which permits distributing bundled applications under their own
  license. [License and exception](https://pyinstaller.org/en/stable/license.html)
  · [Source](https://github.com/pyinstaller/pyinstaller).

The LGPLv3 text and the GPLv3 text it incorporates accompany the Windows build
under `licenses`. Qt module attribution metadata and full linked copyright/license
files are included under `licenses/qt-6.11.1`, with an index in
`licenses/QT-THIRD-PARTY-NOTICES.txt`. This is a conservative superset for Qt Base,
SVG and Image Formats, including some platform/build-only components. Canonical texts:
[LGPLv3](https://www.gnu.org/licenses/lgpl-3.0.html) and
[GPLv3](https://www.gnu.org/licenses/gpl-3.0.html).

Qt/PySide6/Shiboken6 libraries are dynamically loaded. You may replace or modify
those libraries and reverse engineer the combined application as necessary to
debug modifications to the LGPL-covered components. MCyard Server imposes no
restriction on those rights. Keep the matching architecture and compatible ABI
when replacing the libraries. The source links above provide upstream source;
the exact bundled package versions are pinned in `pyproject.toml` and recorded
by the release build. No changes to Qt/PySide6/Shiboken6 are made by this project.

## Downloaded separately for a server

These are not included in the source archive or portable application (apart from
MCyard Server's own bridge). Their downloads and use remain subject to their own
terms and licenses:

| Component | Source and terms |
| --- | --- |
| Minecraft Java server | [Official server download](https://www.minecraft.net/en-us/download/server), [Minecraft EULA](https://www.minecraft.net/en-us/eula) |
| Java runtime | The selected Java distributor's terms; the app does not bundle a Java runtime |
| Fabric Loader / server launcher | [Fabric project](https://fabricmc.net/), [Fabric Loader source/license](https://github.com/FabricMC/fabric-loader) |
| Minecraft Forge | [Official downloads](https://files.minecraftforge.net/), [Forge source and license](https://github.com/MinecraftForge/MinecraftForge) |
| Fabric API | [Project and license](https://modrinth.com/mod/fabric-api) |
| Forge Config API Port | [Project and license](https://modrinth.com/mod/forge-config-api-port) |
| Simple Backups for Fabric | [Project and license](https://modrinth.com/mod/simple-backups-for-fabric) |
| Lithium | [Project and license](https://modrinth.com/mod/lithium) |

The created server's `mcyard.json` records the exact mod versions, download
sources and hashes. The user explicitly accepts Minecraft's EULA in setup before
server downloads begin. Third-party project names do not imply endorsement.

## Artwork and branding

The MCyard Server mark, interface line icons and fallback forest illustration are original drawings. No Minecraft
artwork, fonts, music, game textures or promotional images are distributed with
MCyard Server. Panoramas imported from an installed game and user-provided background images remain local and retain their owners'
rights. Do not include them in a source upload or release bundle.

NOT AN OFFICIAL MINECRAFT PRODUCT. NOT APPROVED BY OR ASSOCIATED WITH MOJANG OR
MICROSOFT. Minecraft is a trademark of Mojang Synergies AB.
