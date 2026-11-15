"""Decode Kirka game-room sockets (Colyseus) for the headless spectator (tools/specd.py, WIP).

A room socket frame is: opcode byte + payload.
  10 JOIN_ROOM   : [10, len, "schema", <reflection>]  -- the self-describing schema definition
  13 ROOM_DATA   : [13, type, <msgpack>]              -- room.send messages  (FULLY DECODED here)
  14 ROOM_STATE  : [14, <schema-encoded full state>]  -- the roster lives here (WIP: schema decoder)
  15 ROOM_STATE_PATCH : incremental schema changes
  12 LEAVE_ROOM

The op-13 messages are MessagePack and carry the live telemetry (see captures/ws-spectate/NOTES.md):
  type 28 player positions/rotations (per tick), 29 loadouts/skins, 31/3/67/70 spawn/health/kill events.
The roster (name, short-id, team, kills, deaths, score) is in the schema STATE (op 14/15).

Status: COMPLETE and validated against captures/ws-spectate/session.json. msgpack decodes every op-13 message;
the reflection-driven schema decoder decodes the full op-14 state -> all 13 players with name, short-id, team,
role, skin, health, score, kills/deaths and live position. Use: `types, root = parse_reflection(join_frame)`
then `state = Decoder(types, root).decode(state_frame)`; `roster(state)` gives clean player rows.
"""
import struct


class Reader:
    __slots__ = ('b', 'o')

    def __init__(self, b, o=0):
        self.b = b
        self.o = o

    def eof(self):
        return self.o >= len(self.b)


# ---------------------------------------------------------------- MessagePack (op-13 messages) -- DONE
def msgpack(b, r=None):
    """Decode one MessagePack value. Validated on every op-13 message type in the capture."""
    own = r is None
    if own:
        r = Reader(b)
    c = r.b[r.o]
    r.o += 1
    if c < 0x80:
        return c
    if c >= 0xe0:
        return c - 256
    if c < 0x90:  # fixmap
        return {_mp(r): _mp(r) for _ in range(c & 0xf)}
    if c < 0xa0:  # fixarray
        return [_mp(r) for _ in range(c & 0xf)]
    if c < 0xc0:  # fixstr
        n = c & 0x1f
        s = r.b[r.o:r.o + n].decode('utf-8', 'replace')
        r.o += n
        return s
    if c == 0xc0:
        return None
    if c == 0xc2:
        return False
    if c == 0xc3:
        return True
    if c == 0xca:
        v = struct.unpack('>f', r.b[r.o:r.o + 4])[0]; r.o += 4; return v
    if c == 0xcb:
        v = struct.unpack('>d', r.b[r.o:r.o + 8])[0]; r.o += 8; return v
    if c == 0xcc:
        v = r.b[r.o]; r.o += 1; return v
    if c == 0xcd:
        v = int.from_bytes(r.b[r.o:r.o + 2], 'big'); r.o += 2; return v
    if c == 0xce:
        v = int.from_bytes(r.b[r.o:r.o + 4], 'big'); r.o += 4; return v
    if c == 0xcf:
        v = int.from_bytes(r.b[r.o:r.o + 8], 'big'); r.o += 8; return v
    if c == 0xd0:
        v = r.b[r.o]; r.o += 1; return v - 256 if v >= 128 else v
    if c == 0xd1:
        v = int.from_bytes(r.b[r.o:r.o + 2], 'big'); r.o += 2; return v - 65536 if v >= 32768 else v
    if c == 0xd2:
        v = int.from_bytes(r.b[r.o:r.o + 4], 'big'); r.o += 4; return v - (1 << 32) if v >= (1 << 31) else v
    if c == 0xd9:
        n = r.b[r.o]; r.o += 1; s = r.b[r.o:r.o + n].decode('utf-8', 'replace'); r.o += n; return s
    if c == 0xda:
        n = int.from_bytes(r.b[r.o:r.o + 2], 'big'); r.o += 2; s = r.b[r.o:r.o + n].decode('utf-8', 'replace'); r.o += n; return s
    if c == 0xdc:
        n = int.from_bytes(r.b[r.o:r.o + 2], 'big'); r.o += 2; return [_mp(r) for _ in range(n)]
    if c == 0xde:
        n = int.from_bytes(r.b[r.o:r.o + 2], 'big'); r.o += 2; return {_mp(r): _mp(r) for _ in range(n)}
    if c == 0xdf:
        n = int.from_bytes(r.b[r.o:r.o + 4], 'big'); r.o += 4; return {_mp(r): _mp(r) for _ in range(n)}
    # ext / fixext: [type byte][data]; we skip (return the raw bytes tagged)
    if c in (0xd4, 0xd5, 0xd6, 0xd7, 0xd8):
        size = {0xd4: 1, 0xd5: 2, 0xd6: 4, 0xd7: 8, 0xd8: 16}[c]
        et = r.b[r.o]; r.o += 1
        data = r.b[r.o:r.o + size]; r.o += size
        return {'__ext__': et, 'data': list(data)}
    if c in (0xc7, 0xc8, 0xc9):
        ln = {0xc7: 1, 0xc8: 2, 0xc9: 4}[c]
        size = int.from_bytes(r.b[r.o:r.o + ln], 'big'); r.o += ln
        et = r.b[r.o]; r.o += 1
        data = r.b[r.o:r.o + size]; r.o += size
        return {'__ext__': et, 'data': list(data)}
    if c == 0xc4:  # bin8
        n = r.b[r.o]; r.o += 1; d = r.b[r.o:r.o + n]; r.o += n; return list(d)
    if c == 0xc5:  # bin16
        n = int.from_bytes(r.b[r.o:r.o + 2], 'big'); r.o += 2; d = r.b[r.o:r.o + n]; r.o += n; return list(d)
    raise ValueError(f'msgpack byte {hex(c)} at {r.o - 1}')


