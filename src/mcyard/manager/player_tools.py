"""Explicit inventory transfers and reversible player freeze controls."""
from copy import deepcopy
import re

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QGridLayout,QLabel,
    QComboBox,QSpinBox,QCheckBox,QLineEdit)
from .ui_components import HoverButton,icon


SLOTS=tuple(str(index) for index in range(36))+('head','chest','legs','feet','offhand')


def _label(text='',kind=None):
    widget=QLabel(text);widget.setTextFormat(Qt.TextFormat.PlainText)
    if kind:widget.setObjectName(kind)
    return widget


def _pending(owner,action,payload):
    check=getattr(owner,'action_pending',None)
    return bool(check and check(action,payload))


class ItemTransferDialog(QDialog):
    """A captured slot revision is required; the server validates it again."""
    def __init__(self,owner,source,kind,slot,item):
        super().__init__(owner)
        self.owner=owner;self.source=deepcopy(source);self.kind=kind;self.slot=str(slot)
        self.item=deepcopy(item);self._submitted=False;self._message_edited=False
        self.item_name=str(item.get('name') or item.get('id','Item').split(':')[-1].replace('_',' '))
        self.setWindowTitle('Item · MCyard Server');self.setMinimumWidth(470);self.resize(510,350)
        box=QVBoxLayout(self);box.setContentsMargins(24,22,24,22);box.setSpacing(14)
        title=_label(self.item_name,'section');title.setWordWrap(True);box.addWidget(title)
        count=item.get('count',0)
        self.snapshot_count=count if type(count) is int and count>0 else 0
        place='Ender Chest' if kind=='ender' else 'Inventory'
        box.addWidget(_label(f'{source.get("name","Player")} · {place} · Slot {self.slot} · ×{self.snapshot_count}','muted'))
        form=QGridLayout();form.setHorizontalSpacing(14);form.setVerticalSpacing(7)
        self.recipient=QComboBox();self.recipient.setMinimumWidth(230)
        self.amount=QSpinBox();maximum=max(1,min(999,self.snapshot_count));self.amount.setRange(1,maximum);self.amount.setValue(maximum)
        form.addWidget(_label('Move to','muted'),0,0);form.addWidget(_label('Amount','muted'),0,1)
        form.addWidget(self.recipient,1,0);form.addWidget(self.amount,1,1);form.setColumnStretch(0,1);box.addLayout(form)
        self.announce=QCheckBox('Announce in chat');self.announce.setChecked(False);box.addWidget(self.announce)
        self.message=QLineEdit();self.message.setMaxLength(200)
        self.message.setPlaceholderText('Message for everyone on the server');self.message.hide();box.addWidget(self.message)
        self.message.textEdited.connect(self._message_changed)
        self.announce.toggled.connect(self.message.setVisible)
        self.announce.toggled.connect(self._announcement_changed)
        self.recipient.currentIndexChanged.connect(self._selection_changed)
        self.amount.valueChanged.connect(self._default_message)
        self.reason=_label('','muted');self.reason.setWordWrap(True);box.addWidget(self.reason)
        buttons=QHBoxLayout();buttons.setSpacing(8)
        self.details=HoverButton('Details');self.details.setIcon(icon('info'))
        self.details.clicked.connect(lambda:self.owner.show_json('Item details',self.item));buttons.addWidget(self.details);buttons.addStretch()
        cancel=HoverButton('Cancel');cancel.clicked.connect(self.reject);buttons.addWidget(cancel)
        self.transfer=HoverButton('Transfer');self.transfer.setObjectName('primary');self.transfer.setIcon(icon('arrow','#233019'))
        self.transfer.clicked.connect(self.submit);self.transfer.setDefault(True);buttons.addWidget(self.transfer);box.addLayout(buttons)
        self.refresh_availability()

    def _message_changed(self,*_):self._message_edited=True

    def _announcement_changed(self,checked):
        if checked:self._default_message()

    def _default_message(self,*_):
        if self._message_edited:return
        name=self.recipient.currentText() if self.recipient.currentData() else 'another player'
        self.message.setText(f'Moved {self.amount.value()}× {self.item_name} from {self.source.get("name","Player")} to {name}.')

    def _selection_changed(self,*_):
        self._default_message();self._apply_availability()

    def _payload(self):
        return {'source':self.source.get('uuid',''),'target':self.recipient.currentData(),
                'kind':self.kind,'slot':self.slot,'count':self.amount.value(),
                'expected':self.item.get('revision',''),
                'message':self.message.text().strip() if self.announce.isChecked() else ''}

    def _availability_reason(self):
        if self._submitted:return 'Waiting for the server…'
        state=getattr(self.owner,'state',{})
        if not state.get('fresh'):return 'Start the server to transfer items.'
        if not state.get('features',{}).get('inventoryTransfer'):return 'This server does not support item transfers.'
        source=next((p for p in self.owner.people if p.get('uuid')==self.source.get('uuid')),None)
        if not source or not source.get('online'):return 'This player is offline.'
        expected=self.item.get('revision')
        if not isinstance(expected,str) or not re.fullmatch(r'[0-9a-fA-F]{64}',expected) or not self.snapshot_count:
            return 'Refresh the inventory before transferring this item.'
        current=next((item for item in source.get(self.kind,[]) if str(item.get('slot'))==self.slot),None)
        if not current or current.get('revision')!=expected or current.get('count')!=self.snapshot_count:
            return 'The item changed. Close this window and select it again.'
        if self.recipient.count()<2:return 'No other players are online.'
        target=self.recipient.currentData()
        if not target:return 'Choose a player.'
        if target==source.get('uuid') or not any(p.get('uuid')==target and p.get('online') for p in self.owner.people):
            return 'Choose an online player.'
        if _pending(self.owner,'transfer_item',self._payload()):return 'A transfer for this item is still waiting for the server.'
        return ''

    def _apply_availability(self):
        reason=self._availability_reason();self.reason.setText(reason);self.reason.setVisible(bool(reason))
        self.transfer.setEnabled(not reason)
        state=getattr(self.owner,'state',{})
        ready=bool(state.get('fresh') and state.get('features',{}).get('inventoryTransfer') and not self._submitted)
        for widget in (self.recipient,self.amount,self.announce):widget.setEnabled(ready)
        self.message.setEnabled(ready)

    def refresh_availability(self):
        current=self.recipient.currentData()
        others={p.get('uuid'):p for p in self.owner.people
                if p.get('online') and p.get('uuid') and p.get('uuid')!=self.source.get('uuid')}
        desired=[('Choose a player…',None)]+[(str(p.get('name','Player')),uid)
            for uid,p in sorted(others.items(),key=lambda entry:str(entry[1].get('name','')).casefold())]
        existing=[(self.recipient.itemText(i),self.recipient.itemData(i)) for i in range(self.recipient.count())]
        if existing!=desired:
            self.recipient.blockSignals(True);self.recipient.clear()
            for name,uid in desired:self.recipient.addItem(name,uid)
            self.recipient.setCurrentIndex(max(0,self.recipient.findData(current)))
            self.recipient.blockSignals(False);self._default_message()
        self._apply_availability()

    def submit(self):
        self.refresh_availability()
        if self._availability_reason():return
        if self.announce.isChecked() and not self.message.text().strip():
            self.reason.setText('Enter a chat message or turn the announcement off.');self.reason.show();return
        self.transfer.setEnabled(False)
        try:request=self.owner.send_action('transfer_item',self._payload(),self.source)
        except Exception as exc:
            self.reason.setText(str(exc));self.reason.show();self.transfer.setEnabled(True);return
        if request:
            self._submitted=True;self.accept()
        else:
            self.reason.setText('The transfer was not queued. Check the server connection.');self.reason.show();self.transfer.setEnabled(True)


