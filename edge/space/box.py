import numpy as np
from numbers import Number

from .space import DiscretizableSpace, ProductSpace
from edge import error
from edge.utils import ensure_np


class Segment(DiscretizableSpace):
    def __init__(self, low, high, n_points):
        if low >= high:
            raise ValueError(f'Bounds {low} and {high} create empty Segment')
        super(Segment, self).__init__(
            discretization=np.linspace(low, high, n_points).reshape((-1, 1))
        )
        self.low = low
        self.high = high
        self.n_points = n_points
        self.tolerance = (high - low) * 1e-7

    def _get_closest_index(self, x):
        return int(np.around(
            (self.n_points - 1) * (x - self.low) / (self.high - self.low)
        ))

    def _get_value_of_index(self, index):
        t = index / (self.n_points - 1)
        return (1 - t) * self.low + t * self.high

    def contains(self, x):
        if x.shape != (1,):
            return False
        else:
            return (self.low <= x[0]) and (self.high >= x[0])

    def is_on_grid(self, x):
        if x not in self:
            return False
        closest_index = self._get_closest_index(x)
        return np.all(np.abs(self[closest_index] - x) <= self.tolerance)

    def get_index_of(self, x, around_ok=False):
        if x not in self:
            raise error.OutOfSpace
        index = self._get_closest_index(x)
        if around_ok:
            return index
        elif np.all(self.is_on_grid(x)):
            return index
        else:
            raise error.NotOnGrid

    def closest_in(self, x):
        return np.clip(x, self.low, self.high)


class Box(ProductSpace):
    def __init__(self, low, high, shape):
        if isinstance(low, Number) and isinstance(high, Number):
            self.dim = len(shape)
            low = np.array([low] * self.dim)
            high = np.array([high] * self.dim)
        else:
            low = ensure_np(low)
            high = ensure_np(high)
            if not (low.shape == high.shape) and (low.shape == shape):
                raise ValueError(f'Shape mismatch. Low {low.shape} High '
                                 '{high.shape} Shape {shape}')
            self.dim = len(shape)

        self.segments = [None] * self.dim
        for d in range(self.dim):
            self.segments[d] = Segment(low[d], high[d], shape[d])

        super(Box, self).__init__(*self.segments)
