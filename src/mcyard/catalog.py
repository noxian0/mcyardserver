"""Released server versions from Mojang, Fabric and Forge's own catalogs."""
import hashlib
import json
import re
import threading
import time
import xml.etree.ElementTree as ET

MOJANG_MANIFEST='https://piston-meta.mojang.com/mc/game/version_manifest_v2.json'
FABRIC_GAMES='https://meta.fabricmc.net/v2/versions/game'
FORGE_METADATA='https://maven.minecraftforge.net/net/minecraftforge/forge/maven-metadata.xml'
SERVER_TYPES=('vanilla','fabric','forge')
_cache={}
_lock=threading.Lock()


def valid_version(value):
    return isinstance(value,str) and bool(re.fullmatch(r'\d+(?:\.\d+){1,3}',value))


def supported_version(value):
    if not valid_version(value):return False
    numbers=tuple(map(int,value.split('.')))
    return numbers>=(1,18) and (numbers[0]==1 or numbers[0]>=26)


def required_java(mc_version):
    """UI guidance; installation also checks the authoritative version manifest."""
    if not supported_version(mc_version):raise ValueError('Choose a released Minecraft version from 1.18 onward.')
    version=tuple(map(int,mc_version.split('.')))
    return 25 if version[0]>=26 else 21 if version>=(1,20,5) else 17


def _read(url,cancel_event=None):
    # Lazy import keeps this public catalog independent from provisioning imports.
    from .provision import _cancel,_open
    _cancel(cancel_event)
    with _lock:cached=_cache.get(url)
    if cached and time.monotonic()-cached[0]<300:return cached[1]
    with _open(url) as response:data=response.read(8*1024*1024+1)
    _cancel(cancel_event)
    if len(data)>8*1024*1024:raise RuntimeError('The version catalog is unexpectedly large.')
    with _lock:_cache[url]=(time.monotonic(),data)
    return data


def _json(url,cancel_event=None):
    return json.loads(_read(url,cancel_event))


def _releases(cancel_event=None):
    info=_json(MOJANG_MANIFEST,cancel_event)
    if not isinstance(info,dict) or not isinstance(info.get('versions'),list):raise RuntimeError('Minecraft returned an invalid version catalog.')
    return [entry for entry in info['versions'] if isinstance(entry,dict) and entry.get('type')=='release' and supported_version(entry.get('id'))]


def _forge_versions(cancel_event=None):
    data=_read(FORGE_METADATA,cancel_event)
    if b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():raise RuntimeError('Forge returned an invalid version catalog.')
    root=ET.fromstring(data)
    versions={}
    for node in root.findall('./versioning/versions/version'):
        match=re.fullmatch(r'(\d+(?:\.\d+){1,3})-(\d+(?:\.\d+){1,3})',node.text or '')
        if match and supported_version(match[1]):versions.setdefault(match[1],set()).add(match[2])
    return versions


def list_mc_versions(server_type,cancel_event=None):
    if server_type not in SERVER_TYPES:raise ValueError('Choose Vanilla, Fabric or Forge.')
    releases=[entry['id'] for entry in _releases(cancel_event)]
    if server_type=='fabric':
        supported={entry.get('version') for entry in _json(FABRIC_GAMES,cancel_event) if entry.get('stable')}
        releases=[value for value in releases if value in supported]
    elif server_type=='forge':
        supported=_forge_versions(cancel_event)
        releases=[value for value in releases if value in supported]
    return releases


def list_loader_versions(server_type,mc_version,cancel_event=None):
    if server_type not in SERVER_TYPES:raise ValueError('Choose Vanilla, Fabric or Forge.')
    if not supported_version(mc_version):raise ValueError('Unsupported Minecraft version.')
    if server_type=='vanilla':return []
    if server_type=='forge':
        return sorted(_forge_versions(cancel_event).get(mc_version,()),key=lambda value:tuple(map(int,value.split('.'))),reverse=True)
    entries=_json(f'https://meta.fabricmc.net/v2/versions/loader/{mc_version}',cancel_event)
    versions=list(dict.fromkeys(entry['loader']['version'] for entry in entries
        if isinstance(entry,dict) and isinstance(entry.get('loader'),dict)
        and entry['loader'].get('stable') and valid_version(entry['loader'].get('version'))))
    # The bundled management bridge targets this release and loader generation.
    if mc_version=='26.3':versions=[value for value in versions if tuple(map(int,value.split('.')))>=(0,20,1)]
    return versions


def version_details(mc_version,cancel_event=None):
    entry=next((entry for entry in _releases(cancel_event) if entry['id']==mc_version),None)
    if not entry:raise ValueError('This released Minecraft version is not in the official catalog.')
    data=_read(entry['url'],cancel_event)
    checksum=entry.get('sha1','')
    if not re.fullmatch('[0-9a-fA-F]{40}',checksum) or hashlib.sha1(data).hexdigest()!=checksum.lower():
        raise RuntimeError('Minecraft version metadata failed checksum verification.')
    info=json.loads(data)
    if info.get('id')!=mc_version or not info.get('downloads',{}).get('server'):raise ValueError('This release does not offer a standalone Minecraft server.')
    required=info.get('javaVersion',{}).get('majorVersion',required_java(mc_version))
    if isinstance(required,bool) or not isinstance(required,int) or not 17<=required<=99:raise RuntimeError('Minecraft returned an invalid Java requirement.')
    return info
