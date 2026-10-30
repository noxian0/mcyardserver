"""Local data and commands for a MCyard Server. No HTTP service or credentials."""
from pathlib import Path
import gzip
import io
import json
import os
import re
import sqlite3
import struct
import time
import uuid
import hashlib
import datetime
import msvcrt
from .actions import FEATURES,validate_action,action_subject,action_description

if not os.environ.get('MCYARD_SERVER_ROOT'):
    raise RuntimeError('Open a server from the MCyard Server library.')
ROOT = Path(os.environ['MCYARD_SERVER_ROOT']).resolve()
DATA = ROOT / 'manager' / 'data'


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {} if default is None else default


def atomic_json(path, value):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8')
    tmp.replace(path)


def properties():
    result={}
    for line in (ROOT/'server.properties').read_text(encoding='ascii').splitlines():
        if '=' in line and not line.startswith('#'):
            k,v=line.split('=',1)
            result[k]=v
    return result


def world_locked():
    path=ROOT/properties().get('level-name','world')/'session.lock'
    if not path.exists():return False
    try:
        with path.open('r+b') as f:
            try:msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
            except OSError:return True
            f.seek(0);msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)
        return False
    except OSError:return True


def save_properties(changes):
    """Preserve unknown keys, secrets and all unrelated values."""
    if any('\n' in str(v) or '\r' in str(v) for v in changes.values()):
        raise ValueError('Settings cannot contain line breaks.')
    p=ROOT/'server.properties'
    before=p.read_text(encoding='ascii')
    backup=DATA/'settings-history'/f'{time.time_ns()}.properties'
    backup.parent.mkdir(parents=True,exist_ok=True)
    backup.write_text(before,encoding='ascii')
    left=dict(changes)
    lines=[]
    for line in before.splitlines():
        k=line.split('=',1)[0]
        if k in left:
            value=str(left.pop(k))
            value=''.join(c if ord(c)<128 else ('\\u%04x'%ord(c)) for c in value)
            line=f'{k}={value}'
        lines.append(line)
    lines.extend(f'{k}={v}' for k,v in left.items())
    tmp=p.with_suffix('.properties.tmp')
    tmp.write_text('\n'.join(lines)+'\n',encoding='ascii')
    tmp.replace(p)


def location(data):
    if not data: return 'Not recorded'
    try:
        dim=str(data.get('dimension','overworld')).removeprefix('minecraft:')
        return f"{float(data['x']):.1f}, {float(data['y']):.1f}, {float(data['z']):.1f}  \u00b7  {dim}"
    except (KeyError,ValueError,TypeError): return 'Not recorded'


def timestamp(value):
    return time.strftime('%d %b %Y  %H:%M:%S',time.localtime(value/1000)) if value else 'Not recorded'


class NBTByte(int): pass


class NBT:
    """Read-only Java NBT decoder for saved player data, all 12 tag types."""
    def __init__(self,data): self.f=io.BytesIO(data)
    def num(self,fmt): return struct.unpack('>'+fmt,self.f.read(struct.calcsize('>'+fmt)))[0]
    def string(self): return self.f.read(self.num('H')).decode('utf-8',errors='replace')
    def tag(self,t):
        if t==1:return NBTByte(self.num('b'))
        if 2<=t<=6: return self.num({2:'h',3:'i',4:'q',5:'f',6:'d'}[t])
        if t==8: return self.string()
        if t in (7,11,12):
            n=self.num('i')
            if n<0 or n>10_000_000: raise ValueError('Invalid NBT array')
            return [self.num({7:'b',11:'i',12:'q'}[t]) for _ in range(n)]
        if t==9:
            kind,n=self.num('B'),self.num('i')
            if n<0 or n>1_000_000: raise ValueError('Invalid NBT list')
            return [self.tag(kind) for _ in range(n)]
        if t==10:
            result={}
            while True:
                kind=self.num('B')
                if kind==0: return result
                name=self.string(); result[name]=self.tag(kind)
        raise ValueError(f'Unknown NBT tag {t}')
    @classmethod
    def load(cls,path):
        data=Path(path).read_bytes()
        if data[:2]==b'\x1f\x8b': data=gzip.decompress(data)
        parser=cls(data); kind=parser.num('B'); parser.string()
        return parser.tag(kind)


