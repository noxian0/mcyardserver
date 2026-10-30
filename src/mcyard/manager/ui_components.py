"""Small, local-only presentation primitives for the desktop manager.

The vector icons are original drawings. No Minecraft artwork is bundled here.
Set MCYARD_REDUCED_MOTION=1 to disable motion, and MCYARD_BACKGROUND_IMAGE to use a
local image in PanoramaHeader. Components retain the regular Qt widget APIs.
"""
from functools import lru_cache
import math
import time

from PySide6.QtCore import (
    QByteArray, QEvent, QEasingCurve, QPointF, Property, QPropertyAnimation, QRectF, QSize, Qt, QTimer,
)
from PySide6.QtGui import QColor, QIcon, QLinearGradient, QPainter, QPainterPath, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QComboBox, QListWidget, QPushButton, QStackedWidget, QWidget
from ..preferences import motion_enabled, motion_signals


def reduced_motion():
    return not motion_enabled()


# All shapes use a common 24-unit canvas and a quiet 1.65-unit stroke.
_ICONS = {
    'home': '<path d="m3 10 9-7 9 7v10a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1Z"/>',
    'users': '<circle cx="9" cy="8" r="3"/><path d="M3 21v-3a6 6 0 0 1 12 0v3M16 5a3 3 0 0 1 0 6m2 4a5 5 0 0 1 3 4v2"/>',
    'sliders': '<path d="M4 6h7m4 0h5M4 12h2m4 0h10M4 18h10m4 0h2"/><circle cx="13" cy="6" r="2"/><circle cx="8" cy="12" r="2"/><circle cx="16" cy="18" r="2"/>',
    'settings': '<path d="m10 3-.6 3-2 .9-2.6-1L3 9l2 2v2l-2 2 1.8 3.1 2.6-1 2 .9.6 3h4l.6-3 2-.9 2.6 1L21 15l-2-2v-2l2-2-1.8-3.1-2.6 1-2-.9L14 3Z"/><circle cx="12" cy="12" r="3"/>',
    'terminal': '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="m7 9 3 3-3 3m6 1h4"/>',
    'archive': '<rect x="3" y="3" width="18" height="5" rx="1"/><path d="M5 8v12h14V8m-9 4h4"/>',
    'history': '<path d="M3 4v5h5M3 9a9 9 0 1 1 .4 7M12 7v5l3 2"/>',
    'play': '<path d="m8 4 12 8-12 8Z"/>',
    'stop': '<rect x="6" y="6" width="12" height="12" rx="1"/>',
    'restart': '<path d="M20 4v6h-6M20 10a8 8 0 1 0 0 5"/>',
    'save': '<path d="M4 3h13l4 4v14H3V4a1 1 0 0 1 1-1Zm3 0v6h9V3M7 21v-8h10v8"/>',
    'sun': '<circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.4 1.4m11.2 11.2L19 19M5 19l1.4-1.4M17.6 6.4 19 5"/>',
    'cloud': '<path d="M7 18h11a4 4 0 0 0 .4-8A6 6 0 0 0 7 8a5 5 0 0 0 0 10Z"/>',
    'folder': '<path d="M3 6a2 2 0 0 1 2-2h5l2 3h7a2 2 0 0 1 2 2v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1Z"/>',
    'search': '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m15.5 15.5 5 5"/>',
    'chevron': '<path d="m9 5 7 7-7 7"/>',
    'copy': '<rect x="8" y="8" width="13" height="13" rx="2"/><path d="M16 5V3H3v13h2"/>',
    'shield': '<path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6Z"/><path d="m8 12 3 3 5-6"/>',
    'kick': '<path d="M10 4H4v16h6m3-12 4 4-4 4m-5-4h13"/>',
    'ban': '<circle cx="12" cy="12" r="9"/><path d="m6 6 12 12"/>',
    'unban': '<path d="M20 10a8 8 0 1 0-4 9m0-2 3 3 4-5"/>',
    'pin': '<path d="M19 10c0 5-7 11-7 11S5 15 5 10a7 7 0 0 1 14 0Z"/><circle cx="12" cy="10" r="2"/>',
    'teleport': '<path d="m13 2-8 11h6l-1 9 9-12h-7Z"/>',
    'inventory': '<rect x="3" y="4" width="18" height="17" rx="2"/><path d="M3 9h18M9 9v12m6-12v12M3 15h18"/>',
    'arrow': '<path d="M4 12h16m-6-6 6 6-6 6"/>',
    'more': '<circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/>',
    'external': '<path d="M14 3h7v7m0-7L10 14M10 4H4v16h16v-6"/>',
    'download': '<path d="M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5"/>',
    'check': '<path d="m4 12 5 5L20 6"/>',
    'close': '<path d="m6 6 12 12M18 6 6 18"/>',
    'info': '<circle cx="12" cy="12" r="9"/><path d="M12 11v6m0-10v.1"/>',
    'cpu': '<rect x="6" y="6" width="12" height="12" rx="1"/><rect x="9" y="9" width="6" height="6"/><path d="M9 3v3m6-3v3M9 18v3m6-3v3M3 9h3m-3 6h3m12-6h3m-3 6h3"/>',
    'clock': '<circle cx="12" cy="12" r="9"/><path d="M12 6v6l4 2"/>',
    'memory': '<rect x="2" y="6" width="20" height="12" rx="1"/><path d="M6 10h4v4H6Zm8 0h4v4h-4ZM5 18v3m5-3v3m4-3v3m5-3v3"/>',
    'link': '<path d="m10 7 2-2a5 5 0 0 1 7 7l-2 2m-3 3-2 2a5 5 0 0 1-7-7l2-2m1 6 8-8"/>',
}


