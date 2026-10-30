"""Maintainer-only collection of pinned Qt notices; never run by the app.

Reads the official Qt GitHub mirrors. Downloads only attribution metadata,
explicit license/copyright files, and SPDX license texts from LICENSES/.
"""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path, PurePosixPath
import posixpath
import re
import urllib.parse
import urllib.request

VERSION='6.11.1'
REPOS=('qtbase','qtsvg','qtimageformats')
ROOT=Path(__file__).resolve().parents[1]/'resources/licenses'
DEST=ROOT/f'qt-{VERSION}'


def fetch(url):
    request=urllib.request.Request(url,headers={'User-Agent':'MCyard Server-license-collector/0.1.0'})
    limit=32_000_000 if url.startswith('https://api.github.com/') else 4_000_000
    with urllib.request.urlopen(request,timeout=45) as response:
        data=response.read(limit+1)
    if len(data)>limit:raise RuntimeError('Unexpectedly large notice: '+url)
    return data


def source_url(repo,path):
    return f'https://raw.githubusercontent.com/qt/{repo}/v{VERSION}/'+urllib.parse.quote(path,safe='/')


def strings(entry,*keys):
    result=[]
    for key in keys:
        value=entry.get(key,[])
        if isinstance(value,str):result.append(value)
        elif isinstance(value,list):result.extend(v for v in value if isinstance(v,str))
    return result


def main():
    ROOT.mkdir(parents=True,exist_ok=True)
    files={};components=[];missing=[]
    for repo in REPOS:
        tree=json.loads(fetch(f'https://api.github.com/repos/qt/{repo}/git/trees/v{VERSION}?recursive=1'))
        if tree.get('truncated'):raise RuntimeError('Incomplete GitHub tree for '+repo)
        paths={e['path'] for e in tree['tree'] if e['type']=='blob'}
        attributions=sorted(p for p in paths if p.endswith('qt_attribution.json'))
        with ThreadPoolExecutor(max_workers=12) as pool:
            results=list(pool.map(lambda p:(p,fetch(source_url(repo,p))),attributions))
        wanted={p for p in paths if p.startswith('LICENSES/')}
        for path,data in results:
            files[(repo,path)]=data
            # Qt's attribution format permits literal newlines within strings.
            entries=json.loads(data.decode('utf-8-sig'),strict=False)
            if isinstance(entries,dict):entries=[entries]
            for entry in entries:
                links=[]
                for relative in strings(entry,'LicenseFile','LicenseFiles','CopyrightFile','CopyrightFiles'):
                    target=posixpath.normpath(posixpath.join(posixpath.dirname(path),relative))
                    if target.startswith('../') or target not in paths:
                        missing.append(f'{repo}/{path}: missing explicit notice {relative}');continue
                    wanted.add(target);links.append(target)
                # Without an explicit file, Qt resolves SPDX IDs from LICENSES/.
                for token in re.findall(r'[A-Za-z0-9][A-Za-z0-9.+-]*',entry.get('LicenseId','')):
                    candidate='LICENSES/'+token+'.txt'
                    if candidate in paths:links.append(candidate)
                components.append({'repository':repo,'attribution':path,'metadata':entry,'notice_files':sorted(set(links))})
        with ThreadPoolExecutor(max_workers=12) as pool:
            results=list(pool.map(lambda p:(p,fetch(source_url(repo,p))),sorted(wanted)))
        files.update({(repo,path):data for path,data in results})
    if missing:raise RuntimeError('\n'.join(missing))
    manifest=[]
    for (repo,path),data in sorted(files.items()):
        destination=DEST/repo/Path(*PurePosixPath(path).parts)
        destination.parent.mkdir(parents=True,exist_ok=True);destination.write_bytes(data)
        manifest.append({'path':destination.relative_to(ROOT).as_posix(),'url':source_url(repo,path),'sha256':hashlib.sha256(data).hexdigest()})
    (DEST/'manifest.json').write_text(json.dumps({'qt_version':VERSION,'repositories':list(REPOS),'files':manifest},indent=2)+'\n',encoding='utf-8')
    (DEST/'components.json').write_text(json.dumps(components,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    lines=[f'QT {VERSION} THIRD-PARTY ATTRIBUTIONS','',
        'Collected from official Qt source tags v'+VERSION+'. Full license and',
        'copyright texts are included beside this document under qt-'+VERSION+'/.',
        'This is a conservative superset for Qt Base, Qt SVG and Qt Image Formats.',
        'Platform-specific, test and build-tool notices may be included even when',
        'those components are absent from the Windows application. This list does',
        'not mean that every listed component is linked into MCyard Server.',
        'Original upstream attribution metadata, file URLs and SHA-256 hashes are',
        'preserved in the accompanying manifest and components JSON files.','']
    for component in components:
        entry=component['metadata'];repo=component['repository']
        lines += ['='*72,entry.get('Name',entry.get('Id','Unnamed component')),
                  'Qt module: '+repo,'Version: '+str(entry.get('Version','Not specified')),
                  'License: '+entry.get('License',entry.get('LicenseId','See upstream notice')),
                  'Use: '+entry.get('QtUsage','See upstream attribution'),
                  'Source: '+source_url(repo,component['attribution'])]
        copyright_text=entry.get('Copyright','')
        if isinstance(copyright_text,list):copyright_text='\n'.join(copyright_text)
        if copyright_text:lines += ['',copyright_text]
        for path in component['notice_files']:
            relative=f'qt-{VERSION}/{repo}/{path}'
            lines += ['', 'Full notice: '+relative, 'Upstream: '+source_url(repo,path)]
            if path in strings(entry,'CopyrightFile','CopyrightFiles'):
                lines.append(files[(repo,path)].decode('utf-8',errors='replace'))
        lines.append('')
    (ROOT/'QT-THIRD-PARTY-NOTICES.txt').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(f'Collected {len(components)} attributions and {len(files)} notice files for Qt {VERSION}.')


if __name__=='__main__':main()