class PlayerToolsMixin:
    def open_item_tools(self,index):
        if type(index) is not int or not 0<=index<len(SLOTS):return
        source=self.selected_player();slot=SLOTS[index];item=self.current_items.get(slot)
        if not source or not item:return
        existing=getattr(self,'_item_dialog',None)
        if existing is not None and existing.isVisible():existing.raise_();existing.activateWindow();return
        dialog=ItemTransferDialog(self,source,'ender' if self.inventory_kind.currentIndex() else 'inventory',slot,item)
        self._item_dialog=dialog
        try:dialog.exec()
        finally:self._item_dialog=None;dialog.deleteLater()

    def update_player_tools(self,player,active):
        state=getattr(self,'state',{})
        supported=bool(state.get('fresh') and state.get('features',{}).get('freezePlayer'))
        frozen=bool(player and player.get('frozen'))
        self.freeze_action.setText('Unfreeze player' if frozen else 'Freeze player')
        payload={'player':player.get('uuid'),'frozen':not frozen} if player else {}
        enabled=bool(player and active and player.get('online') and supported and not _pending(self,'set_frozen',payload))
        self.freeze_action.setEnabled(enabled)
        self.freeze_action.setToolTip('Allow this player to move again' if frozen else 'Keep this player at their current location')
        self.freeze_badge.setVisible(frozen)
        if hasattr(self,'inv_caption'):
            kind='Ender Chest' if self.inventory_kind.currentIndex() else 'Hotbar 0–8'
            transfer=bool(state.get('fresh') and state.get('features',{}).get('inventoryTransfer'))
            self.inv_caption.setText(kind+' · click an item to inspect'+(' or transfer' if transfer else ''))
        dialog=getattr(self,'_item_dialog',None)
        if dialog is not None and dialog.isVisible():dialog.refresh_availability()

    def toggle_player_freeze(self,*_):
        player=self.selected_player();state=getattr(self,'state',{})
        if not (player and player.get('online') and state.get('fresh') and state.get('features',{}).get('freezePlayer')):
            return self.notice('Start a server with player-freeze support and select an online player.',True)
        payload={'player':player['uuid'],'frozen':not bool(player.get('frozen'))}
        if _pending(self,'set_frozen',payload):return
        self.send_action('set_frozen',payload,player)
