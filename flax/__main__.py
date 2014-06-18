from collections import deque
import sys

import urwid

from flax.world import World


PALETTE = [
    # (name, other)
    # (name, fg, bg, mono, fg_high, bg_high)

    # UI
    ('message-old', 'dark gray', 'default', None, '#666', 'default'),
    ('message-fresh', 'white', 'default', None, '#fff', 'default'),
    ('inventory-default', 'default', 'default', None, 'default', 'default'),
    ('inventory-selected', 'default', 'dark blue', None, 'default', '#068'),

    # Architecture
    ('floor', 'black', 'default', None, '#666', 'default'),
    ('grass', 'dark green', 'default', None, '#060', 'default'),
    ('dirt', 'brown', 'default', None, '#960', 'default'),

    # Creatures
    ('player', 'yellow', 'default', None, '#ff6', 'default'),
    ('salamango', 'brown', 'default', None, '#fa0', 'default'),

    # Items
    ('potion', 'light magenta', 'default', None, '#f6f', 'default'),

    # Debug
    ('stdout', 'light gray', 'default', None, '#aaa', 'default'),
    ('stderr', 'light red', 'default', None, '#d66', 'default'),
]

class MapWidget(urwid.BoxWidget):
    def __init__(self):
        self.map = []


class MainWidget(urwid.WidgetWrap):
    _selectable = True

    def __init__(self):
        main_container = urwid.SolidFill('x')

        main_container = urwid.Filler(urwid.Edit('x'), 'top')

        super().__init__(main_container)

    def keypress(self, size, key):
        if key == 'q':
            raise urwid.ExitMainLoop

        return key


class CellCanvas(urwid.Canvas):
    def __init__(self, map):
        self.map = map

        super().__init__()

    def rows(self):
        return self.map.rect.height

    def cols(self):
        return self.map.rect.width

    def translated_coords(self, dx, dy):
        return None

    def content(self, trim_left=0, trim_top=0, cols=None, rows=None, attr=None):
        for row in self.map.rows:
            ret = []
            current_attr = None
            current_glyphs = []
            for tile in row:
                obj = next(tile.things)
                glyph, attr = obj.type.tmp_rendering
                if current_attr != attr:
                    if current_glyphs:
                        ret.append((current_attr, None, ''.join(current_glyphs).encode('utf8')))
                        current_glyphs = []
                    current_attr = attr
                current_glyphs.append(glyph)
            if current_glyphs:
                ret.append((current_attr, None, ''.join(current_glyphs).encode('utf8')))

            yield ret

    def content_delta(self):
        return self.content()


class CellWidget(urwid.Widget):
    _sizing = {'box'}
    _selectable = True

    def __init__(self, world):
        super().__init__()

        self.world = world
        self.canvas = CellCanvas(world.current_map)

    def render(self, size, focus=False):
        cols, rows = size
        map_canvas = urwid.CompositeCanvas(self.canvas)
        map_canvas.pad_trim_left_right(0, cols - self.canvas.cols())
        map_canvas.pad_trim_top_bottom(0, rows - self.canvas.rows())
        return map_canvas

    def keypress(self, size, key):
        if key == 'q':
            raise urwid.ExitMainLoop

        from flax.event import Walk
        from flax.geometry import Direction
        if key == 'up':
            event = self.world.player_action_from_direction(Direction.up)
        elif key == 'down':
            event = self.world.player_action_from_direction(Direction.down)
        elif key == 'left':
            event = self.world.player_action_from_direction(Direction.left)
        elif key == 'right':
            event = self.world.player_action_from_direction(Direction.right)
        else:
            return key

        if event:
            self.world.push_player_action(event)

        # TODO this should eventually become self.world i think
        # TODO also should probably use the event loop?  right?

        self.world.advance()
        self._invalidate()


class WriteDetectingStream:
    def __init__(self, stream, callback):
        self._stream = stream
        self._pending = None
        self._callback = callback

    def __getattr__(self, attr):
        return getattr(self._stream, attr)

    def write(self, data):
        lines = data.splitlines(True)
        if lines:
            if self._pending:
                lines[0] = self._pending + lines[0]
                self._pending = None
            if not lines[-1].endswith('\n'):
                self._pending = lines.pop()

            for line in lines:
                self._callback(line)

        self._stream.write(data)


class DebugWidget(urwid.ListBox):
    def __init__(self):
        super().__init__(urwid.SimpleListWalker([]))

    def activate(self):
        import sys
        self.orig_stdout = sys.stdout
        self.orig_stderr = sys.stderr

        sys.stdout = WriteDetectingStream(sys.stdout, self.write_stdout)
        sys.stderr = WriteDetectingStream(sys.stderr, self.write_stderr)

    def deactivate(self):
        import sys
        sys.stdout = self.orig_stdout
        sys.stderr = self.orig_stderr

        del self.orig_stdout
        del self.orig_stderr

    def write_stdout(self, line):
        self.body.append(urwid.Text(('stdout', line.rstrip('\n'))))
        self.set_focus(len(self.body) - 1)

    def write_stderr(self, line):
        self.body.append(urwid.Text(('stderr', line.rstrip('\n'))))
        self.set_focus(len(self.body) - 1)

    def render(self, *a, **kw):
        return super().render(*a, **kw)


world = World()
debug_widget = DebugWidget()
main_widget = urwid.Pile([
    CellWidget(world),
    debug_widget,
])
loop = urwid.MainLoop(main_widget, PALETTE)
# TODO upstream detection for these?
loop.screen.set_terminal_properties(
    colors=256,
    bright_is_bold=False,
)
debug_widget.activate()
try:
    loop.run()
except BaseException as e:
    # Need to unhook sys.stderr BEFORE re-raising, or we'll never see the
    # exception
    debug_widget.deactivate()

    # Also for some reason the exception just sort of vanishes unless we flush
    # right here?
    sys.stdout.flush()
    sys.stderr.flush()

    raise
else:
    debug_widget.deactivate()
