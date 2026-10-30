"""Application resources and per-user state never share a server/source folder."""
import os
import sys
from pathlib import Path


def app_data():
    override=os.environ.get('MCYARD_DATA_DIR')
    root=Path(override).expanduser() if override else Path(os.environ.get('LOCALAPPDATA',Path.home()/'AppData/Local'))/'MCyard Server'
    root.mkdir(parents=True,exist_ok=True)
    return root.resolve()


def resource_path(name):
    root=Path(sys._MEIPASS)/'resources' if getattr(sys,'frozen',False) else Path(__file__).resolve().parents[2]/'resources'
    if not root.is_dir():root=Path(sys.prefix)/'share/mcyard'
    result=(root/name).resolve()
    if not result.is_relative_to(root.resolve()):raise ValueError('Invalid resource path')
    return result


def launch_command(*args):
    if getattr(sys,'frozen',False):return sys.executable,list(args)
    return sys.executable,['-m','mcyard',*args]
