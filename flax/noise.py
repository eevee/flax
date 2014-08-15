"""Perlin noise implementation."""
from itertools import product
import random


def s_curve(t):
    """Smooth curve with a zero derivative at 0 and 1, making it useful for
    interpolating.
    """
    t2 = t * t
    t3 = t2 * t
    return t3 * (6 * t2 - 15 * t + 10)


def lerp(t, a, b):
    """Linear interpolation between a and b, given a fraction t."""
    return a + t * (b - a)


def perlin_noise_factory(*resolution):
    """Return a function that will produce Perlin noise for an arbitrary point
    in an arbitrary number of dimensions.

    Arguments are integers, defining the number of cells in the discrete grid
    along each dimension.  That just means how many blocks of distinct noise
    you want along each axis.  1 produces fairly boring noise, but high numbers
    produce too much noise.  Single digits are usually fine.

    The number of dimensions is assumed to match the number of arguments passed in.

    The returned function is `noise(*point)`, where `point` is a sequence of
    floats in [0, 1).  You should, of course, pass the same number of
    arguments to `noise` as you did to this function.  `noise` returns a single
    value in the range [0, 1].
    """
    # Perlin noise is a bit weird.  I picked it up from this general
    # explanation and explanation of the algorithm, respectively:
    # - http://freespace.virgin.net/hugo.elias/models/m_perlin.htm
    # - http://webstaff.itn.liu.se/~stegu/TNM022-2005/perlinnoiselinks/perlin-noise-math-faq.html
    # Imagine you wanted a random smooth curve.  Dead simple way to do it is to
    # pick some random y-values at regular intervals, then interpolate a curve
    # between all those points.  Perlin noise is just a generalization of that
    # to higher dimensions: but instead of random y-values for every integral
    # x, you have a random unit vector at every integral coordinate.
    # I also tried implementing "improved" perlin noise, but I (deliberately)
    # use a fairly small number of cells to generate simple geography, and the
    # non-random gradients work horribly at that resolution.

    dimension = len(resolution)

    # For n dimensions, the range of Perlin noise is ±sqrt(n)/2; multiply
    # by this to scale to ±½ (and then add ½ to make it (0, 1))
    scale_factor = dimension ** -0.5

    # Generate a random unit vector at each grid point -- this is the
    # "gradient" vector, in that the grid tile slopes towards it
    gradients = {}
    for point in product(*(range(res + 1) for res in resolution)):
        # Generate a random point on the surface of the unit n-hypersphere;
        # this is the same as a random unit vector in n dimensions.  Thanks
        # to: http://mathworld.wolfram.com/SpherePointPicking.html
        # Pick n normal random variables with stddev 1
        random_point = [random.gauss(0, 1) for _ in range(dimension)]
        # Then scale the result to a unit vector
        scale = sum(n * n for n in random_point) ** -0.5
        gradients[point] = tuple(coord * scale for coord in random_point)

    def noise(*point):
        assert len(point) == dimension

        # Scale the point from [0, 1] to the given resolution
        point = tuple(coord * res for (coord, res) in zip(point, resolution))

        # Build a list of the (min, max) bounds in each dimension
        grid_coords = []
        for coord in point:
            min_coord = int(coord - 0.000001)
            max_coord = min_coord + 1
            grid_coords.append((min_coord, max_coord))

        # Compute the dot product of each gradient vector and the point's
        # distance from the corresponding grid point.  This gives you each
        # gradient's "influence" on the chosen point.
        dots = []
        for grid_point in product(*grid_coords):
            gradient = gradients[grid_point]
            dot = 0
            for i in range(dimension):
                dot += gradient[i] * (point[i] - grid_point[i])
            dots.append(dot)

        # Interpolate all those dot products together.  The interpolation is
        # done with the S curve to smooth out the slope as you pass from one
        # grid cell into the next.
        # Due to the way product() works, dot products are ordered such that
        # the last dimension alternates: (..., min), (..., max), etc.  So we
        # can interpolate adjacent pairs to "remove" that last dimension.  Then
        # the results will alternate in their second-to-last dimension, and so
        # forth, until we only have a single value left.
        dim = dimension
        while len(dots) > 1:
            dim -= 1
            s = s_curve(point[dim] - grid_coords[dim][0])

            next_dots = []
            while dots:
                next_dots.append(lerp(s, dots.pop(0), dots.pop(0)))

            dots = next_dots

        n = dots[0] * scale_factor + 0.5

        # Finally: the output of the plain Perlin noise algorithm has a fairly
        # strong bias towards the center due to the central limit theorem -- in
        # fact the top and bottom 1/8 virtually never happen.  That's a quarter
        # of our entire output range!  If only we had a function in [0..1] that
        # could introduce a bias towards the endpoints...  oh, hey, we do!
        return s_curve(n)

    return noise


# TODO probably get octaves out of here and put it...  somewhere else?
# wrapper?  should these all just be classes?  jesus
def discrete_perlin_noise_factory(*dimensions, resolution, octaves=1):
    """Return a function that produces Perlin noise for a discrete grid.
    Helpful if you're writing, oh I don't know, a roguelike.

    Positional arguments specify the size of your discrete grid.  The returned
    function expects its arguments to lie within ``range(dimension)``.

    For example, if you have a 100 by 100 grid and want to generate noise for
    every cell, you could use:

        noise = discrete_perlin_noise_factory(100, 100, resolution=4)
        for x in range(100):
            for y in range(100):
                n = noise(x, y)

    Contrast with:

        noise = perlin_noise_factory(4, 4)
        for x in range(100):
            for y in range(100):
                n = noise(x / 100, y / 100)

    Slightly less flexible than the general implementation, since the
    resolution must be the same in every dimension, but you probably didn't
    care about that anyway.

    Note that this implementation assumes each discrete point actually lies
    within the middle of a cell, i.e. has 0.5 added to it.
    """
    dimension = len(dimensions)
    original_noises = []
    for o in range(octaves):
        resolutions = (resolution * 2 ** o,) * dimension
        original_noises.append(perlin_noise_factory(*resolutions))

    def noise(*point):
        assert len(point) == dimension
        scaled_point = tuple(
            (coord + 0.5) / range_
            for (coord, range_) in zip(point, dimensions))

        n = 0
        for o, original in enumerate(original_noises):
            n += original(*scaled_point) / 2 ** o

        # Need to scale n back down since adding all those extra octaves has
        # probably expanded it beyond [0, 1]
        # TODO this will re-introduce the central clustering; any way to avoid
        # that without overcompensating?
        # 1 octave: [0, 1]
        # 2 octaves: [0, 3/2]
        # 3 octaves: [0, 7/4]
        return n / (2 - 2 ** (1 - octaves))

    return noise
