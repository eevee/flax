import urwid

from flax.fractor import MapCanvas

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

    # Creatures
    ('player', 'yellow', 'default', None, '#ff6', 'default'),
    ('newt', 'yellow', 'default', None, '#ff6', 'default'),

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
    def __init__(self, map_canvas):
        self.map_canvas = map_canvas

        super().__init__()

    def rows(self):
        return self.map_canvas.height

    def cols(self):
        return self.map_canvas.width

    def translated_coords(self, dx, dy):
        return None

    def content(self, trim_left=0, trim_top=0, cols=None, rows=None, attr=None):
        for row in self.map_canvas.grid:
            ret = []
            current_attr = None
            current_glyphs = []
            for obj in row:
                glyph, attr = obj.tmp_rendering
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

    def __init__(self):
        super().__init__()

        map_canvas = MapCanvas(20, 20)
        map_canvas.draw_room(0, 0, 5, 5)
        self.canvas = CellCanvas(map_canvas)

    def render(self, size, focus=False):
        comp = urwid.CompositeCanvas(urwid.SolidCanvas(' ', *size))
        comp.overlay(urwid.CompositeCanvas(self.canvas), 1, 1)
        return comp

    def keypress(self, size, key):
        if key == 'q':
            raise urwid.ExitMainLoop

        return key


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


debug_widget = DebugWidget()
main_widget = urwid.Pile([
    CellWidget(),
    debug_widget,
])
loop = urwid.MainLoop(main_widget, PALETTE)
# TODO upstream detection for these?
loop.screen.set_terminal_properties(
    colors=256,
    bright_is_bold=False,
)
debug_widget.activate()
loop.run()
debug_widget.deactivate()
