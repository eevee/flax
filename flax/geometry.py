from enum import Enum


class Direction(Enum):
    up = (0, -1)
    down = (0, 1)
    left = (-1, 0)
    right = (1, 0)


class Point(tuple):
    def __new__(cls, x, y):
        return super().__new__(cls, (x, y))

    @property
    def x(self):
        return self[0]

    @property
    def y(self):
        return self[1]

    def __add__(self, other):
        if isinstance(other, Direction):
            return Point(self.x + other.value[0], self.y + other.value[1])

        return NotImplemented
