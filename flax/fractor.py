import random

from flax.geometry import Point, Rectangle, Size
from flax.map import Map
from flax.things.arch import CaveWall, Wall, Floor, Player


class MapCanvas:
    def __init__(self, size):
        self.rect = size.to_rect(Point.origin())

        self.arch_grid = {point: CaveWall for point in self.rect.iter_points()}
        self.item_grid = {point: [] for point in self.rect.iter_points()}
        self.creature_grid = {point: None for point in self.rect.iter_points()}

    def draw_room(self, rect):
        assert rect in self.rect

        for point in rect.iter_points():
            self.arch_grid[point] = Floor

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


class Fractor:
    def __init__(self, map_canvas):
        self.map_canvas = map_canvas

    def generate_room(self):
        self.map_canvas.draw_room(Rectangle(Point(0, 0), Size(10, 10)))

    def place_player(self):
        floor_points = list(self.map_canvas.find_floor_points())
        assert floor_points, "can't place player with no open spaces"
        point = random.choice(floor_points)
        self.map_canvas.creature_grid[point] = Player


def generate_map():
    map_canvas = MapCanvas(Size(80, 24))
    fractor = Fractor(map_canvas)
    fractor.generate_room()
    fractor.place_player()
    return map_canvas.to_map()
