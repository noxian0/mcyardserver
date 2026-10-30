"""Find private local game artwork, with an original distributable fallback."""
from functools import lru_cache
from pathlib import Path
import hashlib
import json
import os
import struct
import uuid

from .paths import app_data,resource_path


def minecraft_directory():
    configured=os.environ.get('MCYARD_MINECRAFT_HOME')
    return Path(configured).expanduser() if configured else Path(os.environ.get('APPDATA',str(Path.home()/'AppData/Roaming')))/'.minecraft'


def import_local_panorama(destination,minecraft):
    """Copy verified artwork from an installed game; never download game assets."""
    destination=Path(destination);minecraft=Path(minecraft)
    if destination.is_file():return destination
    indexes=minecraft/'assets/indexes';candidates=[]
    try:
        version=json.loads((minecraft/'versions/1.21.5/1.21.5.json').read_text(encoding='utf-8'))
        index_id=version['assetIndex']['id']
        if isinstance(index_id,str) and index_id.replace('-','').replace('.','').isalnum():candidates.append(indexes/(index_id+'.json'))
    except (OSError,ValueError,KeyError,TypeError):pass
    try:candidates.extend(sorted(indexes.glob('*.json'),key=lambda p:p.stat().st_mtime,reverse=True)[:12])
    except OSError:return None
    for index in dict.fromkeys(candidates):
        try:
            if index.stat().st_size>32*1024*1024:continue
            entries=json.loads(index.read_text(encoding='utf-8')).get('objects',{})
            if not isinstance(entries,dict):continue
        except (OSError,ValueError,AttributeError):continue
        for face in (3,0,2,1):
            key=f'minecraft/textures/gui/title/background/panorama_{face}.png'
            entry=entries.get(key,{})
            digest=entry.get('hash','') if isinstance(entry,dict) else ''
            if not isinstance(digest,str) or len(digest)!=40 or any(c not in '0123456789abcdef' for c in digest):continue
            source=minecraft/'assets/objects'/digest[:2]/digest
            try:
                if not 10000<=source.stat().st_size<=12*1024*1024:continue
                data=source.read_bytes()
                if not data.startswith(b'\x89PNG\r\n\x1a\n') or data[12:16]!=b'IHDR' or hashlib.sha1(data).hexdigest()!=digest:continue
                width,height=struct.unpack('>II',data[16:24])
                if not (1<=width<=8192 and 1<=height<=8192 and width*height<=32*1024*1024):continue
                destination.parent.mkdir(parents=True,exist_ok=True)
                temporary=destination.with_name('.panorama-'+uuid.uuid4().hex+'.tmp')
                try:
                    temporary.write_bytes(data)
                    # Atomic and exclusive: a custom picture appearing during import wins.
                    os.link(temporary,destination)
                except FileExistsError:return destination
                finally:
                    if temporary.exists():temporary.unlink()
                provenance={'origin':'Local Minecraft Java installation','asset_index':index.name,'asset_key':key,'sha1':digest,
                    'distribution':'Private local artwork; excluded from source and release packages.'}
                destination.with_name('background-origin.json').write_text(json.dumps(provenance,indent=2)+'\n',encoding='utf-8')
                return destination
            except (OSError,ValueError,struct.error):continue
    return None


@lru_cache(maxsize=8)
def _shared_background(data_directory,game_directory):
    target=Path(data_directory)/'background.png'
    return import_local_panorama(target,Path(game_directory)) or resource_path('landscape.svg')


def background_path(server_root=None):
    configured=os.environ.get('MCYARD_BACKGROUND_IMAGE')
    if configured and Path(configured).is_file():return Path(configured)
    server_root=server_root or os.environ.get('MCYARD_SERVER_ROOT')
    if server_root:
        local=Path(server_root)/'manager/assets/panorama.png'
        if local.is_file():return local
    data=app_data()
    if (data/'background.png').is_file():return data/'background.png'
    return _shared_background(str(data),str(minecraft_directory()))
