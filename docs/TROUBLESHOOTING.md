# Troubleshooting

| Problem | What to check |
| --- | --- |
| Java not found | Select the Java major requested by the wizard: 17 for 1.18–1.20.4, 21 for 1.20.5–1.21.x, and 25 for 26.x. Forge requires the matching major. |
| Port is already in use | Stop the other server or choose another port. Include the changed port when joining. |
| Setup download failed | Check internet access and the service named in the progress message. Retry after it recovers. Existing server folders are not overwritten. |
| First start takes time | Fabric is downloading libraries and Minecraft is generating the world. Read Console for progress. |
| Start fails before Java launches | Check the Java path in `mcyard.json`, available RAM, and that its launcher JAR or Forge argument file exists. |
| Start is blocked by a backup failure | Read the error and `manager/data/backup-last.log`. Free disk space or inspect backups; the latest completed backup is protected. |
| Player controls are disabled | Live inventory/history require the Fabric 26.3 preset and a connected bridge. Use Console on other setups. Check missing/incompatible mods if the preset does not connect. |
| Mod cannot be disabled | Stop the server first. Core management/backup dependencies are protected. Rename conflicts are refused. |
| Settings are disabled | Stop the server first. Use World rules for supported changes that apply live. |
| Friends cannot join | Test `localhost` first, then LAN. For internet access check the router or tunnel, port and Minecraft version. |
| App reports an incomplete installation | Extract/copy the entire portable app folder. The EXE needs its supporting files. |
| App fails before the library opens | Check `%LOCALAPPDATA%\MCyard Server\startup-error.log`. Include its final error line when reporting a problem, after removing private paths. |
| Library entry is missing or invalid | Select the original folder with **Add existing folder**. It must contain `mcyard.json`, server settings and its launcher. |
| Existing server cannot be imported | Select the folder containing `server.properties`, an accepted `eula.txt`, and one supported launcher. Import currently requires `level-name=world`. Nothing is moved or replaced. |

Use Stop for normal shutdown. Closing the server-manager window while it owns a
running server asks to stop, save and back up before closing. Closing the library
does not replace that shutdown process.

Player history begins when the bridge records events. Saved inventories and
locations may be older than live data; the Players page displays its source and
timestamp. A death/spawn location that has never been recorded is shown as such.

When reporting a problem, provide the app version, Windows version, Java version
and relevant error lines. Redact player IP addresses, private paths, usernames,
chat and tokens. Do not upload an entire server folder or backup to an issue.
