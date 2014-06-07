from enum import Enum


class Direction(Enum):
    up = (0, -1)
    down = (0, 1)
    left = (-1, 0)
    right = (1, 0)


class Point(tuple):
    def __new__(cls, x, y):
        return super().__new__(cls, (x, y))

    @classmethod
    def origin(cls):
        return cls(0, 0)

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


class Size(tuple):
    def __new__(cls, width, height):
        assert width >= 0
        assert height >= 0
        return super().__new__(cls, (width, height))

    @property
    def width(self):
        return self[0]

    @property
    def height(self):
        return self[1]

    def to_rect(self, point):
        return Rectangle(point, self)


class Rectangle(tuple):
    """A rectangle.  Note that since we're working with tiles instead of
    coordinates, the edges here are inclusive on all sides; half the point of
    this class is to take care of all the +1/-1 that requires.

    The origin is assumed to be the top left.
    """
    def __new__(cls, origin, size):
        return super().__new__(cls, (origin, size))

    @property
    def topleft(self):
        return self[0]

    @property
    def size(self):
        return self[1]

    @property
    def top(self):
        return self.topleft.y

    @property
    def bottom(self):
        return self.topleft.y + self.size.height - 1

    @property
    def left(self):
        return self.topleft.x

    @property
    def right(self):
        return self.topleft.x + self.size.width - 1

    @property
    def width(self):
        return self.size.width

    @property
    def height(self):
        return self.size.height

    def __contains__(self, other):
        if isinstance(other, Rectangle):
            return (
                self.top <= other.top and
                self.bottom >= other.bottom and
                self.left <= other.left and
                self.right >= other.right
            )
        elif isinstance(other, Point):
            return (
                self.left <= other.x <= self.right and
                self.top <= other.y <= self.bottom
            )
        else:
            return False

    def iter_points(self):
        """Iterate over all tiles within this rectangle as points."""
        for x in range(self.left, self.right + 1):
            for y in range(self.top, self.bottom + 1):
                yield Point(x, y)

    def range_width(self):
        """Iterate over every x-coordinate within the width of the rectangle.
        """
        return range(self.left, self.right + 1)

    def range_height(self):
        """Iterate over every y-coordinate within the height of the rectangle.
        """
        return range(self.top, self.bottom + 1)
