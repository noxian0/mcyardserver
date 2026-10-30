"""Launch arguments and ordinary server-console state, independent of Qt."""
from pathlib import Path
import re
import time


def java_arguments(root,config):
    root=Path(root).resolve();memory=config.get('memory_mb',4096)
    if isinstance(memory,bool) or not isinstance(memory,int) or not 2048<=memory<=32768:
        raise ValueError('RAM must be between 2048 and 32768 MB.')
    launch=config.get('launch') or {'kind':'jar','target':config.get('launcher','')}
    if not isinstance(launch,dict):raise ValueError('Invalid server launch configuration.')
    target=launch.get('target','');kind=launch.get('kind')
    if not isinstance(target,str) or not target or '\\' in target or ':' in target or target.startswith('-'):
        raise ValueError('Invalid server launcher path.')
    relative=Path(target);path=root/relative
    if relative.is_absolute() or '..' in relative.parts or not path.resolve().is_relative_to(root) or not path.is_file():
        raise ValueError('The server launcher is missing or outside its server folder.')
    if any(p.is_symlink() or (hasattr(p,'is_junction') and p.is_junction()) for p in [path,*path.parents] if p!=root and p.is_relative_to(root)):
        raise ValueError('The server launcher cannot use linked files or folders.')
    initial=config.get('initial_memory_mb',1024)
    if isinstance(initial,bool) or not isinstance(initial,int) or not 256<=initial<=32768:
        raise ValueError('Initial RAM must be between 256 and 32768 MB.')
    flags=[f'-Xms{min(initial,memory)}M',f'-Xmx{memory}M']
    timezone=config.get('timezone','')
    if timezone:
        if not isinstance(timezone,str) or not re.fullmatch(r'[A-Za-z_+-]+(?:/[A-Za-z0-9_+-]+)*',timezone):
            raise ValueError('The configured Java timezone is invalid.')
        flags.append('-Duser.timezone='+timezone)
    if kind=='jar' and len(relative.parts)==1 and relative.suffix.lower()=='.jar':return flags+['-jar',target,'nogui']
    if kind=='args' and relative.parts[0]=='libraries' and relative.name=='win_args.txt':return flags+['@'+target,'nogui']
    raise ValueError('Unsupported server launcher. Recreate the server with the setup wizard.')


class ConsoleSession:
    """Track only facts printed by the Java process owned by this window."""
    def __init__(self):
        self.ready=False;self.started=0;self.names=set();self.ips={};self.uuids={};self.pending=''

    def feed(self,text):
        self.pending+=text;events=[]
        lines=self.pending.split('\n');self.pending=lines.pop()[-16000:]
        for line in lines:
            message=line.strip().split(']: ',1)[-1]
            if re.fullmatch(r'Done \([\d.,]+s\)! For help, type "help".*',message):
                self.ready=True;self.started=int(time.time()*1000)
                events.append({'type':'server','text':'Server ready'})
            match=re.fullmatch(r'UUID of player ([A-Za-z0-9_]{1,16}) is ([a-fA-F0-9-]{36})',message)
            if match:self.uuids[match[1]]=match[2]
            match=re.fullmatch(r'([A-Za-z0-9_]{1,16})\[/([^\]]+)\] logged in with entity id .*',message)
            if match:self.ips[match[1]]=match[2].rsplit(':',1)[0]
            match=re.fullmatch(r'([A-Za-z0-9_]{1,16}) (joined|left) the game',message)
            if match:
                name,action=match.groups()
                self.names.add(name) if action=='joined' else self.names.discard(name)
                events.append({'type':'join' if action=='joined' else 'leave','name':name,
                               'uuid':self.uuids.get(name,''),'ip':self.ips.get(name,''),'text':message})
        return events
