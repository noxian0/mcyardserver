"""Attach existing server files to MCyard Server without moving or replacing them."""
from datetime import datetime,timezone
from pathlib import Path
import json
import os
import re
import uuid
import zipfile
from .catalog import required_java,supported_version
from .java_runtime import detect_java,validate_java
from .mods import list_mods
from .registry import register_server,read_server


def _local_file(root,path):
    if not path.is_file() or not path.resolve().is_relative_to(root):raise ValueError('A required server file is missing or outside the server folder.')
    for item in (path,*path.parents):
        if item==root:break
        if item.is_symlink() or (hasattr(item,'is_junction') and item.is_junction()):raise ValueError('Linked server configuration or launch files cannot be imported.')
    return path


def _text(path,limit=262144):
    if path.stat().st_size>limit:raise ValueError('A server configuration file is unexpectedly large.')
    return path.read_text(encoding='utf-8-sig',errors='replace')


def _properties(path):
    values={}
    for line in _text(path).splitlines():
        line=line.strip()
        if not line or line.startswith(('#','!')):continue
        key,separator,value=line.partition('=')
        if separator:values[key.strip()]=value.strip()
    return values


def _memory(value):
    match=re.fullmatch(r'(\d+)([GgMm])',value)
    return int(match[1])*(1024 if match[2].lower()=='g' else 1) if match else None


def _runtime_hints(root):
    hints={'memory_mb':4096,'initial_memory_mb':1024}
    script=root/'start-server.bat'
    if script.is_file() and not script.is_symlink():
        text=_text(_local_file(root,script))
        for flag,key in (('Xmx','memory_mb'),('Xms','initial_memory_mb')):
            values=re.findall(r'-'+flag+r'(\d+[GgMm])\b',text)
            if len(set(values))==1:
                value=_memory(values[0])
                if value is not None:hints[key]=value
        zones=re.findall(r'-Duser\.timezone=([A-Za-z0-9_+\-/]+)',text)
        if len(set(zones))==1:hints['timezone']=zones[0]
    if not 2048<=hints['memory_mb']<=32768:raise ValueError('This server uses a RAM limit outside the supported 2–32 GB range.')
    hints['initial_memory_mb']=min(hints['memory_mb'],max(256,hints['initial_memory_mb']))
    return hints


def _launcher(root):
    found=[]
    for path in root.glob('fabric-server-*.jar'):
        match=re.fullmatch(r'fabric-server-mc\.(\d+(?:\.\d+){1,3})-loader\.(\d+(?:\.\d+){1,3})-launcher\.(\d+(?:\.\d+){1,3})\.jar',path.name)
        if match:
            _local_file(root,path);found.append(('fabric',match[1],match[2],{'kind':'jar','target':path.name}))
    for path in (root/'libraries/net/minecraftforge/forge').glob('*/win_args.txt'):
        match=re.fullmatch(r'(\d+(?:\.\d+){1,3})-(\d+(?:\.\d+){1,3})',path.parent.name)
        if match:
            _local_file(root,path);found.append(('forge',match[1],match[2],{'kind':'args','target':path.relative_to(root).as_posix()}))
    if len(found)>1:raise ValueError('More than one server launcher was found. Keep one active Fabric or Forge installation in this folder before importing.')
    if found:return found[0]
    for path in root.glob('*.jar'):
        if path.name!='server.jar' and not re.fullmatch(r'minecraft_server[.\-].+\.jar',path.name):continue
        _local_file(root,path)
        try:
            with zipfile.ZipFile(path) as jar:
                info=jar.getinfo('version.json')
                if info.file_size>65536:raise ValueError('Oversized server version metadata')
                version=json.loads(jar.read(info))['id']
                manifest=jar.read('META-INF/MANIFEST.MF').decode('utf-8',errors='replace')
                if not re.search(r'Main-Class:\s*net\.minecraft\.(?:bundler|server)\.Main',manifest):continue
            if supported_version(version):found.append(('vanilla',version,'',{'kind':'jar','target':path.name}))
        except (OSError,KeyError,ValueError,zipfile.BadZipFile):continue
    if len(found)!=1:raise ValueError('Could not identify one supported server launcher. Import a Fabric launcher, installed Forge server, or official Vanilla server.jar for Minecraft 1.18 or newer.')
    return found[0]


