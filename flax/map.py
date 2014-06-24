from itertools import product
from weakref import WeakKeyDictionary, ref

from flax.geometry import Point
from flax.things.arch import CaveWall, Thing, Layer, Player


class Map:
    def __init__(self, size):
        self.rect = size.to_rect(Point.origin())

        self.thing_positions = WeakKeyDictionary()

        self.tiles = {
            point: Tile(self, point)
            for point in self.rect.iter_points()
        }

    _player = None

    @property
    def player(self):
        assert self._player is not None, "map is missing a player!"
        return self._player

    @player.setter
    def player(self, value):
        assert self._player is None, "trying to set player when we've already got one!"
        self._player = value

    @player.deleter
    def player(self):
        assert self._player is not None, "can't remove nonexistent player!"
        del self._player

    @property
    def rows(self):
        for y in self.rect.range_height():
            yield (self.tiles[Point(x, y)] for x in self.rect.range_width())

    def place(self, thing, position):
        assert thing not in self.thing_positions
        self.thing_positions[thing] = position
        self.tiles[position].attach(thing)

        if thing.isa(Player):
            self.player = thing

    def find(self, thing):
        assert isinstance(thing, Thing)
        pos = self.thing_positions[thing]
        return self.tiles[pos]

    def move(self, thing, position):
        old_position = self.thing_positions[thing]
        old_tile = self.tiles[old_position]
        old_tile.detach(thing)

        self.thing_positions[thing] = position
        new_tile = self.tiles[position]
        new_tile.attach(thing)

    def remove(self, thing):
        position = self.thing_positions.pop(thing)
        self.tiles[position].detach(thing)

        if thing.isa(Player):
            del self.player

    def __contains__(self, position):
        return position in self.rect


class Tile:
    def __init__(self, map, position):
        self._map = ref(map)
        self.position = position
        # TODO would like architecture to default to something (probably
        # CaveWall) so a freshly-created Tile is cromulent, without having to
        # create a new Thing on every Tile just to have it overwritten a moment
        # later
        self.architecture = None
        self.creature = None
        self.items = []

    @property
    def map(self):
        return self._map()

    @property
    def things(self):
        if self.creature:
            yield self.creature

        yield from self.items
        yield self.architecture

    def attach(self, thing):
        """Add the given thing from this tile.  Its position is not affected.
        This method is only intended to be called by the map object.
        """
        if thing.layer is Layer.architecture:
            assert self.architecture is None
            self.architecture = thing
        elif thing.layer is Layer.item:
            self.items.append(thing)
        elif thing.layer is Layer.creature:
            assert self.creature is None
            self.creature = thing
        else:
            raise TypeError(
                "Unknown layer {!r} for thing {!r}"
                .format(thing.layer, thing))

    def detach(self, thing):
        """Remove the given thing from this tile.  Its position is not
        affected.  This method is only intended to be called by the map object.
        """
        if thing.layer is Layer.architecture:
            assert self.architecture is thing
            self.architecture = None
        elif thing.layer is Layer.item:
            self.items.remove(thing)
        elif thing.layer is Layer.creature:
            assert self.creature is thing
            self.creature = None
        else:
            raise TypeError(
                "Unknown layer {!r} for thing {!r}"
                .format(thing.layer, thing))

    def handle_event(self, event):
        """Let a tile act as an event handler, by delegating to everything in
        the tile.
        """
        for thing in self.things:
            thing.handle_event(event)
            if event.cancelled:
                return
