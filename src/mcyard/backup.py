"""Verified offline full snapshot for each supported server type."""
from datetime import datetime
from pathlib import Path
import msvcrt
import sys
import zipfile
import sqlite3
import tempfile
from contextlib import closing
from .backup_budget import reserve, CappedFile

ROOT = None
DEST = None
SNAPSHOT_FOLDERS = ('world','config','mods','maintenance','manager','libraries','versions')


def main(root):
    global ROOT, DEST
    ROOT=Path(root).resolve();DEST=ROOT/"backups"/"full-server"
    # Java locks session.lock while the world is open. Hold the same byte
    # range throughout the snapshot so a running world cannot be copied.
    world = ROOT / "world"
    if not (world / "level.dat").is_file():
        raise RuntimeError("Expected world/level.dat is missing; refusing an empty backup.")
    # Restored snapshots intentionally omit session.lock. Create it if needed,
    # then always lock the first byte rather than the append position.
    with (world / "session.lock").open("a+b") as lock:
        lock.seek(0)
        if not lock.read(1):lock.write(b'\0');lock.flush()
        lock.seek(0)
        try:
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            raise RuntimeError("Server is running. Stop it before taking a full snapshot, or use a supported live backup.")
        DEST.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        target = DEST / f"server-{stamp}.zip"
        partial = target.with_suffix(".partial")
        try:
            sources=[p for folder in SNAPSHOT_FOLDERS for p in (ROOT/folder).rglob('*') if p.is_file() and not p.is_symlink()]
            sources += [p for p in ROOT.iterdir() if p.is_file() and not p.is_symlink()]
            raw=sum(p.stat().st_size for p in sources)
            allowance=reserve(ROOT/'backups',int(raw*1.02)+len(sources)*2048+1024*1024)
            with CappedFile(partial,allowance) as output, zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED, compresslevel=3) as archive:
                for folder in SNAPSHOT_FOLDERS:
                    for path in sorted((ROOT / folder).rglob("*")):
                        if path.is_symlink() or "__pycache__" in path.parts or "classes" in path.parts:
                            continue
                        if path.name.endswith(('.sqlite-wal','.sqlite-shm','.tmp','.lock')) or path.parent.name in ('inbox','replies'):
                            continue
                        if path.is_file() and path.suffix=='.sqlite' and 'manager' in path.relative_to(ROOT).parts:
                            # The desktop may keep its history open while Java is stopped.
                            with tempfile.TemporaryDirectory(prefix='mcyard-history-backup-') as scratch:
                                snap=Path(scratch)/'history.sqlite'
                                with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as src, closing(sqlite3.connect(snap)) as dest:
                                    src.backup(dest)
                                archive.write(snap,path.relative_to(ROOT))
                        elif path.is_file() and path.name != "session.lock":
                            archive.write(path, path.relative_to(ROOT))
                for path in ROOT.iterdir():
                    if path.is_file() and not path.is_symlink():
                        archive.write(path, path.name)
            with zipfile.ZipFile(partial) as archive:
                bad = archive.testzip()
                if bad or "world/level.dat" not in archive.namelist():
                    raise RuntimeError(f"Backup verification failed: {bad}")
            partial.rename(target)
            # Rotate only our own completed snapshots inside the fixed folder.
            for old in sorted(DEST.glob("server-*.zip"), reverse=True)[14:]:
                if old.resolve().parent == DEST.resolve() and not old.is_symlink():
                    old.unlink()
            print(f"Verified full backup: {target}", flush=True)
        finally:
            if partial.exists():
                partial.unlink()
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)

