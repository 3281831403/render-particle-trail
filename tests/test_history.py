"""Behavioural tests for the particle trail history primitives.

The repository is delivered with every function raising NotImplementedError,
so this file must start fully red: 15 failed, no collection or import errors.
"""

import copy
import math

import pytest

from trail.history import (
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


def particle(pid, x, y, alive=True):
    """Build one input particle in the documented shape."""
    return {"id": pid, "pos": (x, y), "alive": alive}


# Defect 1: the history grows without a frame limit.
def test_push_caps_history_length():
    history = []
    for i in range(4):
        history = push(history, [particle(1, float(i), 0.0)], 3)

    assert len(history) == 3
    assert [frame[1][0] for frame in history] == [1.0, 2.0, 3.0]


# Defect 2: a teleport is joined into one long straight segment.
def test_break_on_teleport_splits_trail():
    history = [
        {1: (0.0, 0.0)},
        {1: (0.5, 0.0)},
        {1: (10.0, 0.0)},
        {1: (10.5, 0.0)},
        {1: (11.0, 0.0)},
    ]

    runs = break_on_teleport(history, 2.0)

    assert [len(run) for run in runs] == [2, 3]
    assert runs[0][-1][1] == (0.5, 0.0)
    assert runs[1][0][1] == (10.0, 0.0)


# Defect 3: the fade is reversed and starts at zero on the head.
def test_fade_alpha_head_bright_tail_zero():
    assert fade_alpha(0, 5, "linear") == pytest.approx(1.0)
    assert fade_alpha(2, 5, "linear") == pytest.approx(0.5)
    assert fade_alpha(4, 5, "linear") == pytest.approx(0.0, abs=1e-6)

    assert fade_alpha(0, 5, "quad") == pytest.approx(1.0)
    assert fade_alpha(2, 5, "quad") == pytest.approx(0.25)
    assert fade_alpha(4, 5, "quad") == pytest.approx(0.0, abs=1e-6)


# Defect 4: normals flip between adjacent ribbon segments.
def test_build_ribbon_normals_continuous():
    history = []
    for i in range(9):
        t = i * math.pi / 16.0
        history.append({1: (3.0 * math.cos(t), 2.0 * math.sin(t))})

    ribbon = build_ribbon(history, 0.5)[1]
    normals = ribbon["normals"]

    assert len(normals) == len(history)
    for nx, ny in normals:
        assert math.hypot(nx, ny) == pytest.approx(1.0, abs=1e-6)

    dots = [
        normals[i][0] * normals[i + 1][0] + normals[i][1] * normals[i + 1][1]
        for i in range(len(normals) - 1)
    ]
    assert min(dots) > 0.9


# Defect 5: stationary samples create zero-area ribbon quads.
def test_dedupe_points_removes_stationary_duplicates():
    history = [
        {1: (0.0, 0.0)},
        {1: (0.0, 0.0)},
        {1: (0.0, 2e-7)},
        {1: (1.0, 0.0)},
        {1: (1.0 + 5e-7, 0.0)},
    ]

    deduped = dedupe_points(history, 1e-6)

    assert [frame[1] for frame in deduped] == [(0.0, 0.0), (1.0, 0.0)]


# Defect 6: equal-depth segments are reordered, causing flicker.
def test_depth_sort_stable_for_equal_distance():
    segments = [
        {"id": "far-a", "center": (0.0, 10.0)},
        {"id": "near", "center": (0.0, 1.0)},
        {"id": "far-b", "center": (0.0, 10.0)},
        {"id": "far-c", "center": (0.0, 10.0)},
    ]

    ordered = depth_sort(segments, (0.0, 0.0))

    assert [segment["id"] for segment in ordered] == [
        "far-a",
        "far-b",
        "far-c",
        "near",
    ]


# Defect 7: an over-long history is accepted instead of reported.
def test_validate_reports_length_overflow():
    history = [{1: (float(i), 0.0)} for i in range(5)]

    assert validate(history, 3) == ["length_exceeded"]
    assert validate(history[:3], 3) == []


# Defect 8: NaN positions pass validation and blacken the ribbon.
def test_validate_reports_nan_position():
    assert validate([{1: (0.0, 0.0)}, {1: (math.nan, 2.0)}], 8) == [
        "nan_position"
    ]
    assert validate([{1: (math.inf, 0.0)}], 8) == ["nan_position"]


# Defect 9: emitters share a history queue and cross-contaminate trails.
def test_trail_batch_isolates_emitters():
    emitters = [
        {"id": "left", "history": [{1: (0.0, 0.0)}, {1: (1.0, 0.0)}]},
        {"id": "right", "history": [{2: (0.0, 5.0)}, {2: (1.0, 5.0)}]},
    ]
    before = copy.deepcopy(emitters)

    result = trail_batch(emitters, {"max_len": 8, "width": 0.2, "eps": 1e-6})

    assert list(result) == ["left", "right"]
    assert result["left"][1]["points"] == [(0.0, 0.0), (1.0, 0.0)]
    assert result["right"][2]["points"] == [(0.0, 5.0), (1.0, 5.0)]
    assert emitters == before


# Defect 10: max_len=0 is accepted and later causes division by zero.
def test_push_max_len_zero_raises():
    with pytest.raises(TrailError):
        push([], [particle(1, 0.0, 0.0)], 0)


# Combination: a one-frame history is a single point, not a segment.
def test_single_frame_history_has_one_point():
    ribbons = build_ribbon([{7: (2.0, 3.0)}], 0.4)

    assert set(ribbons) == {7}
    ribbon = ribbons[7]
    assert ribbon["points"] == [(2.0, 3.0)]
    assert len(ribbon["normals"]) == 1
    assert ribbon["alphas"] == [1.0]


# Combination: over-limit input must drop the oldest and retain the newest.
def test_push_keeps_newest_when_over_limit():
    old = [{1: (float(i), 0.0)} for i in range(5)]

    updated = push(old, [particle(1, 9.0, 0.0)], 3)

    assert updated == [
        {1: (2.0, 0.0)},
        {1: (3.0, 0.0)},
        {1: (9.0, 0.0)},
    ]


# Combination: no live particles adds no frame and returns an empty history.
def test_push_empty_particles_returns_empty():
    assert push([], [], 5) == []
    assert push([{1: (0.0, 0.0)}], [particle(1, 9.0, 9.0, alive=False)], 5) == [
        {1: (0.0, 0.0)}
    ]


# Combination: a zero frame budget is rejected by the batch entry point too.
def test_trail_batch_max_len_zero_raises():
    emitters = [{"id": "a", "history": [{1: (0.0, 0.0)}]}]

    with pytest.raises(TrailError):
        trail_batch(emitters, {"max_len": 0, "width": 0.1, "eps": 1e-6})


# Combination: successful batch keys follow the supplied emitter order.
def test_trail_batch_preserves_emitter_order():
    emitters = [
        {"id": "first", "history": [{1: (0.0, 0.0)}, {1: (1.0, 0.0)}]},
        {"id": "second", "history": [{2: (0.0, 1.0)}, {2: (1.0, 1.0)}]},
        {"id": "third", "history": [{3: (0.0, 2.0)}, {3: (1.0, 2.0)}]},
    ]

    result = trail_batch(emitters, {"max_len": 8, "width": 0.25, "eps": 1e-6})

    assert list(result) == ["first", "second", "third"]
    assert set(result["first"]) == {1}
    assert set(result["second"]) == {2}
    assert set(result["third"]) == {3}
