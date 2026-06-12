# AWS Notes

Current AWS deployment work is driven by the root `Makefile`, `template.yaml`,
and `samconfig.toml`.

Key files:

- `Makefile` - local services, lint/test targets, SAM build/deploy helpers.
- `template.yaml` - AWS SAM template.
- `samconfig.toml` - SAM deployment parameters.
- `docs/Development/configuring_aws.md` - AWS configuration notes.
- `docs/Development/ReleaseProcess.rst` - release and tagging process.

Common variables:

| Variable | Meaning |
|----------|---------|
| `AWS_PROFILE` | AWS profile for administrative/deployment commands. |
| `AWS_REGION` | AWS region; use `local` for MinIO/DynamoDB Local. |
| `DYNAMODB_TABLE_PREFIX` | Prefix for DynamoDB table names. |
| `PLANTTRACER_S3_BUCKET` | Existing S3 bucket name, without `s3://`. |
| `PLANTTRACER_LAMBDA_API_BASE` | Explicit lambda-resize HTTP API base URL. |

The S3 bucket is pre-existing and outlives the CloudFormation stack.
