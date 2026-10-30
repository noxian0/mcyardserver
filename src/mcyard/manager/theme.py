"""Presentation tokens kept separate from server control and saved data."""
from ..paths import resource_path
STYLE = '''
QWidget { color:#e3e7df; font-family:"Segoe UI"; font-size:13px; }
QMainWindow,QDialog,QMessageBox,QInputDialog { background:#121614; }
QWidget#shell,QStackedWidget { background:#121614; }
QFrame#sidebar { background:#0e120f; border-right:1px solid #242b25; }
QLabel { background:transparent; }
QLabel#muted { color:#87958b; }
QLabel#eyebrow { color:#91a08f; font-size:10px; font-weight:650; letter-spacing:2px; }
QLabel#title { font-size:29px; font-weight:600; letter-spacing:-1px; }
QLabel#heroTitle { font-size:52px; font-weight:650; letter-spacing:-2px; }
QLabel#section { font-size:15px; font-weight:600; }
QLabel#metric { font-size:30px; font-weight:500; letter-spacing:-1px; }
QLabel#pill { color:#a4b79d; font-size:11px; font-weight:600; letter-spacing:1px; }
QFrame#metrics { border-top:1px solid #2b342a; border-bottom:1px solid #2b342a; }
QFrame#divider { background:#293128; max-width:1px; }
QPushButton { background:#242c24; border:1px solid #354032; padding:9px 13px; border-radius:5px; font-weight:600; }
QPushButton:hover { background:#303b2c; border-color:#58674e; }
QPushButton:pressed { background:#3a4733; }
QPushButton:disabled { color:#667264; background:#1a211b; border-color:#283126; }
QPushButton#primary { background:#b8d988; border-color:#b8d988; color:#1a2514; }
QPushButton#primary:hover { background:#c9e7a2; border-color:#c9e7a2; }
QPushButton#primary:disabled { background:#33432a; color:#849278; border-color:#33432a; }
QPushButton#danger { background:transparent; border-color:#50352f; color:#d69b8e; }
QPushButton#danger:hover { background:#3a2823; }
QPushButton#quiet { background:transparent; border-color:transparent; color:#a9b3a5; }
QPushButton#quiet:hover { background:#252e23; color:#e3e7df; }
QPushButton#slot { background:#1b231b; border:1px solid #35412f; border-radius:3px; padding:4px; font-size:10px; font-weight:400; }
QPushButton#slot:hover { background:#2d3a25; border-color:#8ba66c; }
QPushButton#slot:disabled { background:#171d17; color:#4c5b49; border-color:#263022; }
QListWidget#nav { background:transparent; border:none; outline:none; }
QListWidget#nav::item { padding:10px 12px; margin:3px 0; border-radius:4px; color:#8f9c8c; }
QListWidget#nav::item:selected { background:#253020; color:#d2e6bb; }
QListWidget#nav::item:hover:!selected { background:#1a2319; }
QTableWidget { background:transparent; alternate-background-color:transparent; border:none; gridline-color:transparent; selection-background-color:#273522; selection-color:#ecf3e6; outline:none; }
QTableWidget::item { padding:8px; border-bottom:1px solid #252e24; }
QTableWidget::item:selected { background:#273522; }
QHeaderView { background:transparent; }
QHeaderView::section { background:#121614; color:#84927d; padding:10px 8px; border:none; border-bottom:1px solid #35402f; font-size:10px; font-weight:600; }
QTableCornerButton::section { background:#121614; border:none; }
QLineEdit,QSpinBox,QComboBox { background:#191f19; border:1px solid #303a2c; border-radius:4px; padding:8px 10px; min-height:18px; selection-background-color:#50633d; }
QLineEdit:focus,QSpinBox:focus,QComboBox:focus { border-color:#8aa76d; }
QLineEdit:disabled,QComboBox:disabled { color:#687360; border-color:#252d23; }
QComboBox::drop-down { border:none; width:23px; }
QComboBox::down-arrow { image:url("__DOWN_ARROW__"); width:12px; height:12px; }
QComboBox QAbstractItemView { background:#222c20; border:1px solid #45533b; selection-background-color:#3a4b30; }
QTextEdit { background:#0e130f; border:1px solid #293425; border-radius:4px; padding:12px; font-family:Consolas; font-size:12px; color:#bccbb3; selection-background-color:#3b4f30; }
QTabWidget::pane { border:none; border-top:1px solid #303b2b; background:transparent; }
QTabBar::tab { background:transparent; color:#8b9983; border-bottom:2px solid transparent; padding:12px 15px; margin-right:5px; }
QTabBar::tab:selected { border-bottom-color:#b8d988; color:#dce7d4; }
QTabBar::tab:hover { color:#c9dcba; }
QSplitter::handle { background:#283023; width:1px; }
QScrollArea { border:none; background:transparent; }
QScrollBar:vertical { background:transparent; width:8px; }
QScrollBar:horizontal { background:transparent; height:8px; }
QScrollBar::handle { background:#3d4a35; border-radius:4px; min-height:25px; min-width:25px; }
QScrollBar::add-line,QScrollBar::sub-line { width:0; height:0; }
QScrollBar::add-page,QScrollBar::sub-page { background:transparent; }
QProgressBar { background:#293324; border:none; border-radius:2px; max-height:4px; }
QProgressBar::chunk { background:#b8d988; border-radius:2px; }
QMenu { background:#1c251a; border:1px solid #3b4932; padding:5px; }
QMenu::item { padding:9px 25px 9px 12px; }
QMenu::item:selected { background:#35452b; }
QMenu::item:disabled { color:#65735c; }
QMenu::separator { background:#35422e; height:1px; margin:4px; }
QToolTip { background:#2b3823; color:#e5eddd; border:1px solid #526342; padding:7px; }
QStatusBar { background:#0e120f; color:#89967f; font-size:11px; }
QStatusBar::item { border:none; }
'''
STYLE=STYLE.replace('__DOWN_ARROW__',resource_path('chevron-down.svg').as_posix())
