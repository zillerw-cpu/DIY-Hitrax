"""Loads config.toml into typed settings."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from hitrax.flight import Conditions, SpinModel

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "config.toml"


@dataclass(frozen=True)
class Features:
    swing_tracking: bool = False


@dataclass(frozen=True)
class Settings:
    features: Features = field(default_factory=Features)
    conditions: Conditions = field(default_factory=Conditions)
    spin: SpinModel = field(default_factory=SpinModel)


def load(path: Path | str = DEFAULT_PATH) -> Settings:
    with open(path, "rb") as f:
        raw = tomllib.load(f)

    fld = raw.get("field", {})
    tee = raw.get("tee", {})
    spin = raw.get("spin", {})
    defaults = Settings()
    return Settings(
        features=Features(**raw.get("features", {})),
        conditions=Conditions(
            temperature_f=fld.get("temperature_f", defaults.conditions.temperature_f),
            elevation_ft=fld.get("elevation_ft", defaults.conditions.elevation_ft),
            contact_height_in=tee.get(
                "contact_height_in", defaults.conditions.contact_height_in
            ),
        ),
        spin=SpinModel(
            base_rpm=spin.get("base_rpm", defaults.spin.base_rpm),
            rpm_per_degree=spin.get("rpm_per_degree", defaults.spin.rpm_per_degree),
        ),
    )
