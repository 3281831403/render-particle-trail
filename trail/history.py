"""Particle-trail history primitives.

Coordinate and history model
----------------------------
* A position is a world-space ``(x, y)`` pair in metres.
* A *history* is a ``list`` of frames ordered oldest first, newest last.
* A *frame* maps ``particle_id -> (x, y)`` for the particles alive in that
  frame.  Dead particles are omitted from the snapshot.
* An input particle is a mapping ``{"id": ..., "pos": (x, y), "alive": bool}``.
* Unless a function says otherwise, floating point comparisons use an
  absolute tolerance of ``1e-6``.

All functions are pure: they return new containers and never mutate the
history, particle or segment objects supplied by the caller.
"""

from __future__ import annotations

import math
from numbers import Real


class TrailError(ValueError):
    """Raised when trail input is invalid or cannot be rendered safely."""


def _is_number(value):
    """Return True for real numeric values (booleans excluded)."""
    return isinstance(value, Real) and not isinstance(value, bool)


def _is_finite(value):
    """Return True for finite real numeric values."""
    return _is_number(value) and math.isfinite(value)


def _is_valid_pos(pos):
    """Return True for a finite ``(x, y)`` pair."""
    return (
        isinstance(pos, (tuple, list))
        and len(pos) == 2
        and _is_finite(pos[0])
        and _is_finite(pos[1])
    )


def _is_positive_int(value):
    """Return True for positive integers (booleans excluded)."""
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def push(history, particles, max_len):
    """Append one live-particle snapshot, keeping at most ``max_len`` frames.

    The returned history is ordered oldest first and newest last, and always
    ends with the newly appended snapshot.  One slot is reserved for it by
    discarding the oldest retained frame (FIFO), so the newest frame is always
    retained.

    An input that is already longer than ``max_len`` is reconciled to the
    budget first: its stale tail frame is discarded together with the excess,
    so pushing onto an over-long history never grows beyond ``max_len`` and
    never resurrects frames outside the budget window.  The input ``history``
    is not modified.

    If no particle in ``particles`` is alive, the existing (already capped)
    history is returned unchanged instead of appending an empty frame.

    Parameters
    ----------
    history:
        Existing history, a list of frames (``dict`` mapping id to ``(x, y)``).
    particles:
        Iterable of ``{"id", "pos", "alive"}`` mappings.  Only particles with
        ``alive is True`` are written to the snapshot.
    max_len:
        Positive integer frame limit.

    Returns
    -------
    list
        A new history containing at most ``max_len`` frames.

    Raises
    ------
    TrailError
        If ``max_len`` is not a positive integer, or a live particle has a
        malformed position.
    """
    if not _is_positive_int(max_len):
        raise TrailError("max_len must be a positive integer")

    snapshot = {}
    for particle in particles:
        if particle.get("alive") is not True:
            continue
        pos = particle.get("pos")
        if not _is_valid_pos(pos):
            raise TrailError("live particle has a malformed position")
        snapshot[particle["id"]] = (pos[0], pos[1])

    if not snapshot:
        return history

    # Reconcile an over-long input to the budget first: if the history already
    # exceeds max_len, the stale tail falls outside the budget window and is
    # discarded along with the excess.
    if len(history) > max_len:
        budgeted = history[len(history) - max_len : -1]
    else:
        # Reserve one slot for the incoming snapshot (FIFO).
        budgeted = history[-(max_len - 1):] if max_len > 1 else []

    return [*budgeted, snapshot]


def break_on_teleport(history, max_dist):
    """Split a history into runs so teleports do not become long segments.

    Two consecutive frames are connected only when the largest displacement of
    any particle id present in both frames is less than or equal to
    ``max_dist``.  If the displacement is strictly greater, a new run starts
    at the destination frame: the two sides are never joined by a straight
    ribbon segment.

    Particle ids that appear in only one of the two frames cannot produce a
    displacement and therefore do not split the run.

    Parameters
    ----------
    history:
        History ordered oldest first.
    max_dist:
        Non-negative finite teleport threshold in world units.

    Returns
    -------
    list
        A list of runs, where each run is a list of consecutive frames.  An
        empty history produces an empty list; a single-frame history produces
        ``[[frame]]``.

    Raises
    ------
    TrailError
        If ``max_dist`` is negative, non-finite, or not a real number.
    """
    if not _is_number(max_dist) or not math.isfinite(max_dist) or max_dist < 0:
        raise TrailError("max_dist must be a non-negative finite number")

    if not history:
        return []

    runs = [[history[0]]]
    for i in range(1, len(history)):
        prev_frame = history[i - 1]
        cur_frame = history[i]
        split = False
        for pid, pos in cur_frame.items():
            if pid not in prev_frame:
                continue
            prev_pos = prev_frame[pid]
            displacement = math.hypot(
                pos[0] - prev_pos[0], pos[1] - prev_pos[1]
            )
            if displacement > max_dist:
                split = True
                break
        if split:
            runs.append([cur_frame])
        else:
            runs[-1].append(cur_frame)
    return runs


