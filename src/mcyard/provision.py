"""Install a Vanilla, Fabric or Forge server in its own new directory."""
from dataclasses import dataclass, replace
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile
from .java_runtime import detect_java, validate_java
from .paths import app_data, resource_path
from .registry import register_server
from . import catalog

MINECRAFT_VERSION='26.3'
LOADER_VERSION='0.20.1'
INSTALLER_VERSION='1.1.2'
USER_AGENT='MCyard-Server/0.1.0 (Windows desktop Minecraft server manager)'
MODS=(('Fabric API','EQKgpeKu'),('Forge Config API Port','JpKvrr9J'),
      ('Simple Backups','w34As43e'),('Lithium','xS0Q8LSi'))
MOD_VERSIONS={'EQKgpeKu':'0.165.0+26.3','JpKvrr9J':'26.3.1',
              'w34As43e':'26.3.0','xS0Q8LSi':'mc26.3-0.26.2-fabric'}
ALLOWED_HOSTS={'meta.fabricmc.net','maven.fabricmc.net','api.modrinth.com','cdn.modrinth.com',
    'piston-meta.mojang.com','piston-data.mojang.com','launcher.mojang.com','launchermeta.mojang.com',
    'maven.minecraftforge.net','files.minecraftforge.net'}


class CreationCancelled(RuntimeError):pass


@dataclass(frozen=True)
class CreateOptions:
    name:str
    parent:Path
    port:int=25565
    memory_mb:int=4096
    java_path:str=''
    eula_accepted:bool=False
    lithium:bool=True
    server_type:str='fabric'
    mc_version:str=MINECRAFT_VERSION
    loader_version:str=''


def recommended_folder_name(name):
    ascii_name=unicodedata.normalize('NFKD',str(name)).encode('ascii','ignore').decode()
    slug=re.sub(r'[^a-zA-Z0-9_-]+','-',ascii_name).strip('-_').lower()[:48].rstrip('-_') or 'minecraft-server'
    if re.fullmatch(r'(?i)(con|prn|aux|nul|com[1-9]|lpt[1-9])',slug):slug='server-'+slug
    return slug


def _cancel(cancel_event):
    if cancel_event is not None and cancel_event.is_set():raise CreationCancelled('Server creation cancelled. No server was added.')


def validate_options(options):
    if not isinstance(options,CreateOptions):raise ValueError('Invalid server creation options.')
    name=options.name.strip()
    if not name or len(name)>60 or any(ord(c)<32 for c in name):raise ValueError('Use a server name from 1 to 60 characters, without line breaks.')
    if options.eula_accepted is not True:raise ValueError('Read and accept the Minecraft EULA before creating a server.')
    if isinstance(options.port,bool) or not isinstance(options.port,int) or not 1024<=options.port<=65535:raise ValueError('Choose a server port from 1024 to 65535.')
    if isinstance(options.memory_mb,bool) or not isinstance(options.memory_mb,int) or not 2048<=options.memory_mb<=32768:raise ValueError('Choose between 2 GB and 32 GB of memory.')
    if options.server_type not in catalog.SERVER_TYPES:raise ValueError('Choose Vanilla, Fabric or Forge.')
    required=catalog.required_java(options.mc_version)
    if options.loader_version and not catalog.valid_version(options.loader_version):raise ValueError('Invalid loader version.')
    if options.server_type=='vanilla' and options.loader_version:raise ValueError('Vanilla does not use a mod loader.')
    parent=Path(options.parent).expanduser().resolve()
    if parent.exists() and not parent.is_dir():raise ValueError('The server location must be a folder.')
    app_folder=Path(sys.executable).resolve().parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parents[2]
    if parent.is_relative_to(app_folder):raise ValueError('Keep server folders outside the MCyard Server app/source folder. Choose a separate location.')
    target=parent/recommended_folder_name(name)
    if target.exists():raise ValueError(f'That folder already exists: {target}. Choose another name or parent folder.')
    java_path=options.java_path
    if not java_path:
        installed=detect_java(required=required,exact=options.server_type=='forge')
        if not installed:raise ValueError(f'Java {required} was not found. Install Java {required}, then choose its java.exe.')
        java_path=installed[0]['path']
    java=validate_java(java_path,required=required,exact=options.server_type=='forge')
    # This is advisory validation only; Start must still handle a later conflict.
    with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as sock:
        try:sock.bind(('127.0.0.1',options.port))
        except OSError as exc:raise ValueError(f'Port {options.port} is already in use. Choose another port.') from exc
    return replace(options,name=name,parent=parent,java_path=java['path'])


def _safe_url(url):
    parsed=urllib.parse.urlsplit(url)
    if parsed.scheme!='https' or parsed.hostname not in ALLOWED_HOSTS or parsed.username or parsed.password or parsed.port not in (None,443):
        raise RuntimeError('The download service returned an unexpected URL.')
    return url


