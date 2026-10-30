# Security and privacy

MCyard Server is a local desktop tool. Its management bridge uses files in the
server folder, not a public HTTP or RCON endpoint. Anyone who can write those
files with your Windows account's permissions can act with server-administrator
privileges. Run it under an account you control and restrict access to server
folders accordingly.

Server/player history may include usernames, UUIDs, IP addresses, inventory,
locations, commands and log text. It is stored locally under `manager/data` and
included in full backups. The app has no analytics upload. Setup contacts Mojang, Fabric, Forge and (for the management preset) Modrinth.
The Forge installer and Fabric launcher fetch dependencies from their publishers. Java/Minecraft and third-party mods have their own
network behavior.

When sharing a bug report, redact private paths, IP addresses, chat, tokens and
account information. Do not attach an entire server folder or backup.

For a suspected vulnerability, use the repository's private vulnerability-report
feature if the maintainer has enabled it. If no private channel is available,
open an issue asking for one without publishing exploit details or private data.

Only version 0.1.x is currently maintained. Updating downloaded mods outside the
tested preset can affect bridge compatibility and the backup guard; test changes
on a separate server first.
