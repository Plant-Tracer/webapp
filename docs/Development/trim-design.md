# Video Trim Design

This document describes post-trace video trim support for the Analyze page.
The goal is to let a user limit analysis to an inclusive frame range while
keeping the current "trace from the current frame to the end" workflow.

## Scope

For this release, trim controls are available after the movie has traceable
frame data. Pre-trace trimming is out of scope because the current application
only has frame 0 before tracing or frame-ZIP generation. A future change may
separate frame extraction from motion tracing so users can trim before the
first trace.

Do not trigger retracing from page-leave or `beforeunload` behavior. Trimming
must be applied by an explicit user action while the page is active.

## Stored Metadata

Store trim bounds as movie-table attributes:

- `trim_start_frame`
- `trim_end_frame`

Both values are zero-based frame numbers and the range is inclusive.

Default values:

- `trim_start_frame = 0`
- `trim_end_frame = total_frames - 1`

If either value is missing in DynamoDB when metadata is served to the movie
analyzer, the server should compute the default when `total_frames`
is known, and include it in the JSON response. If a JSON response handed to the
movie analyzer still lacks one of the values, the JavaScript controller should
compute the same defaults from `metadata.total_frames` and the loaded frame
array.

Add both attributes to the local pydantic `Movie` model and to the movie
metadata integer coercion path.

## Validation

Trim updates must satisfy:

- `0 <= trim_start_frame`
- `trim_start_frame <= trim_end_frame`
- `trim_end_frame < total_frames`

Reject invalid updates before persisting them. In particular, setting start
after end or end before start is invalid. Generate an exception so
that we can fix this in development, not have it silently fixed during runtime.
When reading existing metadata, clamp a stored `trim_end_frame` that is beyond
`total_frames - 1`; this can happen after a movie is replaced with a shorter
one while stale trim metadata remains.

## Analyze Page Controls

Add a checkbox under the motion controls:

- Label: `Show video trim controls`.
- Disabled until traceable frame data exists.
- When disabled, show the tooltip text `Trace movie to enable trimming.`

When checked, show trim controls:

- `Set start`
- `Set end`

`Set start` sets `trim_start_frame` to the currently displayed frame.
`Set end` sets `trim_end_frame` to the currently displayed frame.

To clear the start, the user will go to the first frame (by clicking
the first frame button twice) and then clicking `Set start`.

To clear the end, the user will go to the last frame (by clicking
the last frame button twice) and then clicking `Set end`.

## Trackpoint Rules

Applying a trim does not change stored trackpoints outside the inclusive trim range.
However, graphs and CSV export only expose trackpoints in the trimmed range.

When moving `trim_start_frame` earlier and the new start frame has no markers,
copy the old start frame's marker set to the new start frame as an editable
seed; do not synthesize intermediate frames.

Frames outside the trim range may still be displayed by direct navigation, but
they are not part of the active analysis:

- Draw a semi-transparent gray rectangle over the canvas.
- Do not draw markers or path lines on the frame.
- Do not allow adding, deleting, dragging, or saving trackpoints on the frame.
- When tracing to the end of the movie, tracing stops at `trim_end_frame`.

## Movie Player Behavior

When trim bounds are set, playback buttons use the trimmed range as the primary
navigation target while still allowing explicit inspection outside the trim.

| Control | Behavior |
| --- | --- |
| `first_button` | First press goes to `trim_start_frame`; if already on `trim_start_frame`, second press goes to frame 0. |
| `play_reverse` | Plays backward to `trim_start_frame`. |
| `prev_frame` | Goes to the previous frame and ignores `trim_start_frame`. |
| `frame_number_field` | Goes to the requested frame and ignores trim bounds. |
| `pause_button` | No trim-specific behavior. |
| `next_frame` | Goes to the next frame and ignores `trim_end_frame`. |
| `play_forward` | Plays forward to `trim_end_frame`. |
| `last_button` | First press goes to `trim_end_frame`; if already on `trim_end_frame`, second press goes to the last frame. |

## Tracer Lambda Behavior

Rename user-facing and API terminology from tracker/tracking to tracer/tracing
as part of the implementation. The internal algorithm can be renamed in the
same change set.

The tracer endpoint should accept:

- `movie_id`
- `frame_start`
- optional `frame_end`

`frame_start` remains the edited source frame. Tracing resumes after that
source frame. When `frame_end` is provided, tracing stops after producing
trackpoints for `frame_end`. When `frame_end` is omitted, tracing continues to
the physical end of the movie.

The trim implementation should call the tracer with `frame_end =
trim_end_frame` when applying trim. It should not introduce arbitrary
mid-movie trace ranges beyond the current "from source frame forward" model.

## Outputs

Graphs only include frames from `trim_start_frame` through `trim_end_frame`.

CSV and JSON trackpoint downloads only include frames from `trim_start_frame`
through `trim_end_frame`.

The traced MP4 artifact is generated by the tracer and can be downloaded when
`movie_traced_urn` is present. It includes only frames inside the traced trim
range and renders the current marker locations and accumulated path lines
through each frame. Marker edits after tracing set
`needs_retracing = 1` because the stored traced MP4 may no longer match the
current trackpoints.

## Unresolved Questions

- Should Plant Tracer require retracing before allowing traced MP4 download
  after markers are moved, or should it allow users to download the last traced
  artifact with a visible stale warning?

## Implementation Checklist

- Add `trim_start_frame` and `trim_end_frame` constants.
- Add both fields to the pydantic `Movie` model.
- Add both fields to movie metadata integer coercion.
- Ensure `/api/get-movie-metadata` returns defaults for the movie analyzer
  without automatically persisting missing trim attributes.
- Add a trim update endpoint for `Set start` and `Set end` that validates
  cross-field constraints before persisting the requested bound.
- Preserve stored trackpoints outside the trim range.
- Implement the required seed behavior when moving `trim_start_frame` earlier.
- Update the Analyze page template with trim controls.
- Update the JavaScript controller to initialize default trim values if missing.
- Update movie navigation, playback, out-of-range overlay, and interaction
  guards.
- Update graph generation and trackpoint download requests to honor trim bounds.
- Rename Lambda/user-facing tracker terminology to tracer terminology.
- Update the tracer endpoint, queue payload, local worker, and tracing function
  to accept an optional end frame.
- Add focused tests for metadata defaults, validation, out-of-range trackpoint
  preservation, seed-marker copy, navigation behavior, graph filtering, CSV
  filtering, and tracer end-frame handling.