@lru_cache(maxsize=256)
def icon(name, color='#b9c0bc', size=20):
    """Return an original, antialiased monochrome icon (create after QApplication)."""
    paths = _ICONS.get(name, _ICONS['more'])
    # QColor normalization also avoids interpolating arbitrary markup into SVG.
    shade = QColor(color).name()
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" '
           f'viewBox="0 0 24 24" fill="none" stroke="{shade}" stroke-width="1.65" '
           f'stroke-linecap="round" stroke-linejoin="round">{paths}</svg>')
    pixmap = QPixmap(size * 2, size * 2)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    QSvgRenderer(QByteArray(svg.encode())).render(painter)
    painter.end()
    pixmap.setDevicePixelRatio(2)
    return QIcon(pixmap)


class HoverButton(QPushButton):
    """Native button behavior with a hover glow and a bounded press ripple."""
    def __init__(self, text='', parent=None):
        super().__init__(text, parent)
        self._hover = 0.0
        self._ripple = 1.0
        self._press_origin = None
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setIconSize(QSize(18, 18))
        self._motion = QPropertyAnimation(self, b'hoverProgress', self)
        self._motion.setDuration(140)
        self._motion.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._press_motion = QPropertyAnimation(self, b'rippleProgress', self)
        self._press_motion.setDuration(310)
        self._press_motion.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.pressed.connect(self._pulse)
        motion_signals().changed.connect(self._motion_preference_changed)

    def _motion_preference_changed(self,enabled):
        if not enabled:
            self._motion.stop();self._press_motion.stop()
            self._set_hover(1.0 if self.underMouse() and self.isEnabled() else 0.0)
            self._set_ripple(1.0)

    def _get_hover(self):
        return self._hover

    def _set_hover(self, value):
        self._hover = float(value)
        self.update()

    hoverProgress = Property(float, _get_hover, _set_hover)

    def _get_ripple(self):return self._ripple

    def _set_ripple(self,value):
        self._ripple=float(value);self.update()

    rippleProgress=Property(float,_get_ripple,_set_ripple)

    def _pulse(self):
        self._press_motion.stop()
        if reduced_motion() or not self.isVisible():
            self._set_ripple(1.0);return
        if self._press_origin is None:self._press_origin=QPointF(self.rect().center())
        self._press_motion.setStartValue(0.0);self._press_motion.setEndValue(1.0)
        self._press_motion.start()

    def mousePressEvent(self,event):
        self._press_origin=event.position()
        super().mousePressEvent(event)

    def keyPressEvent(self,event):
        self._press_origin=QPointF(self.rect().center())
        super().keyPressEvent(event)

    def _animate(self, target):
        self._motion.stop()
        if reduced_motion():
            self._set_hover(target)
            return
        self._motion.setStartValue(self._hover)
        self._motion.setEndValue(target)
        self._motion.start()

    def enterEvent(self, event):
        if self.isEnabled():
            self._animate(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._animate(0.0)
        super().leaveEvent(event)

    def hideEvent(self, event):
        self._motion.stop()
        self._press_motion.stop()
        self._hover = 0.0
        self._ripple = 1.0
        super().hideEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self.isEnabled() or (self._hover <= 0 and self._ripple >= 1):
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        clip=QPainterPath();clip.addRoundedRect(QRectF(self.rect()).adjusted(1,1,-1,-1),5,5)
        painter.setClipPath(clip)
        painter.setBrush(QColor(229, 240, 231, round(17 * self._hover)))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 5, 5)
        if self._ripple < 1:
            shade=QColor('#233019' if self.objectName()=='primary' else '#c7e5ac')
            shade.setAlpha(round(42*(1-self._ripple)))
            painter.setBrush(shade)
            radius=math.hypot(self.width(),self.height())*self._ripple
            painter.drawEllipse(self._press_origin or QPointF(self.rect().center()),radius,radius)