def _mp(r):
    return msgpack(None, r)


def decode_message(raw):
    """op-13 ROOM_DATA frame -> (type, payload). payload is MessagePack."""
    assert raw and raw[0] == 13
    mtype = raw[1]
    try:
        return mtype, msgpack(raw[2:])
    except Exception:  # noqa: BLE001
        return mtype, None


# ---------------------------------------------------------------- Colyseus schema (op-14/15 state)
# Faithful port of @colyseus/schema's reflection-driven Decoder. Numbers/strings are LITTLE-ENDIAN here
# (msgpack above is big-endian - different wire formats).
SWITCH_TO_STRUCTURE = 255
TYPE_ID = 213
_SENTINEL = object()


def s_number(r):
    """schema decode.number (little-endian prefixed)."""
    p = r.b[r.o]; r.o += 1
    if p < 0x80:
        return p
    if p >= 0xe0:
        return p - 256
    if p == 0xca:
        v = struct.unpack('<f', r.b[r.o:r.o + 4])[0]; r.o += 4; return v
    if p == 0xcb:
        v = struct.unpack('<d', r.b[r.o:r.o + 8])[0]; r.o += 8; return v
    if p == 0xcc:
        v = r.b[r.o]; r.o += 1; return v
    if p == 0xcd:
        v = int.from_bytes(r.b[r.o:r.o + 2], 'little'); r.o += 2; return v
    if p == 0xce:
        v = int.from_bytes(r.b[r.o:r.o + 4], 'little'); r.o += 4; return v
    if p == 0xcf:
        v = int.from_bytes(r.b[r.o:r.o + 8], 'little'); r.o += 8; return v
    if p == 0xd0:
        v = r.b[r.o]; r.o += 1; return v - 256 if v >= 128 else v
    if p == 0xd1:
        v = int.from_bytes(r.b[r.o:r.o + 2], 'little'); r.o += 2; return v - 65536 if v >= 32768 else v
    if p == 0xd2:
        v = int.from_bytes(r.b[r.o:r.o + 4], 'little'); r.o += 4; return v - (1 << 32) if v >= (1 << 31) else v
    if p == 0xd3:
        v = int.from_bytes(r.b[r.o:r.o + 8], 'little'); r.o += 8; return v - (1 << 64) if v >= (1 << 63) else v
    raise ValueError(f'schema number prefix {hex(p)} at {r.o - 1}')


def s_string(r):
    """schema decode.string: fixstr length (0xA0|len) for <32, else 0xD9/DA/DB prefixes."""
    p = r.b[r.o]; r.o += 1
    if p < 0xc0:
        n = p & 0x1f
    elif p == 0xd9:
        n = r.b[r.o]; r.o += 1
    elif p == 0xda:
        n = int.from_bytes(r.b[r.o:r.o + 2], 'little'); r.o += 2
    elif p == 0xdb:
        n = int.from_bytes(r.b[r.o:r.o + 4], 'little'); r.o += 4
    else:
        raise ValueError(f'schema string prefix {hex(p)} at {r.o - 1}')
    s = r.b[r.o:r.o + n].decode('utf-8', 'replace'); r.o += n
    return s


_FIXED = {
    'int8': (1, True), 'uint8': (1, False), 'int16': (2, True), 'uint16': (2, False),
    'int32': (4, True), 'uint32': (4, False), 'int64': (8, True), 'uint64': (8, False),
}


