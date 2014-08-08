
from itertools import islice
import sys

import urwid

from flax.component import IRender
from flax.geometry import Rectangle
from flax.geometry import Size
from flax.world import World
from .util import DebugWidget
from .util import ToggleableOverlay


PALETTE = [
    # (name, other)
    # (name, fg, bg, mono, fg_high, bg_high)
    # high colors: 0 6 8 a d f, plus g0 .. g100 (24 of them)

    # UI
    ('message-old', 'dark gray', 'default', None, '#666', 'default'),
    ('message-fresh', 'white', 'default', None, '#fff', 'default'),
    ('inventory-default', 'default', 'default', None, 'default', 'default'),
    ('inventory-selected', 'default', 'dark gray', None, 'default', 'g15'),
    ('health-full-fill', 'white', 'dark green', None, '#fff', '#080'),
    ('health-full-empty', 'dark green', 'default', None, '#060', 'default'),

    # Architecture
    ('wall', 'light gray', 'default', None, 'g70', 'g70'),
    ('floor', 'black', 'default', None, 'g20', 'default'),
    ('water', 'light blue', 'dark blue', None, '#06f', '#008'),
    ('stairs', 'white', 'dark gray', None, '#aaa', 'g19'),
    ('grass', 'dark green', 'default', None, '#060', 'default'),
    ('tree', 'dark green', 'default', None, '#080', 'default'),
    ('dirt', 'brown', 'default', None, '#960', 'default'),
    ('decay0', 'white', 'default', None, 'g85', 'default'),
    ('decay1', 'light gray', 'default', None, 'g65', 'default'),
    ('decay2', 'dark gray', 'default', None, 'g45', 'default'),
    ('decay3', 'black', 'default', None, 'g25', 'default'),

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
                render = IRender(obj)
                glyph, attr = render.sprite, render.color
                if current_attr != attr:
                    if current_glyphs:
                        ret.append((current_attr, None, ''.join(current_glyphs).encode('utf8')))
                        current_glyphs = []
                    current_attr = attr
                current_glyphs.append(glyph.value)
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

        # FIXME lol this no longer works! FIXME
        from flax.ui.console import widget
        widget.status_widget.update()
        #widget.status_widget.update()

        self._invalidate()


class MeterWidget(urwid.WidgetWrap):
    def __init__(self, full_attr, empty_attr, current=1, maximum=1):
        self.full_attr = full_attr
        self.empty_attr = empty_attr
        self._current = current
        self._maximum = maximum

        super().__init__(urwid.Text("", wrap='clip'))

    @property
    def current(self):
        return self._current

    @current.setter
    def current(self, value):
        self._current = value
        self._invalidate()

    @property
    def maximum(self):
        return self._maximum

    @maximum.setter
    def maximum(self, value):
        self._maximum = value
        self._invalidate()

    def render(self, size, focus=False):
        cols = size[0]
        # XXX urwid trims trailing whitespace, so this gets cropped if it
        # touches the right edge of the screen  :S
        cols -= 1

        text = "{}/{}".format(self._current, self._maximum)

        fill = round(self.current / self.maximum * cols)
        fill_text = text[:fill].ljust(fill, ' ')
        empty_text = text[fill:].ljust(cols - fill, '░')

        self._w.set_text([
            ('health-full-fill', fill_text),
            ('health-full-empty', empty_text),
        ])
        return super().render(size, focus)


class PlayerStatusWidget(urwid.Pile):
    def __init__(self, player):
        self.player = player

        self.health_meter = MeterWidget('health-cur-full', 'health-max-full')
        health_row = urwid.Columns([
            ('pack', urwid.Text("HP: ")),
            self.health_meter,
        ])
        self.strength_text = urwid.Text("Strength: ???")

        super().__init__([
            ('pack', health_row),
            ('pack', self.strength_text),
            urwid.SolidFill(' '),
        ])

        self.update()

    def update(self):
        from flax.component import ICombatant
        combatant = ICombatant(self.player)
        #self.health_text.set_text("Health: {}".format(ICombatant(self.player).health))
        self.health_meter.current = combatant.current_health
        self.health_meter.maximum = combatant.maximum_health
        self.strength_text.set_text("Strength: {}".format(combatant.strength))
        self._invalidate()


class InventoryItem(urwid.WidgetWrap):
    signals = ['fire', 'return']

    def __init__(self, item):
        self.item = item
        render = IRender(item)
        glyph, attr = render.sprite, render.color
        widget = urwid.Text([
            (attr, glyph.value),
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


class FlaxWidget(urwid.WidgetWrap):
    def __init__(self, world):
        self.world = world

        self.status_widget = PlayerStatusWidget(world.player)
        self.debug_widget = DebugWidget()

        main_widget = urwid.Pile([
            urwid.Columns([
                CellWidget(world),
                (20, self.status_widget),
            ]),
            (10, self.debug_widget),
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
