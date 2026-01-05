IAM Users:
planttracer-dev
* member of planttracer-group

IAM Groups:
planttracer-group:
* Access to S3 buckets


IAM Roles:
planttracer-demo-ZappaLambdaExecutionRole
arn:aws:iam::376778049323:role/planttracer-demo-ZappaLambdaExecutionRole

planttracer-dev-ZappaLambdaExecutionRole
arn:aws:iam::376778049323:role/planttracer-dev-ZappaLambdaExecutionRole

planttracer-production-ZappaLambdaExecutionRole
arn:aws:iam::376778049323:role/planttracer-production-ZappaLambdaExecutionRole

S3 Buckets:

planttracermovies
arn:aws:s3:::planttracermovies
Permission: Block all public access
Region: US East (N. Virginia) us-east-1

Cross-origin resource sharing:
[
    {
        "AllowedHeaders": [
            "*"
        ],
        "AllowedMethods": [
            "PUT",
            "POST",
            "DELETE",
            "GET"
        ],
        "AllowedOrigins": [
            "*"
        ],
        "ExposeHeaders": [],
        "MaxAgeSeconds": 3600
    }
]


S3 bucket policy:

{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Principal": {
                "AWS": [
                    "arn:aws:iam::376778049323:role/planttracer-demo-ZappaLambdaExecutionRole",
                    "arn:aws:iam::376778049323:role/planttracer-production-ZappaLambdaExecutionRole",
                    "arn:aws:iam::376778049323:role/planttracer-dev-ZappaLambdaExecutionRole"
                ]
            },
            "Action": [
                "s3:GetObject",
                "s3:PutObject"
            ],
            "Resource": "arn:aws:s3:::planttracermovies/*"
        }
    ]
}