def inspect_existing(path):
    """Read a preview only. Does not create files or start/download anything."""
    folder=Path(path).expanduser().resolve()
    if not folder.is_dir():raise ValueError('Choose an existing server folder.')
    if (folder/'mcyard.json').exists():return read_server(folder)
    settings=_properties(_local_file(folder,folder/'server.properties'))
    eula=_properties(_local_file(folder,folder/'eula.txt'))
    if eula.get('eula','').lower()!='true':raise ValueError('This server has not accepted the Minecraft EULA. Review it and complete the existing server setup before importing.')
    if settings.get('level-name','world')!='world':raise ValueError('Import currently requires level-name=world so snapshots include the correct world. The folder was left unchanged.')
    try:port=int(settings.get('server-port','25565'))
    except ValueError:raise ValueError('The existing server port is invalid.')
    if not 1024<=port<=65535:raise ValueError('This server port is outside the supported range 1024–65535.')
    software,version,loader,launch=_launcher(folder)
    if not supported_version(version):raise ValueError('Import supports released Minecraft versions from 1.18 onward.')
    mods=list_mods(folder,{'capabilities':{'bridge':False}})
    if any(m['unsafe'] for m in mods):raise ValueError('Linked mods cannot be imported. Keep mod files inside the server folder.')
    active={identifier for mod in mods if mod['enabled'] for identifier in mod['ids']}
    bridges=active.intersection({'gang_manager','mcyard_bridge'})
    if len(bridges)>1:raise ValueError('Both legacy and current management bridges are enabled. Keep one bridge before importing.')
    bridge=software=='fabric' and version=='26.3' and bool(bridges) and {'fabric-api','simplebackups','forgeconfigapiport'}.issubset(active)
    name=settings.get('motd') or folder.name
    name=re.sub(r'\\u([0-9a-fA-F]{4})',lambda m:chr(int(m[1],16)),name)
    name=re.sub(r'§.','',name).replace('\\n',' ').strip()
    name=''.join(c for c in name if ord(c)>=32)[:60] or folder.name[:60]
    return {'name':name,'path':str(folder),'server_type':software,'mc_version':version,'loader_version':loader,
        'java_required':required_java(version),'java_exact':software=='forge','port':port,
        'launcher':launch['target'],'launch':launch,'capabilities':{'bridge':bridge,'live_backups':bridge},
        'mods':[{'name':m['name'],'version':m['version'],'filename':m['filename'],'ids':m['ids'],'enabled':m['enabled']} for m in mods],
        **_runtime_hints(folder)}


def import_server(path,name=None,java_path='',memory_mb=None):
    """Add only mcyard.json and a library entry; preserve all existing server files."""
    folder=Path(path).expanduser().resolve()
    if (folder/'mcyard.json').exists():return register_server(folder)
    preview=inspect_existing(folder)
    name=preview['name'] if name is None else str(name).strip()
    if not name or len(name)>60 or any(ord(c)<32 for c in name):raise ValueError('Use a server name from 1 to 60 characters without line breaks.')
    memory=preview['memory_mb'] if memory_mb is None else memory_mb
    if type(memory) is not int or not 2048<=memory<=32768:raise ValueError('Choose between 2048 and 32768 MB of RAM.')
    required=preview['java_required'];exact=preview['java_exact']
    if not java_path:
        choices=detect_java(required=required,exact=exact)
        if not choices:raise ValueError(f'Choose an installed Java {required} executable.')
        java_path=choices[0]['path']
    java=validate_java(java_path,required=required,exact=exact)
    metadata={key:value for key,value in preview.items() if key!='path'}
    metadata.update(schema_version=1,name=name,memory_mb=memory,java_path=java['path'],backup_limit_bytes=50_000_000_000,
        imported_at=datetime.now(timezone.utc).isoformat(),eula_source='existing eula.txt')
    metadata['initial_memory_mb']=min(memory,metadata['initial_memory_mb'])
    target=folder/'mcyard.json';temporary=folder/('.mcyard-import-'+uuid.uuid4().hex+'.tmp')
    try:
        with temporary.open('x',encoding='utf-8') as stream:json.dump(metadata,stream,indent=2,ensure_ascii=False)
        # Creating a hard link publishes the complete file atomically and refuses
        # to overwrite metadata another window may have created meanwhile.
        os.link(temporary,target)
    finally:
        if temporary.exists():temporary.unlink()
    try:return register_server(folder)
    except Exception as exc:raise RuntimeError('Import metadata was saved, but the library could not be updated. Add this folder again. '+str(exc)) from exc
