"""Build a replaceable-library Windows app and clean GitHub source archive."""
from pathlib import Path
import hashlib
from importlib import metadata
import json
import os
import shutil
import subprocess
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1]
VERSION='0.1.0'
SOURCE_DIRS=('src','bridge','resources','docs','installer')
SOURCE_FILES=('README.md','LICENSE','THIRD_PARTY_NOTICES.md','SECURITY.md','CHANGELOG.md',
              'pyproject.toml','.gitignore','.github/workflows/windows.yml',
              'scripts/build_windows.py','scripts/build_installer.py',
              'scripts/collect_qt_licenses.py','scripts/frozen_entry.py',
              'scripts/pyinstaller_hooks/hook-PySide6.QtGui.py')


def source_files():
    for name in SOURCE_FILES:
        path=ROOT/name
        if not path.is_file():raise RuntimeError('Missing release file: '+name)
        yield path
    for name in SOURCE_DIRS:
        for path in sorted((ROOT/name).rglob('*')):
            if not path.is_file() or path.is_symlink():continue
            rel=path.relative_to(ROOT)
            if any(p in ('__pycache__','classes','build','data','screenshots') or p.endswith('.egg-info') for p in rel.parts):continue
            if path.suffix in ('.pyc','.pyo','.log','.partial','.class'):continue
            yield path


def source_zip(target):
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for path in source_files():archive.write(path,Path('MCyard Server')/path.relative_to(ROOT))


def main():
    if sys.platform!='win32':raise SystemExit('Build this Windows release on Windows.')
    if sys.maxsize<=2**32:raise SystemExit('Use a 64-bit Python installation.')
    for resource in ('app.ico','mcyard.svg','landscape.svg','mcyard-bridge-0.1.0.jar','simplebackups-common.toml','licenses/LGPL-3.0.txt','licenses/GPL-3.0.txt','licenses/QT-THIRD-PARTY-NOTICES.txt','licenses/qt-6.11.1/manifest.json'):
        if not (ROOT/'resources'/resource).is_file():raise SystemExit('Missing required resource: '+resource)
    command=[sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onedir','--windowed',
        '--name','MCyard Server','--icon',str(ROOT/'resources/app.ico'),'--paths',str(ROOT/'src'),
        '--additional-hooks-dir',str(ROOT/'scripts/pyinstaller_hooks'),
        '--add-data',str(ROOT/'resources')+os.pathsep+'resources','--collect-submodules','mcyard',
        '--exclude-module','PyQt5','--exclude-module','PyQt6','--exclude-module','tkinter',
        '--distpath',str(ROOT/'dist'),'--workpath',str(ROOT/'build'),
        '--specpath',str(ROOT/'build'),str(ROOT/'scripts/frozen_entry.py')]
    # Build tools may inherit unrelated native runtimes on PATH (for example a
    # PDF tool's ICU). Qt uses Windows' ICU ABI, so collecting that other DLL
    # breaks the frozen app even when every source test passes.
    env=os.environ.copy()
    windows=Path(env.get('SystemRoot',r'C:\Windows'))
    env['PATH']=os.pathsep.join(dict.fromkeys(map(str,(
        Path(sys.executable).resolve().parent,Path(sys.base_prefix),
        Path(sys.base_prefix)/'Scripts',windows/'System32',windows))))
    for name in ('PYTHONPATH','PYTHONHOME','QT_PLUGIN_PATH','QT_QPA_PLATFORM_PLUGIN_PATH'):
        env.pop(name,None)
    subprocess.run(command,cwd=ROOT,env=env,check=True)
    app=ROOT/'dist/MCyard Server'
    for name in ('README.md','LICENSE','THIRD_PARTY_NOTICES.md'):
        shutil.copy2(ROOT/name,app/name)
    (app/'resources').mkdir(exist_ok=True)
    shutil.copy2(ROOT/'resources/mcyard.svg',app/'resources/mcyard.svg')
    shutil.copytree(ROOT/'resources/licenses',app/'licenses',dirs_exist_ok=True)
    python_license=Path(sys.base_prefix)/'LICENSE.txt'
    if python_license.exists():shutil.copy2(python_license,app/'licenses/Python.txt')
    installer=metadata.distribution('pyinstaller')
    for file in installer.files or []:
        if str(file).endswith('licenses/COPYING.txt'):
            shutil.copy2(installer.locate_file(file),app/'licenses/PyInstaller.txt')
    versions={name:metadata.version(name) for name in ('PySide6','PySide6_Essentials','shiboken6','pyinstaller')}
    versions.update({'MCyard Server':VERSION,'Python':sys.version.split()[0],'architecture':'Windows x64'})
    (app/'BUILD-INFO.json').write_text(json.dumps(versions,indent=2)+'\n',encoding='utf-8')
    shutil.copytree(ROOT/'docs',app/'docs',dirs_exist_ok=True)
    release=ROOT/'release';release.mkdir(exist_ok=True)
    source=release/f'MCyard Server-{VERSION}-source.zip';source_zip(source)
    portable=release/f'MCyard Server-{VERSION}-windows-x64.zip'
    with zipfile.ZipFile(portable,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for path in sorted(app.rglob('*')):
            if path.is_file():archive.write(path,Path('MCyard Server')/path.relative_to(app))
    hashes=[]
    for path in (source,portable):
        with path.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
        hashes.append(digest+'  '+path.name)
    (release/'SHA256SUMS.txt').write_text('\n'.join(hashes)+'\n',encoding='utf-8')
    print('Built executable:',app/'MCyard Server.exe')
    print('GitHub source:',source)
    print('Portable release:',portable)


if __name__=='__main__':main()
