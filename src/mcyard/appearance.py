"""Small appearance controls shared by the library and server managers."""
from PySide6.QtWidgets import QCheckBox,QLabel,QMessageBox
from .preferences import motion_enabled,motion_signals,set_motion_enabled,reduced_motion_forced


CREDITS='GitHub: noxian0 | Discord: noxian_'


class AnimationToggle(QCheckBox):
    def __init__(self,parent=None):
        super().__init__('Animations',parent)
        self.setObjectName('animationsToggle')
        self.setToolTip('Panorama movement and interface transitions. World lighting still follows the server when motion is off.')
        self._sync(motion_enabled())
        motion_signals().changed.connect(self._sync)
        self.toggled.connect(self._save)

    def _sync(self,enabled):
        self.blockSignals(True);self.setChecked(enabled);self.blockSignals(False)
        self.setEnabled(not reduced_motion_forced())
        if reduced_motion_forced():self.setToolTip('Animations are disabled by MCYARD_REDUCED_MOTION.')

    def _save(self,enabled):
        try:set_motion_enabled(enabled)
        except (OSError,ValueError) as exc:
            self._sync(motion_enabled());QMessageBox.warning(self,'Appearance',str(exc))


def add_credits(window):
    label=QLabel(CREDITS,window);label.setObjectName('credits')
    label.setStyleSheet('color:#89967f;font-size:11px;padding:2px 8px;')
    window.statusBar().addPermanentWidget(label)
    return label
