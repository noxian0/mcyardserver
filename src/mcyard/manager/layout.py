"""Desktop layout, independent of the server transport and lifecycle."""
from pathlib import Path
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QAction
from PySide6.QtWidgets import (QWidget,QHBoxLayout,QVBoxLayout,QGridLayout,QLabel,
    QListWidget,QListWidgetItem,QFrame,QTableWidget,QHeaderView,QAbstractItemView,
    QTableWidgetItem,QLineEdit,QComboBox,QTextEdit,QTabWidget,QSplitter,QMenu,
    QMessageBox,QProgressBar,QSizePolicy,QSpinBox)
from .core import ROOT, properties
from ..paths import resource_path
from ..appearance import AnimationToggle,add_credits
from .ui_components import icon, HoverButton, AnimatedList, AnimatedStack, PanoramaHeader, BoolSwitch


def label(text='',kind=None):
    w=QLabel(text)
    if kind:w.setObjectName(kind)
    return w


def button(text,callback,kind=None,glyph=None,tip=None):
    b=HoverButton(text)
    if kind:b.setObjectName(kind)
    if glyph:b.setIcon(icon(glyph,'#233019' if kind=='primary' else '#a7b49e'))
    b.setIconSize(QSize(17,17));b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.clicked.connect(callback)
    if tip:b.setToolTip(tip)
    b.setAccessibleName(text or tip or glyph or 'Action')
    return b


def row(*widgets):
    w=QWidget();box=QHBoxLayout(w);box.setContentsMargins(0,0,0,0);box.setSpacing(9)
    for item in widgets:
        if item is None:box.addStretch()
        else:box.addWidget(item)
    return w


class DataTable(QTableWidget):
    def paintEvent(self,event):
        super().paintEvent(event)
        if not self.rowCount():
            painter=QPainter(self.viewport());painter.setPen(QColor('#7d8c74'))
            painter.drawText(self.viewport().rect(),Qt.AlignmentFlag.AlignCenter,self.property('emptyText') or 'Nothing here yet')


def table(headers,empty='Nothing here yet'):
    t=DataTable(0,len(headers));t.setHorizontalHeaderLabels(headers);t.setProperty('emptyText',empty)
    t.verticalHeader().hide();t.verticalHeader().setDefaultSectionSize(43)
    t.setAlternatingRowColors(False);t.setShowGrid(False);t.setWordWrap(False)
    t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    t.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    t.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    return t


def cells(t,values):
    t.setRowCount(len(values))
    for r,items in enumerate(values):
        for c,text in enumerate(items):
            item=QTableWidgetItem(str(text));item.setToolTip(str(text));t.setItem(r,c,item)


def columns(t,widths):
    for index,width in enumerate(widths):
        if width:
            t.horizontalHeader().setSectionResizeMode(index,QHeaderView.ResizeMode.Fixed);t.setColumnWidth(index,width)
        else:t.horizontalHeader().setSectionResizeMode(index,QHeaderView.ResizeMode.Stretch)


def search(placeholder,callback):
    edit=QLineEdit();edit.setPlaceholderText(placeholder);edit.setClearButtonEnabled(True)
    edit.addAction(icon('search','#7d8f70'),QLineEdit.ActionPosition.LeadingPosition)
    edit.textChanged.connect(callback);return edit


def page(title,subtitle=''):
    w=QWidget();box=QVBoxLayout(w);box.setContentsMargins(30,22,30,24);box.setSpacing(18)
    header=PanoramaHeader();header.setFixedHeight(86)
    h=QHBoxLayout(header);h.setContentsMargins(0,8,22,8);h.addWidget(label(title,'title'));h.addStretch()
    if subtitle:header.setToolTip(subtitle)
    box.addWidget(header)
    return w,box


