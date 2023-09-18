import math

def calculate_results_gravitropism(x1, y1, x2, y2, time_elapsed):
    """
    Calculate distance, rate, and angle of movement.

    Parameters:
        x1, y1: initial coordinates of the plant
        x2, y2: final coordinates of the plant
        time_elapsed: time elapsed between the two points

    Returns:
    dictionary of 
        distance: distance moved (mm)
        rate: rate of movement (mm/min)
        angle: angle of movement in degrees relative to positive x-axis
    """
    
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


