"""Cached, per-user appearance preferences shared by open app windows."""
import json
import os
from pathlib import Path
import time
import uuid

from PySide6.QtCore import QObject,QFileSystemWatcher,Signal
from .paths import app_data


def reduced_motion_forced():
    return os.environ.get('MCYARD_REDUCED_MOTION','').lower() in ('1','true','yes')


class MotionPreferences(QObject):
    changed=Signal(bool)

    def __init__(self,path=None,parent=None):
        super().__init__(parent)
        self.path=Path(path) if path else app_data()/'preferences.json'
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self.enabled=True;self._effective=None
        self.watcher=QFileSystemWatcher(self)
        self.watcher.directoryChanged.connect(self.reload)
        self.watcher.fileChanged.connect(self.reload)
        self.watcher.addPath(str(self.path.parent))
        self.reload()

    def _read(self):
        try:
            if self.path.stat().st_size>65536:return {}
            value=json.loads(self.path.read_text(encoding='utf-8'))
            return value if isinstance(value,dict) else {}
        except (OSError,ValueError):return {}

    def reload(self,*_):
        value=self._read().get('animations',True)
        self.enabled=value if type(value) is bool else True
        self._watch_file()
        effective=self.enabled and not reduced_motion_forced()
        if effective!=self._effective:
            self._effective=effective;self.changed.emit(effective)

    def _watch_file(self):
        if self.path.exists() and str(self.path) not in self.watcher.files():
            self.watcher.addPath(str(self.path))

    def _replace(self,temporary):
        # Windows scanners and file-change notifications can briefly retain an
        # old handle. Keep the old file intact and retry only the atomic rename.
        # Four attempts add at most70ms; this is a user action, never a frame path.
        for attempt in range(4):
            try:
                temporary.replace(self.path)
                return
            except PermissionError:
                if attempt==3:raise
                time.sleep(.01*(2**attempt))

    def set_enabled(self,enabled):
        if type(enabled) is not bool:raise ValueError('Animation preference must be on or off.')
        value=self._read();value['animations']=enabled
        temporary=self.path.with_name('.preferences-'+uuid.uuid4().hex+'.tmp')
        # Keep directory notifications active for other instances, but release
        # our own file watcher before replacing its watched target on Windows.
        if str(self.path) in self.watcher.files():self.watcher.removePath(str(self.path))
        try:
            temporary.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')
            self._replace(temporary)
        finally:
            try:
                if temporary.exists():temporary.unlink()
            finally:self._watch_file()
        self.reload()


_instance=None


def motion_signals():
    global _instance
    if _instance is None:_instance=MotionPreferences()
    return _instance


def motion_enabled():
    # Paint/timer paths only read memory; file watching updates the cached value.
    return motion_signals().enabled and not reduced_motion_forced()


def set_motion_enabled(enabled):
    motion_signals().set_enabled(enabled)
