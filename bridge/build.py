"""Compile original MCyard Server bridge sources against a locally installed server.

This never downloads or bundles Minecraft, Fabric API or third-party mods.
The server folder is a read-only source of compile-time dependencies.
"""
from pathlib import Path
import argparse
import os
import shutil
import subprocess
import tempfile
import zipfile


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--server-dir',type=Path,required=True,
                        help='A prepared Fabric 26.3 server with all bridge dependencies')
    parser.add_argument('--javac',default=shutil.which('javac') or 'javac')
    args=parser.parse_args()
    here=Path(__file__).resolve().parent
    server=args.server_dir.expanduser().resolve(strict=True)
    jars=sorted({p.resolve() for folder in ('libraries','.fabric/processedMods','versions','mods')
                 for p in (server/folder).rglob('*.jar')
                 if not p.name.startswith(('mcyard-bridge-','gang-manager-'))})
    if not jars:
        parser.error('No server dependency JARs found. Start the prepared server once first.')
    sources=sorted((here/'src').glob('*.java'))
    output=here.parent/'resources/mcyard-bridge-0.1.0.jar'
    output.parent.mkdir(parents=True,exist_ok=True)
    # A unique owned temporary directory prevents stale classes entering the JAR.
    with tempfile.TemporaryDirectory(prefix='mcyard-javac-') as temp:
        classes=Path(temp)/'classes';classes.mkdir()
        subprocess.run([args.javac,'--release','25','-encoding','UTF-8','-proc:none',
                        '-classpath',os.pathsep.join(map(str,jars)),'-d',str(classes),
                        *map(str,sources)],check=True)
        entries={p.relative_to(classes).as_posix():p.read_bytes() for p in classes.rglob('*.class')}
        for name in ('fabric.mod.json','mcyard.mixins.json'):
            entries[name]=(here/name).read_bytes()
        license_path=here.parent/'LICENSE'
        if license_path.exists():entries['LICENSE']=license_path.read_bytes()
        pending=output.with_suffix('.jar.tmp')
        try:
            with zipfile.ZipFile(pending,'w',compression=zipfile.ZIP_DEFLATED) as archive:
                for name,data in sorted(entries.items()):
                    info=zipfile.ZipInfo(name,(1980,1,1,0,0,0))
                    info.compress_type=zipfile.ZIP_DEFLATED
                    info.external_attr=0o644 << 16
                    archive.writestr(info,data)
            pending.replace(output)
        finally:
            if pending.exists():pending.unlink()
    print(output)


if __name__=='__main__':main()
