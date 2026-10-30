"""Download verified Temurin JREs into the user's MCyard data directory.

No administrator privileges, registry changes or system PATH changes are used.
The official package's license and legal files remain alongside the runtime.
"""
from contextlib import contextmanager
from datetime import datetime,timezone
from pathlib import Path,PurePosixPath
import hashlib
import json
import os
import re
import stat
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile

from .java_runtime import detect_java,validate_java
from .paths import app_data

SUPPORTED_MAJORS=(17,21,25)
MAX_DOWNLOAD=256*1024*1024
MAX_EXPANDED=768*1024*1024
USER_AGENT='MCyard-Server/0.1.0 (Windows Java runtime setup)'


class RuntimeInstallCancelled(RuntimeError):pass


def _cancel(event):
    if event is not None and event.is_set():raise RuntimeInstallCancelled('Java installation canceled. Existing Java installations were kept.')


def _safe_url(url):
    parsed=urllib.parse.urlsplit(url)
    if parsed.scheme!='https' or parsed.username or parsed.password or parsed.port not in (None,443):
        raise RuntimeError('Java download returned an unexpected URL.')
    allowed=parsed.hostname in ('api.adoptium.net','release-assets.githubusercontent.com','objects.githubusercontent.com')
    if parsed.hostname=='github.com':
        allowed=bool(re.match(r'^/adoptium/temurin(?:17|21|25)-binaries/releases/download/',parsed.path))
    if not allowed:raise RuntimeError('Java downloads must come from Eclipse Adoptium or its official release assets.')
    return url


def _open(url):
    class SafeRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,request,fp,code,message,headers,new_url):
            _safe_url(new_url)
            return super().redirect_request(request,fp,code,message,headers,new_url)
    request=urllib.request.Request(_safe_url(url),headers={'User-Agent':USER_AGENT,'Accept':'application/json, application/octet-stream;q=0.9'})
    response=urllib.request.build_opener(SafeRedirect()).open(request,timeout=30)
    try:_safe_url(response.url)
    except Exception:response.close();raise
    return response


def _package(major,cancel_event=None):
    _cancel(cancel_event)
    url=f'https://api.adoptium.net/v3/assets/latest/{major}/hotspot?architecture=x64&image_type=jre&os=windows&vendor=eclipse'
    with _open(url) as response:data=response.read(2*1024*1024+1)
    _cancel(cancel_event)
    if len(data)>2*1024*1024:raise RuntimeError('The Java release catalog is unexpectedly large.')
    records=json.loads(data)
    if not isinstance(records,list):raise RuntimeError('Adoptium returned an invalid Java release catalog.')
    for record in records:
        if not isinstance(record,dict):continue
        binary=record.get('binary',{});version=record.get('version',{})
        if record.get('vendor')!='eclipse' or version.get('major')!=major:continue
        if any(binary.get(key)!=value for key,value in {'architecture':'x64','image_type':'jre','os':'windows','jvm_impl':'hotspot'}.items()):continue
        package=binary.get('package',{});name=package.get('name','');size=package.get('size');checksum=package.get('checksum','')
        if not isinstance(name,str) or not re.fullmatch(fr'OpenJDK{major}U-jre_x64_windows_hotspot_[A-Za-z0-9._+-]+\.zip',name):continue
        if type(size) is not int or not 0<size<=MAX_DOWNLOAD:raise RuntimeError('The Java package has an invalid size.')
        if not isinstance(checksum,str) or not re.fullmatch('[a-fA-F0-9]{64}',checksum):raise RuntimeError('The Java package did not provide a SHA-256 checksum.')
        source=_safe_url(package.get('link',''))
        if not urllib.parse.urlsplit(source).path.startswith(f'/adoptium/temurin{major}-binaries/releases/download/'):
            raise RuntimeError('The Java package does not match its official release repository.')
        return {'url':source,'sha256':checksum.lower(),'size':size,'name':name,'version':version.get('openjdk_version','')}
    raise RuntimeError(f'No official Windows x64 Java {major} runtime is available. Try again later or select an installed Java executable.')


def _download(package,target,major,progress,cancel_event):
    digest=hashlib.sha256();total=0;last=-1
    with _open(package['url']) as response,target.open('xb') as stream:
        while True:
            _cancel(cancel_event);block=response.read(256*1024)
            if not block:break
            total+=len(block)
            if total>package['size'] or total>MAX_DOWNLOAD:raise RuntimeError('The Java download exceeded its expected size.')
            stream.write(block);digest.update(block)
            step=int(total*20/package['size'])
            if step!=last:progress(f'Downloading Java {major}: {min(step*5,100)}%');last=step
    _cancel(cancel_event)
    if total!=package['size']:raise RuntimeError('Java download was incomplete. Nothing was installed.')
    if digest.hexdigest()!=package['sha256']:raise RuntimeError('Java download failed SHA-256 verification. Nothing was installed.')


def _linked(path):return path.is_symlink() or (hasattr(path,'is_junction') and path.is_junction())


