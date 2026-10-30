"""Read the Overworld's actual clock without simulating Minecraft time.

Live values come from the local management bridge. Saved values are a static
fallback for stopped servers and servers without the bridge. No network or
server commands are used, and unchanged saves are never decoded again.
"""
from pathlib import Path
import gzip
import io
import re
import stat
import struct
import time
import zlib


MAX_COMPRESSED = 2 * 1024 * 1024
MAX_DECODED = 16 * 1024 * 1024
MAX_NODES = 100_000
MAX_DEPTH = 64


class _NBT:
    """A bounded NBT reader; array payloads are skipped, not materialized."""
    def __init__(self, data):
        self.data = data
        self.position = 0
        self.nodes = 0

    def take(self, count):
        end = self.position + count
        if count < 0 or end > len(self.data):
            raise ValueError('Truncated NBT payload')
        result = self.data[self.position:end]
        self.position = end
        return result

    def number(self, kind):
        return struct.unpack('>' + kind, self.take(struct.calcsize('>' + kind)))[0]

    def string(self):
        return self.take(self.number('H')).decode('utf-8')

    def tag(self, kind, depth=0):
        self.nodes += 1
        if depth > MAX_DEPTH or self.nodes > MAX_NODES:
            raise ValueError('NBT structure exceeds its limit')
        if kind in (1, 2, 3, 4, 5, 6):
            return self.number({1: 'b', 2: 'h', 3: 'i', 4: 'q', 5: 'f', 6: 'd'}[kind])
        if kind == 8:
            return self.string()
        if kind in (7, 11, 12):
            count = self.number('i')
            width = {7: 1, 11: 4, 12: 8}[kind]
            if count < 0 or count > MAX_DECODED // width:
                raise ValueError('NBT array exceeds its limit')
            self.take(count * width)
            return None
        if kind == 9:
            item_kind, count = self.number('B'), self.number('i')
            if count < 0 or count > MAX_NODES or (count and not 1 <= item_kind <= 12):
                raise ValueError('Invalid NBT list')
            return [self.tag(item_kind, depth + 1) for _ in range(count)]
        if kind == 10:
            result = {}
            while True:
                child_kind = self.number('B')
                if child_kind == 0:
                    return result
                name = self.string()
                if name in result:
                    raise ValueError('Duplicate NBT name')
                result[name] = self.tag(child_kind, depth + 1)
        raise ValueError('Unsupported NBT tag')


def _read_nbt(path):
    """Read one small save file, bounding both compressed and decoded bytes."""
    with Path(path).open('rb') as stream:
        raw = stream.read(MAX_COMPRESSED + 1)
    if len(raw) > MAX_COMPRESSED:
        raise ValueError('Saved clock file is too large')
    if raw.startswith(b'\x1f\x8b'):
        with gzip.GzipFile(fileobj=io.BytesIO(raw)) as stream:
            raw = stream.read(MAX_DECODED + 1)
    if len(raw) > MAX_DECODED:
        raise ValueError('Saved clock expands beyond its limit')
    parser = _NBT(raw)
    if parser.number('B') != 10:
        raise ValueError('Expected an NBT compound')
    parser.string()
    result = parser.tag(10)
    if parser.position != len(raw):
        raise ValueError('Unexpected bytes after NBT compound')
    return result


def _ticks(value):
    # A Boolean or a floating-point clock would hide malformed bridge data.
    if type(value) is not int or not -(2 ** 63) <= value < 2 ** 63:
        return None
    return value % 24_000


def _flag(value):
    return value is True or (type(value) is int and value == 1)


def _frame(day_time=None, raining=False, thundering=False, live=False):
    return {'day_time': day_time, 'raining': raining, 'thundering': thundering, 'live': live}


class WorldClock:
    """Refresh from server status or cached saves; never advance time locally.

    Call ``update`` with the manager's status on its existing refresh interval.
    The returned dict is suitable for ``PanoramaHeader.set_world_state(**data)``.
    A stale bridge keeps its last known frame while the server is running. Once
    stopped, the latest saved clock takes precedence. ``live`` is true only when
    the current bridge snapshot is fresh and contains a valid world clock.
    """
    def __init__(self, server_root):
        self.root = Path(server_root).resolve()
        self.world = self.root / 'world'
        self._cache = {}
        self._last = _frame()

    def _signature(self, path):
        try:
            # Reads remain inside this server even if a save path is replaced
            # with a link or junction between refreshes.
            current = path
            while current != self.root:
                if current.is_symlink() or (hasattr(current, 'is_junction') and current.is_junction()):
                    return None
                current = current.parent
            if not path.resolve().is_relative_to(self.root):
                return None
            info = path.stat()
            if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_COMPRESSED:
                return None
            return (info.st_mtime_ns, info.st_size, info.st_ino)
        except (OSError, ValueError, RuntimeError):
            return None

    def _saved_file(self, relative):
        path = self.world / relative
        signature = self._signature(path)
        previous = self._cache.get(relative)
        if previous is not None and previous[0] == signature:
            return previous[1]
        result = {}
        if signature is not None:
            try:
                parsed = _read_nbt(path)
                # A concurrent save can replace the file after the initial
                # stat. Retry next refresh rather than cache a torn snapshot.
                if self._signature(path) == signature:
                    result = parsed
                else:
                    return {}
            except (OSError, ValueError, EOFError, struct.error, zlib.error, RecursionError):
                pass
        self._cache[relative] = (signature, result)
        return result

    def _saved(self):
        clocks = self._saved_file('data/minecraft/world_clocks.dat').get('data', {})
        overworld = clocks.get('minecraft:overworld', {}) if isinstance(clocks, dict) else {}
        day_time = _ticks(overworld.get('total_ticks')) if isinstance(overworld, dict) else None
        if day_time is not None:
            weather = self._saved_file('data/minecraft/weather.dat').get('data', {})
            if not isinstance(weather, dict):
                weather = {}
            return _frame(day_time, _flag(weather.get('raining')), _flag(weather.get('thundering')))
        level = self._saved_file('level.dat').get('Data', {})
        if not isinstance(level, dict):
            return None
        # ``Time`` measures elapsed game ticks, not the day/night clock. Modern
        # releases keep that clock in world_clocks.dat instead of DayTime.
        day_time = _ticks(level.get('DayTime'))
        if day_time is None:
            return None
        return _frame(day_time, _flag(level.get('raining')), _flag(level.get('thundering')))

    def update(self, state, running=False):
        state = state if isinstance(state, dict) else {}
        world = state.get('world')
        if state.get('fresh') is True and isinstance(world, dict):
            day_time = _ticks(world.get('dayTime'))
            if day_time is not None:
                self._last = _frame(day_time, _flag(world.get('raining')), _flag(world.get('thundering')), True)
                return dict(self._last)
        # No wall-clock prediction: time commands, sleeping, tick freeze and
        # doDaylightCycle=false are represented solely by real snapshots.
        if not running or self._last['day_time'] is None:
            saved = self._saved()
            if saved is not None:
                self._last = saved
        self._last = {**self._last, 'live': False}
        return dict(self._last)


