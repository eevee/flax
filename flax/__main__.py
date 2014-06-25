from itertools import islice
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
        for row in islice(self.map.rows, trim_top, trim_top + rows):
            ret = []
            current_attr = None
            current_glyphs = []
            for tile in islice(row, trim_left, trim_left + cols):
                obj = next(tile.entities)
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

        # TODO make this stop at the bottom and right edges too! maybe.
        center = self.world.current_map.find(self.world.player).position
        left = min(0, int(cols / 2) - center.x)
        top  = min(0, int(rows / 2) - center.y)

        right  = (cols - left) - self.canvas.cols()
        bottom = (rows - top) - self.canvas.rows()

        map_canvas = urwid.CompositeCanvas(self.canvas)
        map_canvas.pad_trim_left_right(left, right)
        map_canvas.pad_trim_top_bottom(top, bottom)
        return map_canvas

    def keypress(self, size, key):
        # TODO why is this not on the top-level widget whoops?
        if key == 'q':
            raise urwid.ExitMainLoop

        from flax.event import PickUp
        from flax.event import Equip
        from flax.geometry import Direction
        event = None
        if key == 'up':
            event = self.world.player_action_from_direction(Direction.up)
        elif key == 'down':
            event = self.world.player_action_from_direction(Direction.down)
        elif key == 'left':
            event = self.world.player_action_from_direction(Direction.left)
        elif key == 'right':
            event = self.world.player_action_from_direction(Direction.right)
        elif key == ',':
            tile = self.world.current_map.find(self.world.player)
            # TODO might consolidate this to a single event later if it fucks
            # up the sense of time.  or maybe it should!
            for item in tile.items:
                self.world.push_player_action(PickUp(self.world.player, item))
        elif key == 'e':
            # TODO menu prompt plz; identifying items is gonna be pretty
            # important later
            from flax.component import IContainer
            from flax.entity import Armor
            for item in IContainer(self.world.player).inventory:
                if item.type is Armor:
                    break
            else:
                return key
            event = Equip(self.world.player, item)
        else:
            return key

        if event:
            self.world.push_player_action(event)

        # TODO um, shouldn't really advance the world if the player pressed a
        # bogus key
        # TODO should probably use the event loop?  right?
        self.world.advance()

        # TODO this is terrible
        widget.status_widget.update()

        self._invalidate()


class PlayerStatusWidget(urwid.Pile):
    def __init__(self, player):
        self.player = player

        self.health_text = urwid.Text("Health: ???")
        self.strength_text = urwid.Text("Health: ???")

        super().__init__([
            urwid.Filler(self.health_text),
            urwid.Filler(self.strength_text),
        ])

        self.update()

    def update(self):
        from flax.component import ICombatant
        self.health_text.set_text("Health: {}".format(ICombatant(self.player).health))
        self.strength_text.set_text("Strength: {}".format(ICombatant(self.player).strength))
        self._invalidate()


class InventoryItem(urwid.WidgetWrap):
    def __init__(self, item):
        self.item = item
        glyph, attr = item.type.tmp_rendering
        widget = urwid.Text([
            (attr, glyph),
            ' ',
            ('ui-inventory', item.type.name),
        ])
        super().__init__(widget)


class InventoryMenu(urwid.ListBox):
    signals = ['close']

    def __init__(self, player):
        walker = urwid.SimpleListWalker([])
        super().__init__(walker)

        from flax.component import IContainer
        for item in IContainer(player).inventory:
            self.body.append(InventoryItem(item))

    def keypress(self, size, key):
        if key == 'esc':
            self._emit('close')

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


class ToggleableOverlay(urwid.Overlay):
    """An Overlay where the top widget can be swapped out or hidden entirely.

    If the top widget is removed, focus passes to the bottom widget.
    """
    def __init__(self, bottom_w):
        # TODO uhh what are good defaults??
        super().__init__(None, bottom_w, align='center', width=('relative', 90), valign='middle', height=('relative', 90))

    def selectable(self):
        return self.focus.selectable()

    def keypress(self, size, key):
        if self.top_w:
            return super().keypress(size, key)
        else:
            return self.bottom_w.keypress(size, key)

    @property
    def focus(self):
        if self.top_w:
            return self.top_w
        else:
            return self.bottom_w

    @property
    def focus_position(self):
        if self.top_w:
            return 1
        else:
            return 0

    @focus_position.setter
    def focus_position(self, position):
        if position == 0:
            self.top_w = None
        else:
            super().focus_position = position

    # TODO override `contents` to return a 1-element thing

    def render(self, size, focus=False):
        if self.top_w:
            return super().render(size, focus)
        else:
            return self.bottom_w.render(size, focus)

    ### New APIs

    def change_overlay(self, widget):
        self.top_w = widget
        self._invalidate()


class FlaxWidget(urwid.WidgetWrap):
    def __init__(self, world):
        self.world = world

        self.status_widget = PlayerStatusWidget(world.player)
        self.debug_widget = DebugWidget()

        main_widget = urwid.Pile([
            urwid.Columns([
                CellWidget(world),
                self.status_widget,
                (0, urwid.SolidFill('x')),
            ]),
            self.debug_widget,
        ])

        self.overlay = ToggleableOverlay(main_widget)

        super().__init__(self.overlay)

    def keypress(self, size, key):
        key = super().keypress(size, key)
        if not key:
            return

        # TODO this should go on the main screen, not the top level, so when
        # a menu is open keys don't get here
        if key == 'i':
            inventory = InventoryMenu(self.world.player)
            def close(widget):
                self.overlay.change_overlay(None)
            urwid.connect_signal(inventory, 'close', close)
            self.overlay.change_overlay(inventory)
        else:
            return key


world = World()
widget = FlaxWidget(world)
loop = urwid.MainLoop(widget, PALETTE)
# TODO upstream detection for these?
loop.screen.set_terminal_properties(
    colors=256,
    bright_is_bold=False,
)
widget.debug_widget.activate()
try:
    loop.run()
except BaseException as e:
    # Need to unhook sys.stderr BEFORE re-raising, or we'll never see the
    # exception
    widget.debug_widget.deactivate()

    # Also for some reason the exception just sort of vanishes unless we flush
    # right here?
    sys.stdout.flush()
    sys.stderr.flush()

    raise
else:
    widget.debug_widget.deactivate()
