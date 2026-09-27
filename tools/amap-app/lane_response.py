"""Bounded, offline LNDS transport inspection; payload geometry stays opaque.

Pinned libamapr: 1637eec -> descriptor 1b9c3a0 / child 4e43e8;
1675544 -> 1675ee0 -> descriptor 1b9c970 / child 4e4538.
Native byte-array structs have a length prefix in MEMORY, not on the wire.
No successful live lane response has been verified with this decoder yet.
"""
from route_v51 import varint

LIMIT = 16 * 1024 * 1024


def _message(raw, schema, budget):
    if not isinstance(raw, bytes) or len(raw) > LIMIT:
        raise ValueError('invalid lane message size')
    pos, result = 0, {}
    while pos < len(raw):
        budget[0] -= 1
        if budget[0] < 0:
            raise ValueError('lane field limit')
        tag, pos = varint(raw, pos)
        number, wire = tag >> 3, tag & 7
        if not 0 < number < 1 << 29 or wire not in (0, 1, 2, 5):
            raise ValueError('invalid lane tag')
        if wire == 0:
            value, pos = varint(raw, pos)
        else:
            size = 8 if wire == 1 else 4
            if wire == 2:
                size, pos = varint(raw, pos)
            if size > len(raw) - pos:
                raise ValueError('truncated lane field')
            value, pos = raw[pos:pos+size], pos+size
        if number not in schema:
            continue
        kind, repeated = schema[number]
        if wire != (0 if kind in ('u32','u64') else 2):
            raise ValueError('wrong lane wire type')
        if kind in ('u32','u64') and value >= 1 << (32 if kind=='u32' else 64):
            raise ValueError('lane integer overflow')
        if kind == 'text':
            if len(value) > 4096:
                raise ValueError('lane text limit')
            value = value.decode('utf-8')
        if not repeated and number in result:
            raise ValueError('duplicate lane field')
        result.setdefault(number, []).append(value)
    return result


def decode_lane_response(raw):
    budget=[10000]
    root=_message(raw,{1:('u32',False),2:('text',False),3:('text',False),
                       4:('u64',False),5:('bytes',True)},budget)
    get=lambda m,k: m.get(k,[None])[0]
    status=get(root,1)
    if status is None:
        raise ValueError('missing lane response status')
    blocks=[]
    if len(root.get(5,[]))>64:
        raise ValueError('lane block limit')
    for block in root.get(5,[]):
        entry=_message(block,{1:('text',False),2:('bytes',False)},budget)
        records=[]
        payload=get(entry,2)
        if status==200 and payload:
            inner=_message(payload,{1:('bytes',True)},budget)
            if len(inner.get(1,[]))>4096:
                raise ValueError('lane tile limit')
            for record in inner.get(1,[]):
                tile=_message(record,{1:('u32',False),2:('u32',False),3:('bytes',False),
                                      4:('u32',False),6:('u32',False)},budget)
                records.append({'tileId':get(tile,1),'state':get(tile,2),
                                'payload':get(tile,3),'version':get(tile,4),'field6':get(tile,6)})
        blocks.append({'name':get(entry,1),'records':records})
    return {'status':status,'field2':get(root,2),'field3':get(root,3),
            'field4':get(root,4),'blocks':blocks,'verifiedLaneGeometry':False}
