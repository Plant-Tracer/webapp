import pytest

from app.constants import E
from app.gravitropism import calculate_results_gravitropism


@pytest.mark.parametrize("x1, y1, x2, y2, time_elapsed, expected_results", [
    (0, 1, 3, 4, 2, {'distance': pytest.approx(4.24, 0.01), 'rate': pytest.approx(
        2.12, 0.01), 'angle': pytest.approx(45.0, 0.1)}),
    (1, 1, 2, 2, 2, {'distance': pytest.approx(1.41, 0.01), 'rate': pytest.approx(
        0.71, 0.01), 'angle': pytest.approx(45.0, 0.1)}),
    (1, 2, 2, 4, 2, {'distance': pytest.approx(2.24, 0.01), 'rate': pytest.approx(
        1.12, 0.01), 'angle': pytest.approx(63.43, 0.1)}),
    (0, 0, 0, 0, 2, {'distance': pytest.approx(0.0, 0.01), 'rate': pytest.approx(
        0.0, 0.01), 'angle': pytest.approx(0.0, 0.1)}),
    (3, 4, 0, 1, 2, {'distance': pytest.approx(4.24, 0.01), 'rate': pytest.approx(
        2.12, 0.01), 'angle': pytest.approx(-135.0, 0.1)})
])

# pylint: disable=too-many-positional-arguments
def test_calculate_two_points(x1, y1, x2, y2, time_elapsed, expected_results):
    results = calculate_results_gravitropism(x1, y1, x2, y2, time_elapsed)
    assert results == expected_results


def test_coordinates_type_error():
    with pytest.raises(TypeError) as e:
        calculate_results_gravitropism(1, 2, 3, 4, 0)
        assert e.message == E.CALC_RESULTS_PARAM_INVALID['message']