def _extract(archive_path,destination,cancel_event=None):
    """Validate the complete ZIP, then stream files into a fresh owned folder."""
    destination.mkdir()
    with zipfile.ZipFile(archive_path) as archive:
        entries=archive.infolist()
        if len(entries)>20000 or sum(entry.file_size for entry in entries)>MAX_EXPANDED:
            raise RuntimeError('The Java archive expands beyond its size limit.')
        seen=set()
        for entry in entries:
            name=entry.filename;relative=PurePosixPath(name);mode=entry.external_attr>>16
            unsafe=(not name or entry.orig_filename!=name or '\\' in name or ':' in name or relative.is_absolute() or '..' in relative.parts or
                    any(ord(char)<32 for char in name) or stat.S_ISLNK(mode) or bool(entry.external_attr&0x400))
            unsafe=unsafe or any(part.endswith((' ','.')) or re.fullmatch(r'(?i)(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?',part) for part in relative.parts)
            key=str(relative).casefold()
            if unsafe or key in seen:raise RuntimeError('The Java archive contains an unsafe or duplicate path.')
            seen.add(key)
        for entry in entries:
            _cancel(cancel_event);target=destination/Path(PurePosixPath(entry.filename))
            if not target.resolve().is_relative_to(destination.resolve()):raise RuntimeError('The Java archive contains an unsafe path.')
            if entry.is_dir():target.mkdir(parents=True,exist_ok=True);continue
            target.parent.mkdir(parents=True,exist_ok=True)
            with archive.open(entry) as source,target.open('xb') as output:
                while True:
                    _cancel(cancel_event);block=source.read(256*1024)
                    if not block:break
                    output.write(block)
    candidates=list(destination.glob('*/bin/java.exe'))
    if (destination/'bin/java.exe').is_file():candidates.append(destination/'bin/java.exe')
    if len(candidates)!=1:raise RuntimeError('The Java archive does not contain one recognizable runtime.')
    return candidates[0].parent.parent


def _cleanup(stage,parent):
    """Remove only the unique staging directory created by this installation."""
    parent=parent.resolve();stage=Path(stage)
    if _linked(stage) or stage.resolve().parent!=parent or not stage.name.startswith('.mcyard-java-'):
        raise RuntimeError('Refusing to remove an unexpected Java staging path.')
    children=list(stage.rglob('*'))
    if any(_linked(path) or not path.resolve().is_relative_to(stage.resolve()) for path in children):
        raise RuntimeError('A Java staging path changed; leaving it for inspection.')
    for path in sorted(children,key=lambda path:len(path.parts),reverse=True):
        path.rmdir() if path.is_dir() else path.unlink()
    stage.rmdir()


@contextmanager
def _install_lock(parent,major):
    with (parent/f'.java-{major}.lock').open('a+b') as stream:
        stream.seek(0,2)
        if stream.tell()==0:stream.write(b'0');stream.flush()
        stream.seek(0)
        try:
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError as exc:raise RuntimeError(f'Java {major} is already being installed in another window.') from exc
        try:yield
        finally:
            stream.seek(0)
            if os.name=='nt':msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)
            else:fcntl.flock(stream.fileno(),fcntl.LOCK_UN)


def install_java(major,progress=lambda text:None,cancel_event=None,*,force=False):
    """Reuse or install Java 17/21/25; return its path, major and version.

    ``force`` skips other installed runtimes for isolated installer verification;
    it never replaces an existing managed runtime or touches system Java.
    """
    if type(major) is not int or major not in SUPPORTED_MAJORS:raise ValueError('Choose Java 17, 21 or 25.')
    _cancel(cancel_event)
    if not force:
        installed=detect_java(required=major,exact=True)
        if installed:progress(f'Java {major} is already available.');return installed[0]
    parent=app_data()/'runtimes'
    if _linked(parent):raise ValueError('Managed Java must be stored in a real folder inside the app data directory.')
    parent.mkdir(parents=True,exist_ok=True);target=parent/f'java-{major}'
    with _install_lock(parent,major):
        _cancel(cancel_event)
        if target.exists() or _linked(target):
            if _linked(target):raise ValueError('The managed Java folder cannot be a linked folder.')
            try:existing=validate_java(target/'bin/java.exe',required=major,exact=True)
            except ValueError as exc:raise ValueError(f'The managed Java {major} folder needs repair: {target}. Move it aside before retrying.') from exc
            progress(f'Java {major} is already available.');return existing
        progress(f'Checking the official Java {major} release…')
        package=_package(major,cancel_event);_cancel(cancel_event)
        stage=parent/('.mcyard-java-'+uuid.uuid4().hex);stage.mkdir()
        try:
            archive=stage/'runtime.zip';_download(package,archive,major,progress,cancel_event)
            progress(f'Verifying and unpacking Java {major}…')
            runtime=_extract(archive,stage/'unpacked',cancel_event)
            result=validate_java(runtime/'bin/java.exe',required=major,exact=True)
            (runtime/'mcyard-runtime.json').write_text(json.dumps({'provider':'Eclipse Temurin','major':major,'version':result['version'],
                'source':package['url'],'sha256':package['sha256'],'installed_at':datetime.now(timezone.utc).isoformat()},indent=2),encoding='utf-8')
            _cancel(cancel_event)
            if target.exists():raise RuntimeError('The Java destination appeared during installation. It was left unchanged.')
            runtime.rename(target)
            result={**result,'path':str((target/'bin/java.exe').resolve())}
            progress(f'Java {major} is ready.');return result
        except (urllib.error.URLError,TimeoutError) as exc:
            raise RuntimeError('Java could not be downloaded. Check the connection and retry. '+str(exc)) from exc
        finally:
            if stage.exists():_cleanup(stage,parent)
