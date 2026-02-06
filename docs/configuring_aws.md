Configuring AWS
===============

Type these commands to configure

.. code-block ::

sudo dnf install git emacs



Planttracer.com setup
=====================

Rather than have a new certificate created each time we created a
lambda, and then destroyed afterwards, we created an ACM certificate for *.planttracer.com:

```
AWS_PROFILE=plantadmin AWS_REGION=us-east-1 aws acm request-certificate \
   --domain-name "*.planttracer.com" --validation-method DNS \
   --idempotency-token $(date +%s) --query 'CertificateArn' --output text | cat
```

The ARN was arn:aws:acm:us-east-1:343218180669:certificate/66c18f6a-49b3-4be7-a232-a371cbfef29b

We then looked at how the certificate needed to be validated:

```
simsong@Station33 webapp % AWS_PROFILE=plantadmin AWS_REGION=us-east-1 aws acm describe-certificate --certificate-arn arn:aws:acm:us-east-1:343218180669:certificate/66c18f6a-49b3-4be7-a232-a371cbfef29b
{
    "Certificate": {
        "CertificateArn": "arn:aws:acm:us-east-1:343218180669:certificate/66c18f6a-49b3-4be7-a232-a371cbfef29b",
        "DomainName": "*.planttracer.com",
        "SubjectAlternativeNames": [
            "*.planttracer.com"
        ],
        "DomainValidationOptions": [
            {
                "DomainName": "*.planttracer.com",
                "ValidationDomain": "*.planttracer.com",
                "ValidationStatus": "PENDING_VALIDATION",
                "ResourceRecord": {
                    "Name": "_693eec3d1a88d2bb16b920b0983d2c6e.planttracer.com.",
                    "Type": "CNAME",
                    "Value": "_1dbd50deb5bb4c92ad60be81cc417d4e.jkddzztszm.acm-validations.aws."
                },
                "ValidationMethod": "DNS"
            }
        ],
        "Subject": "CN=*.planttracer.com",
        "Issuer": "Amazon",
        "CreatedAt": "2026-02-05T20:56:30.767000-05:00",
        "Status": "PENDING_VALIDATION",
        "KeyAlgorithm": "RSA-2048",
        "SignatureAlgorithm": "SHA256WITHRSA",
        "InUseBy": [],
        "Type": "AMAZON_ISSUED",
        "KeyUsages": [],
        "ExtendedKeyUsages": [],
        "RenewalEligibility": "INELIGIBLE",
        "Options": {
            "CertificateTransparencyLoggingPreference": "ENABLED",
            "Export": "DISABLED"
        }
    }
}
```

And we created the validation record:

```
AWS_PROFILE=plantadmin AWS_REGION=us-east-1 aws acm describe-certificate \
     --certificate-arn arn:aws:acm:us-east-1:343218180669:certificate/66c18f6a-49b3-4be7-a232-a371cbfef29b
     --query 'Certificate.DomainValidationOptions[0].ResourceRecord'
```

simsong@Station33 webapp % AWS_PROFILE=plantadmin aws route53 change-resource-record-sets \
  --hosted-zone-id Z02875141U8JDG1N8N5BO \
  --change-batch '{
    "Changes": [
      {
        "Action": "CREATE",
        "ResourceRecordSet": {
          "Name": "_693eec3d1a88d2bb16b920b0983d2c6e.planttracer.com.",
          "Type": "CNAME",
          "TTL": 300,
          "ResourceRecords": [
            {
              "Value": "_1dbd50deb5bb4c92ad60be81cc417d4e.jkddzztszm.acm-validations.aws."
            }
          ]
        }
      }
    ]
  }'
{
    "ChangeInfo": {
        "Id": "/change/C027674015JBXLS9E0L1L",
        "Status": "PENDING",
        "SubmittedAt": "2026-02-06T20:01:36.875000+00:00"
    }
}
simsong@Station33 webapp %
