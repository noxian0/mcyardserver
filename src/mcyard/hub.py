"""MCyard Server library and guided creation. No Minecraft process starts implicitly."""
from pathlib import Path
import threading

from PySide6.QtCore import Qt, QSize, QThread, Signal, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QListWidget, QListWidgetItem, QLineEdit, QSpinBox, QComboBox,
    QFileDialog, QMessageBox, QCheckBox, QStackedWidget, QProgressBar,
    QPlainTextEdit, QFrame, QSizePolicy,
)

from .manager.theme import STYLE
from .manager.ui_components import icon, HoverButton, AnimatedList, AnimatedStack
from .paths import app_data, resource_path
from .provision import CreateOptions, create_server, recommended_folder_name
from .java_runtime import detect_java
from .runtime_install import install_java
from .catalog import list_mc_versions, list_loader_versions, required_java
from .registry import list_servers, register_server, forget_server
from .import_existing import inspect_existing, import_server
from .appearance import AnimationToggle,add_credits


def _label(text='', kind=None):
    result=QLabel(text)
    if kind:result.setObjectName(kind)
    return result


def _button(text, callback, glyph=None, primary=False):
    result=HoverButton(text)
    if glyph:result.setIcon(icon(glyph,'#203017' if primary else '#a7b49e'))
    if primary:result.setObjectName('primary')
    result.setIconSize(QSize(17,17));result.setCursor(Qt.CursorShape.PointingHandCursor)
    result.clicked.connect(callback)
    return result


def _row(*items):
    widget=QWidget();layout=QHBoxLayout(widget);layout.setContentsMargins(0,0,0,0);layout.setSpacing(10)
    for item in items:
        if item is None:layout.addStretch()
        else:layout.addWidget(item)
    return widget


def _link(text, url):
    result=QLabel(f'<a href="{url}" style="color:#b8d988;text-decoration:none">{text} ↗</a>')
    result.setOpenExternalLinks(True)
    return result


def _app_icon():
    path=resource_path('app.ico')
    if not path.exists():path=resource_path('mcyard.svg')
    return QIcon(str(path)) if path.exists() else icon('inventory','#b8d988',32)


class _Discovery(QThread):
    """Never run Java's version probes on the GUI thread."""
    def __init__(self,parent=None):
        super().__init__(parent);self.result=[];self.error=''
    def run(self):
        try:self.result=detect_java(required=17)
        except Exception as exc:self.error=str(exc)


class _Catalog(QThread):
    """Catalog requests are cancellable and never block the window."""
    def __init__(self,kind,server_type,mc_version='',parent=None):
        super().__init__(parent)
        self.kind=kind;self.server_type=server_type;self.mc_version=mc_version
        self.cancel_event=threading.Event();self.result=[];self.error=''
    def run(self):
        try:
            if self.kind=='minecraft':self.result=list_mc_versions(self.server_type,cancel_event=self.cancel_event)
            else:self.result=list_loader_versions(self.server_type,self.mc_version,cancel_event=self.cancel_event)
        except Exception as exc:self.error=str(exc)


class _Creation(QThread):
    progress=Signal(str)
    def __init__(self,options,parent=None):
        super().__init__(parent);self.options=options;self.cancel_event=threading.Event();self.result=None;self.error=''
    def run(self):
        try:self.result=create_server(self.options,progress=self.progress.emit,cancel_event=self.cancel_event)
        except Exception as exc:self.error=str(exc)


class _JavaInstall(QThread):
    progress=Signal(str)
    def __init__(self,major,parent=None):
        super().__init__(parent);self.major=major;self.cancel_event=threading.Event();self.result=None;self.error=''
    def run(self):
        try:self.result=install_java(self.major,progress=self.progress.emit,cancel_event=self.cancel_event)
        except Exception as exc:self.error=str(exc)


