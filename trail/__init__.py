"""Particle trail history package."""

from .history import (
    TrailError,
    break_on_teleport,
    build_ribbon,
    dedupe_points,
    depth_sort,
    fade_alpha,
    push,
    trail_batch,
    validate,
)

__all__ = [
    "TrailError",
    "break_on_teleport",
    "build_ribbon",
    "dedupe_points",
    "depth_sort",
    "fade_alpha",
    "push",
    "trail_batch",
    "validate",
]
