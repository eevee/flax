from itertools import islice
import logging

import urwid

from flax.component import IRender
from flax.geometry import Rectangle
from flax.geometry import Size
from .util import LogWidget
from .util import ToggleableOverlay


log = logging.getLogger(__name__)


PALETTE = [
    # (name, other)
    # (name, fg, bg, mono, fg_high, bg_high)
    # high colors: 0 6 8 a d f, plus g0 .. g100 (24 of them)

    # UI
    ('ui-dividers', 'dark gray', 'default', None, 'g30', 'default'),
    ('message-old', 'dark gray', 'default', None, '#666', 'default'),
    ('message-fresh', 'white', 'default', None, '#fff', 'default'),
    ('inventory-default', 'default', 'default', None, 'default', 'default'),
    ('inventory-selected', 'default', 'dark gray', None, 'default', 'g15'),
    ('health-full-fill', 'white', 'dark green', None, '#fff', '#080'),
    ('health-full-empty', 'dark green', 'default', None, '#060', 'default'),

    # Architecture
    ('wall', 'light gray', 'default', None, 'g70', 'g70'),
    ('rock', 'dark gray', 'default', None, '#860', 'default'),
    ('floor', 'black', 'default', None, 'g20', 'default'),
    ('water', 'light blue', 'dark blue', None, '#06f', '#008'),
    ('bridge', 'dark blue', 'dark gray', None, 'g50', 'g30'),
    ('stairs', 'white', 'dark gray', None, '#aaa', 'g19'),
    ('grass', 'dark green', 'default', None, '#060', 'default'),
    ('tree', 'dark green', 'default', None, '#080', 'default'),
    ('dirt', 'brown', 'default', None, '#660', 'default'),
    ('decay0', 'white', 'default', None, 'g85', 'default'),
    ('decay1', 'light gray', 'default', None, 'g65', 'default'),
    ('decay2', 'dark gray', 'default', None, 'g45', 'default'),
    ('decay3', 'black', 'default', None, 'g25', 'default'),

    # Special
    ('gate', 'light magenta', 'default', None, '#a0f', 'default'),

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

    # Proportion of the map that must be visible in all directions from the
    # player.  Should probably be smaller than 0.5.
    MAP_MARGIN = 0.2

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
        # If the entire map fits within the viewport, just show the whole
        # thing, centered within the available space.
        if len(bounds) <= width:
            return bounds.scale(width)

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
        # Need to move the viewport by the distance from the left margin to the
        # player, if that distance is < 0, and reverse for the right margin
        margin = int(self.MAP_MARGIN * width + 0.99)
        viewport = viewport.shift_into_view(pos, margin=margin)

        # If there's any empty space left, shift the map to fill it.  (This can
        # never produce space on the other side, because we already checked
        # for a map smaller than the viewport above.)
        leading = viewport.end - bounds.end
        trailing = bounds.start - viewport.start
        if leading > 0:
            move = - leading
        elif trailing > 0:
            move = trailing
        else:
            move = 0

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
        pad_right = (size.width - pad_left) - map_rect.width
        pad_bottom = (size.height - pad_top) - map_rect.height

        # TODO it's unclear when you're near the edge of the map, which i hate.
        # should either show a clear border past the map edge, or show some
        # kinda fade or whatever along a cut-off edge
        map_canvas = urwid.CompositeCanvas(CellCanvas(map))
        map_canvas.pad_trim_left_right(pad_left, pad_right)
        map_canvas.pad_trim_top_bottom(pad_top, pad_bottom)
        return map_canvas

    def keypress(self, size, key):
        return key


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
    _selectable = False

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


def entity_to_text_widget(entity):
    render = IRender(entity)
    glyph, attr = render.sprite, render.color
    return urwid.Text([
        (attr, glyph.value),
        ' ',
        entity.type.name,
    ])


class TileContentsWidget(urwid.Pile):
    # TODO if there's space pressure, this should be the first thing to go
    _selectable = False

    def __init__(self):
        super().__init__([urwid.SolidFill(' ')])

    def update_from_tile(self, tile):
        widgets = []
        widgets.append((urwid.SolidFill(' '), self.options('weight', 1)))

        for entity in tile.entities:
            widget = entity_to_text_widget(entity)
            # TODO i have to use "pack" here because Text is a flow widget
            # only, but i actually want to force it to never wrap
            widgets.append((widget, self.options('pack')))

        self.contents = widgets


class InventoryItem(urwid.WidgetWrap):
    signals = ['fire', 'return']

    def __init__(self, item):
        self.item = item
        widget = entity_to_text_widget(item)
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
    signals = ['close-overlay']

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
        key = super().keypress(size, key)
        if not key:
            return

        if key == 'esc':
            self._emit('close-overlay')
        elif key == 'q':
            self._emit('close-overlay')

        # Don't let any keypresses bubble back up to the top widget, which
        # handles all the usual game controls!
        return


class WizardPrompt(urwid.WidgetWrap):
    signals = ['close-overlay']

    def __init__(self):
        super().__init__(urwid.Edit("Wizard command: "))

    def keypress(self, size, key):
        key = super().keypress(size, key)
        if not key:
            return

        if key == 'enter':
            self._emit('close-overlay', self._w.edit_text)
        elif key == 'esc':
            self._emit('close-overlay')

        # Don't let any keypresses bubble back up to the top widget, which
        # handles all the usual game controls!
        return


class FlaxWidget(urwid.WidgetWrap):
    def __init__(self, world):
        self.world = world

        self.world_widget = CellWidget(world)
        self.status_widget = PlayerStatusWidget(world.player)
        self.tile_widget = TileContentsWidget()
        self.tile_widget.update_from_tile(
            self.world.current_map.find(self.world.player))
        self.log_widget = LogWidget()

        main_widget = urwid.Columns([
            # Main area
            urwid.Pile([
                self.world_widget,
                (1, urwid.AttrMap(urwid.SolidFill('─'), 'ui-dividers')),
                (10, self.log_widget),
            ]),
            # Copy the layout of the above Pile, so the T piece is in the right
            # place
            (1, urwid.Pile([
                urwid.AttrMap(urwid.SolidFill('│'), 'ui-dividers'),
                (1, urwid.AttrMap(urwid.SolidFill('┤'), 'ui-dividers')),
                (10, urwid.AttrMap(urwid.SolidFill('│'), 'ui-dividers')),
            ])),
            # Right sidebar
            (20, urwid.Pile([
                self.status_widget,
                self.tile_widget,
            ])),
        ])

        self.overlay = ToggleableOverlay(main_widget)

        super().__init__(self.overlay)

    def keypress(self, size, key):
        # Let WidgetWrap pass the keypress to the wrapped overlay first
        key = super().keypress(size, key)
        if not key:
            return

        if key == 'q':
            raise urwid.ExitMainLoop

        if key == 'i':
            inventory = InventoryMenu(self.world.player)
            self.overlay.change_overlay(inventory)
            return

        if key == '^':
            # TODO the obvious disconnect between launching the prompt and
            # getting the value back bothers me a bit here.  maybe command
            # actions should become functions, which can optionally `yield`...
            def wizard(command=None):
                if not command:
                    return

                if command == 'down':
                    import random
                    from flax.component import PortalDownstairs
                    maps = []
                    for mapname, entity in self.world.current_map.portal_index.items():
                        if PortalDownstairs in entity:
                            maps.append(mapname)
                    if not maps:
                        log.info("No down stairs here.")
                        return
                    new_map = random.choice(maps)
                    self.world.change_map(new_map)
                else:
                    log.info("'{}' is not a wizard spell.".format(command))
            self.overlay.change_overlay(WizardPrompt(), onclose=wizard)
            return

        from flax.event import Ascend
        from flax.event import Descend
        from flax.event import PickUp
        from flax.event import Equip
        from flax.event import Unequip
        from flax.geometry import Direction
        event = None
        if key == 'up' or key == '8':
            event = self.world.player_action_from_direction(Direction.up)
        elif key == 'down' or key == '2':
            event = self.world.player_action_from_direction(Direction.down)
        elif key == 'left' or key == '4':
            event = self.world.player_action_from_direction(Direction.left)
        elif key == 'right' or key == '6':
            event = self.world.player_action_from_direction(Direction.right)
        elif key == 'end' or key == '1':
            event = self.world.player_action_from_direction(Direction.down_left)
        elif key == 'page down' or key == '3':
            event = self.world.player_action_from_direction(Direction.down_right)
        elif key == 'home' or key == '7':
            event = self.world.player_action_from_direction(Direction.up_left)
        elif key == 'page up' or key == '9':
            event = self.world.player_action_from_direction(Direction.up_right)
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

        # TODO unclear when the right time to update this is
        self.tile_widget.update_from_tile(
            self.world.current_map.find(self.world.player))

        self.status_widget.update()
        self.world_widget._invalidate()
