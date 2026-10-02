Marker placement, navigation, and tracing
=========================================

Issue `#1256 <https://github.com/Plant-Tracer/webapp/issues/1256>`_.
Frame numbers are zero based. The analysis range includes both Set Start and
Set End. Trimming changes this range; it does not renumber or erase frames.

Rules
-----

A marker has a birth frame, manual placements, and computed trace positions.
These are different from a position merely displayed while navigating.

* **Birth:** a new movie receives Apex, Ruler 0mm, and Ruler 10mm at frame 0.
  Analyze saves this initial placement before initialization finishes. These
  markers are protected from deletion and remain editable. A custom marker
  added at frame X is saved immediately; it exists from X onward, never before X.
* **Navigation:** seeking, stepping, and playing do not save annotations or add
  samples to graphs, paths, or exports. For each marker separately, show its
  latest preceding position. A position saved on the target frame wins. An
  explicit empty annotation is a boundary; it stops preceding seeds.
* **Moving before tracing:** moving a marker on X saves a manual anchor at X.
  Earlier frames retain their positions. Later untraced frames inherit the new
  position, up to a later explicit placement of that same marker. Saving or
  adding another marker does not freeze the inherited positions of other markers.
* **Moving after tracing:** a correction on X changes X only where subsequent
  frames already have computed positions for that marker. Those positions remain
  intact until the user requests retracing. Untraced frames still inherit the
  latest preceding position. Marker identity, color, and birth do not change.
* **Adding after tracing:** a new marker on X appears on X and every later frame,
  even where other markers already have computed positions. Those other markers
  retain their individual positions. The new marker is a displayed seed until
  tracing computes its positions; navigation alone does not create measurements.
* **Initial tracing:** Trace Movie starts at Set Start, even when the user is
  viewing Set End or another frame. It computes through Set End, inclusive.
  Saved manual placements encountered along the way override the computed
  position for that marker and seed the next frame. A later birth is introduced
  at its own frame, never traced backward.
* **Retracing:** an explicit retrace starts at the selected frame and ends at
  Set End. It recomputes subsequent computed positions while retaining later
  manual placements and births. Earlier frames and frames past Set End remain
  unchanged. A corrected frame can therefore be inspected without retracing.
* **Trim:** Set End at 85 leaves the frame-0 anchors intact. A first trace then
  produces positions on 0 through 85. Frames beyond 85 can display the last
  positions without acquiring computed results. Moving Set Start backward
  never copies markers backward or changes their birth frames.
* **Reset:** this is a separate, confirmed operation. It restores default markers
  at Set Start and clears subsequent annotations. Frames before Set Start,
  including frame 0, remain intact. Deleting a custom marker is a separate global
  action; the default apex and ruler markers cannot be deleted.

Worked cases
------------

1. **Upload, jump to 85, Set End, Trace:** defaults are already saved on 0.
   Viewing 85 shows copies. Tracing starts at 0 and computes 1 through 85.
   Returning to 0 or reloading retains all three initial markers.
2. **Leaf appears on 40:** add Leaf on 40. Frames 0 through 39 have no Leaf;
   40 through the last frame show it. Trace from the start introduces Leaf on
   40 and computes its motion beginning at 41.
3. **Move Apex on 30 before tracing:** 0 through 29 retain the original Apex;
   30 onward show the moved Apex unless a later manual placement exists.
   A separate Leaf anchor on 50 does not revert Apex to an older position.
4. **Correct Apex on traced frame 30:** frame 29 and computed frame 31 keep their
   old positions. Reloading preserves the correction. Retracing from 30 updates
   31 onward, honoring any later manual anchors.
5. **Add Leaf on traced frame 40:** existing Apex/rulers keep their computed
   positions on 41 onward. Leaf is carried alongside them. Retracing from 40
   computes Leaf motion without introducing it before 40.
6. **Rapid drag then seek or Trace:** saves are serialized with the frame number
   captured at edit time. Trace waits for all pending saves and refuses to start
   after a failed save. A delayed response cannot overwrite a newer local edit.

Implementation and diagnosis
----------------------------

``Trackpoint.is_manual`` identifies a durable manual placement;
``Trackpoint.is_traced`` identifies an optical-flow result. A displayed copy has
both flags false. The browser resolves seeds per marker, not per frame or from
a movie-wide tracing frontier. The worker preserves manual anchors when clearing
old computed results and merges those anchors into each computed frame.
Existing unflagged saved points retain their exact positions. Old records do
not identify which points were manually edited; those historical edits cannot
be inferred reliably and are treated as legacy trace positions on retracing.

The reported failure had several cooperating causes: initial defaults existed
only in browser memory; tracing started at the currently viewed frame; completion
replaced local frames with server data; and a global frontier hid earlier gaps.
Additionally, adding a marker did not immediately save it, whole-frame seed
selection lost new markers across existing traced frames, and the worker cleared
future manual placements before tracing.

A read-only database inspection of the reported movie
``md206462d-87c6-4eff-81ea-a7c135ad3c88`` found 57 marker-bearing frames, 29 through
85, and no records on 0 through 28. The original coordinates on missing frames
cannot be recovered from those records. This fix prevents the loss; it does not
invent historical measurements or silently rewrite existing research movies.

Validation
----------

Regression checks cover independent marker births, carried positions versus
computed positions, navigation without mutation, explicit empty boundaries,
initial tracing from the trim start, durable defaults, ordered saves, preservation
of manual anchors in DynamoDB Local, and their use by optical flow on real video.
The UI must also be exercised with actual frame navigation and a deployed test
movie. Existing tutorial screenshots of Analyze controls should be reviewed when
updating the tutorial; they are not automatically regenerated by this change.
