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
        if isinstance(other, (Point, Size)):
            return Point(self.x + other[0], self.y + other[1])

        return NotImplemented

    def __sub__(self, other):
        if isinstance(other, Direction):
            return Point(self.x - other.value[0], self.y - other.value[1])
        if isinstance(other, (Point, Size)):
            return Point(self.x - other[0], self.y - other[1])

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

    @classmethod
    def from_edges(cls, *, top, bottom, left, right):
        return cls(Point(left, top), Size(right - left + 1, bottom - top + 1))

    @classmethod
    def centered_at(cls, size, center):
        left = center.x - size.width // 2
        top = center.y - size.height // 2
        return cls(Point(left, top), size)

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

    def relative_point(self, relative_width, relative_height):
        """Find a point x% across the width and y% across the height.  The
        arguments should be floats between 0 and 1.

        For example, ``relative_point(0, 0)`` returns the top left, and
        ``relative_point(0.5, 0.5)`` returns the center.
        """
        return Point(
            self.left + int(self.width * relative_width + 0.5),
            self.top + int(self.height * relative_height + 0.5),
        )

    def center(self):
        return self.relative_point(0.5, 0.5)

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

    def replace(self, *, top=None, bottom=None, left=None, right=None):
        if top is None:
            top = self.top
        if bottom is None:
            bottom = self.bottom
        if left is None:
            left = self.left
        if right is None:
            right = self.right

        return type(self).from_edges(
            top=top,
            bottom=bottom,
            left=left,
            right=right,
        )

    def shift(self, *, top=0, bottom=0, left=0, right=0):
        return type(self).from_edges(
            top=self.top + top,
            bottom=self.bottom + bottom,
            left=self.left + left,
            right=self.right + right,
        )

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
