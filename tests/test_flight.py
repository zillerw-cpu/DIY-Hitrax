import math

import pytest

from hitrax.flight import Conditions, SpinModel, batted_ball_type, simulate


def test_barrel_carries_about_400_ft():
    # MLB rule of thumb: 100 mph at 28 degrees lands around 400 ft
    r = simulate(100, 28)
    assert 385 <= r.carry_ft <= 420


def test_harder_hit_goes_farther():
    assert simulate(105, 28).carry_ft > simulate(95, 28).carry_ft


def test_thin_air_adds_distance():
    sea = simulate(100, 28).carry_ft
    denver = simulate(100, 28, conditions=Conditions(elevation_ft=5280)).carry_ft
    assert 1.03 < denver / sea < 1.10


def test_spray_angle_only_changes_direction():
    center = simulate(100, 28)
    pull = simulate(100, 28, spray_angle_deg=-30)
    assert pull.carry_ft == pytest.approx(center.carry_ft, rel=1e-6)
    assert pull.landing_x_ft < 0
    assert math.degrees(math.atan2(pull.landing_x_ft, pull.landing_y_ft)) == pytest.approx(-30)


def test_foul_lines():
    assert not simulate(90, 25, spray_angle_deg=44).is_foul
    assert simulate(90, 25, spray_angle_deg=-46).is_foul


def test_backspin_adds_carry():
    no_spin = SpinModel(base_rpm=0, rpm_per_degree=0)
    assert simulate(95, 28).carry_ft > simulate(95, 28, spin_model=no_spin).carry_ft


def test_spin_model_clamps():
    m = SpinModel()
    assert m.backspin_rpm(90) == m.max_rpm
    assert m.backspin_rpm(-90) == m.min_rpm


@pytest.mark.parametrize(
    "la, kind",
    [(-5, "ground ball"), (12, "line drive"), (30, "fly ball"), (55, "pop up")],
)
def test_batted_ball_type(la, kind):
    assert batted_ball_type(la) == kind
