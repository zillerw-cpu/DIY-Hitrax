"""Quick flight calculator, handy for sanity checking the model.

    python -m hitrax.calc 95 28 -15

Arguments are exit velo (mph), launch angle (deg) and an optional spray
angle (deg, negative is left field). Field conditions come from config.toml.
"""

from __future__ import annotations

import argparse

from hitrax import config
from hitrax.flight import simulate


def describe_spray(spray_deg: float) -> str:
    if abs(spray_deg) < 0.5:
        return "dead center"
    side = "left" if spray_deg < 0 else "right"
    return f"{abs(spray_deg):.0f}° toward {side} field"


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Project where a batted ball would land.")
    p.add_argument("exit_velo_mph", type=float)
    p.add_argument("launch_angle_deg", type=float)
    p.add_argument(
        "spray_angle_deg",
        type=float,
        nargs="?",
        default=0.0,
        help="negative is left field, positive is right field",
    )
    args = p.parse_args(argv)

    s = config.load()
    r = simulate(
        args.exit_velo_mph,
        args.launch_angle_deg,
        args.spray_angle_deg,
        conditions=s.conditions,
        spin_model=s.spin,
    )
    print(
        f"{args.exit_velo_mph:.0f} mph at {args.launch_angle_deg:.0f}°, "
        f"{describe_spray(args.spray_angle_deg)}"
    )
    print(f"{r.batted_ball_type.capitalize()}, {'foul' if r.is_foul else 'fair'}")
    print(f"Carry      {r.carry_ft:5.0f} ft")
    print(f"Apex       {r.apex_ft:5.0f} ft")
    print(f"Hang time  {r.hang_time_s:5.1f} s")
    print(f"Backspin   {r.backspin_rpm:5.0f} rpm (estimated)")


if __name__ == "__main__":
    main()