def fade_alpha(index, length, mode):
    """Return the opacity of sample ``index`` in a trail of ``length`` samples.

    Index ``0`` is the newest sample (the head, next to the emitter) and
    ``length - 1`` is the oldest sample (the tail).  The head is fully opaque
    and the tail is fully transparent, so a correct fade never starts at zero
    on the head.

    ``linear`` fades linearly from ``1.0`` at index 0 to ``0.0`` at the tail.
    ``quad`` uses the square of that linear factor, giving a faster falloff
    near the tail.  A one-sample trail is fully opaque (``1.0``) in both modes.

    Parameters
    ----------
    index:
        Zero-based sample index, ``0 <= index < length``.
    length:
        Number of samples, a positive integer.
    mode:
        Either ``"linear"`` or ``"quad"``.

    Returns
    -------
    float
        Alpha in ``[0.0, 1.0]``; the tail is exactly ``0.0``.

    Raises
    ------
    TrailError
        If ``length`` is not positive, ``index`` is outside the trail, or
        ``mode`` is unknown.
    """
    if not _is_positive_int(length):
        raise TrailError("length must be a positive integer")
    if not isinstance(index, int) or isinstance(index, bool) or not (
        0 <= index < length
    ):
        raise TrailError("index must satisfy 0 <= index < length")
    if mode not in ("linear", "quad"):
        raise TrailError(f"unknown fade mode: {mode!r}")

    if length == 1:
        factor = 1.0
    else:
        # Head (index 0) -> 1.0, tail (index length - 1) -> 0.0.
        factor = 1.0 - index / (length - 1)

    if mode == "quad":
        return factor * factor
    return factor


def build_ribbon(history, width):
    """Build one ribbon per particle id from a history.

    For every id that occurs in at least one frame, the samples are collected
    oldest first.  The returned mapping has this shape::

        {
            particle_id: {
                "points": [(x, y), ...],       # oldest -> newest
                "normals": [(nx, ny), ...],    # unit normals, one per point
                "alphas": [float, ...],        # linear fade, newest -> 1.0
                "left": [(x, y), ...],         # points offset by width / 2
                "right": [(x, y), ...],        # points offset by width / 2
                "width": width,
            },
            ...
        }

    Normals are perpendicular to the local tangent and are sign-corrected so
    that adjacent normals stay on the same side of the ribbon; this prevents
    the fold-over crease caused by flipping normals from segment to segment.
    Duplicate or zero-length tangents reuse the previous normal, with
    ``(1.0, 0.0)`` as the initial fallback.  A single-point ribbon therefore
    has exactly one point and one unit normal.

    Parameters
    ----------
    history:
        History ordered oldest first.
    width:
        Positive finite ribbon width in world units.

    Returns
    -------
    dict
        Mapping of particle id to ribbon dictionaries.  An empty history, or
        a history with no particle samples, returns ``{}``.

    Raises
    ------
    TrailError
        If ``width`` is not positive and finite.
    """
    if not _is_finite(width) or width <= 0:
        raise TrailError("width must be a positive finite number")

    # Collect each id's samples oldest first, remembering first-seen order.
    samples = {}
    id_order = []
    for frame in history:
        for pid, pos in frame.items():
            if pid not in samples:
                samples[pid] = []
                id_order.append(pid)
            samples[pid].append((pos[0], pos[1]))

    half_width = width / 2.0
    ribbons = {}
    for pid in id_order:
        points = samples[pid]
        count = len(points)
        normals = []
        prev_normal = None

        for i in range(count):
            x, y = points[i]
            if count == 1:
                dx = dy = 0.0
            elif i == 0:
                # Forward tangent at the first point.
                dx = points[1][0] - x
                dy = points[1][1] - y
            elif i == count - 1:
                # Backward tangent at the last point.
                dx = x - points[i - 1][0]
                dy = y - points[i - 1][1]
            else:
                # Central tangent everywhere else.
                dx = points[i + 1][0] - points[i - 1][0]
                dy = points[i + 1][1] - points[i - 1][1]

            tangent_len = math.hypot(dx, dy)
            if tangent_len == 0.0:
                # Stationary/duplicate point: reuse the previous normal.
                normal = prev_normal if prev_normal is not None else (1.0, 0.0)
            else:
                nx = -dy / tangent_len
                ny = dx / tangent_len
                # Keep adjacent normals on the same side of the ribbon.
                if prev_normal is not None and (
                    nx * prev_normal[0] + ny * prev_normal[1] < 0.0
                ):
                    nx, ny = -nx, -ny
                normal = (nx, ny)

            normals.append(normal)
            prev_normal = normal

        # Points run oldest -> newest, while fade_alpha index 0 is the
        # newest: mirror the index so the head (last point) is opaque and
        # the tail (first point) fades to zero.
        alphas = [
            fade_alpha(count - 1 - i, count, "linear") for i in range(count)
        ]
        left = [
            (
                points[i][0] + normals[i][0] * half_width,
                points[i][1] + normals[i][1] * half_width,
            )
            for i in range(count)
        ]
        right = [
            (
                points[i][0] - normals[i][0] * half_width,
                points[i][1] - normals[i][1] * half_width,
            )
            for i in range(count)
        ]

        ribbons[pid] = {
            "points": points,
            "normals": normals,
            "alphas": alphas,
            "left": left,
            "right": right,
            "width": width,
        }

    return ribbons


