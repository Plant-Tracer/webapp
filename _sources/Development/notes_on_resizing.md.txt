# Notes on Resizing

Historical EC2 disk/snapshot notes were removed from this page because instance
IDs, public IP addresses, AMIs, snapshots, and volume IDs become stale quickly
and should not be treated as current deployment documentation.

Current video-resizing guidance for users is in `docs/VideoResizing.rst`.

Current local/deployment behavior:

- Uploaded original movies are stored in S3/MinIO.
- lambda-resize scales extracted analysis frames to the tracker size.
- The upload limit is `C.MAX_FILE_UPLOAD` in `src/app/constants.py`.
- Local development uses MinIO and DynamoDB Local through Makefile targets.