def _open(url):
    request=urllib.request.Request(_safe_url(url),headers={'User-Agent':USER_AGENT})
    class CheckedRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,request,fp,code,msg,headers,newurl):
            _safe_url(newurl)
            return super().redirect_request(request,fp,code,msg,headers,newurl)
    response=urllib.request.build_opener(CheckedRedirect()).open(request,timeout=30)
    try:_safe_url(response.url)
    except Exception:response.close();raise
    return response


def _json(url,cancel_event=None):
    _cancel(cancel_event)
    with _open(url) as response:
        raw=response.read(8*1024*1024+1)
    _cancel(cancel_event)
    if len(raw)>8*1024*1024:raise RuntimeError('The download service returned too much metadata.')
    return json.loads(raw)


def _verify_jar(path):
    try:
        with zipfile.ZipFile(path) as archive:
            if len(archive.infolist())>50000 or sum(info.file_size for info in archive.infolist())>512*1024*1024:
                raise ValueError('Archive expands beyond its safety limit')
            if not archive.namelist() or archive.testzip():raise ValueError('Damaged archive')
    except (OSError,ValueError,zipfile.BadZipFile) as exc:
        raise RuntimeError('A downloaded JAR is damaged. Try creating the server again.') from exc


def _download(url,target,hashes=None,expected_size=None,cancel_event=None):
    """Verified caching for pinned mods; every transfer lands in a unique temp file."""
    _safe_url(url);_cancel(cancel_event);hashes=hashes or {}
    algorithm=next((key for key in ('sha512','sha256','sha1') if key in hashes),None)
    expected=hashes.get(algorithm,'').lower() if algorithm else None
    if algorithm and not re.fullmatch('[0-9a-f]{'+str(hashlib.new(algorithm).digest_size*2)+'}',expected):
        raise RuntimeError('The service returned an invalid file checksum.')
    cache=app_data()/'downloads';cache.mkdir(parents=True,exist_ok=True)
    key=expected if expected else hashlib.sha256(url.encode()).hexdigest()
    cached=cache/(key+'.jar')
    if algorithm and cached.is_file():
        with cached.open('rb') as stream:valid=hashlib.file_digest(stream,algorithm).hexdigest()==expected
        if valid and (expected_size is None or cached.stat().st_size==expected_size):
            _cancel(cancel_event);shutil.copyfile(cached,target);return
    temporary=cache/(key+'.'+uuid.uuid4().hex+'.partial')
    try:
        total=0;hasher=hashlib.new(algorithm or 'sha256')
        with _open(url) as response,temporary.open('xb') as output:
            while True:
                _cancel(cancel_event);block=response.read(256*1024)
                if not block:break
                total+=len(block)
                if total>256*1024*1024:raise RuntimeError('The requested server component exceeds its size limit.')
                output.write(block);hasher.update(block)
        if expected_size is not None and total!=expected_size:raise RuntimeError('A download was incomplete; expected size did not match.')
        if expected and hasher.hexdigest()!=expected:raise RuntimeError('A download failed checksum verification. Nothing was installed.')
        _verify_jar(temporary);_cancel(cancel_event)
        temporary.replace(cached);shutil.copyfile(cached,target)
    finally:
        if temporary.exists():temporary.unlink()


def _property(value):
    result=[]
    for c in str(value):
        if c=='\\':result.append('\\\\')
        elif ord(c)>127:
            raw=c.encode('utf-16-be')
            result.extend('\\u'+raw[i:i+2].hex() for i in range(0,len(raw),2))
        else:result.append(c)
    return ''.join(result)


def _remove_staging(stage,parent):
    """Check every path before removing only our fresh staging directory."""
    parent=parent.resolve();stage=Path(stage)
    if stage.is_symlink() or stage.resolve().parent!=parent or not stage.name.startswith('.mcyard-create-'):
        raise RuntimeError('Refusing to remove an unexpected staging path: '+str(stage))
    children=list(stage.rglob('*'))
    if any(p.is_symlink() or not p.resolve().is_relative_to(stage.resolve()) for p in children):
        raise RuntimeError('A staging link changed; leaving that folder for manual inspection.')
    for p in sorted(children,key=lambda p:len(p.parts),reverse=True):
        p.rmdir() if p.is_dir() else p.unlink()
    stage.rmdir()


