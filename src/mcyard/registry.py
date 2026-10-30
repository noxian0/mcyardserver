"""A small per-user catalog; removing a catalog entry never deletes a server."""
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
import json
import os
import time
import uuid
from .paths import app_data
from .catalog import supported_version,required_java,valid_version,SERVER_TYPES


def _catalog():return app_data()/'servers.json'


@contextmanager
def _locked():
    path=app_data()/'servers.lock';path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('a+b') as stream:
        stream.seek(0,2)
        if stream.tell()==0:stream.write(b'0');stream.flush()
        until=time.monotonic()+5
        while True:
            try:
                stream.seek(0)
                if os.name=='nt':
                    import msvcrt
                    msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
                else:
                    import fcntl
                    fcntl.flock(stream.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic()>until:raise RuntimeError('Another MCyard Server window is updating the server list. Try again.')
                time.sleep(.05)
        try:yield
        finally:
            stream.seek(0)
            if os.name=='nt':msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)
            else:fcntl.flock(stream.fileno(),fcntl.LOCK_UN)


def _read():
    path=_catalog()
    if not path.exists():return []
    try:
        data=json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(data,list) or any(not isinstance(x,dict) or not isinstance(x.get('path'),str) or not x['path'] for x in data):raise ValueError()
        return data
    except (OSError,ValueError) as exc:
        raise RuntimeError('The MCyard Server catalog could not be read. Your server folders are unchanged. Catalog: '+str(path)) from exc


def _write(data):
    path=_catalog();path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        temporary.write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding='utf-8')
        temporary.replace(path)
    finally:
        if temporary.exists():temporary.unlink()


def _key(path):return os.path.normcase(str(Path(path).expanduser().resolve()))


def server_metadata(path):
    """Read an existing MCyard Server without changing files or its world."""
    folder=Path(path).expanduser().resolve()
    try:metadata=json.loads((folder/'mcyard.json').read_text(encoding='utf-8'))
    except (OSError,ValueError) as exc:
        raise ValueError('Choose a server folder created by MCyard Server (containing mcyard.json).') from exc
    required=('name','mc_version','loader_version','java_path','memory_mb','port','launcher')
    if not isinstance(metadata,dict) or any(k not in metadata for k in required):
        raise ValueError('This mcyard.json is incomplete or unsupported.')
    if metadata.get('schema_version')!=1 or not supported_version(metadata['mc_version']):
        raise ValueError('This MCyard Server metadata version or Minecraft release is unsupported.')
    server_type=metadata.get('server_type','fabric')
    if server_type not in SERVER_TYPES:raise ValueError('The server type must be Vanilla, Fabric or Forge.')
    if not isinstance(metadata['loader_version'],str) or (server_type!='vanilla' and not valid_version(metadata['loader_version'])):
        raise ValueError('This server has an invalid loader version.')
    java_required=metadata.get('java_required',required_java(metadata['mc_version']))
    if isinstance(java_required,bool) or not isinstance(java_required,int) or not 17<=java_required<=99:
        raise ValueError('This server has an invalid Java requirement.')
    if 'capabilities' in metadata and (not isinstance(metadata['capabilities'],dict) or any(type(metadata['capabilities'].get(key)) is not bool for key in ('bridge','live_backups'))):
        raise ValueError('This server has invalid manager capabilities.')
    if not isinstance(metadata['name'],str) or not metadata['name'].strip() or len(metadata['name'])>60:
        raise ValueError('This server has an invalid name in mcyard.json.')
    if not isinstance(metadata['java_path'],str) or not metadata['java_path'].strip():
        raise ValueError('This server has no Java executable configured.')
    for key,low,high in [('memory_mb',2048,32768),('port',1024,65535)]:
        value=metadata[key]
        if isinstance(value,bool) or not isinstance(value,int) or not low<=value<=high:
            raise ValueError('This server has an invalid '+key+' in mcyard.json.')
    launch=metadata.get('launch',{'kind':'jar','target':metadata['launcher']})
    if not isinstance(launch,dict) or launch.get('kind') not in ('jar','args') or not isinstance(launch.get('target'),str):
        raise ValueError('This server has invalid launch settings.')
    target=launch['target'];relative=PurePosixPath(target)
    if not target or '\\' in target or ':' in target or relative.is_absolute() or '..' in relative.parts or any(ord(c)<32 for c in target):
        raise ValueError('The server launcher path is unsafe.')
    if launch['kind']=='jar':
        safe=len(relative.parts)==1 and relative.suffix.lower()=='.jar'
    else:
        expected=PurePosixPath('libraries/net/minecraftforge/forge')/(metadata['mc_version']+'-'+metadata['loader_version'])/'win_args.txt'
        safe=server_type=='forge' and relative==expected
    launcher=folder/Path(relative)
    if not safe or not launcher.is_file() or not launcher.resolve().is_relative_to(folder):
        raise ValueError('The server launcher listed in mcyard.json is missing or unsafe.')
    if metadata['launcher']!=target:raise ValueError('The server launcher fields disagree.')
    if not (folder/'server.properties').is_file():raise ValueError('This folder is missing server.properties.')
    enhanced=server_type=='fabric' and metadata['mc_version']=='26.3'
    return {**metadata,'server_type':server_type,'java_required':java_required,'java_exact':server_type=='forge',
        'launch':launch,'capabilities':metadata.get('capabilities',{'bridge':enhanced,'live_backups':enhanced}),'path':str(folder)}


def read_server(path):
    """Public validator used before launching a manager or backup worker."""
    return server_metadata(path)


def list_servers():
    with _locked():entries=_read()
    results=[]
    for entry in entries:
        entry=dict(entry);folder=Path(entry['path'])
        entry['missing']=not folder.is_dir()
        if not entry['missing']:
            try:entry.update(server_metadata(folder))
            except ValueError:entry['invalid']=True
        results.append(entry)
    return sorted(results,key=lambda item:item.get('name','').casefold())


def register_server(path):
    entry=server_metadata(path)
    with _locked():
        entries=[item for item in _read() if _key(item['path'])!=_key(entry['path'])]
        entries.append(entry);_write(entries)
    return entry


def forget_server(path):
    with _locked():_write([item for item in _read() if _key(item['path'])!=_key(path)])
