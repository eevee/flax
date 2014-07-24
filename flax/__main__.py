from itertools import islice
import sys

import urwid

from flax.geometry import Rectangle
from flax.geometry import Size
from flax.world import World


PALETTE = [
    # (name, other)
    # (name, fg, bg, mono, fg_high, bg_high)
    # high colors: 0 6 8 a d f, plus g0 .. g100 (24 of them)

    # UI
    ('message-old', 'dark gray', 'default', None, '#666', 'default'),
    ('message-fresh', 'white', 'default', None, '#fff', 'default'),
    ('inventory-default', 'default', 'default', None, 'default', 'default'),
    ('inventory-selected', 'default', 'dark gray', None, 'default', 'g15'),

    # Architecture
    ('floor', 'black', 'default', None, '#666', 'default'),
    ('stairs', 'white', 'dark gray', None, '#aaa', 'g19'),
    ('grass', 'dark green', 'default', None, '#060', 'default'),
    ('tree', 'dark green', 'default', None, '#080', 'default'),
    ('dirt', 'brown', 'default', None, '#960', 'default'),

    # Creatures
    ('player', 'yellow', 'default', None, '#ff6', 'default'),
    ('salamango', 'brown', 'default', None, '#fa0', 'default'),

    # Items
    ('potion', 'light magenta', 'default', None, '#f6f', 'default'),
    ('wood', 'brown', 'default', None, '#960', 'default'),

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

    # Number of rows/columns that must exist between the player and the edge of
    # the map
    MAP_MARGIN = 4

    def __init__(self, world):
        super().__init__()

        self.world = world

        self.viewport = None

    def _adjust_viewport(self, viewport, width, pos, bounds):
        """Adjust the given `viewport` span so that it's the given `width`,
        contains the point `pos`, and doesn't unnecessarily exceed `bounds`
        (the span of the map).

        Returns a new `Span`.
        """
        # The goal here is to scroll the map /as little as possible/, to reduce
        # the changes we'll have to write to the terminal.  Reduces flicker,
        # helps with lag when played over a network, and lets the player move
        # around without feeling like it's just the map scrolling instead.

        # Make sure the player position is actually visible to start with
        viewport = viewport.shift_into_view(pos)

        # Two steps here.
        # 1. If the size changed, position the new size so the player is still
        # roughly the same relative distance across the screen.
        viewport = viewport.scale(width, pivot=pos)

        # 2. If the player is no longer within the map view (excluding the
        # border of MAP_MARGIN), shift the view towards the player.
        # BUT!  Avoid having needless space on the bottom and right, and avoid
        # having ANY space on the top and left.

        # Shrink the margin so that it's less than half the viewport.  So if
        # MAP_MARGIN is 4, but the viewport is only 6 wide, cut it down to 2.
        margin = min(self.MAP_MARGIN, (width - 1) // 2)

        # Need to move the viewport by the distance from the left margin to the
        # player, if that distance is < 0, and reverse for the right margin
        viewport = viewport.shift_into_view(pos, margin=margin)

        # We never want empty space on the leading side, so start cannot go
        # below map.start (0).  We want to /avoid/ empty space on the trailing
        # side, so end cannot go above map.end...  unless the map is smaller
        # than the viewport, in which case it can go until map.start + width.
        move = max(0, bounds.start - viewport.start)
        move = min(move, max(bounds.end, bounds.start + width) - viewport.end)

        return viewport + move

    def render(self, size, focus=False):
        size = Size(*size)
        map = self.world.current_map
        map_rect = map.rect
        player_position = map.find(self.world.player).position

        if not self.viewport:
            # Let's pretend the map itself is the viewport, and the below logic
            # can adjust it as necessary.
            self.viewport = self.world.current_map.rect

        horizontal = self._adjust_viewport(
            self.viewport.horizontal_span,
            size.width,
            player_position.x,
            map.rect.horizontal_span,
        )
        vertical = self._adjust_viewport(
            self.viewport.vertical_span,
            size.height,
            player_position.y,
            map.rect.vertical_span,
        )

        self.viewport = Rectangle.from_spans(
            horizontal=horizontal, vertical=vertical)

        # viewport is from the pov of the map; negate it to get how much space
        # is added or removed around the map
        pad_left = - self.viewport.left
        pad_top = - self.viewport.top
        pad_right  = (size.width - pad_left) - map_rect.width
        pad_bottom = (size.height - pad_top) - map_rect.height

        # TODO it's unclear when you're near the edge of the map, which i hate.
        # should either show a clear border past the map edge, or show some
        # kinda fade or whatever along a cut-off edge
        map_canvas = urwid.CompositeCanvas(CellCanvas(map))
        map_canvas.pad_trim_left_right(pad_left, pad_right)
        map_canvas.pad_trim_top_bottom(pad_top, pad_bottom)
        return map_canvas

    def keypress(self, size, key):
        # TODO why is this not on the top-level widget whoops?
        if key == 'q':
            raise urwid.ExitMainLoop

        from flax.event import Ascend
        from flax.event import Descend
        from flax.event import PickUp
        from flax.event import Equip
        from flax.event import Unequip
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
        elif key == '>':
            event = Descend(self.world.player)
        elif key == '<':
            event = Ascend(self.world.player)
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
        elif key == 'r':
            # TODO menu prompt plz; identifying items is gonna be pretty
            # important later
            from flax.relation import Wearing
            rels = self.world.player.relates_to[Wearing]
            if rels:
                rel = next(iter(rels))
                event = Unequip(self.world.player, rel.to_entity)
            else:
                pass
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
            ('pack', self.health_text),
            ('pack', self.strength_text),
            urwid.SolidFill(' '),
        ])

        self.update()

    def update(self):
        from flax.component import ICombatant
        self.health_text.set_text("Health: {}".format(ICombatant(self.player).health))
        self.strength_text.set_text("Strength: {}".format(ICombatant(self.player).strength))
        self._invalidate()


class InventoryItem(urwid.WidgetWrap):
    signals = ['fire', 'return']

    def __init__(self, item):
        self.item = item
        glyph, attr = item.type.tmp_rendering
        widget = urwid.Text([
            (attr, glyph),
            ' ',
            item.type.name,
        ])
        widget = urwid.AttrMap(widget, 'inventory-default', 'inventory-selected')
        super().__init__(widget)

    # _selectable doesn't work on WidgetWrap
    def selectable(self):
        return True

    def keypress(self, size, key):
        if key == 'e':
            from flax.event import Equip
            self._emit('fire', Equip, self.item)
            return
        return key


class InventoryMenu(urwid.WidgetWrap):
    signals = ['close']

    def __init__(self, player):
        walker = urwid.SimpleListWalker([])
        self.listbox = urwid.ListBox(walker)

        from flax.component import IContainer
        for item in IContainer(player).inventory:
            item_w = InventoryItem(item)

            urwid.connect_signal(item_w, 'fire', lambda *a: self._emit('close', *a))

            self.listbox.body.append(item_w)

        super().__init__(urwid.LineBox(self.listbox))

    def keypress(self, size, key):
        if key == 'esc':
            self._emit('close')
        elif key == 'q':
            self._emit('close')

        return self._w.keypress(size, key)


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
            def close(widget, *args):
                print("well at least we got some args", *args)
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
