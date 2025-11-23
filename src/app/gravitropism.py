""" Implement the gravitropism algorithm """

import math

from .constants import E,C

def calculate_results_gravitropism(x1, y1, x2, y2, time_elapsed):
    """
    Calculate distance, rate, and angle of movement.

    :param x1: initial x coordinate
    :type x1: float
    :param x2: final x coordinate
    :type x2: float
    :param y1: initial y coordinate
    :type y1: float
    :param y2: final y coordinate
    :type y2: float
    :param time_elapsed: time elapsed between the two points
    :type time_elapsed: float

    :raises TypeError: All coordinates must be provided and time elapsed must be greater than zero.

    :return:A dictionary of
        distance - distance moved (mm)
        rate - rate of movement (mm/min)
        angle - angle of movement relative to positive x-axis (degrees)
    :rtype: dict
    """

    # check to see if any of the parameters are not valid (null or 0)
    if any(parameter is None for parameter in [x1, y1, x2, y2]) or time_elapsed == 0:
        raise TypeError(E.CALC_RESULTS_PARAM_INVALID['message'])

    # Calculate the distance using the Euclidean distance formula
    distance = math.sqrt((x2 - x1)**2 + (y2 - y1)**2)

    # Calculate the rate of movement
    rate = distance / time_elapsed

    # Calculate the angle using the arctan2 (returns arctan in radians of y/x) function and convert to degrees
    angle = math.degrees(math.atan2(y2 - y1, x2 - x1))

    distance = round(distance, 2)
    rate = round(rate, 2)
    angle = round(angle, 2)

    return {'distance': distance, 'rate': rate, 'angle': angle}
