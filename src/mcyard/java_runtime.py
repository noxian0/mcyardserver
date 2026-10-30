"""Locate installed Java without downloading or changing system settings."""
from pathlib import Path
import os
import re
import shutil
import subprocess


def validate_java(path, required=25, exact=False):
    """Return an installed runtime description, or raise a useful ValueError."""
    candidate=str(path).strip().strip('"')
    if not candidate:
        raise ValueError(f'Choose a Java {required} installation. Java is separate from MCyard Server.')
    executable=shutil.which(candidate) or candidate
    resolved=Path(executable).expanduser().resolve()
    if not resolved.is_file():
        raise ValueError(f'Java executable was not found. Choose java.exe inside a Java {required} bin folder.')
    try:
        result=subprocess.run([str(resolved),'-version'],capture_output=True,text=True,
            encoding='utf-8',errors='replace',timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    except (OSError,subprocess.TimeoutExpired) as exc:
        raise ValueError('Could not run the selected Java executable: '+str(exc)) from exc
    output=result.stderr+'\n'+result.stdout
    match=re.search(r'(?:version\s+"|(?:openjdk|java)\s+)(\d+(?:[.\w+-]*))',output)
    if result.returncode or not match:
        raise ValueError('The selected program did not report a usable Java version.')
    version=match.group(1);parts=version.split('.')
    major=int(parts[1] if parts[0]=='1' and len(parts)>1 else parts[0])
    if major<required or (exact and major!=required):
        qualifier=' exactly for this Forge version' if exact else ' or newer'
        raise ValueError(f'This server needs Java {required}{qualifier}; this installation is Java {major}.')
    return {'path':str(resolved),'major':major,'version':version}


def detect_java(required=25, exact=False):
    """Find suitable installed runtimes, newest first; never install anything."""
    candidates=[]
    # Prerequisites installed by MCyard are private to this Windows user. They
    # never change JAVA_HOME, PATH, or another application's Java installation.
    from .paths import app_data
    managed=app_data()/'runtimes'
    if managed.is_dir():candidates.extend(managed.glob('java-*/bin/java.exe'))
    if os.environ.get('JAVA_HOME'):
        candidates.append(Path(os.environ['JAVA_HOME'])/'bin'/('java.exe' if os.name=='nt' else 'java'))
    if shutil.which('java'):candidates.append(Path(shutil.which('java')))
    for base in (Path(os.environ.get('ProgramFiles','C:/Program Files')),
                 Path(os.environ.get('LOCALAPPDATA',str(Path.home()/'AppData/Local')))/'Programs'):
        for vendor in ('Java','Eclipse Adoptium','Microsoft','Amazon Corretto','BellSoft'):
            folder=base/vendor
            if folder.is_dir():candidates.extend(folder.glob('*/bin/java.exe'))
    result=[];seen=set()
    for candidate in candidates:
        key=os.path.normcase(str(candidate.resolve()))
        if key in seen:continue
        seen.add(key)
        try:result.append(validate_java(candidate,required=required,exact=exact))
        except ValueError:continue
    return sorted(result,key=lambda item:(item['major'],item['version']),reverse=True)