def saved_player(uid):
    if not re.fullmatch(r'[a-fA-F0-9-]{36}',uid): return {}
    world=ROOT/properties().get('level-name','world')
    p=world/'players'/'data'/f'{uid}.dat'
    if not p.exists(): p=world/'playerdata'/f'{uid}.dat'
    try: n=NBT.load(p)
    except (OSError,ValueError,struct.error,RecursionError): return {}
    def items(entries):
        result=[]
        for item in entries:
            slot=int(item.get('Slot',item.get('slot',0)))
            slot={100:'feet',101:'legs',102:'chest',103:'head',-106:'offhand',150:'offhand'}.get(slot,str(slot))
            result.append({'slot':slot,'id':item.get('id','unknown'),'count':item.get('count',item.get('Count',1)),'data':item})
        return result
    result={'uuid':uid,'time':int(p.stat().st_mtime*1000),'source':'Saved player file',
            'health':n.get('Health',0),'food':n.get('foodLevel',0),'xp':n.get('XpLevel',0),
            'mode':{0:'survival',1:'creative',2:'adventure',3:'spectator'}.get(n.get('playerGameType'),'unknown'),
            'inventory':items(n.get('Inventory',n.get('inventory',[]))), 'ender':items(n.get('EnderItems',n.get('ender_items',[])))}
    for slot,item in n.get('equipment',{}).items():
        if isinstance(item,dict) and item.get('id'):
            result['inventory'].append({'slot':slot,'id':item['id'],'count':item.get('count',1),'data':item})
    pos=n.get('Pos',n.get('pos',[]))
    if len(pos)==3: result['position']=dict(zip(('x','y','z'),pos),dimension=n.get('Dimension',n.get('dimension','minecraft:overworld')))
    death=n.get('LastDeathLocation',n.get('last_death_location',{}))
    if isinstance(death,dict) and len(death.get('pos',[]))==3:
        result['lastDeath']=dict(zip(('x','y','z'),death['pos']),dimension=death.get('dimension','minecraft:overworld'))
    if 'SpawnX' in n:
        result['spawn']={'x':n['SpawnX'],'y':n['SpawnY'],'z':n['SpawnZ'],'dimension':n.get('SpawnDimension','minecraft:overworld'),'source':'Saved personal spawn'}
    # Modern respawn codec stores global position under respawn -> dimension/pos.
    respawn=n.get('respawn',{})
    if isinstance(respawn,dict):
        entry=respawn.get('respawn_data',respawn)
        if isinstance(entry,dict) and len(entry.get('pos',[]))==3:
            result['spawn']=dict(zip(('x','y','z'),entry['pos']),dimension=entry.get('dimension','minecraft:overworld'),source='Saved personal spawn')
    if 'spawn' not in result:
        try:
            spawn=NBT.load(world/'level.dat').get('Data',{}).get('spawn',{})
            if len(spawn.get('pos',[]))==3:
                result['spawn']=dict(zip(('x','y','z'),spawn['pos']),dimension=spawn.get('dimension','minecraft:overworld'),source='Saved world spawn')
        except (OSError,ValueError,struct.error):pass
    return result


def saved_rules():
    try:
        world=ROOT/properties().get('level-name','world')
        modern=world/'data/minecraft/game_rules.dat'
        if not modern.is_file():
            rules=NBT.load(world/'level.dat').get('Data',{}).get('GameRules',{})
            return {k:{'type':'bool' if str(v) in ('true','false') else 'int','value':str(v)}
                    for k,v in rules.items() if str(v) in ('true','false') or re.fullmatch(r'-?\d+',str(v))}
        rules=NBT.load(modern).get('data',{})
        return {k:{'type':'bool' if isinstance(v,NBTByte) else 'int',
                   'value':str(bool(v)).lower() if isinstance(v,NBTByte) else str(v)} for k,v in rules.items() if isinstance(v,int)}
    except (OSError,ValueError,struct.error):return {}


