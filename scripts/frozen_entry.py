"""Executable bootstrap with a local diagnostic for startup failures."""
import os
from pathlib import Path
import sys
import traceback


def launch():
    try:
        from mcyard.__main__ import main
        return main()
    except Exception:
        detail=traceback.format_exc()
        directory=Path(os.environ.get('MCYARD_DATA_DIR') or
                       str(Path(os.environ.get('LOCALAPPDATA',Path.home()/'AppData/Local'))/'MCyard Server'))
        log=directory/'startup-error.log'
        try:
            directory.mkdir(parents=True,exist_ok=True)
            log.write_text(detail,encoding='utf-8')
        except OSError:pass
        # Automation and background backups must fail rather than wait on a dialog.
        if not any(flag in sys.argv for flag in ('--smoke-test','--screenshot','--backup','--install-java')):
            try:
                from PySide6.QtWidgets import QApplication,QMessageBox
                app=QApplication.instance() or QApplication([])
                QMessageBox.critical(None,'MCyard Server could not start',
                    'Startup failed. Details were saved to:\n'+str(log)+'\n\n'+detail.splitlines()[-1])
            except Exception:pass
        return 1

if __name__=='__main__':
    sys.exit(launch())