def s_primitive(kind, r):
    if kind == 'string':
        return s_string(r)
    if kind == 'number':
        return s_number(r)
    if kind == 'boolean':
        v = r.b[r.o]; r.o += 1; return v > 0
    if kind == 'float32':
        v = struct.unpack('<f', r.b[r.o:r.o + 4])[0]; r.o += 4; return v
    if kind == 'float64':
        v = struct.unpack('<d', r.b[r.o:r.o + 8])[0]; r.o += 8; return v
    if kind in _FIXED:
        n, signed = _FIXED[kind]
        v = int.from_bytes(r.b[r.o:r.o + n], 'little', signed=signed); r.o += n; return v
    raise ValueError(f'unknown primitive {kind}')


_PRIMS = set(_FIXED) | {'string', 'number', 'boolean', 'float32', 'float64'}


class Decoder:
    """Reflection-driven Colyseus state decoder. `types` maps typeId -> {'fields': [field,...]};
    each field = {'name', 'kind'('ref'|'array'|'map'|primitive), 'child'(typeId or None), 'prim'(elem primitive or None)}."""

    def __init__(self, types, root_id):
        self.types = types
        self.refs = {0: self._mk(root_id, 'schema')}

    def _mk(self, type_id, kind, child=None, prim=None):
        return {'kind': kind, 'type': type_id, 'child': child, 'prim': prim,
                'val': [] if kind == 'array' else {}, 'keys': {}}

    def decode(self, data):
        r = Reader(data[1:] if data and data[0] in (14, 15) else data)
        cur = 0; ref = self.refs[0]
        while not r.eof():
            if r.b[r.o] == SWITCH_TO_STRUCTURE:
                r.o += 1; cur = s_number(r)
                ref = self.refs.get(cur)
                if ref is None:  # unknown structure -> resync at next known SWITCH
                    ref = self._skip(r)
                    cur = -1
                continue
            if ref['kind'] == 'schema':
                self._schema_op(r, ref)
            elif ref['kind'] == 'array':
                self._array_op(r, ref)
            else:
                self._map_op(r, ref)
        return self.refs[0]['val']

    def _skip(self, r):
        while not r.eof():
            if r.b[r.o] == SWITCH_TO_STRUCTURE:
                save = r.o; r.o += 1; nid = s_number(r)
                if nid in self.refs:
                    r.o = save; return self.refs[0]  # caller re-reads the SWITCH
                r.o = save + 1
            else:
                r.o += 1
        return self.refs[0]

    def _schema_op(self, r, ref):
        b = r.b[r.o]; r.o += 1
        op = (b >> 6) << 6
        index = b % (op or 255)
        fields = self.types[ref['type']]['fields']
        if index >= len(fields):
            raise ValueError(f'definition mismatch: field {index} in type {ref["type"]}')
        f = fields[index]
        v = self._value(r, op, f)
        if v is not _SENTINEL:
            ref['val'][f['name']] = v

    def _value(self, r, op, f):
        if op == 64:  # plain DELETE: no value on wire
            return _SENTINEL
        kind = f['kind']
        if kind in _PRIMS:
            return s_primitive(kind, r)
        if kind == 'ref':
            rid = s_number(r)
            child = f['child']
            if op & 128 and r.o < len(r.b) and r.b[r.o] == TYPE_ID:
                r.o += 1; child = s_number(r)
            if rid not in self.refs:
                self.refs[rid] = self._mk(child, 'schema')
            return self.refs[rid]['val']
        if kind in ('array', 'map'):
            rid = s_number(r)
            if rid not in self.refs:
                self.refs[rid] = self._mk(f['child'], kind, prim=f['prim'])
            return self.refs[rid]['val']
        raise ValueError(f'unknown field kind {kind}')

    def _elem(self, r, op, ref):
        """decode one collection element value."""
        if ref['prim']:
            return s_primitive(ref['prim'], r)
        # element is a schema ref
        rid = s_number(r)
        child = ref['type']
        if op & 128 and r.o < len(r.b) and r.b[r.o] == TYPE_ID:
            r.o += 1; child = s_number(r)
        if rid not in self.refs:
            self.refs[rid] = self._mk(child, 'schema')
        return self.refs[rid]['val']

    def _array_op(self, r, ref):
        op = r.b[r.o]; r.o += 1
        if op == 10:  # CLEAR
            ref['val'].clear(); return
        if op == 15:  # REVERSE
            ref['val'].reverse(); return
        if op == 33:  # DELETE_BY_REFID
            s_number(r); return
        if op == 129:  # ADD_BY_REFID
            rid = s_number(r)
            idx = len(ref['val'])
            if rid not in self.refs:
                self.refs[rid] = self._mk(ref['type'], 'schema')
            while len(ref['val']) <= idx:
                ref['val'].append(None)
            ref['val'][idx] = self.refs[rid]['val']
            return
        index = s_number(r)
        if op == 64:  # plain DELETE: no value on the wire (fixed 2026-11-15; reading one misaligned the patch)
            if index < len(ref['val']):
                ref['val'][index] = None
            return
        v = self._elem(r, op, ref)
        while len(ref['val']) <= index:
            ref['val'].append(None)
        ref['val'][index] = v

    def _map_op(self, r, ref):
        op = r.b[r.o]; r.o += 1
        if op == 10:  # CLEAR
            ref['val'].clear(); ref['keys'].clear(); return
        index = s_number(r)
        if op & 128:
            key = s_string(r); ref['keys'][index] = key
        else:
            key = ref['keys'].get(index)
        if op == 64:  # plain DELETE: no value on the wire (fixed 2026-11-15 - a player leaving broke decoding)
            ref['val'].pop(key, None); ref['keys'].pop(index, None); return
        v = self._elem(r, op, ref)
        ref['val'][key] = v