def dedupe_points(history, eps):
    """Remove stationary duplicate samples that would create zero-area quads.

    For each particle id, a position is kept only when it is farther than
    ``eps`` from that id's previously kept position.  The first occurrence of
    an id is always kept.  Frames that become empty after filtering are
    dropped from the returned history.  Ids are tracked independently, so one
    moving particle does not cause another particle's static samples to be
    retained.

    Parameters
    ----------
    history:
        History ordered oldest first.
    eps:
        Non-negative finite deduplication tolerance in world units.

    Returns
    -------
    list
        A new, possibly shorter, history.  Input frames are not mutated.

    Raises
    ------
    TrailError
        If ``eps`` is negative, non-finite, or not a real number.
    """
    if not _is_number(eps) or not math.isfinite(eps) or eps < 0:
        raise TrailError("eps must be a non-negative finite number")

    last_kept = {}
    result = []
    for frame in history:
        filtered = {}
        for pid, pos in frame.items():
            if pid not in last_kept:
                filtered[pid] = pos
                last_kept[pid] = pos
                continue
            last_x, last_y = last_kept[pid]
            if math.hypot(pos[0] - last_x, pos[1] - last_y) > eps:
                filtered[pid] = pos
                last_kept[pid] = pos
        if filtered:
            result.append(filtered)
    return result


def depth_sort(segments, camera):
    """Sort ribbon segments far-to-near for stable alpha overdraw.

    Distance is the squared Euclidean distance from each segment's
    ``"center"`` point to ``camera``.  Segments are ordered from the farthest
    to the nearest (painter's algorithm).  Equal distances retain their input
    order; the sort must never reorder ties, because tie jitter makes
    overlapping trail quads flicker between frames.

    Parameters
    ----------
    segments:
        Iterable of mappings that each contain a 2D ``"center"`` position.
        Other keys are treated as opaque payload and preserved.
    camera:
        Camera ``(x, y)`` position in world units.

    Returns
    -------
    list
        A new list of the same segment objects in draw order.

    Raises
    ------
    TrailError
        If ``camera`` or a segment center is malformed or non-finite.
    """
    if not _is_valid_pos(camera):
        raise TrailError("camera must be a finite (x, y) position")

    ordered = list(segments)
    for segment in ordered:
        if not _is_valid_pos(segment.get("center")):
            raise TrailError("segment center must be a finite (x, y) position")

    def squared_distance(segment):
        cx, cy = segment["center"]
        return (cx - camera[0]) ** 2 + (cy - camera[1]) ** 2

    # Python's sort is stable: equal distances keep their input order.
    return sorted(ordered, key=lambda segment: -squared_distance(segment))


