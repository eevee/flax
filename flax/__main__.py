from itertools import islice
import sys

import urwid

from flax.geometry import Rectangle
from flax.geometry import Size
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

    # Number of rows/columns that must exist between the player and the edge of
    # the map
    MAP_MARGIN = 4

    def __init__(self, world):
        super().__init__()

        self.world = world
        self.canvas = CellCanvas(world.current_map)

        self.prior_map_view = None

    def _distribute_space(self, start, end, pos, delta):
        """Distribute `delta` space between `start` and `end` points, such that
        `pos` ends up moving more towards the midpoint.

        Return `(delta_start, delta_end)`, the amount of space that should be
        added to the start and end sides.
        """
        assert start <= pos <= end
        # OK here is an ASCII chart.
        # |---------P---|
        # We split the delta into parts proportional to how P divides the
        # available space.  Then the bigger part goes toward the near side,
        # and the smaller part goes toward the far side.  Note that even if the
        # delta is negative, the "bigger" part will actually be the least
        # negative, and thus reduce the near side the least.

        if not delta:
            # That was easy!
            return 0, 0

        start_offset = pos - start
        end_offset = end - pos

        start_fraction = start_offset / (end - start + 1)
        d1 = start_fraction * delta

        # We have floats right now, and want integers.  Always round the
        # smaller fraction up, to keep the parts as close to equal as possible.
        if start_fraction < 0.5:
            d1 += 0.5
        d1 = int(d1)
        d2 = delta - d1

        # OK, got our parts.  First make sure we know which is smaller (put it
        # in d1), then return the smaller one for the smaller of the gaps.
        if d1 > d2:
            d1, d2 = d2, d1

        if start_offset < end_offset:
            return d1, d2
        else:
            return d2, d1

    def render(self, size, focus=False):
        size = Size(*size)
        player_position = self.world.current_map.find(self.world.player).position

        # The goal here is to scroll the map /as little as possible/, to reduce
        # the changes we'll have to write to the terminal.  Reduces flicker,
        # helps with lag when played over a network, and lets the player move
        # around without feeling like it's just the map scrolling instead.
        # TODO i suspect this is ripe for some simplification, ho ho, but
        # moving a rectangle around with multiple subtle rules is awkward.

        if self.prior_map_view:
            map_view = self.prior_map_view
            center = map_view.center()

            # Two steps here.
            # 1. If the size changed, add/remove the extra space proportional
            # to the player's position.
            # Here is an ASCII chart.
            # |---------P---|
            # We split the delta into parts proportional to how P divides the
            # available space (here, 3/4 and 1/4).  Then the bigger part (or
            # least negative) goes towards the smaller side, and the other goes
            # towards the bigger side.  So we bias towards moving the player
            # towards the middle of the screen.
            shift = {}
            dw = size.width - self.prior_map_view.width
            dh = size.height - self.prior_map_view.height

            if dw:
                dw_left, dw_right = self._distribute_space(
                    map_view.left, map_view.right, player_position.x, dw)

                # We want to move the edges out from the center, so the left
                # edge is actually moving the other direction
                shift['left'] = - dw_left
                shift['right'] = dw_right

            if dh:
                dh_top, dh_bottom = self._distribute_space(
                    map_view.top, map_view.bottom, player_position.y, dh)

                # Same as above
                shift['top'] = - dh_top
                shift['bottom'] = dh_bottom


            if shift:
                map_view = map_view.shift(**shift)
            assert map_view.size == size, (
                "expected map_view {!r} to have size {!r} "
                "after shifting edges, but got {!r}".format(
                    self.prior_map_view, size, map_view))

            # 2. If the player is no longer within the map view (excluding the
            # border of MAP_MARGIN), shift the view towards the player.
            center = map_view.center()
            move_x = move_y = 0

            # For extreme cases, shrink the margin so that it's less than half
            # the playing field.  So if MAP_MARGIN is 4, but the screen is only
            # 6 cells wide, cut it down to 2.
            margin_x = min(self.MAP_MARGIN, (size.width - 1) // 2)
            margin_y = min(self.MAP_MARGIN, (size.height - 1) // 2)

            left_offset = player_position.x - map_view.left
            right_offset = map_view.right - player_position.x
            if left_offset < margin_x:
                # Move the viewport further left
                move_x = left_offset - margin_x
            elif right_offset < margin_x:
                move_x = margin_x - right_offset

            top_offset = player_position.y - map_view.top
            bottom_offset = map_view.bottom - player_position.y
            if top_offset < margin_y:
                # Move the viewport further up
                move_y = top_offset - margin_y
            elif bottom_offset < margin_y:
                move_y = margin_y - bottom_offset

            if move_x or move_y:
                map_view = map_view.shift(
                    left=move_x, right=move_x, top=move_y, bottom=move_y)

        else:
            # OK, well, this is the first time we're drawing the map at all.
            # In this case we just center the player.
            map_view = Rectangle.centered_at(size, player_position)

        # Finally, avoid showing void space as much as possible.  If there has
        # to be extra space, prefer putting it towards the bottom and right.
        # TODO this can definitely be simpler wtf
        map_rect = self.world.current_map.rect
        if map_view.right > map_rect.right:
            dx = map_rect.right - map_view.right
            map_view = map_view.shift(left=dx, right=dx)
        if map_view.left < 0:
            dx = - map_view.left
            map_view = map_view.shift(left=dx, right=dx)

        if map_view.bottom > map_rect.bottom:
            dy = map_rect.bottom - map_view.bottom
            map_view = map_view.shift(top=dy, bottom=dy)
        if map_view.top < 0:
            dy = - map_view.top
            map_view = map_view.shift(top=dy, bottom=dy)

        self.prior_map_view = map_view

        # map_view is from the pov of the map; negate it to get the pov of the
        # canvas
        canvas_left = - map_view.left
        canvas_top = - map_view.top
        canvas_right  = (size.width - canvas_left) - map_rect.width
        canvas_bottom = (size.height - canvas_top) - map_rect.height

        map_canvas = urwid.CompositeCanvas(self.canvas)
        map_canvas.pad_trim_left_right(canvas_left, canvas_right)
        map_canvas.pad_trim_top_bottom(canvas_top, canvas_bottom)
        return map_canvas

    def keypress(self, size, key):
        # TODO why is this not on the top-level widget whoops?
        if key == 'q':
            raise urwid.ExitMainLoop

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
            from flax.relation import Wears
            for item in IContainer(self.world.player).inventory:
                if item.type is Armor:
                    break
            else:
                return key
            event = Equip(self.world.player, item)
        elif key == 'r':
            # TODO menu prompt plz; identifying items is gonna be pretty
            # important later
            from flax.relation import Wears
            rels = self.world.player.relations[Wears]
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
