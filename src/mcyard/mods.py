"""Inspect local mods without executing them; toggles only rename a JAR."""
from pathlib import Path
import json
import os
import tomllib
import zipfile

ESSENTIAL_NAMES={'Fabric API','Forge Config API Port','Simple Backups'}
ESSENTIAL_IDS={'mcyard_bridge','gang_manager','fabric-api','forgeconfigapiport','simplebackups'}


def _linked(path):
    return path.is_symlink() or (hasattr(path,'is_junction') and path.is_junction())


def _folder(root):
    root=Path(root).resolve();folder=root/'mods'
    if _linked(folder) or folder.resolve().parent!=root:
        raise ValueError('The mods folder must be a real folder inside this server.')
    if folder.exists() and not folder.is_dir():raise ValueError('The mods path is not a folder.')
    return folder


def _metadata(path):
    result={'name':path.name.removesuffix('.disabled').removesuffix('.jar'),'version':'—','ids':[],'error':''}
    try:
        with zipfile.ZipFile(path) as jar:
            names=jar.namelist()
            if len(names)>100000:raise ValueError('Too many archive entries')
            def read(name):
                info=jar.getinfo(name)
                if info.file_size>1024*1024:raise ValueError('Mod metadata is too large')
                return jar.read(name).decode('utf-8-sig')
            if 'fabric.mod.json' in names:
                data=json.loads(read('fabric.mod.json'))
                result.update(name=str(data.get('name') or data.get('id') or result['name']),
                              version=str(data.get('version','—')),ids=[str(data.get('id',''))])
            else:
                name=next((n for n in ('META-INF/mods.toml','META-INF/neoforge.mods.toml') if n in names),None)
                if name:
                    data=tomllib.loads(read(name));entries=data.get('mods',[])
                    if not isinstance(entries,list):raise ValueError('Invalid mods metadata')
                    result['ids']=[str(m.get('modId','')) for m in entries if isinstance(m,dict)]
                    if entries and isinstance(entries[0],dict):
                        result['name']=str(entries[0].get('displayName') or entries[0].get('modId') or result['name'])
                        version=str(entries[0].get('version','—'))
                        result['version']='From JAR' if '${' in version else version
    except (OSError,ValueError,KeyError,TypeError,AttributeError,RuntimeError,zipfile.BadZipFile) as exc:
        result['error']='Could not read mod metadata: '+str(exc)
    result['name']=result['name'][:160];result['version']=result['version'][:80]
    return result


def mod_signature(root):
    folder=_folder(root)
    if not folder.exists():return ()
    return tuple((p.name,p.lstat().st_size,p.lstat().st_mtime_ns) for p in sorted(folder.iterdir()))


def _protected(filename,info,config):
    enhanced=config.get('capabilities',{}).get('bridge',config.get('server_type','fabric')=='fabric' and config.get('mc_version')=='26.3')
    if not enhanced:return False
    essential={m.get('filename','').casefold() for m in config.get('mods',[]) if isinstance(m,dict) and m.get('name') in ESSENTIAL_NAMES}
    return (filename.removesuffix('.disabled').casefold() in essential or
            filename.casefold().startswith('mcyard-bridge-') or bool(ESSENTIAL_IDS.intersection(info['ids'])))


def list_mods(root,config=None):
    folder=_folder(root);result=[]
    if not folder.exists():return result
    for path in sorted(folder.iterdir(),key=lambda p:p.name.casefold()):
        lower=path.name.lower()
        if not lower.endswith(('.jar','.jar.disabled')):continue
        unsafe=_linked(path) or path.resolve().parent!=folder.resolve()
        if not unsafe and not path.is_file():continue
        info={'name':path.name,'version':'—','ids':[],'error':'Linked mod files cannot be changed.'} if unsafe else _metadata(path)
        protected=_protected(path.name,info,config or {})
        result.append({**info,'filename':path.name,'enabled':not lower.endswith('.disabled'),
                       'size':0 if unsafe else path.stat().st_size,'protected':protected,'unsafe':unsafe})
    return result


def set_mod_enabled(root,filename,enabled,config=None,*,server_running=False):
    if server_running:raise ValueError('Stop the server before changing mods.')
    if not isinstance(enabled,bool):raise ValueError('Invalid mod state.')
    if not isinstance(filename,str) or not filename or Path(filename).name!=filename or any(c in filename for c in '/\\:'):
        raise ValueError('Choose a mod inside this server’s mods folder.')
    folder=_folder(root);source=folder/filename
    if _linked(source) or source.resolve().parent!=folder.resolve() or not source.is_file():
        raise ValueError('The selected mod is missing or is a linked file.')
    lower=filename.lower()
    if not lower.endswith(('.jar','.jar.disabled')):raise ValueError('Only JAR mods can be enabled or disabled.')
    active=not lower.endswith('.disabled')
    if active==enabled:return source
    info=_metadata(source)
    if not enabled and _protected(filename,info,config or {}):
        raise ValueError('This mod is required for live management and the 50 GB backup limit.')
    target=source.with_name(filename[:-9] if enabled else filename+'.disabled')
    if target.exists() or _linked(target):raise ValueError('A mod with the destination filename already exists. No files were changed.')
    # Windows rename refuses an existing destination, including a concurrent one.
    os.rename(source,target)
    return target
