from itertools import product
from weakref import WeakKeyDictionary, ref

from flax.geometry import Point
from flax.things.arch import Thing, Layer, Player


class Map:
    def __init__(self, map_canvas):
        self.height = map_canvas.height
        self.width = map_canvas.width

        self.thing_positions = WeakKeyDictionary()

        self.tiles = {}
        for x, y in product(range(map_canvas.width), range(map_canvas.height)):
            position = Point(x, y)
            tile = self.tiles[position] = Tile(self, position)
            self.place(Thing(map_canvas.grid[x][y]), position)

        # TODO hmm!  unclear how fractor would end up placing the player.  also
        # there's no grid for items or critter yet, ahem.
        # TODO maybe these shouldn't be directly assignable
        self.player = Thing(Player)
        self.place(self.player, Point(2, 2))

    @property
    def rows(self):
        for y in range(self.height):
            yield (self.tiles[x, y] for x in range(self.width))

    def place(self, thing, position):
        assert thing not in self.thing_positions
        self.thing_positions[thing] = position
        self.tiles[position].attach(thing)

    def find(self, thing):
        return self.thing_positions[thing]

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

    def __contains__(self, position):
        return (
            0 <= position.x < self.width and
            0 <= position.y < self.height)


    # XXX this stuff should all be on a world object XXX

    player_action_queue = None

    def advance(self):
        if self.player_action_queue:
            player_action = self.player_action_queue.popleft()
            self.fire_event(player_action)


    def fire_event(self, event):
        event.fire(self)


class Tile:
    def __init__(self, map, position):
        self._map = ref(map)
        self.position = position
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