class CreateWizard(QDialog):
    """Three concise setup steps with explicit consent and cancellable installation."""
    def __init__(self,parent=None):
        super().__init__(parent)
        self.setWindowTitle('Create a server · MCyard Server');self.setWindowIcon(_app_icon())
        self.resize(700,740);self.setMinimumSize(650,700)
        self.created=None;self.open_after=False;self.worker=None;self.discovery=None;self.runtime_worker=None
        self.catalog_jobs=[];self._catalog_token=0;self.catalog_ready=False
        self._java_runtimes=[];self._auto_java_path='';self._required_java=25
        self._closing=False;self._accept_when_idle=False
        outer=QVBoxLayout(self);outer.setContentsMargins(30,26,30,25);outer.setSpacing(18)
        outer.addWidget(_label('New server','title'))
        self.steps=_label('01  World     /     02  Runtime     /     03  Create','muted');outer.addWidget(self.steps)
        self.pages=AnimatedStack();outer.addWidget(self.pages,1)
        self._world_page();self._runtime_page();self._review_page();self._progress_page()
        self.error_label=_label('','muted');self.error_label.setWordWrap(True);outer.addWidget(self.error_label)
        self.back=_button('Back',self.previous)
        self.cancel=_button('Cancel',self.reject)
        self.next=_button('Continue',self.advance,'arrow',True)
        outer.addWidget(_row(self.back,None,self.cancel,self.next))
        self.pages.currentChanged.connect(self._page_changed);self._page_changed(0)
        self.name.textChanged.connect(self.update_destination)
        self.parent_folder.textChanged.connect(self.update_destination)
        self.eula.toggled.connect(lambda checked:self.next.setEnabled(checked) if self.pages.currentIndex()==2 else None)
        self.update_destination()
        QTimer.singleShot(0,self.discover_java)
        QTimer.singleShot(0,self.reload_catalog)

    def _page(self):
        page=QWidget();box=QVBoxLayout(page);box.setContentsMargins(0,0,0,0);box.setSpacing(12)
        self.pages.addWidget(page);return box

    def _world_page(self):
        box=self._page();box.addWidget(_label('World & location','section'))
        box.addWidget(_label('Server name','muted'));self.name=QLineEdit('My server');self.name.setMaxLength(60);box.addWidget(self.name)
        box.addWidget(_label('Keep servers in','muted'))
        self.parent_folder=QLineEdit(str(app_data()/'servers'))
        browse=_button('',self.browse_parent,'folder');browse.setToolTip('Choose parent folder')
        box.addWidget(_row(self.parent_folder,browse))
        self.destination=_label('','muted');self.destination.setWordWrap(True);self.destination.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse);box.addWidget(self.destination)
        box.addSpacing(8);box.addWidget(_label('Server software','section'))
        self.server_type=QComboBox()
        for title,key in [('Vanilla','vanilla'),('Fabric','fabric'),('Forge','forge')]:self.server_type.addItem(title,key)
        self.server_type.setCurrentIndex(1);self.server_type.currentIndexChanged.connect(self.reload_catalog);box.addWidget(self.server_type)
        versions=QGridLayout();versions.setHorizontalSpacing(18);versions.setVerticalSpacing(8)
        self.mc_version=QComboBox();self.mc_version.setEnabled(False)
        self.loader_version=QComboBox();self.loader_version.setEnabled(False)
        self.mc_version.currentIndexChanged.connect(self.minecraft_changed)
        self.loader_label=_label('Loader version','muted')
        versions.addWidget(_label('Minecraft version','muted'),0,0);versions.addWidget(self.loader_label,0,1)
        versions.addWidget(self.mc_version,1,0);versions.addWidget(self.loader_version,1,1);box.addLayout(versions)
        self.catalog_status=_label('Loading official versions…','muted');self.catalog_status.setWordWrap(True)
        self.catalog_status.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Preferred)
        self.catalog_retry=_button('Retry',self.reload_catalog,'restart');self.catalog_retry.hide()
        box.addWidget(_row(self.catalog_status,self.catalog_retry))
        self.features=_label('','muted');self.features.setWordWrap(True);box.addWidget(self.features);box.addStretch()

    def _runtime_page(self):
        box=self._page();box.addWidget(_label('Runtime','section'))
        self.java_status=_label('Looking for installed Java…','muted');self.java_status.setWordWrap(True);box.addWidget(self.java_status)
        self.java_choices=QComboBox();self.java_choices.setEnabled(False)
        self.java_choices.currentIndexChanged.connect(self.choose_java);box.addWidget(self.java_choices)
        self.java_path=QLineEdit();self.java_path.setPlaceholderText('Path to java.exe')
        browse=_button('',self.browse_java,'folder');browse.setToolTip('Locate Java executable')
        box.addWidget(_row(self.java_path,browse))
        self.java_install=_button('Install Java 25',self.install_runtime,'download')
        self.java_install.setToolTip('Download Eclipse Temurin for MCyard Server. Your system Java settings stay unchanged.')
        self.java_link=_link('Java downloads','https://adoptium.net/temurin/releases/?version=25')
        box.addWidget(_row(self.java_install,None,self.java_link))
        box.addSpacing(10)
        grid=QGridLayout();grid.setHorizontalSpacing(24);grid.setVerticalSpacing(8)
        self.memory=QSpinBox();self.memory.setRange(2,32);self.memory.setValue(4);self.memory.setSuffix(' GB')
        self.port=QSpinBox();self.port.setRange(1024,65535);self.port.setValue(25565)
        grid.addWidget(_label('Maximum memory','muted'),0,0);grid.addWidget(_label('Server port','muted'),0,1)
        grid.addWidget(self.memory,1,0);grid.addWidget(self.port,1,1);box.addLayout(grid)
        hint=_label('Keep some memory free for Windows and your game. Each running server needs a different port.','muted');hint.setWordWrap(True);box.addWidget(hint)
        self.lithium=QCheckBox('Install Lithium performance improvements');self.lithium.setChecked(True);box.addWidget(self.lithium);box.addStretch()

    def _review_page(self):
        box=self._page();box.addWidget(_label('Ready to build','section'))
        self.review=_label();self.review.setWordWrap(True);self.review.setTextFormat(Qt.TextFormat.PlainText);self.review.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse);box.addWidget(self.review)
        box.addSpacing(18)
        note=_label('Downloads come from Minecraft, Fabric, Forge, and Modrinth. Setup creates a new server folder.','muted');note.setWordWrap(True);box.addWidget(note)
        box.addWidget(_link('Read the Minecraft EULA','https://www.minecraft.net/eula'))
        self.eula=QCheckBox('I have read and agree to the Minecraft EULA.');self.eula.setChecked(False);box.addWidget(self.eula)
        box.addStretch();box.addWidget(_label('The server starts only when you click Start in its manager.','muted'))

    def _progress_page(self):
        box=self._page();self.progress_title=_label('Creating server','section');box.addWidget(self.progress_title)
        self.stage=_label('Preparing…','muted');self.stage.setWordWrap(True);box.addWidget(self.stage)
        self.progress=QProgressBar();self.progress.setRange(0,0);self.progress.setTextVisible(False);box.addWidget(self.progress)
        self.log=QPlainTextEdit();self.log.setReadOnly(True);self.log.setMaximumBlockCount(100)
        self.log.setStyleSheet('QPlainTextEdit {background:#0e130f;border:1px solid #293425;border-radius:4px;color:#a6b69a;padding:10px;font-family:Consolas;font-size:11px;}')
        box.addWidget(self.log,1)

    def update_destination(self):
        try:
            dest=Path(self.parent_folder.text().strip()).expanduser()/recommended_folder_name(self.name.text().strip())
            self.destination.setText(str(dest))
        except Exception:self.destination.setText('Choose a server name and parent folder.')

    def browse_parent(self):
        selected=QFileDialog.getExistingDirectory(self,'Server parent folder',self.parent_folder.text())
        if selected:self.parent_folder.setText(selected)

    def browse_java(self):
        selected,_=QFileDialog.getOpenFileName(self,'Choose Java executable',self.java_path.text(),'Java executable (java.exe java);;All files (*)')
        if selected:self.java_path.setText(selected)

    def _software(self):return str(self.server_type.currentData() or 'fabric')

    def _enhanced(self):return self._software()=='fabric' and self.mc_version.currentText()=='26.3'

    def _catalog_loading(self,text):
        self.catalog_ready=False;self.catalog_status.setText(text);self.catalog_retry.hide()
        if self.pages.currentIndex()==0:self.next.setEnabled(False)

    def reload_catalog(self,*_):
        if self._closing:return
        self._catalog_token+=1
        for job in self.catalog_jobs:job.cancel_event.set()
        self._catalog_loading('Loading official Minecraft versions…')
        self.mc_version.blockSignals(True);self.mc_version.clear();self.mc_version.blockSignals(False)
        self.mc_version.setEnabled(False);self.loader_version.clear();self.loader_version.setEnabled(False)
        self.features.clear();self.loader_label.setText('Forge version' if self._software()=='forge' else 'Loader version')
        self._request_catalog('minecraft')

    def _request_catalog(self,kind):
        job=_Catalog(kind,self._software(),self.mc_version.currentText(),self)
        token=self._catalog_token;self.catalog_jobs.append(job)
        job.finished.connect(lambda:self._catalog_finished(job,token));job.start()

    def _catalog_finished(self,job,token):
        if job in self.catalog_jobs:self.catalog_jobs.remove(job)
        job.deleteLater()
        if self._closing:
            self._finish_close();return
        if token!=self._catalog_token:return
        if job.error:
            self.catalog_status.setText('Could not load versions. '+job.error)
            self.catalog_retry.show();return
        values=list(dict.fromkeys(str(value) for value in job.result if value))
        if not values:
            self.catalog_status.setText('No supported releases found for this selection. Choose different server software.')
            self.catalog_retry.show();return
        if job.kind=='minecraft':
            self.mc_version.blockSignals(True);self.mc_version.addItems(values)
            preferred=self.mc_version.findText('26.3') if self._software()=='fabric' else 0
            self.mc_version.setCurrentIndex(max(0,preferred));self.mc_version.blockSignals(False)
            self.mc_version.setEnabled(True);self.minecraft_changed()
        else:
            self.loader_version.clear();self.loader_version.addItems(values);self.loader_version.setEnabled(True)
            self._catalog_complete()

    def minecraft_changed(self,*_):
        if self._closing or not self.mc_version.currentText():return
        self._catalog_token+=1
        for job in self.catalog_jobs:job.cancel_event.set()
        self._catalog_loading('Loading compatible loader versions…')
        self.loader_version.clear();self.loader_version.setEnabled(False)
        self._required_java=required_java(self.mc_version.currentText())
        self._select_java_runtime()
        enhanced=self._enhanced();self.lithium.setVisible(enhanced)
        basic='Start, stop, console, settings, and offline backups.' if self._software()=='vanilla' else 'Start, stop, console, settings, mod controls, and offline backups.'
        self.features.setText('Player inventory, live history, world rules, and live backups included.' if enhanced else
            basic+' Detailed player tools require Fabric 26.3.')
        if self._software()=='vanilla':
            self.loader_version.addItem('Not needed');self._catalog_complete()
        else:self._request_catalog('loader')

    def _catalog_complete(self):
        self.catalog_ready=True;self.catalog_status.setText(f'Official releases · Java {self._required_java}'+(' required' if self._software()=='forge' else ' or newer'))
        if self.pages.currentIndex()==0:self.next.setEnabled(True)

    def discover_java(self):
        if self.discovery and self.discovery.isRunning():return
        self.discovery=_Discovery(self);self.discovery.finished.connect(self._java_finished);self.discovery.start()

    def _java_finished(self):
        self._java_runtimes=self.discovery.result
        self._select_java_runtime()
        if self._closing:self._finish_close()

    def install_runtime(self):
        if self._closing or (self.runtime_worker and self.runtime_worker.isRunning()):return
        if self.discovery and self.discovery.isRunning():return
        self.error_label.clear();self.java_install.setEnabled(False)
        self.back.setEnabled(False);self.next.setEnabled(False);self.java_path.setEnabled(False);self.java_choices.setEnabled(False)
        self.runtime_worker=_JavaInstall(self._required_java,self)
        self.runtime_worker.progress.connect(self.java_status.setText)
        self.runtime_worker.finished.connect(self._runtime_installed);self.runtime_worker.start()

    def _runtime_installed(self):
        if self._closing:self._finish_close();return
        worker=self.runtime_worker
        if worker.result:
            self._java_runtimes=[entry for entry in self._java_runtimes if str(entry['path'])!=str(worker.result['path'])]
            self._java_runtimes.append(worker.result)
            self._auto_java_path=str(worker.result['path']);self.java_path.setText(self._auto_java_path)
        self.java_path.setEnabled(True);self.back.setEnabled(True)
        self._select_java_runtime();self._page_changed(self.pages.currentIndex())
        if worker.error:self.error_label.setText('Java setup failed. '+worker.error)

    def _select_java_runtime(self):
        choices=self._java_runtimes;required=self._required_java;exact=self._software()=='forge'
        current=self.java_path.text().strip()
        preserve=bool(current and current!=self._auto_java_path)
        self.java_choices.blockSignals(True);self.java_choices.clear()
        compatible=[item for item in choices if int(item.get('major',0))==required or (not exact and int(item.get('major',0))>required)]
        compatible.sort(key=lambda item:(int(item.get('major',0))!=required,int(item.get('major',0))))
        for entry in compatible:self.java_choices.addItem(f'Java {entry.get("major", "?")}  ·  {entry.get("path", "")}',entry)
        requirement=f'Java {required}'+(' is required for this Forge version.' if exact else ' or newer is required.')
        if compatible:
            self.java_choices.setCurrentIndex(0)
            if not preserve:
                self._auto_java_path=str(compatible[0]['path']);self.java_path.setText(self._auto_java_path)
            self.java_status.setText(requirement)
        else:
            if not preserve:self.java_path.clear();self._auto_java_path=''
            self.java_status.setText(requirement+' Install it or choose its executable below.')
        self.java_choices.blockSignals(False)
        self.java_choices.setEnabled(bool(compatible))
        installing=bool(self.runtime_worker and self.runtime_worker.isRunning())
        self.java_install.setText(f'Install Java {required}')
        self.java_install.setVisible(not compatible or installing)
        self.java_install.setEnabled(not installing and not (self.discovery and self.discovery.isRunning()))
        self.java_link.setText(f'<a href="https://adoptium.net/temurin/releases/?version={required}" style="color:#b8d988;text-decoration:none">Java downloads ↗</a>')

    def choose_java(self,index):
        entry=self.java_choices.itemData(index)
        if entry:self.java_path.setText(str(entry.get('path','')))

    def _page_changed(self,index):
        self.error_label.clear();self.back.setVisible(index in (1,2))
        self.next.setText('Create server' if index==2 else 'Continue')
        self.next.setEnabled(self.eula.isChecked() if index==2 else self.catalog_ready if index==0 else index<3)
        self.steps.setText(['01  World     /     02  Runtime     /     03  Create',
                            'World  ✓     /     02  Runtime     /     03  Create',
                            'World  ✓     /     Runtime  ✓     /     03  Create',
                            'World  ✓     /     Runtime  ✓     /     Creating'][index])

    def previous(self):
        if self.pages.currentIndex() in (1,2):self.pages.setCurrentIndex(self.pages.currentIndex()-1)

    def advance(self):
        index=self.pages.currentIndex()
        if index==0:
            if not self.catalog_ready:return self.error_label.setText('Wait for the official version list, or retry the download.')
            if not self.name.text().strip():return self.error_label.setText('Enter a server name.')
            if not self.parent_folder.text().strip():return self.error_label.setText('Choose a parent folder.')
            try:
                name=recommended_folder_name(self.name.text().strip())
                if (Path(self.parent_folder.text()).expanduser()/name).exists():return self.error_label.setText('That server folder already exists. Choose a different name or location.')
            except Exception as exc:return self.error_label.setText(str(exc))
            self.pages.setCurrentIndex(1)
        elif index==1:
            if not self.java_path.text().strip():return self.error_label.setText(f'Select Java {self._required_java} before continuing.')
            software=self.server_type.currentText();loader='' if self._software()=='vanilla' else ' '+self.loader_version.currentText()
            self.review.setText(f'{self.name.text().strip()}\n\n{self.destination.text()}\n\nMinecraft {self.mc_version.currentText()} · {software}{loader}\nJava {self._required_java} · {self.memory.value()} GB maximum memory · Port {self.port.value()}\nBackup storage limit: 50 GB')
            self.pages.setCurrentIndex(2)
        elif index==2:self.begin_creation()
        elif index==3 and self.created:
            self.open_after=True;self.accept()

    def begin_creation(self):
        if not self.eula.isChecked():return
        if self.worker and self.worker.isRunning():return
        if not self.catalog_ready:return
        options=CreateOptions(name=self.name.text().strip(),parent=Path(self.parent_folder.text()).expanduser(),port=self.port.value(),memory_mb=self.memory.value()*1024,java_path=self.java_path.text().strip(),eula_accepted=self.eula.isChecked(),lithium=self.lithium.isChecked() and self._enhanced(),server_type=self._software(),mc_version=self.mc_version.currentText(),loader_version='' if self._software()=='vanilla' else self.loader_version.currentText())
        self.log.clear();self.pages.setCurrentIndex(3);self.next.hide();self.back.hide();self.cancel.setText('Cancel creation')
        self.progress.setRange(0,0);self.progress.show();self.progress_title.setText('Creating server')
        self.worker=_Creation(options,self);self.worker.progress.connect(self._progress);self.worker.finished.connect(self._created);self.worker.start()

    def _progress(self,text):
        self.stage.setText(text);self.log.appendPlainText(text)

    def _created(self):
        self.progress.setRange(0,1);self.progress.setValue(1)
        if self._closing:
            self._finish_close();return
        self.next.show();self.cancel.setText('Close');self.cancel.setEnabled(True)
        if self.worker.result:
            self.created=self.worker.result;self.steps.setText('World  ✓     /     Runtime  ✓     /     Created  ✓')
            self.progress_title.setText('Server ready');self.stage.setText(str(self.created['path']))
            self.next.setText('Open manager');self.next.setEnabled(True)
        else:
            self.progress_title.setText('Creation stopped');self.stage.setText(self.worker.error or 'No server was created.')
            self.next.setText('Review settings');self.next.setEnabled(True)
            self.next.clicked.disconnect(self.advance);self.next.clicked.connect(self._retry)

    def _retry(self):
        self.next.clicked.disconnect(self._retry);self.next.clicked.connect(self.advance)
        self.pages.setCurrentIndex(2);self.cancel.setText('Cancel')

    def _busy(self):
        return any(worker is not None and worker.isRunning() for worker in (self.worker,self.discovery,self.runtime_worker,*self.catalog_jobs))

    def reject(self):
        self._closing=True;self._accept_when_idle=False
        for job in self.catalog_jobs:job.cancel_event.set()
        if self.runtime_worker and self.runtime_worker.isRunning():self.runtime_worker.cancel_event.set()
        if self.worker and self.worker.isRunning():
            self.worker.cancel_event.set();self.stage.setText('Canceling… finishing the current download safely.')
        if self._busy():
            self.pages.setEnabled(False)
            self.cancel.setEnabled(False);self.next.setEnabled(False);self.back.setEnabled(False)
            self.error_label.setText('Finishing the current operation before closing…')
        else:super().reject()

    def accept(self):
        if self._busy():self._closing=True;self._accept_when_idle=True
        else:super().accept()

    def _finish_close(self):
        if not self._busy():
            if self._accept_when_idle:super().accept()
            else:super().reject()

    def closeEvent(self,event):
        self.reject()
        if self._busy():event.ignore()
        else:event.accept()


