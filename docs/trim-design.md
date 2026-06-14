Design for video trim:

On video analyze pane, underneath the motion controls, will be a
checkbox that says "Show video trim controls"

- The checkbox is disabled before the movie is traced. There is a
  tooltip that says 'trace movie to enable trimming.' The tooltip goes
  away once the movie is traced.

Pressing the checkbox shows new row of controls that has:
- button on left - "set start".
- Next button - "reset start" - disabled
- third button "reset end" - disabled
- fourth button - "set end"

Pressing "set start":
- It disables the "set start" button. (debouncing!)
- Sets the currently displayed frame as the
  frame_start and stores this as a movie table attribute in DynamoDB.
- enables "reset start"

Pressing "reset start":
- Disables "reset start" button
- erase frame_start in movie table.
- enables the "set start" button

Pressing "set end":
- It disables the "set end" button. (debouncing!)
- Sets the currently displayed frame as the
  frame_end and stores this as a movie table attribute in DynamoDB.
- enables "reset end"

Pressing "reset end":
- Disables "reset end" button
- erase frame_end in movie table.
- enables the "set end" button



Modifications to movie player:
- If displayed movie frame is smaller than `frame_start` or larger than `frame_end` then a
  semi-transparent gray rectangle is displayed over the canvas and
  trackpoints are not shown on it. Trackpoints cannot be added.

Modifications to tracer lambda:
First frame traced is 0 or `frame_start`, whichever is larger.
Last frame traced is the last frame or `frame_end`, whichever is
smaller.

Modifications to HTML page:
- If user leaves the page after a change is made to `frame_start` or
  `frame_end`,  and the movie has not been retraced, the command to
  retrace is sent to the lambda, so it starts retracing and
  re-rendering the traced movie in the background.
