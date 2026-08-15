# Frame-step conformance fixtures

The four committed PPM images are solid red, green, blue, and yellow source
frames. `four-frame-probe.mp4` is their 4 FPS H.264 encoding with a four-frame
GOP and B-frames. The browser conformance test reads the PPM center pixels as
its expected colors and decodes the committed MP4.

CI must use these committed fixtures. FFmpeg is needed only when intentionally
regenerating the MP4:

```sh
ffmpeg -hide_banner -loglevel error -y \
  -framerate 4 -i frame_%d.ppm -frames:v 4 \
  -c:v libx264 -pix_fmt yuv420p -g 4 -bf 2 -sc_threshold 0 \
  -movflags +faststart four-frame-probe.mp4
```
