# src/core/filters.py
import math
import time


class LowPassFilter:
    def __init__(self, alpha, init_value=0):
        self.__y = self.s = init_value
        self.__alpha = alpha

    def filter(self, value, alpha=None):
        if alpha is not None:
            self.__alpha = alpha
        # Формула: y = a * x + (1 - a) * y_prev
        self.__y = self.__alpha * value + (1.0 - self.__alpha) * self.s
        self.s = self.__y
        return self.__y

    def last_value(self):
        return self.__y


class OneEuroFilter:
    def __init__(self, min_cutoff=1.0, beta=0.0, d_cutoff=1.0):
        """
        min_cutoff: Минимальная частота отсечения (меньше = плавнее в статике).
        beta: Коэффициент скорости (больше = меньше лаг в движении).
        d_cutoff: Отсечение для вычисления скорости.
        """
        self.min_cutoff = min_cutoff
        self.beta = beta
        self.d_cutoff = d_cutoff

        self.x_filter = LowPassFilter(alpha=1.0)
        self.dx_filter = LowPassFilter(alpha=1.0)
        self.t_prev = None

    def __call__(self, x, t=None):
        if t is None:
            t = time.time()

        # Если данных еще нет, возвращаем как есть
        if self.t_prev is None:
            self.t_prev = t
            self.x_filter = LowPassFilter(alpha=1.0, init_value=x)
            self.dx_filter = LowPassFilter(alpha=1.0, init_value=0)
            return x

        dt = t - self.t_prev
        self.t_prev = t

        if dt <= 0:
            return self.x_filter.last_value()

        # Вычисляем скорость изменения (производную)
        dx = (x - self.x_filter.last_value()) / dt
        edx = self.dx_filter.filter(dx, alpha=self._alpha(dt, self.d_cutoff))

        # Динамически меняем cutoff в зависимости от скорости
        cutoff = self.min_cutoff + self.beta * abs(edx)

        return self.x_filter.filter(x, alpha=self._alpha(dt, cutoff))

    def _alpha(self, dt, cutoff):
        tau = 1.0 / (2 * math.pi * cutoff)
        return 1.0 / (1.0 + tau / dt)


class PointSmoother:
    """
    Удобная обертка для 2D точки (X, Y).
    """

    def __init__(self, min_cutoff=0.5, beta=0.01):
        self.f_x = OneEuroFilter(min_cutoff, beta)
        self.f_y = OneEuroFilter(min_cutoff, beta)

    def filter(self, x, y, timestamp):
        return (
            self.f_x(x, timestamp),
            self.f_y(y, timestamp)
        )