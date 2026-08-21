Analyze: Aggregate Result Statistics
====================================

After a movie is traced, the Analyze page computes aggregate statistics from the
per-frame trackpoint data, in addition to the position-vs-time charts. The
calculations are ported from the legacy iOS app's ``showResult()`` and live in the
pure, DOM-free module ``src/app/static/analysis_results.mjs`` (issue #986). The
display wiring lives in ``canvas_tracer_controller.mjs`` (``display_results()``).

Result modes
------------

A selector on the Analyze page (``#result-mode-select``) chooses which statistics
to show:

* **All** (default) — both groups below.
* **Gravitropism** — Distance and Angle.
* **Circumnutation** — Max Amplitude.

The tracked "tip" marker is the **Apex** if present, otherwise the first graphable
(non-ruler) marker. Ruler markers set the millimeter scale; when two or more are
present, distances are reported in mm, otherwise in pixels.

Gravitropism
------------

Computed from the tip in the first and last (trimmed) frames, and the
**Inflection Point** marker (see `Reserved marker names`_ below).

* **Distance** — Euclidean displacement of the tip from first to last frame,
  multiplied by the scale.
* **Angle** — the bend at the inflection pivot, via the law of cosines. With
  ``b`` = first-tip→first-inflection, ``c`` = last-tip→last-inflection, and
  ``a`` = first-tip→last-tip::

      angle = acos((b² + c² − a²) / (2·b·c)) · 180/π

  The inflection point is tracked per frame, so ``b`` uses its first-frame
  position and ``c`` its last-frame position. The angle is scale-invariant. It is
  omitted when no inflection point is present or the triangle is degenerate (a tip
  coincides with the inflection point).

Circumnutation
--------------

* **Max Amplitude** — horizontal range of the tip over all (trimmed) frames,
  ``(max x − min x) × scale``.
* **Rate** — ``Max Amplitude ÷ elapsed time between the x-extreme frames`` (legacy
  semantics; see #1053). Null when the extremes fall on the same frame.

Rate and the capture interval (fpm)
-----------------------------------

Rate is displacement per unit time. The time base is the **capture interval**
``fpm`` (frames per minute), a per-movie value the user supplies at upload or on the
Analyze page (#1056). The conversion is::

   elapsed_time(min) = frame_span ÷ fpm

* **Gravitropism Rate** = ``Distance ÷ elapsed_time`` over the first→last frame.
* **Circumnutation Rate** = ``Max Amplitude ÷ elapsed_time`` between the frames of
  the minimum and maximum x.

When ``fpm`` is unset (legacy movies, or not yet entered), the graph x-axis stays in
frames and Rate is reported **per frame** (``mm/frame`` or ``pixel/frame``); once a
positive ``fpm`` is set it is reported **per minute**. ``fpm`` is distinct from the
encoded playback ``fps`` and is stored as a string on the movie row (authoritative)
with a best-effort snapshot in the traced MP4 (see
:doc:`MOVIE_METADATA`). Editing ``fpm`` on the Analyze page only rescales time and
rate — it does not require retracing.

This replaces the legacy ``frames × 20 ÷ framerate`` formula (an iOS playback-time
artifact); the ``FPS = 20`` constant is not used.

Reserved marker names
---------------------

Two marker names are reserved and given special treatment:

* ``Ruler Nmm`` (e.g. ``Ruler 0mm``, ``Ruler 10mm``) — define the mm/pixel scale;
  excluded from graphing.
* ``Inflection Point`` (matched **case-insensitively**) — the gravitropism pivot.
  It is tracked and graphed like any plant marker, but its reserved name lets the
  dedicated **Add Inflection Point** button and the Angle calculation locate it.
  Only one is allowed per movie. See issue #1033.
