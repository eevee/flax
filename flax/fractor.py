import random

from flax.geometry import Point, Rectangle, Size
from flax.map import Map
from flax.entity import Entity, CaveWall, Wall, Floor, Tree, Grass, CutGrass, Dirt, Player, Salamango, Armor, StairsDown, StairsUp
from flax.component import IPhysics, Empty


class MapCanvas:
    def __init__(self, size):
        self.rect = size.to_rect(Point.origin())

        # TODO i think using types instead of entities /most of the time/ is
        # more trouble than it's worth
        self._arch_grid = {point: CaveWall for point in self.rect.iter_points()}
        self._item_grid = {point: [] for point in self.rect.iter_points()}
        self._creature_grid = {point: None for point in self.rect.iter_points()}

        self.floor_spaces = set()

    def set_architecture(self, point, entity_type):
        self._arch_grid[point] = entity_type

        # TODO this is a little hacky, but it's unclear how this /should/ work
        # before there are other kinds of physics
        if isinstance(entity_type, Entity):
            entity_type = entity_type.type

        if entity_type.components.get(IPhysics) is Empty:
            self.floor_spaces.add(point)
        else:
            self.floor_spaces.discard(point)

    def add_item(self, point, entity_type):
        self._item_grid[point].append(entity_type)

    def set_creature(self, point, entity_type):
        #assert entity_type.layer is Layer.creature
        self._creature_grid[point] = entity_type

    def draw_room(self, rect):
        # TODO i think this should probably return a Room or something, and
        # hold off on drawing the walls yet, so we can erode them a bit and
        # then add line-drawing walls later
        assert rect in self.rect

        for point in rect.iter_points():
            self.set_architecture(point, random.choice([Floor, CutGrass, CutGrass, Grass]))

        # Top and bottom
        for x in rect.range_width():
            self.set_architecture(Point(x, rect.top), Wall)
            self.set_architecture(Point(x, rect.bottom), Wall)

        # Left and right (will hit corners again, whatever)
        for y in rect.range_height():
            self.set_architecture(Point(rect.left, y), Wall)
            self.set_architecture(Point(rect.right, y), Wall)

    def maybe_create(self, type_or_thing):
        if isinstance(type_or_thing, Entity):
            return type_or_thing
        else:
            return type_or_thing()

    def to_map(self):
        map = Map(self.rect.size)
        maybe_create = self.maybe_create

        for point in self.rect.iter_points():
            map.place(maybe_create(self._arch_grid[point]), point)
            for item_type in self._item_grid[point]:
                map.place(maybe_create(item_type), point)
            if self._creature_grid[point]:
                map.place(maybe_create(self._creature_grid[point]), point)

        return map


def random_rect_in_rect(area, size):
    """Return a rectangle created by randomly placing the given size within the
    given area.
    """
    top = random.randint(area.top, area.bottom - size.height + 1)
    left = random.randint(area.left, area.right - size.width + 1)

    return Rectangle(Point(left, top), size)


class Fractor:
    """The agent noun form of 'fractal'.  An object that generates maps in a
    particular style.

    This is a base class, containing some generally-useful functionality; the
    interesting differentiation happens in subclasses.
    """
    def __init__(self, map_size, region=None):
        self.map_canvas = MapCanvas(map_size)
        if region is None:
            self.region = self.map_canvas.rect
        else:
            self.region = region

    def generate_map(self, start=False, up=None, down=None):
        """The method you probably want to call.  Does some stuff, then spits
        out a map.
        """
        self.generate()

        if start:
            self.place_player()

        if up:
            self.place_portal(StairsUp, up)
        if down:
            self.place_portal(StairsDown, down)

        return self.map_canvas.to_map()

    def generate(self):
        """Implement in subclasses.  Ought to do something to the canvas."""
        raise NotImplementedError

    # Utility methods follow

    def generate_room(self, region, room_size=Size(8, 8)):
        room_rect = random_rect_in_rect(region, room_size)
        self.map_canvas.draw_room(room_rect)

    def place_player(self):
        assert self.map_canvas.floor_spaces, "can't place player with no open spaces"
        points = random.sample(list(self.map_canvas.floor_spaces), 3)
        self.map_canvas.set_creature(points[0], Player)
        self.map_canvas.set_creature(points[1], Salamango)
        self.map_canvas.add_item(points[2], Armor)

    def place_portal(self, portal_type, destination):
        from flax.component import IPortal

        # TODO should be able to maybe pass in attribute definitions directly?
        portal = portal_type()
        portal.component_data[IPortal['destination']] = destination


        # TODO not guaranteed
        assert self.map_canvas.floor_spaces, "can't place portal with no open spaces"
        point = random.choice(list(self.map_canvas.floor_spaces))
        self.map_canvas.set_architecture(point, portal)


class BinaryPartitionFractor(Fractor):
    def __init__(self, *args, minimum_size):
        super().__init__(*args)
        self.minimum_size = minimum_size

    def generate(self):
        regions = self.maximally_partition()
        for region in regions:
            self.generate_room(region)

    def maximally_partition(self):
        # TODO this should preserve the tree somehow, so a hallway can be drawn
        # along the edges
        regions = [self.region]
        final_regions = []

        while regions:
            nonfinal_regions = []
            for region in regions:
                new_regions = self.partition(region)
                if len(new_regions) > 1:
                    nonfinal_regions.extend(new_regions)
                else:
                    final_regions.extend(new_regions)

            regions = nonfinal_regions

        return final_regions

    def partition(self, region):
        possible_directions = []

        # TODO this needs a chance to stop before hitting the minimum size --
        # some sort of ramp-down where larger sizes are much less likely.  a
        # bit awkward though since just not dividing means we end up with a
        # room 2x the minimum size.  maybe the partitioning needs tweaking too,
        # like normal curve or something.

        if region.height >= self.minimum_size.height * 2:
            possible_directions.append(self.partition_horizontal)
        if region.width >= self.minimum_size.width * 2:
            possible_directions.append(self.partition_vertical)

        if possible_directions:
            method = random.choice(possible_directions)
            return method(region)
        else:
            return [region]

    def partition_horizontal(self, region):
        # We're looking for the far edge of the top partition, so subtract 1
        # to allow it on the border of the minimum size
        top = region.top + self.minimum_size.height - 1
        bottom = region.bottom - self.minimum_size.height

        if top > bottom:
            return [region]

        midpoint = random.randrange(top, bottom + 1)

        return [
            region.replace(bottom=midpoint),
            region.replace(top=midpoint + 1),
        ]

    def partition_vertical(self, region):
        # We're looking for the far edge of the left partition, so subtract 1
        # to allow it on the border of the minimum size
        left = region.left + self.minimum_size.width - 1
        right = region.right - self.minimum_size.width

        if left > right:
            return [region]

        midpoint = random.randrange(left, right + 1)

        return [
            region.replace(right=midpoint),
            region.replace(left=midpoint + 1),
        ]


class PerlinFractor(Fractor):
    def generate(self):
        # TODO not guaranteed that all the walkable spaces are attached
        from flax.noise import discrete_perlin_noise_factory
        noise = discrete_perlin_noise_factory(*self.region.size, resolution=4, octaves=2)
        for point in self.region.iter_points():
            n = noise(*point)
            if n < 0.2:
                arch = Floor
            elif n < 0.4:
                arch = Dirt
            elif n < 0.6:
                arch = CutGrass
            elif n < 0.8:
                arch = Grass
            else:
                arch = Tree
            self.map_canvas.set_architecture(point, arch)