def _install_management_mods(options,stage,progress,cancel_event):
    bridge=resource_path('mcyard-bridge-0.1.0.jar');config=resource_path('simplebackups-common.toml')
    if not bridge.is_file() or not config.is_file():raise RuntimeError('MCyard Server resources are incomplete. Download the complete app folder or rebuild the app.')
    installed=[]
    for title,version_id in MODS:
        if title=='Lithium' and not options.lithium:continue
        _cancel(cancel_event);progress('Downloading '+title+'…')
        info=_json('https://api.modrinth.com/v2/version/'+version_id,cancel_event)
        if options.mc_version not in info.get('game_versions',[]) or 'fabric' not in info.get('loaders',[]) or info.get('version_number')!=MOD_VERSIONS[version_id]:raise RuntimeError(title+' metadata no longer matches this server version.')
        files=info.get('files',[]);file=next((f for f in files if f.get('primary')),files[0] if files else None)
        if not file:raise RuntimeError(title+' does not offer a downloadable file.')
        name=file['filename']
        if Path(name).name!=name or not name.endswith('.jar') or any(c in name for c in '\\/:'):raise RuntimeError('A mod supplied an invalid filename.')
        if not any(key in file.get('hashes',{}) for key in ('sha512','sha256','sha1')):
            raise RuntimeError(title+' did not supply a file checksum; nothing was installed.')
        _download(file['url'],stage/'mods'/name,file['hashes'],file.get('size'),cancel_event)
        installed.append({'name':title,'version':info['version_number'],'version_id':version_id,'filename':name,'source':file['url'],'sha512':file['hashes'].get('sha512')})
    _cancel(cancel_event)
    shutil.copyfile(bridge,stage/'mods'/bridge.name)
    (stage/'config/simplebackups').mkdir(parents=True,exist_ok=True)
    shutil.copyfile(config,stage/'config/simplebackups/common.toml')
    return installed


def _stop_installer(process):
    if process.poll() is not None:return
    if os.name=='nt':
        subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True,
            creationflags=subprocess.CREATE_NO_WINDOW,timeout=20,check=False)
    else:
        import signal
        os.killpg(process.pid,signal.SIGTERM)
    try:process.wait(timeout=10)
    except subprocess.TimeoutExpired:process.kill();process.wait(timeout=10)


def _run_forge_installer(java,installer,stage,progress,cancel_event=None):
    """Run the official installer directly; never execute its generated scripts."""
    _cancel(cancel_event)
    log_path=stage/'manager/data/install.log'
    progress('Installing Forge and its libraries. This can take several minutes…')
    with log_path.open('wb') as log:
        process=subprocess.Popen([java,'-jar',str(installer),'--installServer',str(stage)],
            cwd=stage,stdout=log,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0,
            start_new_session=os.name!='nt')
        deadline=time.monotonic()+900
        try:
            while process.poll() is None:
                _cancel(cancel_event)
                if time.monotonic()>deadline:raise RuntimeError('Forge installation timed out after 15 minutes. Check the internet connection and retry.')
                time.sleep(.15)
            _cancel(cancel_event)
            if process.returncode:
                log.flush()
                with log_path.open('rb') as source:
                    source.seek(max(0,log_path.stat().st_size-4000));detail=source.read().decode('utf-8',errors='replace')
                raise RuntimeError('Forge could not be installed. Its installer reported:\n'+detail)
        finally:
            if process.poll() is None:_stop_installer(process)


def _install_launcher(options,details,stage,progress,cancel_event):
    if options.server_type=='vanilla':
        progress('Downloading the official Minecraft server…')
        server=details['downloads']['server']
        _download(server['url'],stage/'server.jar',{'sha1':server['sha1']},server.get('size'),cancel_event)
        return {'kind':'jar','target':'server.jar'},''
    versions=catalog.list_loader_versions(options.server_type,options.mc_version,cancel_event)
    loader=options.loader_version or (versions[0] if versions else '')
    if not loader or loader not in versions:raise ValueError('That loader version is not available for the selected Minecraft release. Refresh the version list.')
    if options.server_type=='fabric':
        progress('Downloading Fabric server launcher…')
        launcher=f'fabric-server-mc.{options.mc_version}-loader.{loader}-launcher.{INSTALLER_VERSION}.jar'
        url=f'https://meta.fabricmc.net/v2/versions/loader/{options.mc_version}/{loader}/{INSTALLER_VERSION}/server/jar'
        _download(url,stage/launcher,cancel_event=cancel_event)
        return {'kind':'jar','target':launcher},loader
    progress('Downloading the official Forge installer…')
    coordinate=options.mc_version+'-'+loader
    url=f'https://maven.minecraftforge.net/net/minecraftforge/forge/{coordinate}/forge-{coordinate}-installer.jar'
    _cancel(cancel_event)
    with _open(url+'.sha1') as response:checksum=response.read(1024).decode('ascii').strip()
    if not re.fullmatch('[0-9a-fA-F]{40}',checksum):raise RuntimeError('Forge did not return a valid installer checksum.')
    installer=stage/('forge-'+coordinate+'-installer.jar')
    _download(url,installer,{'sha1':checksum},cancel_event=cancel_event)
    _run_forge_installer(options.java_path,installer,stage,progress,cancel_event)
    args=stage/'libraries/net/minecraftforge/forge'/coordinate/'win_args.txt'
    if not args.is_file():raise RuntimeError('The Forge installer did not create its server launch arguments. This Forge build is not supported.')
    return {'kind':'args','target':args.relative_to(stage).as_posix()},loader


