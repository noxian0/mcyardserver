"""Validation for structured, acknowledged player-management requests."""
import re
import uuid


FEATURES={'transfer_item':'inventoryTransfer','set_frozen':'freezePlayer'}


def _player(value):
    if not isinstance(value,str):raise ValueError('Choose a valid player.')
    try:parsed=uuid.UUID(value)
    except (ValueError,AttributeError):raise ValueError('Choose a valid player.') from None
    if str(parsed)!=value.lower():raise ValueError('Choose a valid player.')
    return str(parsed)


def validate_action(action,payload):
    if action not in FEATURES or not isinstance(payload,dict):raise ValueError('Unsupported player action.')
    if action=='set_frozen':
        if set(payload)!={'player','frozen'} or type(payload['frozen']) is not bool:raise ValueError('Choose Freeze or Unfreeze.')
        return {'player':_player(payload['player']),'frozen':payload['frozen']}
    fields={'source','target','kind','slot','count','expected','message'}
    if set(payload)-fields or fields-{'message'}-set(payload):raise ValueError('Incomplete item transfer.')
    source,target=_player(payload['source']),_player(payload['target'])
    if source==target:raise ValueError('Choose a different recipient.')
    kind=payload['kind'];slot=payload['slot']
    slots={str(index) for index in range(27 if kind=='ender' else 36)}
    if kind=='inventory':slots.update(('head','chest','legs','feet','offhand'))
    if kind not in ('inventory','ender') or not isinstance(slot,str) or slot not in slots:raise ValueError('Choose a valid inventory slot.')
    count=payload['count']
    if type(count) is not int or not 1<=count<=999:raise ValueError('Choose an item count from 1 to 999.')
    expected=payload['expected']
    if not isinstance(expected,str) or not re.fullmatch('[a-fA-F0-9]{64}',expected):raise ValueError('Refresh the player inventory before transferring this item.')
    message=payload.get('message','')
    if not isinstance(message,str) or len(message)>200 or any(ord(char)<32 or ord(char)==127 for char in message):
        raise ValueError('Use a chat message of up to 200 characters on one line.')
    return {'source':source,'target':target,'kind':kind,'slot':slot,'count':count,'expected':expected.lower(),'message':message}


def action_subject(action,payload):
    return (action,payload['source'],payload['kind'],payload['slot']) if action=='transfer_item' else (action,payload['player'])


def action_description(action,payload):
    if action=='transfer_item':return f'Transfer {payload["count"]} item(s)'
    return 'Freeze player' if payload['frozen'] else 'Unfreeze player'
