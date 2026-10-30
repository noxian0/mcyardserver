"""Shared policy: managed backups stay below 50 decimal GB, including staging."""
from pathlib import Path
import os

LIMIT = 50_000_000_000
HEADROOM = 64 * 1024 * 1024


def usage(root):
    return sum(p.stat().st_size for p in Path(root).rglob('*') if p.is_file() and not p.is_symlink())


def groups(root):
    root=Path(root).resolve()
    result=[]
    for p in root.rglob('*.zip'):
        if p.is_symlink() or not p.resolve().is_relative_to(root):continue
        if p.name=='full.zip' and 'world' in p.relative_to(root).parts:
            result.append((p.stat().st_mtime,p.parent))
        elif p.parent==root or p.parent==root/'full-server':
            result.append((p.stat().st_mtime,p))
    return sorted(result,key=lambda pair:pair[0])


def delete_group(root,target):
    root=Path(root).resolve();target=Path(target)
    if target.is_symlink() or target.resolve()==root or not target.resolve().is_relative_to(root):
        raise RuntimeError('Unsafe backup retention target')
    if target.is_dir():
        children=list(target.rglob('*'))
        # Validate every resolved path before any deletion; never traverse junctions.
        if any(p.is_symlink() or not p.resolve().is_relative_to(root) for p in children):
            raise RuntimeError('Backup chain contains a link outside the backup directory')
        for p in sorted(children,key=lambda p:len(p.parts),reverse=True):
            p.rmdir() if p.is_dir() else p.unlink()
        target.rmdir()
    else:target.unlink()


def reserve(root,needed,limit=LIMIT,headroom=HEADROOM):
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    available=limit-headroom
    if needed>available:raise RuntimeError('Backup cannot fit within the 50 GB total limit; existing backups preserved.')
    candidates=groups(root)
    # Never delete the newest completed backup to make an attempt at a new one.
    removable=candidates[:-1]
    amount=usage(root)
    reclaimable=sum(usage(p) if p.is_dir() else p.stat().st_size for _,p in removable)
    if amount-reclaimable+needed>available:
        raise RuntimeError('Not enough backup space within 50 GB while preserving the latest backup.')
    for _,p in removable:
        if amount+needed<=available:break
        print('Removing oldest backup to respect 50 GB limit:',p,flush=True)
        delete_group(root,p);amount=usage(root)
    return available-amount


class CappedFile:
    """Seekable ZIP output which refuses a write BEFORE it exceeds its allowance."""
    def __init__(self,path,allowance):
        self.file=open(path,'x+b');self.allowance=allowance
    def write(self,data):
        if self.file.tell()+len(data)>self.allowance:
            raise OSError('Backup stopped before exceeding the 50 GB total limit.')
        return self.file.write(data)
    def __getattr__(self,name):return getattr(self.file,name)
    def __enter__(self):return self
    def __exit__(self,*args):self.file.close()
