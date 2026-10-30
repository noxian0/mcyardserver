# Windows setup

Run **MCyard Server Setup.exe**. Setup installs the app for your Windows account
and creates a Desktop shortcut and a Start Menu shortcut. Administrator access is
not needed. Python and Qt are included in the app.

The default destination is `%LOCALAPPDATA%\Programs\MCyard Server`. Keep server
folders outside that directory. Your server library, managed Java runtimes and
default server folders live separately under `%LOCALAPPDATA%\MCyard Server`.
Existing imported servers stay where they are. Uninstall removes the installed
app and shortcuts; it does not remove your separate worlds, backups or app data.

## Java

Setup checks for Java 25 by default and downloads it only if a compatible runtime
is missing. Select Java 21 or Java 17 too if you plan to create older servers.
The creation wizard shows the Java version needed by your chosen server.

Downloaded runtimes are official Eclipse Temurin JRE packages. Their SHA-256
checksums are verified before installation, and their licenses stay in the
runtime folders. Downloads need internet access. Setup reuses existing suitable
Java installations and does not change your system PATH or default Java.

If Java installation fails, MCyard Server stays installed. Setup reports the
failure and does not automatically open the app. Check
`%LOCALAPPDATA%\MCyard Server\prerequisites.log`, then rerun Setup or install the
missing runtime from the creation wizard. Minecraft's EULA is presented separately
when creating a server; running this installer does not accept it.

## Building the installer

Install [Inno Setup 6](https://jrsoftware.org/isdl.php), then run on Windows x64:

```powershell
python scripts/build_windows.py
python scripts/build_installer.py
```

The second command finds Inno Setup in its normal per-user or system location.
You can supply `--compiler "C:\path\to\ISCC.exe"`, or set `INNO_SETUP_COMPILER`.
It produces `MCyard Server Setup.exe` in the project root, a versioned installer
in `release`, and adds its SHA-256 checksum to `release/SHA256SUMS.txt`.
Build the portable application first so Setup includes the latest code.

The installer is unsigned. A future public release can add code signing without
changing where user servers are kept.

## Unattended installation

Inno Setup's standard `/VERYSILENT /SUPPRESSMSGBOXES /NORESTART` options are
supported. Tasks are `desktopicon`, `java25`, `java21` and `java17`; select them
with `/TASKS="desktopicon,java25"`. Use `/TASKS="" /NOICONS` for an isolated
installation test without Java checks or shortcuts, and `/DIR="..."` to choose
its destination. Silent installation never launches the app.

Exit code 0 indicates successful setup. Exit code 10 means the application was
installed but at least one selected Java runtime failed to install. Other exit
codes are provided by Inno Setup. Close MCyard Server yourself before updating;
Setup does not automatically stop a running manager or Minecraft server.
