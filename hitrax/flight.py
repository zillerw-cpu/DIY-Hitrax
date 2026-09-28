"""Batted ball flight model.

Takes what the camera can measure in a garage (exit velo, launch angle,
spray angle) and projects where the ball would have landed on a real field.

We can't see spin at 120 fps, so backspin is estimated from launch angle.
The drag and lift fits follow Alan Nathan's baseball trajectory calculator.

Field coordinates: origin at home plate on the ground, +y toward center
field, +x toward right field, +z up. Spray angle is 0 to dead center,
negative toward left field, positive toward right field, so the foul lines
sit at -45 and +45 degrees.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

MPH_TO_MS = 0.44704
M_TO_FT = 3.28084

BALL_MASS_KG = 0.1453  # 5.125 oz
BALL_RADIUS_M = 9.125 * 0.0254 / (2 * math.pi)  # 9.125 in circumference
BALL_AREA_M2 = math.pi * BALL_RADIUS_M**2

# Nathan's fits: Cd = CD0 + CD_SPIN * (rpm / 1000), Cl = CL2*S / (CL0 + CL1*S)
CD0 = 0.3008
CD_SPIN = 0.0292
CL0 = 0.583
CL1 = 2.333
CL2 = 1.120
SPIN_DECAY_S = 25.0

GRAVITY = 9.80665


@dataclass(frozen=True)
class Conditions:
    """Virtual field conditions. Defaults are a 70F day near sea level."""

    temperature_f: float = 70.0
    elevation_ft: float = 0.0
    contact_height_in: float = 30.0

    @property
    def air_density(self) -> float:
        temp_k = (self.temperature_f - 32) * 5 / 9 + 273.15
        pressure_ratio = math.exp(-self.elevation_ft / M_TO_FT / 8434.0)
        return 1.2929 * (273.15 / temp_k) * pressure_ratio


@dataclass(frozen=True)
class SpinModel:
    """Backspin guess from launch angle, since the camera can't measure it.

    Line drives come off around 1500 to 2000 rpm and fly balls closer to
    2500, which a straight line in launch angle covers well enough.
    Negative results mean topspin.
    """

    base_rpm: float = 1000.0
    rpm_per_degree: float = 50.0
    min_rpm: float = -1500.0
    max_rpm: float = 4000.0

    def backspin_rpm(self, launch_angle_deg: float) -> float:
        rpm = self.base_rpm + self.rpm_per_degree * launch_angle_deg
        return max(self.min_rpm, min(self.max_rpm, rpm))


@dataclass(frozen=True)
class FlightResult:
    carry_ft: float
    apex_ft: float
    hang_time_s: float
    landing_x_ft: float
    landing_y_ft: float
    backspin_rpm: float
    batted_ball_type: str
    is_foul: bool


def batted_ball_type(launch_angle_deg: float) -> str:
    """Statcast style buckets."""
    if launch_angle_deg < 10:
        return "ground ball"
    if launch_angle_deg < 25:
        return "line drive"
    if launch_angle_deg < 50:
        return "fly ball"
    return "pop up"


def simulate(
    exit_velo_mph: float,
    launch_angle_deg: float,
    spray_angle_deg: float = 0.0,
    conditions: Conditions | None = None,
    spin_model: SpinModel | None = None,
    dt: float = 0.001,
) -> FlightResult:
    """Fly the ball until it reaches the ground and report where it landed."""
    conditions = conditions or Conditions()
    spin_model = spin_model or SpinModel()

    rho = conditions.air_density
    k = 0.5 * rho * BALL_AREA_M2 / BALL_MASS_KG
    rpm0 = spin_model.backspin_rpm(launch_angle_deg)

    la = math.radians(launch_angle_deg)
    sa = math.radians(spray_angle_deg)
    speed = exit_velo_mph * MPH_TO_MS
    state = [
        0.0,
        0.0,
        conditions.contact_height_in * 0.0254,
        speed * math.cos(la) * math.sin(sa),
        speed * math.cos(la) * math.cos(sa),
        speed * math.sin(la),
    ]
    # Pure backspin: the axis is horizontal and square to the direction of
    # travel, so lift stays in the vertical plane of the spray angle.
    axis = (math.cos(sa), -math.sin(sa), 0.0)

    def accel(s: list[float], t: float) -> list[float]:
        vx, vy, vz = s[3], s[4], s[5]
        v = math.sqrt(vx * vx + vy * vy + vz * vz)
        rpm = rpm0 * math.exp(-t / SPIN_DECAY_S)
        omega = rpm * 2 * math.pi / 60
        spin_factor = BALL_RADIUS_M * abs(omega) / v if v > 0 else 0.0
        cd = CD0 + CD_SPIN * abs(rpm) / 1000
        cl = CL2 * spin_factor / (CL0 + CL1 * spin_factor)
        cl = math.copysign(cl, rpm)
        # axis x v gives lift perpendicular to travel; |axis x v| == v here
        lx = axis[1] * vz - axis[2] * vy
        ly = axis[2] * vx - axis[0] * vz
        lz = axis[0] * vy - axis[1] * vx
        return [
            vx,
            vy,
            vz,
            -k * cd * v * vx + k * cl * v * lx,
            -k * cd * v * vy + k * cl * v * ly,
            -k * cd * v * vz + k * cl * v * lz - GRAVITY,
        ]

    t = 0.0
    apex = state[2]
    while True:
        k1 = accel(state, t)
        k2 = accel([s + dt / 2 * d for s, d in zip(state, k1)], t + dt / 2)
        k3 = accel([s + dt / 2 * d for s, d in zip(state, k2)], t + dt / 2)
        k4 = accel([s + dt * d for s, d in zip(state, k3)], t + dt)
        nxt = [
            s + dt / 6 * (a + 2 * b + 2 * c + d)
            for s, a, b, c, d in zip(state, k1, k2, k3, k4)
        ]
        if nxt[2] <= 0:
            # land between the two steps
            frac = state[2] / (state[2] - nxt[2])
            state = [s + frac * (n - s) for s, n in zip(state, nxt)]
            t += frac * dt
            break
        state = nxt
        t += dt
        apex = max(apex, state[2])
        if t > 20:
            break

    x_ft, y_ft = state[0] * M_TO_FT, state[1] * M_TO_FT
    return FlightResult(
        carry_ft=math.hypot(x_ft, y_ft),
        apex_ft=apex * M_TO_FT,
        hang_time_s=t,
        landing_x_ft=x_ft,
        landing_y_ft=y_ft,
        backspin_rpm=rpm0,
        batted_ball_type=batted_ball_type(launch_angle_deg),
        is_foul=abs(spray_angle_deg) > 45,
    )
