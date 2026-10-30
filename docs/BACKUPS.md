# Backups and restoring a world

Each server has its own **50,000,000,000-byte (50 GB) managed-backup limit**.
This includes full snapshots, live world archives and temporary backup copies.

| Backup | When | Includes |
| --- | --- | --- |
| Full snapshot | Before a normal start, after a clean stop, or manually while stopped | World, mods, configuration, libraries, local manager history and root server files |
| Live world backup | Fabric 26.3 preset: daily while active, or manually while running | Saved world data through Simple Backups |

The first start has no existing world to snapshot. Library/version
files are included so Forge launch arguments and installed dependencies restore
together. The live preset excludes regenerable
SQLite caches; full snapshots include them while the world is stopped.

Oldest completed archives/chains are removed when space is needed. The newest
completed backup is kept. If there is not enough room to attempt a backup while
keeping it, the new backup is refused. Writes are also capped during creation,
and a safety margin is reserved for small metadata files. Up to 14 full snapshots
and 14 live chains are retained within the shared limit.

The limit controls the app's backup workflow; it is not a Windows disk quota for
arbitrary files you copy into the folder. For the enhanced Fabric preset, keep Simple Backups in its supplied ZIP
and full-backup configuration and keep MCyard Server Bridge installed. Other
server types use verified offline snapshots and do not offer live world backups.

## Restore

1. Stop the server and close its manager. Keep the current world and configuration
   in a separate recovery folder before changing anything.
2. Extract the chosen ZIP into an empty folder. Check its contents before using it.
3. For a live world archive, locate the folder containing `level.dat` and use that
   as the replacement `world` folder. Do not overlay it onto a newer world.
4. For a full snapshot, restore its world, configuration and matching mod set
   together. Do not combine arbitrary versions. Keep or adjust `mcyard.json`
   if the server moved or Java was installed at a different path.
5. Open the restored server from the library, start it and check the world before
   inviting friends back.

There is no automatic restore button in this release. A backup stored on the same
disk cannot protect against that disk failing. Copy important verified archives
to another drive as well.
