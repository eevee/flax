import random

from flax.geometry import Point, Rectangle, Size
from flax.map import Map
from flax.things.arch import CaveWall, Wall, Floor, Tree, Grass, CutGrass, Dirt, Player, Salamango


class MapCanvas:
    def __init__(self, size):
        self.rect = size.to_rect(Point.origin())

        self.arch_grid = {point: CaveWall for point in self.rect.iter_points()}
        self.item_grid = {point: [] for point in self.rect.iter_points()}
        self.creature_grid = {point: None for point in self.rect.iter_points()}

    def draw_room(self, rect):
        assert rect in self.rect

        for point in rect.iter_points():
            self.arch_grid[point] = random.choice([Floor, CutGrass, CutGrass, Grass])

        # Top and bottom
        for x in rect.range_width():
            self.arch_grid[Point(x, rect.top)] = Wall
            self.arch_grid[Point(x, rect.bottom)] = Wall

        # Left and right (will hit corners again, whatever)
        for y in rect.range_height():
            self.arch_grid[Point(rect.left, y)] = Wall
            self.arch_grid[Point(rect.right, y)] = Wall

    def find_floor_points(self):
        for point, arch in self.arch_grid.items():
            # TODO surely other things are walkable
            # TODO maybe this should be a more general method
            # TODO also should exclude a point with existing creature
            if arch is Floor:
                yield point

    def to_map(self):
        map = Map(self.rect.size)

        for point in self.rect.iter_points():
            map.place(self.arch_grid[point](), point)
            for item_type in self.item_grid[point]:
                map.place(item_type(), point)
            if self.creature_grid[point]:
                map.place(self.creature_grid[point](), point)

        return map


def random_rect_in_rect(area, size):
    """Return a rectangle created by randomly placing the given size within the
    given area.
    """
    top = random.randint(area.top, area.bottom - size.height + 1)
    left = random.randint(area.left, area.right - size.width + 1)

    return Rectangle(Point(left, top), size)


class Fractor:
    def __init__(self, map_canvas, region=None):
        self.map_canvas = map_canvas
        if region is None:
            self.region = map_canvas.rect
        else:
            self.region = region

    def refract(self, fractor_cls, **kwargs):
        return fractor_cls(self.map_canvas, self.region, **kwargs)

    def generate_room(self):
        room_size = Size(5, 5)
        room_rect = random_rect_in_rect(self.region, room_size)
        self.map_canvas.draw_room(room_rect)

    def place_player(self):
        floor_points = list(self.map_canvas.find_floor_points())
        assert floor_points, "can't place player with no open spaces"
        points = random.sample(floor_points, 2)
        self.map_canvas.creature_grid[points[0]] = Player
        self.map_canvas.creature_grid[points[1]] = Salamango


class BinaryPartitionFractor(Fractor):
    def __init__(self, *args, minimum_size):
        super().__init__(*args)
        self.minimum_size = minimum_size

    # TODO i feel like this class doesn't quite...  do...  anything.  all it
    # will ever do is spit out a list of other regions, and it has to construct
    # a bunch of other copies of itself to do that...

    def maximally_partition(self):
        # TODO this should preserve the tree somehow, so a hallway can be drawn
        # along the edges
        regions = [self.region]
        final_regions = []

        while regions:
            nonfinal_regions = []
            for region in regions:
                fractor = BinaryPartitionFractor(
                    self.map_canvas,
                    region,
                    minimum_size=self.minimum_size,
                )
                new_regions = fractor.partition()
                if len(new_regions) > 1:
                    nonfinal_regions.extend(new_regions)
                else:
                    final_regions.extend(new_regions)

            regions = nonfinal_regions

        return final_regions

    def partition(self):
        possible_directions = []

        # TODO this needs a chance to stop before hitting the minimum size

        if self.region.height >= self.minimum_size.height * 2:
            possible_directions.append(self.partition_horizontal)
        if self.region.width >= self.minimum_size.width * 2:
            possible_directions.append(self.partition_vertical)

        if possible_directions:
            method = random.choice(possible_directions)
            return method()
        else:
            return [self.region]

    def partition_horizontal(self):
        # We're looking for the far edge of the top partition, so subtract 1
        # to allow it on the border of the minimum size
        top = self.region.top + self.minimum_size.height - 1
        bottom = self.region.bottom - self.minimum_size.height

        if top > bottom:
            return [self.region]

        midpoint = random.randrange(top, bottom + 1)

        return [
            self.region.adjust(bottom=midpoint),
            self.region.adjust(top=midpoint + 1),
        ]

    def partition_vertical(self):
        # We're looking for the far edge of the left partition, so subtract 1
        # to allow it on the border of the minimum size
        left = self.region.left + self.minimum_size.width - 1
        right = self.region.right - self.minimum_size.width

        if left > right:
            return [self.region]

        midpoint = random.randrange(left, right + 1)

        return [
            self.region.adjust(right=midpoint),
            self.region.adjust(left=midpoint + 1),
        ]


class PerlinFractor(Fractor):
    def draw_something_something_rename_me(self):
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
            self.map_canvas.arch_grid[point] = arch


def generate_map():
    map_canvas = MapCanvas(Size(80, 24))

    perlin_fractor = PerlinFractor(map_canvas)
    perlin_fractor.draw_something_something_rename_me()

    fractor = Fractor(map_canvas)
    fractor.place_player()
    return map_canvas.to_map()

    # TODO probably need to start defining different map generation schemes and
    # figure out how to let the world choose which one it wants
    bsp_fractor = BinaryPartitionFractor(map_canvas, minimum_size=Size(8, 8))
    regions = bsp_fractor.maximally_partition()

    for region in regions:
        fractor = Fractor(map_canvas, region)
        fractor.generate_room()

    fractor = Fractor(map_canvas)
    fractor.place_player()
    return map_canvas.to_map()