# ---- the fixed Reflection schema (to decode the self-describing JOIN handshake) ----
def _f(name, kind, child=None, prim=None):
    return {'name': name, 'kind': kind, 'child': child, 'prim': prim}


# type ids chosen arbitrarily (100+) so they don't collide with the game's own ids
_R_REFLECTION, _R_TYPE, _R_FIELD, _R_QUANT = 100, 101, 102, 103
REFLECTION_TYPES = {
    _R_REFLECTION: {'fields': [_f('types', 'array', child=_R_TYPE), _f('rootType', 'number')]},
    # NOTE: this Kirka schema build has ReflectionType = {id, fields} (no extendsId, verified against the capture).
    _R_TYPE: {'fields': [_f('id', 'number'), _f('fields', 'array', child=_R_FIELD)]},
    _R_FIELD: {'fields': [_f('name', 'string'), _f('type', 'string'), _f('referencedType', 'number'),
                          _f('childPrimitive', 'string'), _f('quantized', 'ref', child=_R_QUANT)]},
    _R_QUANT: {'fields': [_f('min', 'float64'), _f('max', 'float64'), _f('bits', 'uint8'), _f('mode', 'uint8')]},
}


# ---- Kirka game-state field map (game 0.44.x) ----
# The players live in state['wMNWWnmw'] (a map, sessionId -> player). Obfuscated keys -> meaning,
# mapped from the decoded capture (names/short-ids/teams are certain; kills/deaths confirmed by value shape).
PLAYERS_KEY = 'wMNWWnmw'
PLAYER_FIELDS = {
    'wwMnWmW': 'name', 'wMNWWm': 'shortId', 'wwMnWm': 'team', 'wwMnWN': 'role',
    'wNWWwMmn': 'weaponSkin', 'WmwNWnMw': 'sessionId',
    'WmwNWnw': 'health', 'wNWWnMwm': 'shield', 'wNWWnMm': 'score',
    'wNWWnMmw': 'kills', 'wnMWWwN': 'deaths',
    'WwMwnWN': 'pos', 'WwMwNmnW': 'rot',
}


def roster(state):
    """Extract a clean player list from a decoded room state (name, shortId, team, kills, deaths, score, ...)."""
    out = []
    for p in (state.get(PLAYERS_KEY) or {}).values():
        if not isinstance(p, dict):
            continue
        row = {name: p.get(key) for key, name in PLAYER_FIELDS.items()}
        row['isBot'] = not p.get('wMNWWm')  # bots have no short-id
        row['isSpectator'] = bool(p.get('wmMNWn'))  # spectators (incl. our own seat) sit in the players map too
        out.append(row)
    return out


def parse_reflection(join_frame):
    """Decode the op-10 JOIN handshake -> (types registry, root_type_id) for decoding state."""
    slen = join_frame[1]
    refl = join_frame[2 + slen:]  # after "schema"
    dec = Decoder(REFLECTION_TYPES, _R_REFLECTION)
    r = dec.decode(refl)
    # build a game types registry the state Decoder can use
    types = {}
    for t in r.get('types', []):
        if not t:
            continue
        fields = []
        for fld in t.get('fields', []):
            if not fld:
                continue
            ft = fld.get('type')
            ref_t = fld.get('referencedType')
            prim = fld.get('childPrimitive') or None
            if ft in ('ref', 'array', 'map'):
                fields.append(_f(fld['name'], ft, child=ref_t, prim=prim))
            elif ':' in (ft or ''):  # compound collection of primitives, e.g. "map:string", "array:uint32"
                coll, el = ft.split(':', 1)
                fields.append(_f(fld['name'], coll, child=ref_t, prim=el))
            else:
                fields.append(_f(fld['name'], ft))
        types[t['id']] = {'fields': fields}
    return types, r.get('rootType')
