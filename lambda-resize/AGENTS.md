# Lambda Resize Packaging Rules

Keep `lambda-resize` comfortably below AWS Lambda's unzipped deployment limit.
The function ZIP and every attached layer count toward that limit.

## Dependency boundary

`lambda-resize/src/requirements.txt` must be exported from only the root uv
project's `lambda` dependency group:

```console
uv export --locked --only-group lambda --no-emit-project --no-hashes \
  --output-file lambda-resize/src/requirements.txt
```

Do not add these packages to the lambda-resize ZIP:

- `boto3` or `botocore`: use the versions in the AWS-managed Python Lambda
  runtime. Do not package `urllib3` independently because it can conflict with
  the runtime Botocore version.
- `aws-lambda-powertools`: use the Powertools Lambda layer configured in
  `template.yaml`.
- `requests`: use `urllib.request` and other Python standard-library HTTP
  facilities.
- `Pillow`: use OpenCV for JPEG generation, decoding, resizing, rotation, and
  annotation. Inject JPEG COM metadata without decoding or recompressing.
- `imageio`: call the narrow `imageio-ffmpeg` interface directly when H.264
  encoding is required.
- Web-only dependencies such as `apig-wsgi` and Flask.

`tests/test_lambda_requirements.py` enforces the required and forbidden
dependency lists. Update that test whenever the boundary deliberately changes.

## FFmpeg boundary

Do not add or invoke a system FFmpeg installation, the legacy static binaries
named in `src/app/paths.py`, or another FFmpeg distribution.

OpenCV's wheel embeds FFmpeg libraries, and `cv2.VideoCapture` uses them to
decode uploaded MOV/MP4 files. Those embedded libraries cannot provide the
software H.264 encoder required by the traced MP4: on the Linux ARM64 wheel,
OpenCV's H.264 `VideoWriter` fails because only a hardware encoder is exposed.

The sole standalone executable allowed in the ZIP is the ARM64 binary supplied
by `imageio-ffmpeg`. `resize_app.video_writer.H264Writer` calls it directly with
`libx264`; full ImageIO must not be restored. It is used only to encode:

- the traced H.264 movie uploaded by the production tracing job; and
- the H.264 analysis bundle created by the developer CLI.

If traced output no longer requires browser-compatible H.264, remove
`imageio-ffmpeg`, `H264Writer`, and the executable together. Do not silently
replace H.264 with OpenCV's `mp4v`; browser support is not equivalent.

## Build verification

Always build for `linux/arm64` through the Makefile. `make sam-build`:

1. regenerates `lambda-resize/src/requirements.txt`;
2. builds with the SAM Python 3.12 ARM64 container;
3. removes `.DS_Store` files and restores the packaged FFmpeg executable bit;
4. runs `make sam-resize-artifact-test`, which encodes with packaged `libx264`
   and decodes the result through packaged OpenCV; and
5. rejects an oversized unzipped function artifact.

After dependency changes, inspect the built directory as well as the generated
requirements. A passing local virtual-environment test does not prove that the
Linux ARM64 artifact contains the right binary, permissions, or codec.