def create_server(options,progress=lambda text:None,cancel_event=None):
    """Create, then register a fresh managed server. Does not start Minecraft."""
    progress('Checking Java and folder…');options=validate_options(options);_cancel(cancel_event)
    progress('Checking the selected Minecraft release…')
    details=catalog.version_details(options.mc_version,cancel_event)
    required=details.get('javaVersion',{}).get('majorVersion',catalog.required_java(options.mc_version))
    validate_java(options.java_path,required=required,exact=options.server_type=='forge')
    target=options.parent/recommended_folder_name(options.name)
    options.parent.mkdir(parents=True,exist_ok=True)
    stage=options.parent/('.mcyard-create-'+uuid.uuid4().hex);stage.mkdir()
    committed=False
    try:
        for name in ('mods','config','manager/data','backups/full-server'):(stage/name).mkdir(parents=True,exist_ok=True)
        launch,loader=_install_launcher(options,details,stage,progress,cancel_event)
        enhanced=options.server_type=='fabric' and options.mc_version==MINECRAFT_VERSION
        installed=_install_management_mods(options,stage,progress,cancel_event) if enhanced else []
        _cancel(cancel_event);progress('Configuring world, backups and management…')
        # This file is written only after the unchecked-by-default wizard consent.
        (stage/'eula.txt').write_text('# Accepted in MCyard Server setup. https://www.minecraft.net/eula\neula=true\n',encoding='ascii')
        settings={'server-ip':'','server-port':options.port,'motd':options.name,'online-mode':'true','enforce-secure-profile':'true',
            'max-players':10,'level-name':'world','gamemode':'survival','difficulty':'normal','hardcore':'false',
            'white-list':'false','allow-flight':'false','enable-command-block':'false','enable-rcon':'false','enable-query':'false',
            'spawn-protection':16,'view-distance':10,'simulation-distance':6,'pause-when-empty-seconds':60}
        (stage/'server.properties').write_text('\n'.join(k+'='+_property(v) for k,v in settings.items())+'\n',encoding='ascii')
        metadata={'schema_version':1,'name':options.name,'server_type':options.server_type,'mc_version':options.mc_version,
            'loader_version':loader,'java_path':options.java_path,'java_required':required,'java_exact':options.server_type=='forge',
            'memory_mb':options.memory_mb,'port':options.port,'launcher':launch['target'],'launch':launch,
            'capabilities':{'bridge':enhanced,'live_backups':enhanced},
            'created_at':datetime.now(timezone.utc).isoformat(),'backup_limit_bytes':50_000_000_000,'mods':installed,
            'eula_accepted_at':datetime.now(timezone.utc).isoformat()}
        (stage/'mcyard.json').write_text(json.dumps(metadata,indent=2,ensure_ascii=False),encoding='utf-8')
        description=f"Minecraft {options.mc_version} / {options.server_type.title()} {loader} / Java {required}{'' if options.server_type=='forge' else '+'}."
        (stage/'SERVER-INFO.txt').write_text('Created with MCyard Server. Open this folder from its library.\n'
            'Press Start to generate the world. Fabric downloads its remaining libraries on first start.\n'
            'Keep this folder outside your source repository: it contains private player data, logs and backups.\n'+description+'\n'
            'Minecraft EULA: https://www.minecraft.net/eula\n'
            'Backup storage: 50 GB maximum across managed backups, including staging. Oldest first; newest completed retained.\n'
            'Advanced player history and live backups require the included Fabric 26.3 management mods.\n'
            'Internet access: use router port forwarding or an optional service such as playit.gg.\n',encoding='utf-8')
        _cancel(cancel_event)
        if target.exists():raise ValueError('The destination folder was created while setup was running; it was left unchanged.')
        stage.rename(target);committed=True
        try:result=register_server(target)
        except Exception as exc:
            raise RuntimeError(f'The server was created at {target}, but could not be added to the library. Use Add existing folder. Details: {exc}') from exc
        progress('Server created. Open it and press Start to generate the world.')
        return result
    except (urllib.error.URLError,TimeoutError) as exc:
        raise RuntimeError('A server component could not be downloaded. Check your internet connection and try again. '+str(exc)) from exc
    finally:
        if not committed and stage.exists():_remove_staging(stage,options.parent)