class _Import(QThread):
    def __init__(self,folder,name,java_path,memory,parent=None):
        super().__init__(parent)
        self.folder=folder;self.name=name;self.java_path=java_path;self.memory=memory
        self.result=None;self.error=''
    def run(self):
        try:self.result=import_server(self.folder,self.name,self.java_path,self.memory)
        except Exception as exc:self.error=str(exc)


class ImportDialog(QDialog):
    """Preview an existing installation and attach it without moving its files."""
    def __init__(self,preview,parent=None):
        super().__init__(parent);self.preview=preview;self.imported=None;self.worker=None
        self.discovery=None;self._closing=False
        self.setWindowTitle('Import server · MCyard Server');self.setWindowIcon(_app_icon())
        self.resize(680,540);self.setMinimumSize(600,500)
        box=QVBoxLayout(self);box.setContentsMargins(30,26,30,25);box.setSpacing(15)
        box.addWidget(_label('Import server','title'))
        software=preview['server_type'].title()
        box.addWidget(_label(f"{software} {preview['mc_version']}  ·  Port {preview['port']}",'section'))
        path=_label(preview['path'],'muted');path.setTextFormat(Qt.TextFormat.PlainText);path.setWordWrap(True);box.addWidget(path)
        box.addWidget(_label('Server name','muted'));self.name=QLineEdit(preview['name']);self.name.setMaxLength(60);box.addWidget(self.name)
        grid=QGridLayout();grid.setHorizontalSpacing(20)
        self.memory=QSpinBox();self.memory.setRange(2048,32768);self.memory.setSingleStep(1024)
        self.memory.setSuffix(' MB');self.memory.setValue(preview['memory_mb'])
        self.java_choices=QComboBox();self.java_choices.setEnabled(False);self.java_choices.currentIndexChanged.connect(self._choose_java)
        grid.addWidget(_label('Maximum memory','muted'),0,0);grid.addWidget(_label('Java runtime','muted'),0,1)
        grid.addWidget(self.memory,1,0);grid.addWidget(self.java_choices,1,1);grid.setColumnStretch(1,1);box.addLayout(grid)
        self.java_path=QLineEdit();self.java_path.setPlaceholderText('Path to java.exe')
        browse=_button('',self._browse_java,'folder');browse.setToolTip('Choose Java executable');box.addWidget(_row(self.java_path,browse))
        required=preview['java_required'];self.java_status=_label(f'Looking for Java {required}…','muted');self.java_status.setWordWrap(True);box.addWidget(self.java_status)
        note=_label('Uses this folder in place. World, settings, mods, and player history stay here.','muted');note.setWordWrap(True);box.addWidget(note)
        if preview['capabilities']['bridge']:box.addWidget(_label('Existing management bridge detected. Live player tools are available.','muted'))
        box.addStretch();self.error=_label('','muted');self.error.setWordWrap(True);box.addWidget(self.error)
        self.cancel=_button('Cancel',self.reject);self.add=_button('Import server',self.begin_import,'arrow',True)
        box.addWidget(_row(None,self.cancel,self.add));QTimer.singleShot(0,self._discover)

    def _discover(self):
        if self._closing:return
        self.discovery=_Discovery(self);self.discovery.finished.connect(self._discovered);self.discovery.start()

    def _discovered(self):
        required=self.preview['java_required'];exact=self.preview['java_exact']
        choices=[x for x in self.discovery.result if x['major']==required or (not exact and x['major']>required)]
        choices.sort(key=lambda x:(x['major']!=required,x['major']))
        current=self.java_path.text().strip();self.java_choices.blockSignals(True)
        for item in choices:self.java_choices.addItem(f"Java {item['major']}",item)
        if choices and not current:self.java_path.setText(choices[0]['path'])
        self.java_choices.setEnabled(bool(choices));self.java_choices.blockSignals(False)
        self.java_status.setText(f'Java {required}'+(' is required for Forge.' if exact else ' or newer is required.')+('' if choices else ' Choose an installed runtime.'))
        if self._closing:self._finish_close()

    def _choose_java(self,index):
        item=self.java_choices.itemData(index)
        if item:self.java_path.setText(item['path'])

    def _browse_java(self):
        path,_=QFileDialog.getOpenFileName(self,'Choose Java executable',self.java_path.text(),'Java executable (java.exe java);;All files (*)')
        if path:self.java_path.setText(path)

    def _busy(self):return any(job is not None and job.isRunning() for job in (self.discovery,self.worker))

    def begin_import(self):
        if self.worker and self.worker.isRunning():return
        if not self.name.text().strip() or not self.java_path.text().strip():
            self.error.setText('Enter a name and choose Java.');return
        self.add.setEnabled(False);self.cancel.setEnabled(False);self.error.setText('Checking Java and adding the server…')
        self.worker=_Import(Path(self.preview['path']),self.name.text().strip(),self.java_path.text().strip(),self.memory.value(),self)
        self.worker.finished.connect(self._imported);self.worker.start()

    def _imported(self):
        self.imported=self.worker.result
        if self.imported:
            if self.discovery and self.discovery.isRunning():self._closing=True
            else:super().accept()
        elif not self._closing:
            self.error.setText(self.worker.error);self.add.setEnabled(True);self.cancel.setEnabled(True)
        if self._closing:self._finish_close()

    def _finish_close(self):
        if not self._busy():
            if self.imported:super().accept()
            else:super().reject()

    def reject(self):
        self._closing=True
        if self._busy():
            self.add.setEnabled(False);self.cancel.setEnabled(False);self.error.setText('Finishing the current operation…')
        else:super().reject()

    def closeEvent(self,event):
        self.reject()
        if self._busy():event.ignore()
        else:event.accept()