class _SelectionAccent(QWidget):
    """A moving accent over the native selection, without intercepting input."""
    def __init__(self,parent):
        super().__init__(parent);self._rect=QRectF();self._hover_rect=QRectF();self._hover_opacity=0.0
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def _get_rect(self):return self._rect

    def _set_rect(self,value):self._rect=QRectF(value);self.update()

    selectionRect=Property(QRectF,_get_rect,_set_rect)

    def _get_hover_rect(self):return self._hover_rect

    def _set_hover_rect(self,value):self._hover_rect=QRectF(value);self.update()

    hoverRect=Property(QRectF,_get_hover_rect,_set_hover_rect)

    def _get_hover_opacity(self):return self._hover_opacity

    def _set_hover_opacity(self,value):self._hover_opacity=float(value);self.update()

    hoverOpacity=Property(float,_get_hover_opacity,_set_hover_opacity)

    def paintEvent(self,event):
        painter=QPainter(self);painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        if not self._hover_rect.isEmpty() and self._hover_opacity>0:
            painter.setBrush(QColor(184,217,136,round(16*self._hover_opacity)))
            painter.drawRoundedRect(self._hover_rect,5,5)
        if self._rect.isEmpty():return
        painter.setBrush(QColor(184,217,136,12))
        painter.drawRoundedRect(self._rect,5,5)
        painter.setBrush(QColor('#b8d988'))
        painter.drawRoundedRect(QRectF(self._rect.left()+1,self._rect.top()+8,2,max(4,self._rect.height()-16)),1,1)


