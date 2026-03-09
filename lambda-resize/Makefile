# -----------------------------------------------------------------------------
# lambda-resize Makefile
# -----------------------------------------------------------------------------
# This directory holds the Lambda code that processes uploads (S3 -> move to
# final key, update DynamoDB, set MP4 metadata). The Lambda is deployed as part
# of the main webapp stack (see ../template.yaml), not as a separate stack.
#
# Deploy from the repo root:  make sam-build && make sam-deploy
#
# This Makefile is for:
#   - Local dev: install, vend-app, lint, check (pytest)
#   - Observability: sam-logs (last N CloudWatch log events), sam-status (curl
#     /status). Both use the stack name from ../samconfig.toml (same as main
#     app), and resolve the Lambda from Outputs or nested stack resources.
#   - Clean: remove .venv and build artifacts
#
# Overrides: LAMBDA_STACK, BASE_DOMAIN, SAM_CONFIG, SAM_LOGS_LIMIT, REGION,
#            PROFILE (defaults from AWS_REGION, AWS_PROFILE).
# -----------------------------------------------------------------------------

AWS_PROFILE         ?= planttracer
AWS_REGION          ?= us-east-1
STACK               ?= resize-app
PYTHON              = python3.13
DJLINT_FLAGS        ?= --profile=jinja --lint --quiet --ignore J004,J018
SHELL               := /bin/bash
.SHELLFLAGS         := -eu -o pipefail -c

REGION              ?= $(AWS_REGION)
PROFILE             ?= $(AWS_PROFILE)

# Stack name from main app samconfig; used for sam-status and sam-logs.
SAM_CONFIG          ?= ../samconfig.toml
LAMBDA_STACK        ?= $(or $(shell grep "stack_name" $(SAM_CONFIG) 2>/dev/null | head -1 | cut -d'=' -f2 | tr -d ' "'),$(STACK))
BASE_DOMAIN         ?= planttracer.com
STATUS_URL          := https://$(LAMBDA_STACK)-lambda.$(BASE_DOMAIN)/status

export PYTHONDONTWRITEBYTECODE=1
export AWS_PROFILE
export AWS_REGION

.PHONY: install vend-app lint check sam-logs sam-status clean info run run-proxy-local run-proxy-app

# --- Local dev and CI ---
install: .venv/pyvenv.cfg

.venv/pyvenv.cfg: pyproject.toml Makefile
	poetry config virtualenvs.in-project true
	poetry install
	npm install -g browser-sync

src/requirements.txt: pyproject.toml Makefile .venv/pyvenv.cfg
	poetry export -f requirements.txt --only main --without-hashes --output src/requirements.txt

vend-app: Makefile
	rsync --verbose --archive ../src/app/{odb,schema,constants,mp4_metadata_lib}.py src/resize_app/src/app/

lint: .venv/pyvenv.cfg
	make vend-app
	poetry run ruff check --fix
	poetry run pylint src
	echo poetry run pyright does not work well yet

check: .venv/pyvenv.cfg
	make vend-app
	make lint
	poetry run pytest -q --cov=.   --cov-report=term --cov-report=xml --junitxml=junit.xml -o junit_family=legacy --log-cli-level=DEBUG tests/

# --- Observability (stack from samconfig; Lambda found in Outputs or nested stack) ---
SAM_LOGS_LIMIT ?= 100
sam-logs:
	@FUNC=$$(aws cloudformation describe-stacks --stack-name $(LAMBDA_STACK) --region $(REGION) --profile $(PROFILE) \
		--query 'Stacks[0].Outputs[?OutputKey==`LambdaFunction`].OutputValue' --output text 2>/dev/null); \
	if [ -z "$$FUNC" ]; then \
	  FUNC=$$(aws cloudformation describe-stacks --stack-name $(LAMBDA_STACK) --region $(REGION) --profile $(PROFILE) \
		--query 'Stacks[0].Outputs[?OutputKey==`ResizeFunction`].OutputValue' --output text 2>/dev/null); \
	fi; \
	if [ -z "$$FUNC" ]; then \
	  FUNC=$$(aws cloudformation describe-stack-resources --stack-name $(LAMBDA_STACK) --region $(REGION) --profile $(PROFILE) \
		--query "StackResources[?ResourceType=='AWS::Lambda::Function'].PhysicalResourceId" --output text 2>/dev/null | tr '\t' '\n' | head -1); \
	fi; \
	if [ -z "$$FUNC" ]; then \
	  for NESTED in $$(aws cloudformation describe-stack-resources --stack-name $(LAMBDA_STACK) --region $(REGION) --profile $(PROFILE) \
		--query "StackResources[?ResourceType=='AWS::CloudFormation::Stack'].PhysicalResourceId" --output text 2>/dev/null); do \
	    FUNC=$$(aws cloudformation describe-stack-resources --stack-name "$$NESTED" --region $(REGION) --profile $(PROFILE) \
		--query "StackResources[?ResourceType=='AWS::Lambda::Function'].PhysicalResourceId" --output text 2>/dev/null | tr '\t' '\n' | head -1); \
	    [ -n "$$FUNC" ] && break; \
	  done; \
	fi; \
	if [ -z "$$FUNC" ]; then echo "No Lambda function found for stack $(LAMBDA_STACK)"; exit 1; fi; \
	echo "Last $(SAM_LOGS_LIMIT) log events for /aws/lambda/$$FUNC (stack=$(LAMBDA_STACK))..."; \
	aws logs filter-log-events --log-group-name "/aws/lambda/$$FUNC" --limit $(SAM_LOGS_LIMIT) \
		--region $(REGION) --profile $(PROFILE) --output text

sam-status:
	@echo "Checking Lambda status at $(STATUS_URL)..."
	@sleep 3; \
	RESP=$$(curl -s -w "\n%{http_code}" "$(STATUS_URL)" 2>/dev/null); \
	CODE=$$(echo "$$RESP" | tail -1); \
	BODY=$$(echo "$$RESP" | sed '$$d'); \
	if echo "$$BODY" | grep -q '"status"[[:space:]]*:[[:space:]]*"ok"'; then \
	  echo "Lambda status: operational ($(STATUS_URL))"; \
	else \
	  echo "Lambda status: FAIL (HTTP $$CODE) ($(STATUS_URL))"; \
	  echo "  response: $$BODY"; exit 1; \
	fi

# --- Clean and info ---
clean:
	/bin/rm -rf .venv
	/bin/rm -rf .aws-sam/build

info:
	@echo "Stack (for status/logs): $(LAMBDA_STACK) (from $(SAM_CONFIG))"
	@echo "Region: $(REGION)  Profile: $(PROFILE)"
	@echo "Status URL: $(STATUS_URL)"
	@echo ""
	@echo "Targets: install vend-app lint check sam-logs sam-status clean info run run-proxy-local run-proxy-app"

# --- Development (browser-sync) ---
run:
	browser-sync start --server --files "*.html, *.css, *.js"

run-proxy-local:
	@echo "Proxy to localhost:5000"
	(cd src/sync; browser-sync start --proxy "localhost:5000" --files "*.html, *.css, *.js")

run-proxy-app:
	@echo "Proxy to localhost:5000"
	(cd src/sync; browser-sync start --proxy "localhost:5000" --files "*.html, *.css, *.js")
