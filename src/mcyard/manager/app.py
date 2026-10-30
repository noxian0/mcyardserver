from pathlib import Path
import json
import os
import re
import sys
import time
from PySide6.QtCore import Qt, QTimer, QProcess, QLockFile, QUrl
from PySide6.QtGui import QDesktopServices, QShortcut, QKeySequence
from PySide6.QtWidgets import (QApplication,QMainWindow,QComboBox,QLineEdit,
    QTableWidgetItem,QMessageBox,QInputDialog,QFileDialog,QDialog,QVBoxLayout,
    QTextEdit,QDialogButtonBox)
from .core import ROOT,DATA,Store,properties,save_properties,read_json,location,timestamp,player_command,saved_rules,world_locked,atomic_json
from .theme import STYLE
from .layout import Layout,button,cells
from .ui_components import BoolSwitch
from ..paths import resource_path,launch_command
from ..java_runtime import validate_java
from ..mods import list_mods,set_mod_enabled,mod_signature
from .runtime import java_arguments,ConsoleSession
from .world_clock import WorldClock,ConsoleWorldClock
from .ui_components import PanoramaHeader
from .player_tools import PlayerToolsMixin


class Window(PlayerToolsMixin,Layout,QMainWindow):
    def __init__(self):
        super().__init__()
        self.store=Store();self.state={};self.people=[];self.selected=None;self.rules_widgets={}
        self.process=None;self.backup_process=None;self.restarting=False;self.close_when_stopped=False
        self.operation='';self.log_size=-1;self.console_text='';self.last_activity=None
        self.current_items={};self.session=ConsoleSession();self.mod_signature=None;self.mod_entries=[]
        self.config=read_json(ROOT/'mcyard.json')
        self.world_clock=WorldClock(ROOT)
        self.console_clock=ConsoleWorldClock()
        self.build_shell()
        self.shortcuts=[]
        for i in range(8):
            shortcut=QShortcut(QKeySequence(f'Ctrl+{i+1}'),self)
            shortcut.activated.connect(lambda index=i:self.nav.setCurrentRow(index));self.shortcuts.append(shortcut)
        console_shortcut=QShortcut(QKeySequence('Ctrl+L'),self)
        console_shortcut.activated.connect(self.focus_console);self.shortcuts.append(console_shortcut)
        self.timer=QTimer(self);self.timer.timeout.connect(self.refresh);self.timer.start(2000)
        self.refresh()

    def focus_console(self):
        self.nav.setCurrentRow(4);self.command_input.setFocus()

    def notice(self,text,error=False):
        self.statusBar().showMessage(text,20000)
        if error: QMessageBox.warning(self,'MCyard Server',text)

    def bridge_enabled(self):
        return self.config.get('capabilities',{}).get('bridge',self.config.get('server_type','fabric')=='fabric' and self.config.get('mc_version')=='26.3')

    def live_backups_enabled(self):
        return self.config.get('capabilities',{}).get('live_backups',self.bridge_enabled())

    def owns_process(self):
        return bool(self.process and self.process.state()!=QProcess.ProcessState.NotRunning)

    def send(self,command,player=None):
        try:
            command=command.strip().lstrip('/')
            if not command or any(c in command for c in '\r\n\x00') or len(command)>4096:raise ValueError('Enter one valid console command.')
            if command.startswith('simplebackups ') and not self.live_backups_enabled():raise ValueError('Stop the server to create a full backup.')
            if self.bridge_enabled() and self.state.get('fresh'):
                self.store.command(command,(player or {}).get('uuid',''),(player or {}).get('name',''))
            elif self.owns_process():
                if self.process.write((command+'\n').encode('utf-8'))<0:raise ValueError('The server console is unavailable.')
                self.store.add({'type':'admin_command','uuid':(player or {}).get('uuid',''),'name':(player or {}).get('name',''),'text':command+' · sent to console'})
            else:raise ValueError('Start this server here before sending commands.')
            self.notice('Sent: '+command)
        except Exception as e:self.notice(str(e),True)

    def send_action(self,action,payload,player=None):
        try:
            player=player or {}
            key=self.store.action(action,payload,player.get('uuid',''),player.get('name',''))
            self.notice('Waiting for the server to confirm the player action…')
            return key
        except Exception as exc:
            self.notice(str(exc),True);return None

    def action_pending(self,action,payload):
        return self.store.action_pending(action,payload) if hasattr(self.store,'action_pending') else False

    def save_ram(self):
        try:
            value=self.ram.value()
            if not 2048<=value<=32768:raise ValueError('Choose 2048–32768 MB of RAM.')
            config=read_json(ROOT/'mcyard.json')
            if not config:raise ValueError('Server configuration could not be read.')
            config['memory_mb']=value;atomic_json(ROOT/'mcyard.json',config);self.config=config
            self.notice(f'RAM saved: {value/1024:g} GB. Applies on next start.')
        except Exception as exc:self.notice(str(exc),True)

    def open_mods_folder(self):
        try:
            list_mods(ROOT,self.config)  # Validate that the folder is local before opening it.
            (ROOT/'mods').mkdir(exist_ok=True);self.open_folder(ROOT/'mods')
        except Exception as exc:self.notice(str(exc),True)

    def render_mods(self,force=False):
        try:
            signature=mod_signature(ROOT)
            if force or signature!=self.mod_signature:
                self.mod_entries=list_mods(ROOT,self.config);self.mod_signature=signature
                cells(self.mods_table,[(m['name'],m['version'],m['filename'],'Required' if m['protected'] else ('Enabled' if m['enabled'] else 'Disabled'),'') for m in self.mod_entries])
                for r,mod in enumerate(self.mod_entries):
                    toggle=button('Disable' if mod['enabled'] else 'Enable',lambda checked=False,m=mod:self.toggle_mod(m),'quiet','stop' if mod['enabled'] else 'play')
                    toggle.setToolTip('Required for live management and capped backups' if mod['protected'] else mod['error'] or 'Rename this JAR to change whether the loader uses it')
                    self.mods_table.setCellWidget(r,4,toggle)
                    if mod['error']:self.mods_table.item(r,0).setToolTip(mod['error'])
            busy=self.running();vanilla=self.config.get('server_type')=='vanilla'
            for r,mod in enumerate(self.mod_entries):
                self.mods_table.cellWidget(r,4).setEnabled(not busy and not mod['unsafe'] and not (mod['protected'] and mod['enabled']))
            self.mods_hint.setText('Vanilla does not load mods. Create a Fabric or Forge server to use them.' if vanilla else ('Stop the server to change mods.' if busy else 'Enable or disable mods for the next start. Files stay in this folder.'))
        except (OSError,ValueError) as exc:
            self.mods_table.setRowCount(0);self.mod_signature=None;self.mods_hint.setText(str(exc))

    def toggle_mod(self,mod):
        try:
            path=set_mod_enabled(ROOT,mod['filename'],not mod['enabled'],self.config,server_running=self.running())
            self.notice(('Enabled: ' if mod['enabled']==False else 'Disabled: ')+path.name)
            self.render_mods(force=True)
        except Exception as exc:self.notice(str(exc),True)

    def selected_player(self): return next((p for p in self.people if p['uuid']==self.selected),None)

    def player_action(self,action):
        p=self.selected_player()
        if not p: return
        argument=''
        if action in ('kick','ban'):
            argument,ok=QInputDialog.getText(self,action.title()+' '+p['name'],'Reason:',text='By server administrator')
            if not ok:return
        if action=='kill':
            if not p.get('online'):return self.notice('Select an online player.',True)
            if QMessageBox.question(self,'Kill player',f'Kill {p["name"]}?\nMinecraft’s normal death rules will apply.',
                QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)!=QMessageBox.StandardButton.Yes:return
        if action in ('ban','op','spawnpoint'):
            if QMessageBox.question(self,'Confirm action',f'{action.replace("spawnpoint","Set spawn at current position for").upper()} {p["name"]}?')!=QMessageBox.StandardButton.Yes:return
        if action=='gamemode': argument=self.mode.currentText()
        if action=='tp':
            argument,ok=QInputDialog.getText(self,'Teleport '+p['name'],'X Y Z (in the player’s current dimension):')
            if not ok:return
        try:self.send(player_command(action,p,argument),p)
        except Exception as e:self.notice(str(e),True)

    def render_players(self):
        term=self.player_search.text().lower(); selected=self.selected
        items=[p for p in self.people if term in p.get('name','').lower()]
        self.player_table.blockSignals(True)
        cells(self.player_table,[(p.get('name','Unknown'),('● Online' if p.get('online') else 'Offline')+(' · OP' if p.get('op') else '')) for p in items])
        for r,p in enumerate(items):
            self.player_table.item(r,0).setData(Qt.ItemDataRole.UserRole,p['uuid'])
            if p['uuid']==selected:self.player_table.selectRow(r)
        self.player_table.blockSignals(False)
        if selected is None and items:
            self.selected=items[0]['uuid']
            self.player_table.selectRow(0)
            self.render_detail()

    def choose_player(self):
        r=self.player_table.currentRow()
        if r>=0 and self.player_table.item(r,0):self.selected=self.player_table.item(r,0).data(Qt.ItemDataRole.UserRole)
        self.render_detail()

    def render_detail(self):
        p=self.selected_player(); active=self.state.get('fresh',False) or (self.owns_process() and self.session.ready)
        for b,a in self.action_buttons:b.setEnabled(bool(p and active and (p.get('online') or a in ('op','deop','ban','pardon','whitelist add','whitelist remove'))))
        self.mode_btn.setEnabled(bool(p and active and p.get('online')))
        self.update_player_tools(p,active)
        if not p:
            self.player_name.setText('Select a player');self.player_source.clear()
            self.facts.setRowCount(0);self.inv_list.setRowCount(0);self.player_events.setRowCount(0);self.current_items={}
            for slot in self.slots:slot.setText('');slot.setEnabled(False)
            return
        self.player_name.setText(p.get('name','Unknown')+('  ·  OP' if p.get('op') else ''))
        self.player_source.setText(p.get('source','Not yet recorded')+'  ·  '+timestamp(p.get('time')))
        spawn=p.get('spawn',{})
        facts=[('UUID',p['uuid']),('IP address',p.get('ip','Not recorded yet')),('Gamemode',p.get('mode','Unknown')),
               ('Health / food / XP',f"{p.get('health','—')} / {p.get('food','—')} / {p.get('xp','—')}"),
               ('Position',location(p.get('position'))),('Spawn point',location(spawn)),('Spawn type',spawn.get('source','Not recorded')),
               ('Last death',location(p.get('lastDeath'))),('Access','Banned' if p.get('banned') else 'Not banned')]
        cells(self.facts,facts)
        inv=p.get('ender' if self.inventory_kind.currentIndex() else 'inventory',[])
        self.current_items={str(i.get('slot')):i for i in inv}
        slots=[str(i) for i in range(36)]+['head','chest','legs','feet','offhand']
        for index,b in enumerate(self.slots):
            key=slots[index]; item=self.current_items.get(key)
            b.setVisible(self.inventory_kind.currentIndex()==0 or index<27)
            name=(item.get('name') or item.get('id','').split(':')[-1].replace('_',' ')) if item else ''
            b.setText((name[:22]+'\n×'+str(item.get('count',1))) if item else (key if index<36 else key.title()))
            b.setToolTip((name+'\nSlot '+key) if item else 'Empty slot '+key)
            b.setEnabled(bool(item))
        cells(self.inv_list,[(i.get('slot'),i.get('name',i.get('id','')),i.get('count',1)) for i in inv])
        self.fill_events(self.player_events,self.store.events(p['uuid'],limit=200),player_view=True)

    def inspect_item(self,index):
        self.open_item_tools(index)

    def show_json(self,title,data):
        dialog=QDialog(self); dialog.setWindowTitle(title); dialog.resize(640,480); box=QVBoxLayout(dialog)
        text=QTextEdit(); text.setReadOnly(True); text.setPlainText(json.dumps(data,indent=2,ensure_ascii=False));box.addWidget(text)
        close=QDialogButtonBox(QDialogButtonBox.StandardButton.Close);close.rejected.connect(dialog.reject);box.addWidget(close);dialog.exec()

    def fill_events(self,t,events,player_view=False):
        values=[(timestamp(e.get('time')),e.get('type'),e.get('text')) if player_view else (timestamp(e.get('time')),e.get('name') or 'Server',e.get('type'),e.get('text')) for e in events]
        cells(t,values)
        for i,e in enumerate(events):t.item(i,0).setData(Qt.ItemDataRole.UserRole,e)

    def event_detail(self,t,r):
        item=t.item(r,0)
        if item:self.show_json('Event details',item.data(Qt.ItemDataRole.UserRole))

    def render_activity(self):
        events=self.store.events(search=self.activity_search.text())
        self.fill_events(self.activity,events)
        recent=self.store.events(limit=8)
        cells(self.recent,[(timestamp(e.get('time'))[12:] if e.get('time') else '—',e.get('name') or 'Server',e.get('text')) for e in recent])

    def render_rules(self):
        rules=self.state.get('rules') or saved_rules() or read_json(DATA/'rules.json')
        if set(rules)!=set(self.rules_widgets):
            self.rules_widgets={}; self.rule_table.setRowCount(len(rules))
            priority=['pvp','fire_spread_radius_around_player','fire_damage','keep_inventory','mob_griefing','tnt_explodes','players_sleeping_percentage']
            ordered=sorted(rules,key=lambda x:(priority.index(x.removeprefix('minecraft:')) if x.removeprefix('minecraft:') in priority else 99,x))
            for r,key in enumerate(ordered):
                info=rules[key]; human=key.removeprefix('minecraft:').replace('_',' ').capitalize()
                item=QTableWidgetItem(human); item.setToolTip(key); self.rule_table.setItem(r,0,item)
                if info.get('type')=='bool':
                    editor=BoolSwitch();editor.addItems(['true','false']);editor.setCurrentText(info['value'])
                else:
                    editor=QLineEdit(str(info['value']));editor.setMaximumWidth(150)
                apply=button('Set',lambda checked=False,k=key:self.apply_rule(k),'quiet','check')
                self.rule_table.setCellWidget(r,2,editor);self.rule_table.setCellWidget(r,3,apply)
                self.rules_widgets[key]=(r,editor,apply)
            self.filter_rules()
        for key,(r,editor,apply) in self.rules_widgets.items():
            value=str(rules[key]['value']);self.rule_table.setItem(r,1,QTableWidgetItem({'true':'On','false':'Off'}.get(value,value)))
            apply.setEnabled(self.state.get('fresh',False))
            editor.setEnabled(self.state.get('fresh',False))
        self.rule_status.setText(('Live' if self.bridge_enabled() else 'Saved values · console changes') if self.state.get('fresh') else 'Saved · start to edit')

    def apply_rule(self,key):
        _,editor,_=self.rules_widgets[key]
        value=editor.currentText() if isinstance(editor,QComboBox) else editor.text().strip()
        if value not in ('true','false') and not re.fullmatch(r'-?\d+',value):return self.notice('Enter true, false, or a whole number.',True)
        self.send(f'gamerule {key} {value}')

    def filter_rules(self):
        term=self.rule_search.text().lower()
        for key,(r,_,_) in self.rules_widgets.items(): self.rule_table.setRowHidden(r,term not in key.replace('_',' ').lower() and term not in key.lower())

    def filter_settings(self):
        term=self.settings_search.text().lower()
        group=self.settings_group.currentText()
        essentials={'motd','max-players','difficulty','gamemode','hardcore','white-list','online-mode','view-distance','simulation-distance','spawn-protection','allow-flight','enable-command-block','server-port','pause-when-empty-seconds'}
        network={'server-ip','server-port','online-mode','white-list','enforce-whitelist','enable-query','query.port','enable-rcon','rcon.port','network-compression-threshold','prevent-proxy-connections','rate-limit','hide-online-players'}
        performance={'view-distance','simulation-distance','max-tick-time','sync-chunk-writes','use-native-transport','entity-broadcast-range-percentage','pause-when-empty-seconds','max-chained-neighbor-updates','region-file-compression'}
        world={'level-name','level-seed','level-type','generate-structures','generator-settings','gamemode','force-gamemode','hardcore','difficulty','spawn-protection','allow-flight','enable-command-block','max-world-size'}
        subset={'Essentials':essentials,'Network':network,'Performance':performance,'World':world}.get(group)
        for r in range(self.settings_table.rowCount()):
            item=self.settings_table.item(r,0);key=item.data(Qt.ItemDataRole.UserRole)
            matches=term in key.lower() or term in item.text().lower()
            self.settings_table.setRowHidden(r,not matches or (not term and subset is not None and key not in subset))

    def apply_settings(self):
        if self.running():return self.notice('Stop the server before changing server.properties.',True)
        changes={k:(w.currentText() if isinstance(w,QComboBox) else w.text()) for k,w in self.settings_widgets.items()}
        changes={k:v for k,v in changes.items() if v!=self.initial_properties.get(k)}
        if not changes:return self.notice('No settings changed.')
        try:
            for key in ['server-port','query.port','rcon.port']:
                if key in changes and not 1<=int(changes[key])<=65535:raise ValueError(key+' must be between 1 and 65535.')
            for key in ['view-distance','simulation-distance']:
                if key in changes and not 2<=int(changes[key])<=32:raise ValueError(key+' must be between 2 and 32.')
            if 'max-players' in changes and int(changes['max-players'])<1:raise ValueError('max-players must be positive.')
            if 'level-name' in changes and changes['level-name']!='world':raise ValueError('Changing the world folder requires updating the backup workflow. Keep level-name=world here.')
            if any(k in changes for k in ['online-mode','white-list','enforce-whitelist','server-ip','server-port']):
                if QMessageBox.question(self,'Connection settings','These changes affect who can connect. Save them for the next start?')!=QMessageBox.StandardButton.Yes:return
            save_properties(changes);self.initial_properties.update(changes)
            if 'server-port' in changes:
                self.config['port']=int(changes['server-port']);atomic_json(ROOT/'mcyard.json',self.config)
            self.store.add({'type':'settings','text':'Updated: '+', '.join(changes)})
            self.notice('Settings saved. They will apply next start.')
        except Exception as e:self.notice(str(e),True)

    def console_send(self):
        command=self.command_input.text().strip()
        if command:self.send(command);self.command_input.clear()

    def render_log(self):
        term=self.log_filter.text().lower(); lines=self.console_text.splitlines()
        if term:lines=[line for line in lines if term in line.lower()]
        bar=self.console.verticalScrollBar();at_bottom=bar.value()>=bar.maximum()-5
        self.console.setPlainText('\n'.join(lines[-2500:]))
        if at_bottom:bar.setValue(bar.maximum())

    def running(self):return bool(self.state.get('fresh') or (self.process and self.process.state()!=QProcess.ProcessState.NotRunning) or self.operation or world_locked())

    def start_server(self):
        if self.running():return
        if not (ROOT/'world/level.dat').is_file():
            self.notice('First start: downloading libraries and creating your world…')
            self.launch_java();return
        self.operation='Backing up';self.notice('Creating a verified full snapshot before startup…')
        self.run_backup(self.launch_java)

    def launch_java(self):
        try:
            config=read_json(ROOT/'mcyard.json')
            if not config:raise ValueError('Server configuration could not be read.')
            self.config=config
            required=int(self.config.get('java_required',25))
            java=validate_java(self.config['java_path'],required=required)
            if self.config.get('server_type')=='forge' and java['major']!=required:
                raise ValueError(f'This Forge server needs Java {required}; selected Java is {java["major"]}.')
            arguments=java_arguments(ROOT,self.config)
        except (KeyError,TypeError,ValueError,OSError) as exc:
            self.operation='';self.notice(str(exc),True);return
        self.session=ConsoleSession();self.console_clock=ConsoleWorldClock();self.log_size=-1;self.console_text=''
        self.process=QProcess(self);self.process.setWorkingDirectory(str(ROOT));self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.process.readyReadStandardOutput.connect(self.drain_server)
        self.process.finished.connect(self.server_finished)
        self.process.errorOccurred.connect(self.server_error)
        self.operation='Starting';self.process.start(java['path'],arguments)
        self.refresh()

    def drain_server(self):
        output=bytes(self.process.readAllStandardOutput()).decode('utf-8',errors='replace')
        if output:
            self.console_clock.feed(output)
            self.console_text=(self.console_text+output)[-500000:];self.render_log()
            events=self.session.feed(output)
            if not self.bridge_enabled():
                for event in events:self.store.add(event)
            if self.session.ready and self.operation=='Starting':self.operation='';self.refresh()

    def server_error(self,error):
        if error==QProcess.ProcessError.FailedToStart:
            self.operation='';self.restarting=False;self.close_when_stopped=False
            self.notice('Could not run Java: '+self.process.errorString(),True)

    def stop_server(self):
        if self.operation in ('Backing up','Stopping'):return
        if self.state.get('fresh'):
            self.operation='Stopping';self.send('stop')
        elif self.process and self.process.state()!=QProcess.ProcessState.NotRunning:
            self.operation='Stopping';self.process.write(b'stop\n')
        self.refresh()

    def restart_server(self):
        if QMessageBox.question(self,'Restart server','Disconnect players, save the world, then restart?')!=QMessageBox.StandardButton.Yes:return
        if self.process and self.process.state()!=QProcess.ProcessState.NotRunning:
            self.restarting=True;self.stop_server()
        else:self.notice('This server was launched elsewhere. Stop it here, then use Start server.',True)

    def server_finished(self,code,status):
        self.operation='';self.state['fresh']=False;self.session.ready=False;self.session.names.clear()
        if code!=0:
            self.restarting=False;self.close_when_stopped=False
            self.notice(f'Server exited with code {code}. Check Console for details.',True);return
        def done():
            self.operation=''
            if self.restarting:self.restarting=False;self.launch_java()
            elif self.close_when_stopped:self.close_when_stopped=False;self.close()
        self.operation='Backing up';self.run_backup(done)

    def run_backup(self,after=None):
        if self.backup_process and self.backup_process.state()!=QProcess.ProcessState.NotRunning:return
        self.backup_process=QProcess(self);self.backup_process.setWorkingDirectory(str(ROOT))
        self.backup_process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        output=[]
        self.backup_process.readyReadStandardOutput.connect(lambda:output.append(bytes(self.backup_process.readAllStandardOutput()).decode(errors='replace')))
        def finished(code,status):
            self.operation=''
            if code==0:
                self.notice('Full backup verified.');self.store.add({'type':'backup','text':'Full server snapshot verified'})
                if after:after()
            else:
                self.restarting=False;self.close_when_stopped=False
                log=ROOT/'manager/data/backup-last.log'
                detail=log.read_text(encoding='utf-8',errors='replace') if log.exists() else ''.join(output)
                self.notice('Backup failed.\n'+detail[-2000:],True)
            self.refresh()
        self.backup_process.finished.connect(finished)
        def backup_error(error):
            if error==QProcess.ProcessError.FailedToStart:
                self.operation='';self.restarting=False;self.close_when_stopped=False
                self.notice('Could not start backup: '+self.backup_process.errorString(),True)
        self.backup_process.errorOccurred.connect(backup_error)
        program,arguments=launch_command('--backup',str(ROOT))
        self.backup_process.start(program,arguments)

    def backup(self):
        if self.state.get('fresh') and self.live_backups_enabled():self.send('simplebackups backup start')
        elif not self.running():self.operation='Backing up';self.run_backup()
        else:self.notice('Stop this server before taking a full backup.')

    def render_backups(self):
        used=0;archives=[]
        for p in (ROOT/'backups').rglob('*'):
            try:
                if p.is_file() and not p.is_symlink():
                    stat=p.stat();used+=stat.st_size
                    if p.suffix=='.zip':archives.append((p,stat))
            except FileNotFoundError:continue  # Retention may remove a file during refresh.
        self.backup_usage.setText(f'{used/1_000_000_000:.2f} / 50 GB')
        self.backup_progress.setValue(min(1000,int(used/50_000_000)))
        archives=sorted(archives,key=lambda pair:pair[1].st_mtime,reverse=True)[:200]
        cells(self.backup_table,[(timestamp(int(stat.st_mtime*1000)),str(p.relative_to(ROOT/'backups')),f'{stat.st_size/1024/1024:.1f} MB') for p,stat in archives])
        for r,(p,_) in enumerate(archives):self.backup_table.item(r,0).setData(Qt.ItemDataRole.UserRole,str(p))

    def open_backup(self,r,c):
        p=self.backup_table.item(r,0).data(Qt.ItemDataRole.UserRole)
        self.open_folder(Path(p).parent)

    def open_folder(self,path):QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def export_history(self):
        path,_=QFileDialog.getSaveFileName(self,'Export history',str(ROOT/'player-history.json'),'JSON (*.json)')
        if path:Path(path).write_text(json.dumps(self.store.events(search=self.activity_search.text(),limit=100000),indent=2),encoding='utf-8');self.notice('History exported.')

    def refresh(self):
        try:
            self.store.sync();self.state=self.store.status() if self.bridge_enabled() else {'fresh':self.owns_process() and self.session.ready,'started':self.session.started}
            if self.owns_process() and self.session.ready and not self.operation and not self.state.get('world'):
                command=self.console_clock.next_command(self.config.get('mc_version',''))
                if command:self.process.write((command+'\n').encode('utf-8'))
                world=self.console_clock.world()
                if world:self.state['world']=world
            online=self.state.get('fresh',False)
            if online and self.operation=='Starting':self.operation=''
            if not online and self.operation=='Stopping' and (not self.process or self.process.state()==QProcess.ProcessState.NotRunning):self.operation=''
            busy=self.running();status=self.operation or ('Online' if online else ('World in use' if world_locked() else 'Offline'))
            lighting=self.world_clock.update(self.state,running=bool(online or self.owns_process() or world_locked()))
            for header in self.findChildren(PanoramaHeader):header.set_world_state(**lighting)
            self.state_label.setText(status.upper())
            controllable=online or (self.process and self.process.state()!=QProcess.ProcessState.NotRunning)
            self.start_btn.setEnabled(not busy);self.stop_btn.setEnabled(bool(controllable and self.operation not in ('Backing up','Stopping')))
            self.restart_btn.setEnabled(online and not self.operation);self.settings_save.setEnabled(not busy)
            self.settings_hint.setText('Stop the server to edit' if busy else 'Applies on next start')
            self.settings_table.setEnabled(not busy);self.command_send.setEnabled(bool(online or self.owns_process()))
            self.backup_btn.setEnabled(not self.operation and (not busy or (online and self.live_backups_enabled())))
            self.backup_btn.setToolTip('Stop this server to take a full snapshot' if busy and not self.live_backups_enabled() else 'Create a backup within the 50 GB storage limit')
            for index,b in enumerate(self.quick):b.setEnabled(online and not self.operation and (index!=1 or self.live_backups_enabled()))
            self.people=self.store.players(self.state)
            if not self.bridge_enabled():
                for p in self.people:
                    p['online']=online and p.get('name') in self.session.names
                    if p.get('name') in self.session.ips:p['ip']=self.session.ips[p['name']]
                known={p.get('name') for p in self.people}
                for name in self.session.names-known:
                    uid=self.session.uuids.get(name)
                    if uid:self.people.append({'uuid':uid,'name':name,'online':online,'ip':self.session.ips.get(name,''),'source':'Server console'})
            self.render_mods()
            count=sum(p.get('online',False) for p in self.people)
            self.metrics['PLAYERS'].setText(f'{count} / {self.state.get("maxPlayers",properties().get("max-players","10"))}')
            self.metrics['TICK TIME'].setText(f'{self.state.get("mspt",0):.1f} ms' if online and self.bridge_enabled() else '—')
            self.metrics['MEMORY'].setText(f'{self.state.get("memoryUsed",0)/1024**3:.2f} GB' if online and self.bridge_enabled() else '—')
            seconds=int((time.time()*1000-self.state.get('started',time.time()*1000))/1000)
            self.metrics['UPTIME'].setText(f'{seconds//3600}h {(seconds%3600)//60}m' if online else '—')
            for command,reply in self.store.replies():self.notice(command+' · '+reply.get('message',''),not reply.get('ok'))
            self.render_players();self.render_detail();self.render_activity();self.render_rules();self.render_backups()
            log=ROOT/'logs/latest.log'
            if log.exists() and log.stat().st_size!=self.log_size:
                self.log_size=log.stat().st_size
                with log.open('rb') as f:f.seek(max(0,self.log_size-500000));self.console_text=f.read().decode('utf-8',errors='replace')
                self.render_log()
        except Exception as e:self.statusBar().showMessage('Refresh error: '+str(e))

    def closeEvent(self,event):
        owned=self.process and self.process.state()!=QProcess.ProcessState.NotRunning
        if owned:
            answer=QMessageBox.question(self,'Server is running','Stop the server safely, back it up, then close the manager?',QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.Cancel)
            if answer==QMessageBox.StandardButton.Yes:self.close_when_stopped=True;self.stop_server()
            event.ignore()
        elif self.backup_process and self.backup_process.state()!=QProcess.ProcessState.NotRunning:
            self.notice('Please wait for the backup to finish.');event.ignore()
        else:event.accept()