class AnimatedList(QListWidget):
    """Native list behavior with moving selection and hover accents; no idle timer."""
    def __init__(self,parent=None):
        super().__init__(parent)
        self._accent=_SelectionAccent(self.viewport())
        self._selection_motion=QPropertyAnimation(self._accent,b'selectionRect',self)
        self._selection_motion.setDuration(240)
        self._selection_motion.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._hover_row=-1;self.setMouseTracking(True)
        self._hover_motion=QPropertyAnimation(self._accent,b'hoverRect',self)
        self._hover_fade=QPropertyAnimation(self._accent,b'hoverOpacity',self)
        for animation in (self._hover_motion,self._hover_fade):
            animation.setDuration(150);animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.currentRowChanged.connect(self._selection_changed)
        self.verticalScrollBar().valueChanged.connect(lambda _:self._sync_accent())
        self.horizontalScrollBar().valueChanged.connect(lambda _:self._sync_accent())
        self.model().modelReset.connect(self._sync_accent)
        self.model().rowsRemoved.connect(lambda *_:self._sync_accent())
        motion_signals().changed.connect(self._motion_preference_changed)

    def _motion_preference_changed(self,enabled):
        if not enabled:self._sync_accent()

    def _target_rect(self):
        item=self.currentItem()
        return QRectF(self.visualItemRect(item)).adjusted(0,2,-1,-2) if item is not None else QRectF()

    def _sync_accent(self):
        self._selection_motion.stop();self._accent.setGeometry(self.viewport().rect())
        self._accent.selectionRect=self._target_rect();self._accent.raise_()
        self._clear_hover()

    def _clear_hover(self):
        self._hover_motion.stop();self._hover_fade.stop();self._hover_row=-1
        self._accent.hoverRect=QRectF();self._accent.hoverOpacity=0.0

    def _hover_changed(self,item):
        row=self.row(item) if item is not None else -1
        if row==self._hover_row:return
        self._hover_row=row
        self._hover_motion.stop();self._hover_fade.stop()
        target=QRectF(self.visualItemRect(item)).adjusted(0,2,-1,-2) if item is not None else QRectF()
        opacity=0.0 if target.isEmpty() else 1.0
        if reduced_motion():
            self._accent.hoverRect=target;self._accent.hoverOpacity=opacity;return
        if not target.isEmpty():
            if self._accent.hoverRect.isEmpty():self._accent.hoverRect=target
            else:
                self._hover_motion.setStartValue(self._accent.hoverRect)
                self._hover_motion.setEndValue(target);self._hover_motion.start()
        self._hover_fade.setStartValue(self._accent.hoverOpacity)
        self._hover_fade.setEndValue(opacity);self._hover_fade.start()

    def mouseMoveEvent(self,event):
        self._hover_changed(self.itemAt(event.position().toPoint()))
        super().mouseMoveEvent(event)

    def viewportEvent(self,event):
        if event.type()==QEvent.Type.Leave and hasattr(self,'_hover_fade'):self._hover_changed(None)
        return super().viewportEvent(event)

    def _selection_changed(self,index):
        target=self._target_rect();self._selection_motion.stop()
        self._accent.setGeometry(self.viewport().rect());self._accent.raise_()
        if target.isEmpty() or self._accent.selectionRect.isEmpty() or not self.isVisible() or reduced_motion():
            self._accent.selectionRect=target;return
        self._selection_motion.setStartValue(self._accent.selectionRect)
        self._selection_motion.setEndValue(target);self._selection_motion.start()

    def resizeEvent(self,event):
        super().resizeEvent(event);self._sync_accent()

    def showEvent(self,event):
        super().showEvent(event);self._sync_accent()

    def hideEvent(self,event):
        self._selection_motion.stop();self._clear_hover();super().hideEvent(event)