def validate(history, max_len):
    """Return the distinct problems found in a history.

    The following issue codes are reported, each at most once, in this order:

    ``"invalid_max_len"``
        ``max_len`` is not a positive integer.  When present this is the only
        issue returned.
    ``"empty_frame"``
        A frame contains no particle positions.
    ``"nan_position"``
        A coordinate is NaN or infinite (non-finite).
    ``"length_exceeded"``
        The history has more than ``max_len`` frames.

    A valid history returns an empty list.

    Parameters
    ----------
    history:
        History ordered oldest first.
    max_len:
        Intended positive frame limit.

    Returns
    -------
    list[str]
        Issue codes in the order described above.
    """
    if not _is_positive_int(max_len):
        return ["invalid_max_len"]

    issues = []
    for frame in history:
        if not frame and "empty_frame" not in issues:
            issues.append("empty_frame")
        for pos in frame.values():
            if not _is_valid_pos(pos):
                if "nan_position" not in issues:
                    issues.append("nan_position")
                break

    if len(history) > max_len and "length_exceeded" not in issues:
        issues.append("length_exceeded")

    return issues


def trail_batch(emitters, config):
    """Build several emitters' ribbons as one all-or-nothing batch.

    ``emitters`` is an iterable of ``{"id": ..., "history": ...}`` mappings.
    Each emitter owns an independent history; no queue or accumulator may be
    shared between emitters.  ``config`` supplies ``max_len`` (positive int),
    ``width`` (positive finite world units) and ``eps`` (non-negative finite
    world units).

    The batch validates every emitter before building anything.  If any
    emitter is invalid (bad config, duplicate/missing id, invalid history), it
    raises ``TrailError`` and returns nothing: no partial mapping and no
    mutation of the supplied histories.  On success it returns a dictionary
    whose keys follow the emitter order, mapping each emitter id to that
    emitter's :func:`build_ribbon` result.

    Parameters
    ----------
    emitters:
        Iterable of emitter mappings with unique hashable ids and histories.
    config:
        Mapping containing ``max_len``, ``width`` and ``eps``.

    Returns
    -------
    dict
        ``{emitter_id: {particle_id: ribbon, ...}, ...}`` in emitter order.

    Raises
    ------
    TrailError
        If the configuration is invalid, an emitter is malformed, an id is
        duplicated, or any history fails :func:`validate`.
    """
    try:
        max_len = config["max_len"]
        width = config["width"]
        eps = config["eps"]
    except (KeyError, TypeError) as exc:
        raise TrailError(
            "config must provide max_len, width and eps"
        ) from exc

    if not _is_positive_int(max_len):
        raise TrailError("config max_len must be a positive integer")
    if not _is_finite(width) or width <= 0:
        raise TrailError("config width must be a positive finite number")
    if not _is_number(eps) or not math.isfinite(eps) or eps < 0:
        raise TrailError("config eps must be a non-negative finite number")

    try:
        emitter_list = list(emitters)
    except TypeError as exc:
        raise TrailError("emitters must be an iterable") from exc

    # Validate everything before building anything, so failure is
    # all-or-nothing and no partial result is ever produced.
    seen_ids = set()
    for emitter in emitter_list:
        try:
            emitter_id = emitter["id"]
            history = emitter["history"]
        except (KeyError, TypeError) as exc:
            raise TrailError(
                "each emitter must contain 'id' and 'history'"
            ) from exc
        try:
            if emitter_id in seen_ids:
                raise TrailError(f"duplicate emitter id: {emitter_id!r}")
            seen_ids.add(emitter_id)
        except TypeError as exc:
            raise TrailError("emitter id must be hashable") from exc

        issues = validate(history, max_len)
        if issues:
            raise TrailError(
                f"emitter {emitter_id!r} has invalid history: {issues}"
            )

    # Each emitter gets its own dedupe pass and ribbon build; histories are
    # never shared or mutated.
    result = {}
    for emitter in emitter_list:
        cleaned_history = dedupe_points(emitter["history"], eps)
        result[emitter["id"]] = build_ribbon(cleaned_history, width)
    return result