class ConsoleWorldClock:
    """Bounded read-only clock queries for an ordinary owned server process.

    Send the command returned by ``next_command`` to Java's stdin only after
    the server is ready. Feed its raw console output to ``feed``. Replies are
    accepted only during the short pending request and from the standard server
    thread INFO logger, never from a player's chat line. This adapter has no
    process, timer, file, or network I/O of its own.
    """
    QUERY_INTERVAL = 6.0
    REPLY_TIMEOUT = 3.0
    STALE_AFTER = 12.0
    MAX_LINE = 4096
    _COMMANDS = {'modern': 'time query time', 'legacy': 'time query daytime'}
    _PREFIX = re.compile(
        r'^\[[0-9]{2}:[0-9]{2}:[0-9]{2}\] \[Server thread/INFO\]'
        r'(?: \[minecraft/MinecraftServer\])?: (?:System chat: )?(.*)$')
    _REPLIES = {
        'modern': re.compile(r'^Clock minecraft:overworld is at (-?[0-9]{1,19}) tick\(s\)$'),
        'legacy': re.compile(r'^The time is (-?[0-9]{1,19})$'),
    }
    _COLOR = re.compile(r'\x1b\[[0-9;]*m')

    def __init__(self):
        self._style = None
        self._pending = None
        self._last_command = None
        self._last_reply = None
        self._day_time = None
        self._fallback_used = False
        self._disabled = False
        self._buffer = ''
        self._discarding = False

    @staticmethod
    def _now(now):
        return time.monotonic() if now is None else now

    def _expire(self, now):
        if self._pending is not None and now - self._pending[1] >= self.REPLY_TIMEOUT:
            self._pending = None

    def next_command(self, mc_version, now=None):
        now = self._now(now)
        self._expire(now)
        if self._disabled or self._pending is not None:
            return None
        if self._last_command is not None and now - self._last_command < self.QUERY_INTERVAL:
            return None
        if self._style is None:
            match = re.match(r'^([0-9]+)(?:\.|$)', str(mc_version))
            self._style = 'modern' if match and int(match[1]) >= 26 else 'legacy'
        # A line already in progress predates this request. Discard its tail so
        # an old partial message cannot become a reply by crossing the request.
        if self._buffer:
            self._buffer = ''
            self._discarding = True
        self._pending = (self._style, now)
        self._last_command = now
        return self._COMMANDS[self._style]

    def _syntax_failure(self):
        self._pending = None
        if self._fallback_used:
            self._disabled = True
        else:
            self._fallback_used = True
            self._style = 'legacy' if self._style == 'modern' else 'modern'

    def _line(self, raw, now):
        if self._pending is None:
            return
        line = self._COLOR.sub('', raw).strip('\r ')
        prefix = self._PREFIX.fullmatch(line)
        if not prefix:
            return
        message = prefix[1]
        match = self._REPLIES[self._pending[0]].fullmatch(message)
        if match:
            day_time = _ticks(int(match[1]))
            if day_time is not None:
                self._day_time = day_time
                self._last_reply = now
                self._pending = None
            return
        # Only vanilla command parser diagnostics can select the one fallback.
        # Player chat carries a name/chat prefix and does not match these forms.
        if (message == "Can't find element 'minecraft:daytime' of type 'minecraft:timeline'"
                or message == 'Unknown or incomplete command, see below for error'
                or message == 'Incorrect argument for command'
                or message.startswith('Incorrect argument for command at position ')):
            self._syntax_failure()

    def feed(self, text, now=None):
        now = self._now(now)
        self._expire(now)
        if not isinstance(text, str):
            return
        parts = text.split('\n')
        for index, part in enumerate(parts):
            ended = index < len(parts) - 1
            if not self._discarding:
                if len(self._buffer) + len(part) > self.MAX_LINE:
                    self._buffer = ''
                    self._discarding = True
                else:
                    self._buffer += part
            if ended:
                if not self._discarding:
                    self._line(self._buffer, now)
                self._buffer = ''
                self._discarding = False

    def world(self, now=None):
        now = self._now(now)
        if self._last_reply is None or not 0 <= now - self._last_reply <= self.STALE_AFTER:
            return None
        return {'dayTime': self._day_time, 'raining': False, 'thundering': False}