class Store:
    def __init__(self):
        DATA.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(DATA/'history.sqlite')
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('CREATE TABLE IF NOT EXISTS events (id TEXT PRIMARY KEY, time INTEGER, uuid TEXT, name TEXT, type TEXT, text TEXT, data TEXT)')
        self.db.execute('CREATE INDEX IF NOT EXISTS player_time ON events(uuid,time)')
        self.offsets={}
        self.pending={}
        self.pending_actions={}
        self.import_logs()
    def import_logs(self):
        people={p.get('name'):p.get('uuid') for p in read_json(ROOT/'usercache.json',[]) if p.get('name')}
        for path in sorted((ROOT/'logs').glob('*.log*')):
            if path.stat().st_size>20_000_000: continue
            try:
                text=gzip.decompress(path.read_bytes()).decode('utf-8',errors='replace') if path.suffix=='.gz' else path.read_text(encoding='utf-8',errors='replace')
                day=path.name[:10] if re.match(r'\d{4}-\d{2}-\d{2}',path.name) else datetime.datetime.fromtimestamp(path.stat().st_mtime).strftime('%Y-%m-%d')
                for line in text.splitlines():
                    match=re.match(r'\[(\d{2}:\d{2}:\d{2})\].*?\]: (.*)',line)
                    if not match:continue
                    clock,message=match.groups()
                    names=[name for name in people if re.search(r'\b'+re.escape(name)+r'\b',message)]
                    for name in names:
                        event={'id':hashlib.sha256((day+line+name).encode()).hexdigest(),'uuid':people[name],'name':name,'type':'historical_log','text':message,'source':'Minecraft log',
                               'time':int(datetime.datetime.fromisoformat(day+'T'+clock).timestamp()*1000)}
                        join=re.search(re.escape(name)+r'\[/([^\]]+)\] logged in',message)
                        if join:event['ip']=join.group(1).rsplit(':',1)[0];event['type']='historical_join'
                        self.add(event)
            except (OSError,ValueError):continue
    def add(self,event):
        self.db.execute('INSERT OR IGNORE INTO events VALUES (?,?,?,?,?,?,?)',
            (event.get('id',str(uuid.uuid4())),event.get('time',int(time.time()*1000)),event.get('uuid',''),event.get('name',''),event.get('type','note'),event.get('text',''),json.dumps(event)))
        self.db.commit()
    def sync(self):
        for path in sorted(DATA.glob('events-*.jsonl')):
            offset=self.offsets.get(str(path),0)
            try:
                if path.stat().st_size<offset: offset=0
                with path.open('rb') as f:
                    f.seek(offset)
                    while True:
                        begin=f.tell(); line=f.readline()
                        if not line or not line.endswith(b'\n'): f.seek(begin); break
                        try: self.add(json.loads(line))
                        except (ValueError,sqlite3.Error): pass
                    self.offsets[str(path)]=f.tell()
            except OSError: pass
    def events(self,uid=None,search='',limit=500):
        sql='SELECT data FROM events WHERE 1=1'; params=[]
        if uid: sql+=' AND uuid=?'; params.append(uid)
        if search: sql+=' AND (text LIKE ? OR name LIKE ? OR type LIKE ?)'; params += ['%'+search+'%']*3
        sql+=' ORDER BY time DESC LIMIT ?'; params.append(limit)
        events=[json.loads(row[0]) for row in self.db.execute(sql,params)]
        for event in events:
            # Version 0.1.0 stored this misencoded separator in admin replies.
            # Repair only its first occurrence for display; retain the original
            # database record and leave player/chat/log text untouched.
            if event.get('type')=='admin_result' and not event.get('text_format') and isinstance(event.get('text'),str):
                event['text']=event['text'].replace(' \u00e2\u20ac\u201d ',' \u2014 ',1)
        return events
    def status(self):
        s=read_json(DATA/'status.json')
        s['fresh']=bool(s.get('online') and time.time()*1000-s.get('time',0)<12000)
        return s
    def players(self,status):
        result={}
        for p in read_json(ROOT/'usercache.json',[]):
            if p.get('uuid'): result[p['uuid']]={'uuid':p['uuid'],'name':p.get('name','Unknown'),'online':False}
        for path in (DATA/'players').glob('*.json'):
            data=read_json(path)
            if data.get('uuid'): result.setdefault(data['uuid'],{}).update(data,online=False,source='Last bridge snapshot')
        for uid in list(result):
            saved=saved_player(uid)
            if saved and saved.get('time',0)>result[uid].get('time',0): result[uid].update(saved)
        if status.get('fresh'):
            for data in status.get('players',[]): result.setdefault(data['uuid'],{}).update(data,online=True,source='Live \u00b7 refreshes every 2 seconds')
        ops={p['uuid'] for p in read_json(ROOT/'ops.json',[]) if 'uuid' in p}
        bans={p.get('uuid') for p in read_json(ROOT/'banned-players.json',[])}
        for p in result.values():
            p['op']=p['uuid'] in ops if not p.get('online') else p.get('op',False); p['banned']=p['uuid'] in bans
            if not p.get('ip'):
                for event in self.events(p['uuid'],limit=1000):
                    if event.get('ip'):p['ip']=event['ip'];break
        return sorted(result.values(),key=lambda p:(not p.get('online'),p.get('name','').lower()))
    def command(self,command,uid='',name=''):
        if not command.strip() or '\n' in command or '\r' in command or len(command)>4096: raise ValueError('Enter one valid console command.')
        status=self.status()
        if not status.get('fresh'): raise ValueError('Start the server and wait for the bridge to connect.')
        key=str(uuid.uuid4())
        atomic_json(DATA/'inbox'/f'{key}.json',{'command':command.lstrip('/'),'session':status['session'],'time':int(time.time()*1000)})
        self.pending[key]=(time.time(),command,uid,name)
        return key
    def replies(self):
        result=[]
        for key,(sent,command,uid,name) in list(self.pending.items()):
            p=DATA/'replies'/f'{key}.json'
            reply=read_json(p)
            if reply or time.time()-sent>35:
                reply=reply or {'ok':False,'message':'No acknowledgement received. Check console before retrying.'}
                action=self.pending_actions.pop(key,None)
                if action:reply={**reply,'request_id':key,'action':action[0]}
                result.append((command,reply))
                self.add({'uuid':uid,'name':name,'type':'admin_result','text':command+' \u2014 '+reply.get('message',''),'text_format':1,'ok':reply.get('ok',False)})
                self.pending.pop(key)
                if p.exists(): p.unlink()
        return result

    def action_pending(self,action,payload):
        subject=action_subject(action,payload)
        return any(action_subject(kind,data)==subject for kind,data in self.pending_actions.values())

    def action(self,action,payload,uid='',name=''):
        payload=validate_action(action,payload)
        status=self.status()
        if not status.get('fresh'):raise ValueError('Start the server and wait for the bridge to connect.')
        if status.get('features',{}).get(FEATURES[action]) is not True:
            raise ValueError('This server needs the updated MCyard management bridge for that action.')
        if self.action_pending(action,payload):raise ValueError('This item or player already has an action waiting for acknowledgement.')
        key=str(uuid.uuid4())
        atomic_json(DATA/'inbox'/f'{key}.json',{'action':action,'payload':payload,'session':status['session'],'time':int(time.time()*1000)})
        self.pending[key]=(time.time(),action_description(action,payload),uid,name)
        self.pending_actions[key]=(action,payload)
        return key


def player_command(action,player,argument=''):
    name=player.get('name','')
    if not re.fullmatch(r'[A-Za-z0-9_]{1,16}',name): raise ValueError('Invalid Minecraft player name.')
    if '\n' in argument or '\r' in argument: raise ValueError('Invalid argument')
    if action in ('op','deop','pardon','kill'): return f'{action} {name}'
    if action in ('kick','ban'): return f'{action} {name} {argument or "By server administrator"}'
    if action=='gamemode':
        if argument not in ('survival','creative','adventure','spectator'): raise ValueError('Invalid gamemode')
        return f'gamemode {argument} {name}'
    if action=='spawnpoint': return f'execute at {name} run spawnpoint {name} ~ ~ ~'
    if action in ('whitelist add','whitelist remove'): return f'{action} {name}'
    if action=='tp':
        if not re.fullmatch(r'-?\d+(?:\.\d+)? -?\d+(?:\.\d+)? -?\d+(?:\.\d+)?',argument): raise ValueError('Use three numeric coordinates, e.g. 100 70 -200.')
        return f'execute at {name} run tp {name} {argument}'
    raise ValueError('Unsupported action')
