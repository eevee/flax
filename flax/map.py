from weakref import WeakKeyDictionary, ref

from flax.component import IPortal
from flax.geometry import Point
from flax.entity import Entity, Layer, Player


class Map:
    def __init__(self, size):
        self.rect = size.to_rect(Point.origin())

        self.entity_positions = WeakKeyDictionary()
        self.portal_index = {}

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
        assert self._player is None, (
            "trying to set player when we've already got one! {} {}".format(
                id(self._player), id(value)))
        self._player = value

    @player.deleter
    def player(self):
        assert self._player is not None, "can't remove nonexistent player!"
        del self._player

    @property
    def rows(self):
        for y in self.rect.range_height():
            yield (self.tiles[Point(x, y)] for x in self.rect.range_width())

    def place(self, entity, position):
        assert entity not in self.entity_positions
        self.entity_positions[entity] = position
        self.tiles[position].attach(entity)

        if entity.isa(Player):
            self.player = entity
        if IPortal in entity.type.components:
            dest = IPortal(entity).destination
            assert dest not in self.portal_index
            self.portal_index[dest] = entity

    def find(self, entity):
        assert isinstance(entity, Entity)
        pos = self.entity_positions[entity]
        return self.tiles[pos]

    def move(self, entity, position):
        old_position = self.entity_positions[entity]
        old_tile = self.tiles[old_position]
        old_tile.detach(entity)

        self.entity_positions[entity] = position
        new_tile = self.tiles[position]
        new_tile.attach(entity)

    def remove(self, entity):
        position = self.entity_positions.pop(entity)
        self.tiles[position].detach(entity)

        if entity.isa(Player):
            del self.player
        if IPortal in entity.type.components:
            dest = IPortal(entity).destination
            del self.portal_index[dest]

    def __contains__(self, position):
        return position in self.rect


class Tile:
    def __init__(self, map, position):
        self._map = ref(map)
        self.position = position
        # TODO would like architecture to default to something (probably
        # CaveWall) so a freshly-created Tile is cromulent, without having to
        # create a new entity on every Tile just to have it overwritten a
        # moment later
        self.architecture = None
        self.creature = None
        self.items = []

    @property
    def map(self):
        return self._map()

    @property
    def entities(self):
        if self.creature:
            yield self.creature

        yield from self.items
        yield self.architecture

    def attach(self, entity):
        """Add the given entity from this tile.  Its position is not affected.
        This method is only intended to be called by the map object.
        """
        if entity.layer is Layer.architecture:
            assert self.architecture is None
            self.architecture = entity
        elif entity.layer is Layer.item:
            self.items.append(entity)
        elif entity.layer is Layer.creature:
            assert self.creature is None
            self.creature = entity
        else:
            raise TypeError(
                "Unknown layer {!r} for entity {!r}"
                .format(entity.layer, entity))

    def detach(self, entity):
        """Remove the given entity from this tile.  Its position is not
        affected.  This method is only intended to be called by the map object.
        """
        if entity.layer is Layer.architecture:
            assert self.architecture is entity
            self.architecture = None
        elif entity.layer is Layer.item:
            self.items.remove(entity)
        elif entity.layer is Layer.creature:
            assert self.creature is entity
            self.creature = None
        else:
            raise TypeError(
                "Unknown layer {!r} for entity {!r}"
                .format(entity.layer, entity))

    def handle_event(self, event):
        """Let a tile act as an event handler, by delegating to everything in
        the tile.
        """
        for entity in self.entities:
            entity.handle_event(event)
            if event.cancelled:
                return