class BoolSwitch(QComboBox):
    """Boolean switch retaining the QComboBox text API used by saved settings.

    Populate with addItems(['true', 'false']) and read currentText() as usual.
    Text remains 'true'/'false' internally; the compact painted label is On/Off.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('boolSwitch')
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._position = 0.0
        self._motion = QPropertyAnimation(self, b'thumbPosition', self)
        self._motion.setDuration(145)
        self._motion.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.currentTextChanged.connect(self._state_changed)
        self.setAccessibleDescription('Boolean setting. Space toggles on or off.')
        motion_signals().changed.connect(self._motion_preference_changed)

    def _motion_preference_changed(self,enabled):
        if not enabled:
            self._motion.stop();self._set_position(1.0 if self.currentText()=='true' else 0.0)

    def _get_position(self):
        return self._position

    def _set_position(self, value):
        self._position = float(value)
        self.update()

    thumbPosition = Property(float, _get_position, _set_position)

    def _state_changed(self, text):
        self._motion.stop()
        target = 1.0 if text == 'true' else 0.0
        if not self.isVisible() or reduced_motion():
            self._set_position(target)
        else:
            self._motion.setStartValue(self._position)
            self._motion.setEndValue(target)
            self._motion.start()
        self.setAccessibleDescription(f'{"On" if target else "Off"}. Space toggles this setting.')

    def _toggle(self):
        if self.isEnabled():
            self.setCurrentText('false' if self.currentText() == 'true' else 'true')

    def showPopup(self):
        self._toggle()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.setFocus(Qt.FocusReason.MouseFocusReason)
            event.accept()
        else:
            event.ignore()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self._toggle()
            event.accept()
        else:
            event.ignore()

    def keyPressEvent(self, event):
        if not self.isEnabled():
            event.ignore()
            return
        if event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._toggle()
            event.accept()
        elif event.key() in (Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Home):
            self.setCurrentText('true')
            event.accept()
        elif event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Down, Qt.Key.Key_End):
            self.setCurrentText('false')
            event.accept()
        else:
            super().keyPressEvent(event)

    def wheelEvent(self, event):
        event.ignore()

    def sizeHint(self):
        return QSize(100, 36)

    def minimumSizeHint(self):
        return QSize(88, 30)

    def hideEvent(self, event):
        self._motion.stop()
        self._position = 1.0 if self.currentText() == 'true' else 0.0
        super().hideEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        enabled = self.isEnabled()
        state = self.currentText() == 'true'
        label_color = '#d9e0da' if enabled else '#68736b'
        track_color = QColor('#6e8760' if enabled and state else '#374139')
        if self.underMouse() and enabled:
            track_color = track_color.lighter(115)
        painter.setPen(QColor(label_color))
        painter.drawText(QRectF(10, 0, self.width() - 57, self.height()),
                         Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                         'On' if state else 'Off')
        track = QRectF(self.width() - 45, (self.height() - 19) / 2, 34, 19)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(track_color)
        painter.drawRoundedRect(track, 9.5, 9.5)
        painter.setBrush(QColor('#d0e5bd' if enabled else '#7b857d'))
        painter.drawEllipse(QRectF(track.x() + 3 + self._position * 15, track.y() + 3, 13, 13))
        if self.hasFocus():
            painter.setPen(QColor('#b8d988'))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(track.adjusted(-3, -3, 3, 3), 12, 12)


class _PageSnapshot(QWidget):
    """Slide and crossfade snapshots while the current page stays interactive."""
    def __init__(self, pixmap, incoming, direction, parent):
        super().__init__(parent)
        self.pixmap = pixmap
        self.incoming = incoming
        self.direction = direction
        self._opacity = 1.0
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setAutoFillBackground(False)
        self.setObjectName('pageTransitionOverlay')

    def _get_opacity(self):
        return self._opacity

    def _set_opacity(self, value):
        self._opacity = float(value)
        self.update()

    opacity = Property(float, _get_opacity, _set_opacity)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(),QColor('#121614'))
        progress=1-self._opacity
        painter.setOpacity(self._opacity)
        painter.drawPixmap(self.rect().translated(round(-24*self.direction*progress),0),self.pixmap)
        painter.setOpacity(progress)
        painter.drawPixmap(self.rect().translated(round(24*self.direction*(1-progress)),0),self.incoming)


class AnimatedStack(QStackedWidget):
    """A short directional slide/fade; new pages receive input immediately."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._overlay = None
        self._animation = None
        motion_signals().changed.connect(self._motion_preference_changed)

    def _motion_preference_changed(self,enabled):
        if not enabled:self._clear_transition()

    def _clear_transition(self):
        if self._animation is not None:
            self._animation.stop()
            self._animation.deleteLater()
            self._animation = None
        if self._overlay is not None:
            self._overlay.hide()
            self._overlay.deleteLater()
            self._overlay = None

    def setCurrentIndex(self, index):
        if index == self.currentIndex() or not 0 <= index < self.count():
            return
        snapshot = None
        direction=1 if index>self.currentIndex() else -1
        if self.isVisible() and self.currentWidget() is not None and not reduced_motion():
            # Capturing an in-flight fade makes rapid tab changes continuous.
            snapshot = self.grab()
        self._clear_transition()
        super().setCurrentIndex(index)
        if snapshot is None or snapshot.isNull():
            return
        # Capture the stack for both frames. Grabbing a transparent child page
        # alone gives it Qt's light palette background and flashes gray mid-fade.
        incoming=self.grab()
        self._overlay = _PageSnapshot(snapshot,incoming,direction,self)
        self._overlay.setGeometry(self.rect())
        self._overlay.show()
        self._overlay.raise_()
        self._animation = QPropertyAnimation(self._overlay, b'opacity', self)
        self._animation.setDuration(240)
        self._animation.setStartValue(1.0)
        self._animation.setEndValue(0.0)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._animation.finished.connect(self._clear_transition)
        self._animation.start()

    def setCurrentWidget(self, widget):
        self.setCurrentIndex(self.indexOf(widget))

    def resizeEvent(self, event):
        self._clear_transition()
        super().resizeEvent(event)

    def hideEvent(self, event):
        self._clear_transition()
        super().hideEvent(event)


