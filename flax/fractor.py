import math
import random

from flax.geometry import Point, Rectangle, Size
from flax.map import Map
from flax.entity import Entity, CaveWall, Wall, Floor, Tree, Grass, CutGrass, Dirt, Player, Salamango, Armor, StairsDown, StairsUp
from flax.component import IPhysics, Empty


def random_normal_int(mu, sigma):
    """Return a normally-distributed random integer, given a mean and standard
    deviation.  The return value is guaranteed never to lie outside µ ± 3σ, and
    anything beyond µ ± 2σ is very unlikely (4% total).
    """
    ret = int(random.gauss(mu, sigma) + 0.5)

    # We have to put a limit /somewhere/, and the roll is only outside these
    # bounds 0.3% of the time.
    lb = int(math.ceil(mu - 2 * sigma))
    ub = int(math.floor(mu + 2 * sigma))

    if ret < lb:
        return lb
    elif ret > ub:
        return ub
    else:
        return ret


def random_normal_range(lb, ub):
    """Return a normally-distributed random integer, given an upper bound and
    lower bound.  Like `random_normal_int`, but explicitly specifying the
    limits.  Return values will be clustered around the midpoint.
    """
    # Like above, we assume the lower and upper bounds are 6σ apart
    mu = (lb + ub) / 2
    sigma = (ub - lb) / 4
    ret = int(random.gauss(mu, sigma) + 0.5)

    if ret < lb:
        return lb
    elif ret > ub:
        return ub
    else:
        return ret


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


class Room:
    """A room, which has not yet been drawn.  Performs some light randomization
    of the room shape.
    """
    MINIMUM_SIZE = Size(5, 5)

    def __init__(self, region):
        self.region = region
        self.size = Size(
            random_normal_range(self.MINIMUM_SIZE.width, region.width),
            random_normal_range(self.MINIMUM_SIZE.height, region.height),
        )
        left = region.left + random.randint(0, region.width - self.size.width)
        top = region.top + random.randint(0, region.height - self.size.height)
        self.rect = Rectangle(Point(left, top), self.size)

    def draw_to_canvas(self, canvas):
        assert self.rect in canvas.rect

        for point in self.rect.iter_points():
            canvas.set_architecture(point, random.choice([Floor, CutGrass, CutGrass, Grass]))

        # Top and bottom
        for x in self.rect.range_width():
            canvas.set_architecture(Point(x, self.rect.top), Wall)
            canvas.set_architecture(Point(x, self.rect.bottom), Wall)

        # Left and right (will hit corners again, whatever)
        for y in self.rect.range_height():
            canvas.set_architecture(Point(self.rect.left, y), Wall)
            canvas.set_architecture(Point(self.rect.right, y), Wall)



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

    def generate_map(self, up=None, down=None):
        """The method you probably want to call.  Does some stuff, then spits
        out a map.
        """
        self.generate()
        self.place_stuff()

        if up:
            self.place_portal(StairsUp, up)
        if down:
            self.place_portal(StairsDown, down)

        return self.map_canvas.to_map()

    def generate(self):
        """Implement in subclasses.  Ought to do something to the canvas."""
        raise NotImplementedError

    # Utility methods follow

    def generate_room(self, region):
        # TODO lol not even using room_size
        room = Room(region)
        room.draw_to_canvas(self.map_canvas)

    def place_stuff(self):
        # TODO this probably varies by room style too, but we don't have a huge
        # variety yet of stuff to generate yet, so.
        assert self.map_canvas.floor_spaces, "can't place player with no open spaces"
        points = random.sample(list(self.map_canvas.floor_spaces), 2)
        self.map_canvas.set_creature(points[0], Salamango)
        self.map_canvas.add_item(points[1], Armor)

    def place_portal(self, portal_type, destination):
        from flax.component import IPortal

        # TODO should be able to maybe pass in attribute definitions directly?
        portal = portal_type()
        portal.component_data[IPortal['destination']] = destination


        # TODO not guaranteed
        assert self.map_canvas.floor_spaces, "can't place portal with no open spaces"
        point = random.choice(list(self.map_canvas.floor_spaces))
        self.map_canvas.set_architecture(point, portal)


# TODO this is better, but still not great.  rooms need to be guaranteed
# to not touch each other, for one.  also has some biases towards big rooms
# still (need a left-leaning distribution for room size?) and it's easy to end
# up with an obvious grid
# TODO also lol needs hallways
class BinaryPartitionFractor(Fractor):
    # TODO should probably accept a (minimum) room size instead, and derive
    # minimum partition size from that
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
        # TODO configurable?  with fewer, could draw bigger interesting things in the big spaces
        wanted = 7

        while regions and len(regions) < wanted:
            region = regions.pop(0)

            new_regions = self.partition(region)
            regions.extend(new_regions)

            regions.sort(key=lambda r: r.size.area, reverse=True)

        return regions

    def partition(self, region):
        possible_directions = []

        # Partition whichever direction has more available space
        rel_height = region.height / self.minimum_size.height
        rel_width = region.width / self.minimum_size.width

        if rel_height < 2 and rel_width < 2:
            # Can't partition at all
            return [region]

        if rel_height > rel_width:
            return self.partition_horizontal(region)
        else:
            return self.partition_vertical(region)

    def partition_horizontal(self, region):
        # We're looking for the far edge of the top partition, so subtract 1
        # to allow it on the border of the minimum size
        min_height = self.minimum_size.height
        top = region.top + min_height - 1
        bottom = region.bottom - min_height

        assert top <= bottom

        midpoint = random.randint(top, bottom + 1)

        return [
            region.replace(bottom=midpoint),
            region.replace(top=midpoint + 1),
        ]

    def partition_vertical(self, region):
        # Exactly the same as above
        min_width = self.minimum_size.width
        left = region.left + min_width - 1
        right = region.right - min_width

        assert left <= right

        midpoint = random.randint(left, right + 1)

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
