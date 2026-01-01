sam deploy --stack-name resize-app-stage \
  --parameter-overrides \
    StageName=stage \
    UploadBucketName=your-stage-bucket \
    DomainName=app-resize.planttracer.com \
    HostedZoneId=Z02875141U8JDG1N8N5BO\ \
    CertificateArn=arn:aws:acm:us-east-1:123456789012:certificate/.... \
  --no-confirm-changeset --region us-east-1 #  --no-progressbar