class Layout:
    def build_shell(self):
        self.setWindowTitle(self.config.get('name','Server')+' · MCyard Server');self.resize(1340,870);self.setMinimumSize(1120,740)
        self.setWindowIcon(QIcon(str(resource_path('mcyard.svg'))))
        shell=QWidget();shell.setObjectName('shell');outer=QHBoxLayout(shell)
        outer.setContentsMargins(0,0,0,0);outer.setSpacing(0);self.setCentralWidget(shell)
        sidebar=QFrame();sidebar.setObjectName('sidebar');sidebar.setFixedWidth(210)
        side=QVBoxLayout(sidebar);side.setContentsMargins(16,29,16,18);side.setSpacing(23)
        brand=QLabel();brand.setPixmap(QPixmap(str(ROOT/'server-icon.png') if (ROOT/'server-icon.png').exists() else str(resource_path('mcyard.svg'))).scaled(32,32,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))
        if brand.pixmap().isNull():brand.setPixmap(icon('inventory','#b8d988',30).pixmap(30,30))
        side.addWidget(row(brand,label('MCyard Server','section')))
        self.nav=AnimatedList();self.nav.setObjectName('nav');self.nav.setIconSize(QSize(19,19))
        for name,glyph in [('Overview','home'),('Players','users'),('World rules','sliders'),('Settings','settings'),('Console','terminal'),('Backups','archive'),('Activity','history'),('Mods','inventory')]:
            self.nav.addItem(QListWidgetItem(icon(glyph,'#a3b296'),name))
        side.addWidget(self.nav,1)
        side.addWidget(row(button('',lambda:self.open_folder(ROOT),'quiet','folder','Open server folder'),None,button('',self.about,'quiet','more','About & controls')))
        self.pages=AnimatedStack();outer.addWidget(sidebar);outer.addWidget(self.pages,1)
        self.build_overview();self.build_players();self.build_rules();self.build_settings()
        self.build_console();self.build_backups();self.build_activity();self.build_mods()
        self.nav.currentRowChanged.connect(self.pages.setCurrentIndex);self.nav.setCurrentRow(0)
        self.statusBar().setSizeGripEnabled(False)
        self.credits=add_credits(self)

    def about(self):
        QMessageBox.information(self,'MCyard Server','MCyard Server · Local server manager\n\n'
            'Ctrl+1–8  Switch pages\nCtrl+L  Open console\n\n'
            'Optional background images stay on your PC.\n'
            'Original interface icons. No remote administration service.\n\n'
            'NOT AN OFFICIAL MINECRAFT PRODUCT. NOT APPROVED BY OR ASSOCIATED WITH MOJANG OR MICROSOFT.')

    def build_overview(self):
        w=QWidget();box=QVBoxLayout(w);box.setContentsMargins(30,26,30,24);box.setSpacing(21)
        hero=PanoramaHeader();hero.setFixedHeight(267)
        h=QVBoxLayout(hero);h.setContentsMargins(25,23,25,21);h.setSpacing(7)
        self.state_label=label('OFFLINE','pill');h.addWidget(row(label('YOUR WORLD','eyebrow'),None,self.state_label))
        h.addStretch();h.addWidget(label(self.config.get('name','My server'),'heroTitle'))
        props=properties();mode=props.get('gamemode','survival').capitalize()
        h.addWidget(label(f'{mode}  /  {self.config.get("server_type","fabric").title()} {self.config.get("mc_version","26.3")}','muted'));h.addSpacing(14)
        self.start_btn=button('Start server',self.start_server,'primary','play')
        self.stop_btn=button('Stop',self.stop_server,None,'stop');self.restart_btn=button('',self.restart_server,'quiet','restart','Restart server')
        h.addWidget(row(self.start_btn,self.stop_btn,self.restart_btn,None,button('',lambda:self.nav.setCurrentRow(4),'quiet','terminal','Open console')))
        box.addWidget(hero)
        metrics=QFrame();metrics.setObjectName('metrics');strip=QHBoxLayout(metrics);strip.setContentsMargins(6,17,6,17);strip.setSpacing(22);self.metrics={}
        for i,(key,title,glyph) in enumerate([('PLAYERS','Players','users'),('TICK TIME','Tick time','sliders'),('MEMORY','Memory','inventory'),('UPTIME','Uptime','history')]):
            if i:
                line=QFrame();line.setObjectName('divider');strip.addWidget(line)
            stack=QVBoxLayout();stack.setSpacing(4)
            tiny=label();tiny.setPixmap(icon(glyph,'#8b9a7f',14).pixmap(14,14))
            stack.addWidget(row(tiny,label(title,'muted'),None));value=label('—','metric');stack.addWidget(value)
            self.metrics[key]=value;strip.addLayout(stack,1)
        box.addWidget(metrics)
        self.quick=[];actions=row(label('World','section'),None)
        for text,command,glyph in [('Save','save-all flush','save'),('Backup','simplebackups backup start','archive'),('Day','time set day','sun'),('Clear weather','weather clear','cloud')]:
            b=button(text,lambda checked=False,c=command:self.send(c),'quiet',glyph);self.quick.append(b);actions.layout().addWidget(b)
        box.addWidget(actions)
        box.addWidget(row(label('Recent activity','section'),None,button('View all',lambda:self.nav.setCurrentRow(6),'quiet','arrow')))
        self.recent=table(['TIME','PLAYER','EVENT'],'No activity yet');columns(self.recent,[90,160,None]);box.addWidget(self.recent,1)
        self.recent.cellDoubleClicked.connect(lambda r,c:self.nav.setCurrentRow(6))
        self.pages.addWidget(w)

    def build_players(self):
        w,box=page('Players')
        if not self.bridge_enabled():box.addWidget(label('Player actions use the console. Inventory and location details come from saved player files.','muted'))
        self.player_search=search('Find a player',self.render_players);box.addWidget(self.player_search)
        split=QSplitter();split.setHandleWidth(1)
        self.player_table=table(['PLAYER','STATUS'],'No players yet');self.player_table.itemSelectionChanged.connect(self.choose_player)
        columns(self.player_table,[None,85]);self.player_table.setMinimumWidth(210);split.addWidget(self.player_table)
        detail=QWidget();right=QVBoxLayout(detail);right.setContentsMargins(22,0,0,0);right.setSpacing(10)
        self.player_name=label('Select a player','section');self.player_source=label('','muted')
        self.freeze_badge=label('FROZEN','pill');self.freeze_badge.hide()
        right.addWidget(row(self.player_name,None,self.freeze_badge));right.addWidget(self.player_source)
        self.player_tabs=QTabWidget();right.addWidget(self.player_tabs,1)
        profile=QWidget();profile_box=QVBoxLayout(profile);profile_box.setContentsMargins(0,14,0,0);profile_box.setSpacing(13)
        self.facts=table(['DETAIL','VALUE'],'Select a player');columns(self.facts,[145,None]);self.facts.verticalHeader().setDefaultSectionSize(37)
        profile_box.addWidget(self.facts,1)
        controls=row();self.action_buttons=[]
        for text,action,glyph in [('Give OP','op','shield'),('Kick','kick','kick'),('Ban','ban','ban')]:
            b=button(text,lambda checked=False,a=action:self.player_action(a),'danger' if action=='ban' else None,glyph)
            controls.layout().addWidget(b);self.action_buttons.append((b,action))
        more=button('',lambda:None,'quiet','more','More player actions');menu=QMenu(more)
        for text,action,glyph in [('Remove OP','deop','shield'),('Unban','pardon','unban'),('Add to whitelist','whitelist add','users'),('Remove from whitelist','whitelist remove','users'),('Set spawn here','spawnpoint','pin'),('Teleport…','tp','teleport')]:
            a=menu.addAction(icon(glyph),text);a.triggered.connect(lambda checked=False,k=action:self.player_action(k));self.action_buttons.append((a,action))
        menu.addSeparator()
        self.freeze_action=menu.addAction(icon('pin'),'Freeze player')
        self.freeze_action.triggered.connect(self.toggle_player_freeze);self.freeze_action.setEnabled(False)
        kill=menu.addAction(icon('stop'),'Kill player…')
        kill.triggered.connect(lambda checked=False:self.player_action('kill'));self.action_buttons.append((kill,'kill'))
        more.setMenu(menu);controls.layout().addWidget(more);controls.layout().addStretch();profile_box.addWidget(controls)
        self.mode=QComboBox();self.mode.addItems(['survival','creative','adventure','spectator'])
        self.mode_btn=button('Set mode',lambda:self.player_action('gamemode'),None,'check')
        profile_box.addWidget(row(self.mode,self.mode_btn,None));self.player_tabs.addTab(profile,'Profile')
        inv=QWidget();iv=QVBoxLayout(inv);iv.setContentsMargins(0,16,0,0);iv.setSpacing(12)
        self.inventory_kind=QComboBox();self.inventory_kind.addItems(['Inventory + equipment','Ender Chest']);self.inventory_kind.currentIndexChanged.connect(self.render_detail)
        iv.addWidget(self.inventory_kind);self.inv_grid=QGridLayout();self.inv_grid.setSpacing(4);self.slots=[]
        for i in range(41):
            b=button('',lambda checked=False,j=i:self.inspect_item(j),'slot');b.setMinimumSize(44,48);b.setMaximumHeight(58)
            b.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Fixed);self.slots.append(b);self.inv_grid.addWidget(b,i//9,i%9)
        iv.addLayout(self.inv_grid);self.inv_caption=label('Hotbar 0–8 · click an item to inspect' if self.bridge_enabled() else 'Saved inventory · updates when Minecraft saves player data','muted');iv.addWidget(self.inv_caption)
        # Retain the data table for integrations; the grid already displays these items.
        self.inv_list=table(['SLOT','ITEM','COUNT'],'Inventory is empty');self.inv_list.setParent(inv);self.inv_list.hide();iv.addStretch()
        self.player_tabs.addTab(inv,'Inventory')
        self.player_events=table(['WHEN','EVENT','DETAILS'],'No history for this player');columns(self.player_events,[155,90,None])
        self.player_events.cellDoubleClicked.connect(lambda r,c:self.event_detail(self.player_events,r));self.player_tabs.addTab(self.player_events,'History')
        split.addWidget(detail);split.setSizes([245,720]);split.setCollapsible(0,False);split.setCollapsible(1,False);box.addWidget(split,1);self.pages.addWidget(w)

    def build_rules(self):
        w,box=page('World rules');self.rule_search=search('Search rules',self.filter_rules)
        self.rule_status=label('Saved values','muted');box.addWidget(row(self.rule_search,self.rule_status))
        self.rule_table=table(['RULE','LIVE' if self.bridge_enabled() else 'SAVED','CHANGE',''],'Start the server once to load world rules')
        self.rule_table.verticalHeader().setDefaultSectionSize(52);columns(self.rule_table,[None,95,190,80])
        self.rule_table.setToolTip('Fire spread radius: 0 off · 128 normal · −1 unlimited. Fire damage is a separate rule.')
        box.addWidget(self.rule_table,1);self.pages.addWidget(w)

    def build_settings(self):
        w,box=page('Settings','Changes apply at the next server start.')
        self.animations_toggle=AnimationToggle(self)
        box.addWidget(row(self.animations_toggle,None))
        self.ram=QSpinBox();self.ram.setRange(2048,32768);self.ram.setSingleStep(512);self.ram.setSuffix(' MB');self.ram.setValue(int(self.config.get('memory_mb',4096)));self.ram.setFixedWidth(155)
        self.ram.setToolTip('Maximum Java heap, 2–32 GB. Leave memory for Windows and Minecraft on this PC.')
        self.ram_save=button('Save RAM',self.save_ram,None,'memory')
        box.addWidget(row(label('RAM allocation','section'),self.ram,self.ram_save,None,label('Applies on next start','muted')))
        self.settings_search=search('Search settings',self.filter_settings)
        self.settings_group=QComboBox();self.settings_group.addItems(['Essentials','All settings','Network','World','Performance']);self.settings_group.currentIndexChanged.connect(self.filter_settings)
        self.settings_save=button('Save changes',self.apply_settings,'primary','save')
        box.addWidget(row(self.settings_search,self.settings_group,self.settings_save))
        self.settings_table=table(['SETTING','VALUE']);self.settings_table.verticalHeader().setDefaultSectionSize(50)
        self.settings_widgets={};enums={'difficulty':['peaceful','easy','normal','hard'],'gamemode':['survival','creative','adventure','spectator']}
        self.initial_properties=properties();visible={k:v for k,v in self.initial_properties.items() if not any(x in k for x in ['password','secret','keystore'])}
        self.settings_table.setRowCount(len(visible))
        for r,(key,value) in enumerate(sorted(visible.items())):
            title=key.replace('-',' ').replace('.',' / ').capitalize();item=QTableWidgetItem(title);item.setData(Qt.ItemDataRole.UserRole,key);item.setToolTip(key);self.settings_table.setItem(r,0,item)
            if value in ('true','false'):
                editor=BoolSwitch();editor.addItems(['true','false']);editor.setCurrentText(value)
            elif key in enums:
                editor=QComboBox();editor.addItems(enums[key]);editor.setCurrentText(value)
            else:editor=QLineEdit(value)
            editor.setToolTip(key);self.settings_widgets[key]=editor;self.settings_table.setCellWidget(r,1,editor)
        self.settings_hint=label('Applies on next start','muted');box.addWidget(self.settings_hint)
        box.addWidget(self.settings_table,1);self.filter_settings();self.pages.addWidget(w)

    def build_console(self):
        w,box=page('Console');self.log_filter=search('Filter output',self.render_log)
        box.addWidget(row(self.log_filter,button('',lambda:self.open_folder(ROOT/'logs'),'quiet','folder','Open logs')))
        self.console=QTextEdit();self.console.setReadOnly(True);self.console.document().setMaximumBlockCount(2500);box.addWidget(self.console,1)
        self.command_input=QLineEdit();self.command_input.setPlaceholderText('Command');self.command_input.addAction(icon('terminal'),QLineEdit.ActionPosition.LeadingPosition);self.command_input.returnPressed.connect(self.console_send)
        self.command_send=button('Run',self.console_send,'primary','arrow');box.addWidget(row(self.command_input,self.command_send));self.pages.addWidget(w)

    def build_backups(self):
        w,box=page('Backups');self.backup_btn=button('Back up now',self.backup,'primary','archive')
        box.addWidget(row(label('Oldest first · newest protected','muted'),None,button('',lambda:self.open_folder(ROOT/'backups'),'quiet','folder','Open backups'),self.backup_btn))
        self.backup_usage=label('0 / 50 GB','section');box.addWidget(self.backup_usage)
        self.backup_usage.setToolTip('50 GB shared by all managed backups, including temporary files. Oversized backups are refused. Up to 14 snapshots of each kind. Restore with the server stopped.')
        self.backup_progress=QProgressBar();self.backup_progress.setRange(0,1000);self.backup_progress.setTextVisible(False);box.addWidget(self.backup_progress)
        self.backup_table=table(['CREATED','ARCHIVE','SIZE'],'No backups yet');columns(self.backup_table,[190,None,100])
        self.backup_table.cellDoubleClicked.connect(self.open_backup);box.addWidget(self.backup_table,1);self.pages.addWidget(w)

    def build_activity(self):
        w,box=page('Activity');self.activity_search=search('Search events or players',self.render_activity)
        box.addWidget(row(self.activity_search,button('Export',self.export_history,'quiet','external')))
        self.activity=table(['WHEN','PLAYER','TYPE','DETAILS'],'No activity yet');columns(self.activity,[175,150,110,None])
        self.activity.setToolTip('Double-click an event for coordinates and details.');self.activity.cellDoubleClicked.connect(lambda r,c:self.event_detail(self.activity,r))
        box.addWidget(self.activity,1);self.pages.addWidget(w)

    def build_mods(self):
        w,box=page('Mods')
        self.mods_hint=label('Stop the server to enable or disable mods. Files stay in this folder.','muted')
        self.mods_hint.setWordWrap(True);box.addWidget(self.mods_hint)
        box.addWidget(row(label('Server mods','section'),None,button('Refresh',lambda:self.render_mods(force=True),'quiet','restart'),button('Open mods folder',self.open_mods_folder,None,'folder')))
        self.mods_table=table(['MOD','VERSION','FILE','STATE',''],'No mods in this server’s mods folder')
        columns(self.mods_table,[None,110,None,110,100]);self.mods_table.verticalHeader().setDefaultSectionSize(48)
        box.addWidget(self.mods_table,1)
        note=label('Disabled mods keep the .jar.disabled extension. Other mods may depend on them.','muted');note.setWordWrap(True);box.addWidget(note)
        self.pages.addWidget(w)
