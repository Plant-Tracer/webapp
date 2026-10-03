Administrative Billing page
===========================

The dedicated ``/billing`` page is linked as **Billing** from the main Admin
page for superadmins. It loads independently of the Admin record summary and
shows the current UTC month to date and previous calendar month: account-wide
gross charges, signed credits/refunds, net charges,
service and Lambda usage-type breakdowns, and cost allocation by stack tag.
It also shows invocations, errors, summed execution seconds, and retained
SnapStart snapshots for existing functions in the collector's region. Function
activity includes all versions using only the ``FunctionName`` dimension.
Web functions combine pages, static assets, and Flask APIs; resize functions
combine resize APIs and video/tracing work. These metrics cannot split those
individual request paths or recover metrics for deleted functions.

Costs and activity have different scopes: account costs cover every region;
function statistics cover the configured region (initially ``us-east-1``).
Activity is not a per-function cost allocation. Stack costs require activating
``aws:cloudformation:stack-name`` as a cost allocation tag in Billing. Until
then, costs appear as **Unallocated / shared**. Credits may remain unallocated.
Changing billing preferences or requesting tag backfill requires separate
operator authorization; this feature does neither automatically.

The 30-day snapshot caching estimate multiplies retained snapshot memory by an
observed gross SnapStart cache rate from the two billing months. It excludes
restore fees, credits, and taxes. It is unavailable when there is no observed
cache usage; it is not a forecast or a published-price guarantee. Current
SnapStart versions remain enabled; collection never changes Lambda versions.

Collection and cost
-------------------

Deploy one shared ``planttracer-billing`` stack per AWS account, rather than
one collector per application stack. EventBridge invokes the collector daily
at 10:00 UTC. Three paginated Cost Explorer queries cover both months, and
CloudWatch queries three metrics per existing function across both months.
At the currently published $0.01 per Cost Explorer request, three single-page
queries daily cost about $0.90 per 30-day month, plus small CloudWatch retrieval,
Lambda, S3, and logging charges. Pagination adds requests. AWS billing data
updates at least daily, so more frequent collection does not make it real time.
See `Cost Explorer pricing <https://aws.amazon.com/aws-cost-management/aws-cost-explorer/pricing/>`_.

The collector stores one encrypted, private ``summary.json`` in a dedicated S3
bucket. Successful same-day retries reuse it; a failed collection leaves the
last successful object intact. Reserved concurrency prevents overlapping runs.
The web function receives only GetObject access to that object. Page loads
perform an S3 read, never Cost Explorer, CloudWatch, or inventory queries.
Course administrators, regular users, and superauditors cannot read the endpoint.
Responses use ``Cache-Control: private, no-store`` to avoid browser/shared caching
of account costs. AWS dashboard links require separate AWS authentication.

Snapshots older than 36 hours, or belonging to the previous calendar month,
are marked stale and retain their original date labels. Missing/corrupt caches
are explicitly unavailable. Missing metrics are shown as **No data**. Reported subtotals identify the number
of functions with missing data, rather than inventing zero activity. Execution seconds sum
Lambda Duration samples, not billed duration; they exclude initialization and
are not a measure of request latency.

Build, validate, and adopt
--------------------------

All commands run from the repository root. ``make billing-check`` validates
both SAM templates, lints the collector, and tests cache/API behavior against
MinIO and DynamoDB Local, including a headless browser check through the Admin-to-Billing link. The normal
``make check`` includes billing logic, API, and browser tests. ``make billing-build``
builds an isolated ARM64 Python Lambda package using the ``billing`` dependency
group. No app image or vision dependencies are needed.

``AWS_PROFILE=planttracer-admin AWS_REGION=us-east-1 make billing-collect``
performs read-only AWS queries and writes local evidence to
``BILLING_OUTPUT`` (default ``.tmp/billing-summary.json``). It incurs the same
query charges but does not write AWS resources or refresh the deployed cache.

Deployment is a separate, explicitly authorized operator action:

1. Run ``AWS_PROFILE=planttracer-admin AWS_REGION=us-east-1 make billing-deploy``.
   This always rebuilds the collector from the current checkout before deploying,
   so an older local build cannot be published accidentally. It creates the
   dedicated bucket, scheduled collector, IAM role, and 14-day log group.
   Set ``BILLING_PAGE_URL=https://slg-dev.planttracer.com/billing`` when adopting
   first on slg-dev; the default is the production Billing page. This supplies
   the collector's ``PLANTTRACER_BILLING_URL`` environment variable. Inspect the resulting account and stack before adoption.
2. Wait for the first scheduled run, or explicitly invoke the output
   ``CollectorFunction`` with the Lambda console. Verify ``summary.json`` and
   logs before attaching web stacks. Use CloudWatch's Lambda Errors metric and
   the Billing stale warning to detect failures.
3. Set each web stack's ``BillingSummaryBucket`` SAM parameter to the collector
   stack's output and deploy the approved application version through the normal
   SAM workflow. This supplies ``PLANTTRACER_BILLING_BUCKET`` and read-only IAM.
   The default empty parameter leaves the panel unconfigured with AWS links.
4. As a superadmin, verify both periods, displayed account/region/timestamp,
   costs against Cost Explorer, and activity against CloudWatch. Verify AWS
   links after signing into the intended account. AWS console routing is owned
   by AWS; console access is not granted by application authentication.

The bucket is retained when the collector stack is deleted, preserving the last
summary; remove it separately only when no web stack references it. There is no
collector SnapStart or provisioned concurrency charge. The collector is a daily
background job; web SnapStart settings and cold-start behavior are unchanged.

Weekly SES digest
-----------------

EventBridge Scheduler sends the cached summary every Monday at 09:00
``America/Los_Angeles`` (automatically following daylight saving time) to
``plantadmin@planttracer.com`` from ``admin@planttracer.com``. It includes both
months' gross/credit/net costs, charge breakdowns, function activity, snapshot
estimate, collection timestamp, and Billing/AWS links. It performs no billing
queries. The IAM permission restricts SES to that domain identity, sender, and
recipient. SES sending and the ``planttracer.com`` identity must be enabled in
``us-east-1``; sandbox accounts additionally require a verified recipient.

A fresh current-month cache is required. Missing or stale data fails the Lambda
invocation visibly rather than sending misleading zeroes. SES acceptance is
recorded in ``weekly-email.json`` to suppress ordinary same-week retries. SES
and S3 cannot commit atomically: if SES accepts the message but persisting the
receipt fails, a retry can send a duplicate. Acceptance is not proof of inbox
delivery. Email sending adds four or five small SES charges per month.

On adoption, verify the weekly schedule's timezone/recipient and an actual
accepted message plus inbox delivery. Deployment and live mail testing are
separate from the local tests, which use real MinIO and a botocore SES protocol
stub. There is no browser-triggered send or extra page-load charge.
