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

We then checked to make sure that the certificate was validated:

```
AWS_PROFILE=plantadmin AWS_REGION=us-east-1 aws acm describe-certificate \
     --certificate-arn arn:aws:acm:us-east-1:343218180669:certificate/66c18f6a-49b3-4be7-a232-a371cbfef29b
     --query 'Certificate.DomainValidationOptions[0].ResourceRecord'
```
