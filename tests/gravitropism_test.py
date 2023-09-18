import pytest 
import logging

# Configuring the logging module
logging.basicConfig(level=logging.INFO)

from gravitropism import calculate_results_gravitropism

@pytest.mark.parametrize("x1, y1, x2, y2, time_elapsed, expected_results", [
    (0, 1, 3, 4, 2, {'distance': pytest.approx(4.24, 0.01), 'rate': pytest.approx(2.12, 0.01), 'angle': pytest.approx(45.0, 0.1)}),
    (1, 1, 2, 2, 2, {'distance': pytest.approx(1.41, 0.01), 'rate': pytest.approx(0.71, 0.01), 'angle': pytest.approx(45.0, 0.1)}),
    (1, 2, 2, 4, 2, {'distance': pytest.approx(2.24, 0.01), 'rate': pytest.approx(1.12, 0.01), 'angle': pytest.approx(63.43, 0.1)}),
    (0, 0, 0, 0, 2, {'distance': pytest.approx(0.0, 0.01), 'rate': pytest.approx(0.0, 0.01), 'angle': pytest.approx(0.0, 0.1)}),
    (3, 4, 0, 1, 2, {'distance': pytest.approx(4.24, 0.01), 'rate': pytest.approx(2.12, 0.01), 'angle': pytest.approx(-135.0, 0.1)})
])

def test_calculate_two_points(x1, y1, x2, y2, time_elapsed, expected_results):
    logging.info("Starting test_calculate_two_points...")

    results = calculate_results_gravitropism(x1, y1, x2, y2, time_elapsed)
    
    logging.info(f"Running calculate_results_gravitropism with coordinates: ({x1}, {y1}), ({x2}, {y2}) and time_elapsed: {time_elapsed}")
     
    logging.info(f"Results from calculate_results_gravitropism: {results}")
    
    assert results == expected_results
    
    logging.info("Test completed successfully.")