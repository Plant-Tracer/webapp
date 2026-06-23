Calculation Reference
=====================

This page documents the statistical calculations performed by Plant Tracer after
a movie is traced. The calculations are implemented in
``src/app/static/analysis_results.mjs`` and ported from the legacy iOS app's
``showResult()`` function (see issue #986). For the implementation notes see
:doc:`AnalysisResults`.

Coordinate system and scale
----------------------------

Trackpoints are stored in **bottom-left coordinates**: the origin is the lower-left
corner of the analysis frame, with x increasing to the right and y increasing
upward. All calculations below operate in this coordinate space.

A **scale factor** (mm/pixel) is derived from the ``Ruler Nmm`` markers. When two or
more Ruler markers are present and have been moved off their default positions the
scale is computed as::

   scale (mm/pixel) = (size_hi − size_lo) mm ÷ Euclidean_distance(lo, hi)

where ``size_lo`` and ``size_hi`` are the numeric mm values of the lowest- and
highest-valued Ruler markers, and the Euclidean distance is computed from their
stored pixel coordinates. When fewer than two Ruler markers are present, or when
they remain at their default positions, ``scale = 1`` and results are reported in
pixels.

Time base (fpm)
---------------

Rate calculations require elapsed time. The time base is the **capture interval**
``fpm`` (frames per minute), a per-movie value entered by the user at upload or on
the Analyze page::

   elapsed_time (minutes) = frame_span ÷ fpm

When ``fpm`` is not set, elapsed time is expressed in frames and Rate is reported
per frame rather than per minute.

This replaces the legacy iOS formula ``frames × 20 ÷ framerate``; the ``FPS = 20``
constant is not used.

Gravitropism
------------

Gravitropism calculations use the tip position in the **first** and **last** trimmed
frames, and optionally the **Inflection Point** marker position in those same two
frames.

The tip is the **Apex** marker when present; otherwise the first non-ruler,
non-inflection-point marker.

**Notation**

* ``(x₀, y₀)`` — tip position in the first trimmed frame
* ``(xₙ, yₙ)`` — tip position in the last trimmed frame
* ``(ix₀, iy₀)`` — Inflection Point position in the first trimmed frame
* ``(ixₙ, iyₙ)`` — Inflection Point position in the last trimmed frame
* ``f₀``, ``fₙ`` — frame numbers of the first and last trimmed frames
* ``s`` — scale factor (mm/pixel; 1 when uncalibrated)

Distance
~~~~~~~~

The Euclidean displacement of the tip from the first frame to the last frame::

   distance_px = √((xₙ − x₀)² + (yₙ − y₀)²)
   distance    = distance_px × s

Reported as **mm** when calibrated, **pixels** when not.

Rate
~~~~

Displacement per unit time over the first-to-last frame span::

   frame_span           = |fₙ − f₀|
   elapsed_time (min)   = frame_span ÷ fpm      (omit division when fpm unset)
   gravitropism_rate    = distance ÷ elapsed_time

Reported as **mm/min** (or **px/min**) when ``fpm`` is set; **mm/frame** (or
**px/frame**) otherwise. Null when ``frame_span = 0``.

Angle
~~~~~

The bend angle at the Inflection Point pivot, via the **law of cosines**. Three
distances are computed in pixel coordinates (scale cancels)::

   b = √((x₀  − ix₀)² + (y₀  − iy₀)²)   (first tip  → first  inflection)
   c = √((xₙ  − ixₙ)² + (yₙ  − iyₙ)²)   (last  tip  → last   inflection)
   a = √((xₙ  − x₀ )² + (yₙ  − y₀ )²)   (first tip  → last   tip       )

   cos θ = (b² + c² − a²) / (2 · b · c)
   θ      = arccos(cos θ) · 180 / π

The result is in **degrees**. The angle is omitted (null) when:

* no Inflection Point marker is present, or
* the triangle is degenerate — i.e. a tip position coincides exactly with the
  Inflection Point in the same frame (``b = 0`` or ``c = 0``).

Circumnutation
--------------

Circumnutation calculations scan **all trimmed frames**. There is no Inflection
Point and no Angle result.

Let:

* ``x_min`` — smallest tip x-value across all trimmed frames, at frame ``f_min``
* ``x_max`` — largest  tip x-value across all trimmed frames, at frame ``f_max``

Max Amplitude
~~~~~~~~~~~~~

The total horizontal range of the tip::

   max_amplitude_px = x_max − x_min
   max_amplitude    = max_amplitude_px × s

Reported in **mm** when calibrated, **pixels** when not. Null when there are no
tip points.

Rate
~~~~

Amplitude per unit time, measured between the frames of the x extremes::

   frame_span              = |f_max − f_min|
   elapsed_time (min)      = frame_span ÷ fpm   (omit division when fpm unset)
   circumnutation_rate     = max_amplitude ÷ elapsed_time

Reported as **mm/min** (or **px/min**) when ``fpm`` is set; **mm/frame** (or
**px/frame**) otherwise. Null when ``frame_span = 0`` (the x extremes fall on the
same frame).

.. note::
   The circumnutation rate uses the time **between the frames of the leftmost and
   rightmost tip positions**, not the total trace duration. If these frames happen
   to be close together in time, the rate will be correspondingly high.

Summary table
-------------

.. list-table::
   :header-rows: 1
   :widths: 25 37 38

   * - Result
     - Gravitropism
     - Circumnutation
   * - **Distance / Max Amplitude**
     - Euclidean displacement, first → last frame
     - Horizontal range (max x − min x), all frames
   * - **Rate**
     - Distance ÷ elapsed time (first → last frame)
     - Amplitude ÷ elapsed time (frame of x_min → x_max)
   * - **Angle**
     - Law of cosines at Inflection Point pivot
     - Not calculated
   * - **Units**
     - mm (calibrated) or pixels
     - mm (calibrated) or pixels
   * - **Time base**
     - fpm (frames/minute), else per-frame
     - fpm (frames/minute), else per-frame
