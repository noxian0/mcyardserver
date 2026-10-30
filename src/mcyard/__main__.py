"""One executable: server library, per-server manager and isolated backup worker."""
import argparse
import contextlib
import os
from pathlib import Path
import sys
import traceback


def main(argv=None):
    parser=argparse.ArgumentParser(prog='MCyard Server')
    group=parser.add_mutually_exclusive_group()
    group.add_argument('--server',type=Path)
    group.add_argument('--backup',type=Path)
    group.add_argument('--install-java',type=int,choices=(17,21,25),metavar='VERSION',
                       help='Install a compatible Java runtime for this user (17, 21 or 25).')
    parser.add_argument('--smoke-test',action='store_true',help=argparse.SUPPRESS)
    parser.add_argument('--screenshot',type=Path,help=argparse.SUPPRESS)
    args=parser.parse_args(argv)
    if args.install_java:
        from datetime import datetime,timezone
        from .paths import app_data
        from .runtime_install import install_java
        log=app_data()/'prerequisites.log'
        with log.open('a',encoding='utf-8') as output:
            def progress(message):
                output.write(str(message)+'\n');output.flush()
            progress(f'[{datetime.now(timezone.utc).isoformat()}] Java {args.install_java} setup')
            try:
                result=install_java(args.install_java,progress=progress)
                progress('Ready: '+str(result['path']));return 0
            except Exception:
                traceback.print_exc(file=output);return 1
    if args.backup:
        from .registry import read_server
        read_server(args.backup)
        from .backup import main as snapshot
        log=args.backup/'manager/data/backup-last.log';log.parent.mkdir(parents=True,exist_ok=True)
        with log.open('w',encoding='utf-8') as output,contextlib.redirect_stdout(output),contextlib.redirect_stderr(output):
            try:snapshot(args.backup);return 0
            except Exception:traceback.print_exc();return 1
    from PySide6.QtCore import QLockFile,QProcess,QTimer
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication,QMessageBox
    from .paths import app_data,resource_path,launch_command
    from .manager.theme import STYLE
    app=QApplication(sys.argv[:1]);app.setApplicationName('MCyard Server');app.setOrganizationName('MCyard Server')
    app.setStyle('Fusion');app.setStyleSheet(STYLE);app.setWindowIcon(QIcon(str(resource_path('mcyard.svg'))))
    if args.server:
        from .registry import read_server
        try:read_server(args.server)
        except (ValueError,OSError) as exc:QMessageBox.warning(None,'MCyard Server',str(exc));return 1
        os.environ['MCYARD_SERVER_ROOT']=str(args.server.resolve())
        from .manager.core import DATA
        DATA.mkdir(parents=True,exist_ok=True)
        lock=QLockFile(str(DATA/'manager.lock'));lock.setStaleLockTime(0)
        if not lock.tryLock(100):QMessageBox.information(None,'MCyard Server','This server manager is already open.');return 0
        from .manager.app import Window
        window=Window()
    else:
        lock=QLockFile(str(app_data()/'library.lock'));lock.setStaleLockTime(0)
        if not lock.tryLock(100):QMessageBox.information(None,'MCyard Server','Your server library is already open.');return 0
        def launch(root):
            program,arguments=launch_command('--server',str(root))
            result=QProcess.startDetached(program,arguments,str(root))
            if not result[0]:QMessageBox.warning(None,'MCyard Server','Could not open the server manager.')
        from .hub import HubWindow
        window=HubWindow(launch_server=launch)
    window.show()
    if args.smoke_test or args.screenshot:
        def done():
            if args.screenshot:
                args.screenshot.parent.mkdir(parents=True,exist_ok=True);window.grab().save(str(args.screenshot))
            app.quit()
        QTimer.singleShot(1000,done)
    return app.exec()


if __name__=='__main__':
    sys.exit(main())
