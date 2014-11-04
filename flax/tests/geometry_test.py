from flax.geometry import Blob, Point, Rectangle, Size, Span


def test_blob_create():
    rect = Rectangle(origin=Point(0, 0), size=Size(5, 5))
    blob = Blob.from_rectangle(rect)

    assert blob.area == rect.area
    assert blob.height == rect.height


def test_blob_math_disjoint():
    # These rectangles look like this:
    # xxx
    # xxx
    # xxx   xxx
    #       xxx
    #       xxx
    rect1 = Rectangle(origin=Point(0, 0), size=Size(3, 3))
    rect2 = Rectangle(origin=Point(6, 2), size=Size(3, 3))
    blob1 = Blob.from_rectangle(rect1)
    blob2 = Blob.from_rectangle(rect2)

    union_blob = blob1 + blob2
    assert union_blob.area == blob1.area + blob2.area
    assert union_blob.area == rect1.area + rect2.area
    assert union_blob.height == 5

    left_blob = blob1 - blob2
    from pprint import pprint
    pprint(blob1.spans)
    pprint(blob2.spans)
    pprint(left_blob.spans)
    assert left_blob.area == blob1.area
    assert left_blob == blob1

    right_blob = blob2 - blob1
    from pprint import pprint
    pprint(blob1.spans)
    pprint(blob2.spans)
    pprint(right_blob.spans)
    assert right_blob.area == blob2.area
    assert right_blob == blob2


def test_blob_math_overlap():
    # These rectangles look like this:
    # xxx
    # x##x
    # x##x
    #  xxx
    rect1 = Rectangle(origin=Point(0, 0), size=Size(3, 3))
    rect2 = Rectangle(origin=Point(1, 1), size=Size(3, 3))
    blob1 = Blob.from_rectangle(rect1)
    blob2 = Blob.from_rectangle(rect2)

    union_blob = blob1 + blob2
    assert union_blob.area == 14

    left_blob = blob1 - blob2
    assert left_blob.area == 5
    assert left_blob.height == 3
    assert left_blob.spans == {
        0: (Span(0, 2),),
        1: (Span(0, 0),),
        2: (Span(0, 0),),
    }

    right_blob = blob2 - blob1
    assert right_blob.area == 5
    assert right_blob.height == 3
    assert right_blob.spans == {
        1: (Span(3, 3),),
        2: (Span(3, 3),),
        3: (Span(1, 3),),
    }


def test_blob_math_contain():
    # These rectangles look like this:
    # xxxxx
    # x###x
    # x###x
    # x###x
    # xxxxx
    rect1 = Rectangle(origin=Point(0, 0), size=Size(5, 5))
    rect2 = Rectangle(origin=Point(1, 1), size=Size(3, 3))
    blob1 = Blob.from_rectangle(rect1)
    blob2 = Blob.from_rectangle(rect2)

    union_blob = blob1 + blob2
    assert union_blob.area == blob1.area
    assert union_blob.height == blob1.height

    left_blob = blob1 - blob2
    assert left_blob.area == 16
    assert left_blob.height == 5
    assert left_blob.spans == {
        0: (Span(0, 4),),
        1: (Span(0, 0), Span(4, 4)),
        2: (Span(0, 0), Span(4, 4)),
        3: (Span(0, 0), Span(4, 4)),
        4: (Span(0, 4),),
    }

    right_blob = blob2 - blob1
    assert right_blob.area == 0
    assert right_blob.height == 0
    assert right_blob.spans == {}


def test_blob_math_fuzzer():
    pass
