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

Rate (deferred)
---------------

The legacy app also reported a **Rate** (displacement per unit time) using a
hardcoded ``FPS = 20`` and the per-video frame rate. The web app stores a movie
``fps`` field but has no working frame→time conversion yet, so Rate is not computed
in this implementation. It is tracked as a follow-up to #986.

Reserved marker names
---------------------

Two marker names are reserved and given special treatment:

* ``Ruler Nmm`` (e.g. ``Ruler 0mm``, ``Ruler 10mm``) — define the mm/pixel scale;
  excluded from graphing.
* ``Inflection Point`` (matched **case-insensitively**) — the gravitropism pivot.
  It is tracked and graphed like any plant marker, but its reserved name lets the
  dedicated **Add Inflection Point** button and the Angle calculation locate it.
  Only one is allowed per movie. See issue #1033.
