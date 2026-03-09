# ===== resize_app Makefile =====
# lambda-resize is the minimal resize page. Production only (no stage).
AWS_PROFILE         ?= planttracer
AWS_REGION          ?= us-east-1
STACK           ?= resize-app
PYTHON          = python3.13
DJLINT_FLAGS ?= --profile=jinja --lint --quiet --ignore J004,J018
SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c

# Use same names as aws-cli (REGION/PROFILE) for log/tail targets
REGION  ?= $(AWS_REGION)
PROFILE ?= $(AWS_PROFILE)

BUILD_DIR := .aws-sam/build/$(FUNC)
ZIP_PATH  := .aws-sam/build/$(FUNC).zip
SRC_TPL   := .aws-sam/build/template.yaml
PKG_TPL   := packaged.yaml

# Lambda HTTP URL depends on stack name (main template: ${StackName}-lambda.${BaseDomain})
# Stack name from samconfig (main app deploys Lambda; use parent samconfig when in lambda-resize/)
SAM_CONFIG     ?= ../samconfig.toml
LAMBDA_STACK   ?= $(or $(shell grep "stack_name" $(SAM_CONFIG) 2>/dev/null | head -1 | cut -d'=' -f2 | tr -d ' "'),$(STACK))
BASE_DOMAIN    ?= planttracer.com
STATUS_URL     := https://$(LAMBDA_STACK)-lambda.$(BASE_DOMAIN)/status

export PYTHONDONTWRITEBYTECODE=1
export AWS_PROFILE
export AWS_REGION

.PHONY: install vend-app lint pytest test
install: .venv/pyvenv.cfg

.venv/pyvenv.cfg: pyproject.toml Makefile
	poetry config virtualenvs.in-project true
	poetry install
	npm install -g browser-sync

src/requirements.txt: pyproject.toml Makefile .venv/pyvenv.cfg
	poetry export -f requirements.txt --only main --without-hashes --output src/requirements.txt

.PHONY: vend-app
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

# AWS Lambda Vend, Build and Deploy (VBD)
prod-vbd: template.yaml samconfig.toml src/requirements.txt
	make lint
	make vend-app
	sam validate --lint
	sam build --parallel --use-container
	sam deploy --no-confirm-changeset
	$(MAKE) sam-status

# Show function name
functions:
	@aws cloudformation describe-stacks --stack-name $(STACK) --region $(REGION) --profile $(PROFILE) \
		--query 'Stacks[0].Outputs[?OutputKey==`ResizeFunction`].OutputValue' --output text 2>/dev/null || echo "Stack not found"

# Tail Lambda CloudWatch logs (production)
prod-tail: sam-logs

sam-logs:
	@echo "Tailing Lambda logs (stack=$(STACK))..."
	@aws logs tail "/aws/lambda/$$(aws cloudformation describe-stacks --stack-name $(STACK) --region $(REGION) --profile $(PROFILE) \
		--query 'Stacks[0].Outputs[?OutputKey==`ResizeFunction`].OutputValue' --output text)" \
		--since 15m --follow --region $(REGION) --profile $(PROFILE)

# Check Lambda status (after deploy). Expects 200 and status_message in JSON.
# URL = https://$(LAMBDA_STACK)-lambda.$(BASE_DOMAIN)/status (e.g. simson2-lambda.planttracer.com)
# Use curl -s (no -f) so we capture and show the body on 4xx/5xx.
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

# Download deployed Lambda package for inspection
fetch-zip-prod:
	@FUNC=$$(aws cloudformation describe-stacks \
		--stack-name $(STACK) \
		--region $(REGION) \
		--profile $(PROFILE) \
		--query 'Stacks[0].Outputs[?OutputKey==`ResizeFunction`].OutputValue' \
		--output text); \
	echo "Fetching deployment package for $$FUNC..."; \
	URL=$$(aws lambda get-function --function-name $$FUNC \
		--region $(REGION) \
		--profile $(PROFILE) \
		--query 'Code.Location' --output text); \
	/bin/rm -f lambda.zip && curl -sSL $$URL -o lambda.zip && ls -l lambda.zip && \
	echo "Deployed package extracted to lambda-package-prod/"

clean:
	/bin/rm -rf .venv
	/bin/rm -rf .aws-sam/build

# Show deployment info
info:
	@echo "Stack: $(STACK)"
	@echo "Region: $(REGION)"
	@echo "Profile: $(PROFILE)"
	@echo "Status URL: $(STATUS_URL) (override: make sam-status LAMBDA_STACK=simson2)"
	@echo "  make prod-vbd    - Build and deploy"
	@echo "  make sam-logs   - Tail Lambda CloudWatch logs"
	@echo "  make sam-status - Curl /status (uses LAMBDA_STACK=$(LAMBDA_STACK))"


#
# Development is done with browser-sync

run:
	browser-sync start --server --files "*.html, *.css, *.js"

run-proxy-local:
	@echo useful for injecting into a proxy running
	(cd src/sync; browser-sync start --proxy "localhost:5000" --files "*.html, *.css, *.js")


run-proxy-app:
	@echo useful for injecting into a proxy running
	(cd src/sync; browser-sync start --proxy "localhost:5000" --files "*.html, *.css, *.js")