class HubWindow(QMainWindow):
    """Server library. launch_server receives one validated server directory."""
    def __init__(self,launch_server=None,parent=None):
        super().__init__(parent);self.launch_server=launch_server;self.entries=[]
        self.setWindowTitle('MCyard Server');self.setWindowIcon(_app_icon());self.resize(1160,760);self.setMinimumSize(940,640)
        self.setStyleSheet(STYLE)
        shell=QWidget();shell.setObjectName('shell');outer=QHBoxLayout(shell);outer.setContentsMargins(0,0,0,0);outer.setSpacing(0);self.setCentralWidget(shell)
        side=QFrame();side.setObjectName('sidebar');side.setFixedWidth(195);nav=QVBoxLayout(side);nav.setContentsMargins(20,30,20,22);nav.setSpacing(21)
        mark=QLabel();mark.setPixmap(_app_icon().pixmap(30,30));nav.addWidget(_row(mark,_label('MCyard Server','section')))
        nav.addSpacing(10);nav.addWidget(_button('Your servers',self.refresh,'home'))
        nav.addWidget(_button('Create server',self.new_server,'play'));nav.addStretch()
        nav.addWidget(_button('Connect friends',self.connection_guide,'users'))
        nav.addWidget(_button('About',self.about,'more'))
        self.animations_toggle=AnimationToggle(self);nav.addWidget(self.animations_toggle)
        nav.addWidget(_label('0.1.1 · Windows','muted'));outer.addWidget(side)
        body=QWidget();box=QVBoxLayout(body);box.setContentsMargins(34,32,34,28);box.setSpacing(20)
        box.addWidget(_row(_label('Your servers','title'),None,_button('Add existing',self.add_existing,'folder'),_button('New server',self.new_server,'play',True)))
        box.addWidget(_label('Minecraft Java  /  Vanilla · Fabric · Forge','muted'))
        self.list=AnimatedList();self.list.setSpacing(4);self.list.setStyleSheet('QListWidget {border:none;background:transparent;outline:none;} QListWidget::item {border-bottom:1px solid #2a3425;padding:12px;border-radius:5px;} QListWidget::item:selected {background:#26351f;} QListWidget::item:hover:!selected {background:#1d2819;}')
        self.list.setIconSize(QSize(25,25));self.list.currentRowChanged.connect(self.select_server);self.list.itemDoubleClicked.connect(lambda _:self.open_selected());box.addWidget(self.list,1)
        self.empty=_label('No servers yet. Create your first world.','section');self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter);box.addWidget(self.empty,1)
        self.detail_name=_label('','section');self.detail_info=_label('','muted');self.detail_path=_label('','muted')
        self.detail_path.setWordWrap(True);self.detail_path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        box.addWidget(self.detail_name);box.addWidget(self.detail_info);box.addWidget(self.detail_path)
        self.open_button=_button('Open manager',self.open_selected,'arrow',True)
        self.folder_button=_button('Open folder',self.open_folder,'folder')
        self.forget_button=_button('Remove from list',self.forget_selected,'close')
        box.addWidget(_row(self.forget_button,None,self.folder_button,self.open_button));outer.addWidget(body,1)
        self.statusBar().setSizeGripEnabled(False);self.refresh()
        self.credits=add_credits(self)

    def refresh(self):
        previous=self.current_entry();previous_path=previous.get('path') if previous else None
        try:self.entries=list_servers()
        except Exception as exc:
            self.entries=[];self.statusBar().showMessage(str(exc));QMessageBox.warning(self,'Server library',str(exc))
        self.list.blockSignals(True);self.list.clear()
        selected=0
        for i,entry in enumerate(self.entries):
            name=entry.get('name','Server');version=entry.get('mc_version','26.3');port=entry.get('port',25565)
            software=str(entry.get('server_type','fabric')).title()
            detail='Folder not found' if entry.get('missing') else ('Server configuration needs attention' if entry.get('invalid') else f'{software} {version}   ·   Port {port}')
            item=QListWidgetItem(icon('inventory','#b8d988',25),f'{name}\n{detail}')
            item.setSizeHint(QSize(200,76));item.setToolTip(str(entry.get('path','')));self.list.addItem(item)
            if entry.get('path')==previous_path:selected=i
        self.list.blockSignals(False);self.empty.setVisible(not self.entries);self.list.setVisible(bool(self.entries))
        if self.entries:self.list.setCurrentRow(selected)
        self.select_server(self.list.currentRow())

    def current_entry(self):
        index=self.list.currentRow() if hasattr(self,'list') else -1
        return self.entries[index] if 0<=index<len(self.entries) else None

    def select_server(self,index):
        entry=self.current_entry();enabled=bool(entry)
        for widget in (self.open_button,self.folder_button,self.forget_button):widget.setEnabled(enabled)
        self.open_button.setEnabled(bool(entry and not entry.get('missing') and not entry.get('invalid')))
        self.folder_button.setEnabled(bool(entry and not entry.get('missing')))
        for widget in (self.detail_name,self.detail_info,self.detail_path):widget.setVisible(enabled)
        if entry:
            self.detail_name.setTextFormat(Qt.TextFormat.PlainText)
            self.detail_name.setText(entry.get('name','Server'))
            self.detail_info.setText(f'{entry.get("memory_mb",4096)/1024:g} GB maximum memory   ·   50 GB backup limit')
            self.detail_path.setText(str(entry.get('path','')))

    def new_server(self):
        wizard=CreateWizard(self);wizard.exec();self.refresh()
        if wizard.created and wizard.open_after:self._launch(Path(wizard.created['path']))
        wizard.deleteLater()

    def add_existing(self):
        folder=QFileDialog.getExistingDirectory(self,'Add an existing server',str(app_data()/'servers'))
        if not folder:return
        try:
            if (Path(folder)/'mcyard.json').exists():
                register_server(Path(folder))
            else:
                dialog=ImportDialog(inspect_existing(folder),self);dialog.exec()
                imported=dialog.imported;dialog.deleteLater()
                if not imported:return
            self.refresh();self.statusBar().showMessage('Server added.',5000)
        except Exception as exc:QMessageBox.warning(self,'Could not add server',str(exc))

    def _launch(self,path):
        try:
            if not (path/'mcyard.json').is_file():raise ValueError('The MCyard server folder is missing. Add its new location if it was moved.')
            if self.launch_server is None:raise RuntimeError('The application launcher is not configured.')
            self.launch_server(path)
        except Exception as exc:QMessageBox.warning(self,'Could not open server',str(exc))

    def open_selected(self):
        entry=self.current_entry()
        if entry:self._launch(Path(entry['path']))

    def open_folder(self):
        entry=self.current_entry()
        if entry:QDesktopServices.openUrl(QUrl.fromLocalFile(str(entry['path'])))

    def forget_selected(self):
        entry=self.current_entry()
        if not entry:return
        if QMessageBox.question(self,'Remove from library',f'Remove {entry.get("name","this server")} from the list?\n\nIts world, backups, and files will stay on disk.')!=QMessageBox.StandardButton.Yes:return
        try:forget_server(Path(entry['path']));self.refresh()
        except Exception as exc:QMessageBox.warning(self,'Could not update library',str(exc))

    def connection_guide(self):
        port=int((self.current_entry() or {}).get('port',25565))
        dialog=QMessageBox(self);dialog.setWindowTitle('Connect friends');dialog.setTextFormat(Qt.TextFormat.RichText)
        dialog.setText(f'<b>On this PC</b><br>Join <code>localhost:{port}</code> in Minecraft Java.<br><br>'
                       '<b>On your Wi-Fi / LAN</b><br>Friends use this PC’s local IP and server port. Allow Java through Windows Firewall for the network you trust.<br><br>'
                       f'<b>Over the internet</b><br>A tunnel such as <a href="https://playit.gg/">playit.gg</a> can connect friends without Hamachi or router changes. Run its agent on this PC, select Minecraft Java, and point it at <code>127.0.0.1:{port}</code>. Keep both apps running.<br><br>'
                       'MCyard Server does not create tunnels or open router/firewall ports automatically.')
        dialog.exec()

    def about(self):
        QMessageBox.about(self,'About MCyard Server','<b>MCyard Server 0.1.1</b><br>A local Minecraft Java server creator and manager.<br><br>'
                          'Server downloads come from their original publishers. Worlds, player history, and backups stay on your PC.<br><br>'
                          'NOT AN OFFICIAL MINECRAFT PRODUCT. NOT APPROVED BY OR ASSOCIATED WITH MOJANG OR MICROSOFT.')