class PanoramaHeader(QWidget):
    """A cached panorama with a gentle camera move and real Overworld lighting.

    The image is cropped/scaled only when its size changes. A single 30fps timer
    paints visible headers; hidden/minimized headers and reduced-motion mode have
    no animation timer. World time is supplied by telemetry, never extrapolated.
    """
    FRAME_MS = 33
    PAN_SECONDS = 32.0
    LIGHT_SECONDS = 1.2

    def __init__(self, image_path=None, parent=None, height=240):
        super().__init__(parent)
        self.setObjectName('panoramaHeader');self.setFixedHeight(height)
        self._source=QPixmap();self._scaled=QPixmap()
        self._phase=0.0;self._last_tick=None;self._observed_window=None
        self._day_time=None;self._world_live=False
        self._lighting=(0.0,0.0,0.0,0.0)
        self._lighting_from=self._lighting;self._target_lighting=self._lighting
        self._light_started=None
        self._timer=QTimer(self);self._timer.setInterval(self.FRAME_MS)
        self._timer.timeout.connect(self._tick)
        motion_signals().changed.connect(self._motion_preference_changed)
        from ..backgrounds import background_path
        self.setImage(image_path if image_path is not None else background_path())

    @staticmethod
    def _world_lighting(day_time,raining=False,thundering=False):
        # Dawn is 0 ticks, midday 6000, sunset around 12000, midnight 18000.
        # Each tuple describes blue night shade, warm horizon, daylight lift.
        if day_time is None:return (0.0,0.0,0.0,0.0)
        frames=((0,(25,16,10)),(1000,(0,0,24)),(11000,(0,0,24)),
                (12500,(72,40,0)),(13500,(174,0,0)),(22500,(174,0,0)),
                (23500,(78,27,0)),(24000,(25,16,10)))
        value=float(day_time)%24000
        for (start,a),(end,b) in zip(frames,frames[1:]):
            if start<=value<=end:
                fraction=(value-start)/(end-start)
                fraction=fraction*fraction*(3-2*fraction)
                colors=tuple(x+(y-x)*fraction for x,y in zip(a,b))
                return (*colors,85.0 if thundering else 52.0 if raining else 0.0)
        return (0.0,0.0,0.0,0.0)

    def set_world_state(self,day_time=None,raining=False,thundering=False,live=False):
        valid=isinstance(day_time,(int,float)) and not isinstance(day_time,bool)
        if valid:
            try:valid=math.isfinite(day_time)
            except (OverflowError,TypeError):valid=False
        value=float(day_time)%24000 if valid else None
        first=self._day_time is None
        self._day_time=value;self._world_live=bool(live and value is not None)
        target=self._world_lighting(value,bool(raining),bool(thundering))
        if target==self._target_lighting:return
        self._advance_light(time.monotonic())
        self._lighting_from=self._lighting;self._target_lighting=target
        if first or not self._animation_allowed():
            self._settle_lighting()
        else:self._light_started=time.monotonic()
        self.update();self._update_timer()

    def setImage(self,image_path):
        self._source=QPixmap(str(image_path)) if image_path else QPixmap()
        self._rescale();self.update();self._update_timer()

    def _rescale(self):
        if self._source.isNull() or self.width()<=0:
            self._scaled=QPixmap();return
        # Crop before scaling, rather than caching a giant square panorama for
        # every narrow page banner. Overscan covers the complete camera path.
        width=self.width()+180;height=self.height()+36
        ratio=width/height;source_width=self._source.width();source_height=self._source.height()
        crop_width=min(source_width,round(source_height*ratio))
        crop_height=min(source_height,round(source_width/ratio))
        cropped=self._source.copy((source_width-crop_width)//2,(source_height-crop_height)//2,
                                  max(1,crop_width),max(1,crop_height))
        dpr=self.devicePixelRatioF()
        self._scaled=cropped.scaled(round(width*dpr),round(height*dpr),
            Qt.AspectRatioMode.IgnoreAspectRatio,Qt.TransformationMode.SmoothTransformation)
        self._scaled.setDevicePixelRatio(dpr)

    def _animation_allowed(self):
        return (self.isVisible() and not self.window().isMinimized()
                and not self._source.isNull() and not reduced_motion())

    def _settle_lighting(self):
        self._lighting=self._target_lighting;self._lighting_from=self._lighting
        self._light_started=None

    def _advance_light(self,now):
        if self._light_started is None:return
        amount=min(1.0,max(0.0,(now-self._light_started)/self.LIGHT_SECONDS))
        smooth=amount*amount*(3-2*amount)
        self._lighting=tuple(a+(b-a)*smooth for a,b in zip(self._lighting_from,self._target_lighting))
        if amount>=1.0:self._settle_lighting()

    def _update_timer(self):
        if self._animation_allowed():
            if not self._timer.isActive():
                self._last_tick=time.monotonic();self._timer.start()
        else:
            self._timer.stop();self._last_tick=None;self._settle_lighting()

    def _motion_preference_changed(self,enabled):
        self._update_timer();self.update()

    def _tick(self):
        if not self._animation_allowed():
            self._update_timer();return
        now=time.monotonic()
        elapsed=min(.25,max(0.0,now-(self._last_tick or now)))
        self._last_tick=now
        self._phase=(self._phase+elapsed*math.tau/self.PAN_SECONDS)%(math.tau*2)
        self._advance_light(now);self.update()

    def _watch_window(self):
        window=self.window()
        if window is self._observed_window:return
        if self._observed_window is not None:
            try:self._observed_window.removeEventFilter(self)
            except RuntimeError:pass
        self._observed_window=window
        if window is not self:window.installEventFilter(self)

    def eventFilter(self,watched,event):
        if watched is self._observed_window and event.type() in (
                QEvent.Type.WindowStateChange,QEvent.Type.Hide,QEvent.Type.Show):
            self._update_timer()
        return super().eventFilter(watched,event)

    def changeEvent(self,event):
        if event.type()==QEvent.Type.WindowStateChange:self._update_timer()
        super().changeEvent(event)

    def showEvent(self,event):
        super().showEvent(event);self._watch_window();self._update_timer()

    def hideEvent(self,event):
        self._timer.stop();self._last_tick=None;self._settle_lighting()
        super().hideEvent(event)

    def resizeEvent(self,event):
        self._rescale();super().resizeEvent(event)

    def paintEvent(self,event):
        painter=QPainter(self);painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        clip=QPainterPath();clip.addRoundedRect(QRectF(self.rect()),8,8);painter.setClipPath(clip)
        painter.fillRect(self.rect(),QColor('#151c18'))
        if not self._scaled.isNull():
            dpr=self._scaled.devicePixelRatio()
            # Fractional coordinates retain a smooth drift on high-DPI displays.
            x=(self.width()-self._scaled.width()/dpr)/2+72*math.sin(self._phase)
            y=(self.height()-self._scaled.height()/dpr)/2+7*math.sin(self._phase*.5)
            painter.drawPixmap(QPointF(x,y),self._scaled)
        night,warm,lift,weather=self._lighting
        if lift>0:
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Screen)
            painter.fillRect(self.rect(),QColor(105,158,177,round(lift)))
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        if warm>0:painter.fillRect(self.rect(),QColor(235,137,72,round(warm)))
        if night>0:painter.fillRect(self.rect(),QColor(6,13,36,round(night)))
        if weather>0:painter.fillRect(self.rect(),QColor(31,40,49,round(weather)))
        wash=QLinearGradient(0,0,self.width(),0)
        wash.setColorAt(0,QColor(14,19,16,215));wash.setColorAt(.48,QColor(14,19,16,115))
        wash.setColorAt(1,QColor(14,19,16,38));painter.fillRect(self.rect(),wash)
        fade=QLinearGradient(0,0,0,self.height())
        fade.setColorAt(0,QColor(16,20,17,5));fade.setColorAt(.55,QColor(16,20,17,25))
        fade.setColorAt(1,QColor(16,20,17,230));painter.fillRect(self.rect(),fade)
