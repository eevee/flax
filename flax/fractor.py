from collections import defaultdict
import math
import random

from flax.component import Breakable, IPhysics, Empty
import flax.entity as e
from flax.entity import (
    Entity, CaveWall, Wall, Floor, Tree, Grass, CutGrass, Salamango, Armor,
    Potion, StairsDown, StairsUp
)
from flax.geometry import Point, Rectangle, Size
from flax.map import Map
from flax.noise import discrete_perlin_noise_factory


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
        self._arch_grid = {
            point: CaveWall for point in self.rect.iter_points()}
        self._item_grid = {point: [] for point in self.rect.iter_points()}
        self._creature_grid = {
            point: None for point in self.rect.iter_points()}

        self.floor_spaces = set()

    def clear(self, entity_type):
        for point in self.rect.iter_points():
            self._arch_grid[point] = entity_type

        if entity_type.components.get(IPhysics) is Empty:
            self.floor_spaces = set(self.rect.iter_points())
        else:
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
        # assert entity_type.layer is Layer.creature
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
            canvas.set_architecture(point, e.Floor)

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
        assert self.map_canvas.floor_spaces, \
            "can't place player with no open spaces"
        points = random.sample(list(self.map_canvas.floor_spaces), 10)
        self.map_canvas.set_creature(points[0], Salamango)
        self.map_canvas.add_item(points[1], Armor)
        self.map_canvas.add_item(points[2], Potion)
        self.map_canvas.add_item(points[3], Potion)
        self.map_canvas.add_item(points[4], e.Gem)
        self.map_canvas.add_item(points[5], e.Crate)

    def place_portal(self, portal_type, destination):
        from flax.component import Portal
        portal = portal_type(Portal(destination=destination))

        # TODO not guaranteed
        assert self.map_canvas.floor_spaces, \
            "can't place portal with no open spaces"
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
        # TODO configurable?  with fewer, could draw bigger interesting things
        # in the big spaces
        wanted = 7

        while regions and len(regions) < wanted:
            region = regions.pop(0)

            new_regions = self.partition(region)
            regions.extend(new_regions)

            regions.sort(key=lambda r: r.size.area, reverse=True)

        return regions

    def partition(self, region):
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
    def _a_star(self, start, goals, costs):
        assert goals
        # TODO need to figure out which points should join to which!  need a...
        # minimum number of paths?  some kind of spanning tree that's
        # minimal...
        # TODO technically there might only be one local minima
        seen = set()
        pending = [start]  # TODO actually a sorted set heap thing
        paths = {}

        def estimate_cost(start, goal):
            dx, dy = goal - start
            dx = abs(dx)
            dy = abs(dy)
            return max(dx, dy) * min(costs[start], costs[goal])

        g_score = {start: 0}
        f_score = {start: min(estimate_cost(start, goal) for goal in goals)}

        while pending:
            pending.sort(key=f_score.__getitem__)
            current = pending.pop(0)
            if current in goals:
                # CONSTRUCT PATH HERE
                break

            seen.add(current)
            for npt in current.neighbors:
                if npt not in self.region or npt in seen:
                    continue
                tentative_score = g_score[current] + costs[npt]

                if npt not in pending or tentative_score < g_score[npt]:
                    paths[npt] = current
                    g_score[npt] = tentative_score
                    f_score[npt] = tentative_score + min(
                        estimate_cost(npt, goal) for goal in goals)
                    pending.append(npt)

        final_path = []
        while current in paths:
            final_path.append(current)
            current = paths[current]
        final_path.reverse()
        return final_path

    def _generate_river(self, noise):
        # TODO seriously starting to feel like i need a Feature type for these
        # things?  like, passing `noise` around is a really weird way to go
        # about this.  what would the state even look like though?

        # TODO i think this needs another flooding algorithm, which probably
        # means it needs to be a lot simpler and faster...
        noise_factory = discrete_perlin_noise_factory(
            *self.region.size, resolution=1, octaves=2)

        noise = {
            point: abs(noise_factory(*point) - 0.5) * 2
            for point in self.region.iter_points()
        }
        for point, n in noise.items():
            if n < 0.1:
                self.map_canvas.set_architecture(point, e.Water)
        return

        center_factory = discrete_perlin_noise_factory(
            self.region.height, resolution=3)
        width_factory = discrete_perlin_noise_factory(
            self.region.height, resolution=6, octaves=2)
        center0 = self.region.left + self.region.width / 2
        center = center0
        crossable_spans = set()
        for y in self.region.range_height():
            center += (center_factory(y) - 0.5) * 3
            width = width_factory(y) * 2 + 5
            x0 = int(center - width / 2)
            x1 = int(x0 + width + 0.5)
            for x in range(x0, x1):
                self.map_canvas.set_architecture(Point(x, y), e.Water)

            # XXX hardcoding the test from below...
            if noise[Point(x0 - 1, y)] < 0.6 and noise[Point(x1 + 1, y)] < 0.6:
                crossable_spans.add(y)

                if random.random() < 0.3:
                    for x in range(x0, x1 + 1):
                        self.map_canvas.set_architecture(Point(x, y), e.Bridge)

    def generate(self):
        # This noise is interpreted roughly as the inverse of "frequently
        # travelled" -- low values are walked often (and are thus short grass),
        # high values are left alone (and thus are trees).
        noise_factory = discrete_perlin_noise_factory(
            *self.region.size, resolution=6)
        noise = {
            point: noise_factory(*point)
            for point in self.region.iter_points()
        }
        local_minima = set()
        for point, n in noise.items():
            # We want to ensure that each "walkable region" is connected.
            # First step is to collect all local minima -- any walkable tile is
            # guaranteed to be conneted to one.
            if all(noise[npt] >= n for npt in point.neighbors if npt in noise):
                local_minima.add(point)

            if n < 0.3:
                arch = CutGrass
            elif n < 0.6:
                arch = Grass
            else:
                arch = Tree
            self.map_canvas.set_architecture(point, arch)

        # self._generate_river(noise)

        for x in self.region.range_width():
            for y in (self.region.top, self.region.bottom):
                point = Point(x, y)
                n = noise[point]
                if (n < noise.get(Point(x - 1, y), 1) and
                        n < noise.get(Point(x + 1, y), 1)):
                    local_minima.add(point)
        for y in self.region.range_height():
            for x in (self.region.left, self.region.right):
                point = Point(x, y)
                n = noise[point]
                if (n < noise.get(Point(x, y - 1), 1) and
                        n < noise.get(Point(x, y + 1), 1)):
                    local_minima.add(point)

        for point in local_minima:
            self.map_canvas.set_architecture(point, e.Dirt)

        # We want to connect all the minima with a forest path.
        # Let's flood the forest.  The algorithm is as follows:
        # - All the local minima are initally full of water, forming a set of
        # distinct puddles.
        # - Raise the water level.  Each newly-flooded tile must touch at least
        # one other flooded tile; it becomes part of that puddle, and remembers
        # the tile that flooded it.
        # - Whenever a tile touches two or more puddles, they merge into one
        # large puddle.  That tile is part of the forest path.  For each
        # puddle, walk back along the chain of flooded tiles to the original
        # minima; these tiles are also part of the forest path.
        # When only one puddle remains, we're done, and all the minima are
        # joined by a path along the lowest route.
        flooded = {}
        puddle_map = {}
        path_from_puddle = defaultdict(dict)
        paths = set()
        for puddle, point in enumerate(local_minima):
            flooded[point] = puddle
            puddle_map[puddle] = puddle
        flood_order = sorted(
            noise.keys() - flooded.keys(),
            key=noise.__getitem__)
        for point in flood_order:
            # Group any flooded neighbors by the puddle they're in.
            # puddle => [neighboring points...]
            adjacent_puddles = defaultdict(list)
            for npt in point.neighbors:
                if npt not in flooded:
                    continue
                puddle = puddle_map[flooded[npt]]
                adjacent_puddles[puddle].append(npt)
            # Every point is either a local minimum OR adjacent to a point
            # lower than itself, by the very definition of "local minimum".
            # Thus there must be at least one adjacent puddle.
            assert adjacent_puddles

            # Remember how to get from adjacent puddles to this point.
            # Only store the lowest adjacent point.
            for puddle, points in adjacent_puddles.items():
                path_from_puddle[point][puddle] = min(
                    points, key=noise.__getitem__)

            flooded[point] = this_puddle = min(adjacent_puddles)
            if len(adjacent_puddles) > 1:
                # Draw the path from both puddles' starting points to here
                paths.add(point)
                for puddle in adjacent_puddles:
                    path_point = point
                    while path_point:
                        paths.add(path_point)

                        next_point = None
                        cand_paths = path_from_puddle[path_point]
                        for cand_puddle, cand_point in cand_paths.items():
                            if puddle_map[cand_puddle] == puddle and (
                                    next_point is None or
                                    noise[cand_point] < noise[next_point]
                            ):
                                next_point = cand_point
                        path_point = next_point

                # This point connects two puddles; merge them.  Have to update
                # the whole mapping, in case some other puddle is already
                # mapped to one we're about to remap.
                for from_puddle, to_puddle in puddle_map.items():
                    if {from_puddle, to_puddle} & adjacent_puddles.keys():
                        puddle_map[from_puddle] = this_puddle

                # If there's only one puddle left, we're done!
                if len(frozenset(puddle_map.values())) == 1:
                    break

        # And draw the path, at last.
        for path_point in paths:
            self.map_canvas.set_architecture(path_point, e.Dirt)


class RuinFractor(Fractor):
    # TODO should really really let this wrap something else
    def generate(self):
        self.map_canvas.clear(Floor)

        room = Room(self.region)
        room.draw_to_canvas(self.map_canvas)

        noise = discrete_perlin_noise_factory(
            *self.region.size, resolution=5, octaves=4)
        for point in self.region.iter_points():
            # TODO would greatly prefer some architecture types that just have
            # a 'decay' property affecting their rendering, but that would
            # require rendering to be per-entity, and either a method or
            # something that could be updated on the fly
            if self.map_canvas._arch_grid[point] is Wall:
                n = noise(*point)
                if n < 0.7:
                    arch = e.Ruin(Breakable(n / 0.7))
                else:
                    arch = e.Wall
                self.map_canvas.set_architecture(point, arch)
            elif self.map_canvas._arch_grid[point] is Floor:
                n = noise(*point)
                if n < 0.5:
                    arch = e.Rubble(Breakable(n / 0.5))
                else:
                    arch = e.Floor
                self.map_canvas.set_architecture(point, arch)
