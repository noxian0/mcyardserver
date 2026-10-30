"""Compile the per-user Windows installer from an already built application."""
from pathlib import Path
import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[1]


def find_compiler(explicit=None):
    candidates = [explicit, os.environ.get('INNO_SETUP_COMPILER'), shutil.which('ISCC.exe')]
    for base in ('LOCALAPPDATA', 'ProgramFiles(x86)', 'ProgramFiles'):
        directory = os.environ.get(base)
        if directory:
            folder = Path(directory) / ('Programs' if base == 'LOCALAPPDATA' else '')
            candidates.append(folder / 'Inno Setup 6' / 'ISCC.exe')
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return Path(candidate).resolve()
    raise SystemExit('Install Inno Setup 6 from https://jrsoftware.org/isdl.php, '
                     'or pass --compiler "C:\\path\\to\\ISCC.exe".')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler', type=Path, help='Path to Inno Setup 6 ISCC.exe')
    args = parser.parse_args(argv)
    if sys.platform != 'win32':
        raise SystemExit('Build the Windows installer on Windows.')
    app = ROOT / 'dist' / 'MCyard Server' / 'MCyard Server.exe'
    if not app.is_file():
        raise SystemExit('Run python scripts/build_windows.py first.')
    with (ROOT / 'pyproject.toml').open('rb') as stream:
        version = tomllib.load(stream)['project']['version']
    compiler = find_compiler(args.compiler)
    subprocess.run([str(compiler), f'/DSourceRoot={ROOT}', f'/DAppVersion={version}',
                    str(ROOT / 'installer' / 'MCyardServer.iss')], cwd=ROOT, check=True)
    setup = ROOT / 'MCyard Server Setup.exe'
    if not setup.is_file():
        raise RuntimeError('The compiler did not create the setup executable.')
    release = ROOT / 'release'
    release.mkdir(exist_ok=True)
    packaged = release / f'MCyard Server-{version}-setup-x64.exe'
    shutil.copy2(setup, packaged)
    checksums = release / 'SHA256SUMS.txt'
    lines = checksums.read_text(encoding='utf-8').splitlines() if checksums.exists() else []
    lines = [line for line in lines if not line.endswith('  ' + packaged.name)]
    with packaged.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    lines.append(digest + '  ' + packaged.name)
    checksums.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print('Setup:', setup)
    print('Release:', packaged)


if __name__ == '__main__':
    main()
