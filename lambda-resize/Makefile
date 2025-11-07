# ===== resize_app Makefile =====
# lambda-resize is the minimal resize page.
STACK           ?= resize-app
STACK_STAGE     ?= resize-app-stage
CAPS            ?= CAPABILITY_IAM CAPABILITY_AUTO_EXPAND
REGION          ?= us-east-1
PROFILE         ?= planttracer
PYTHON          = python3.13
DJLINT_FLAGS ?= --profile=jinja --lint --quiet --ignore J004,J018
SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c

PRODUCTION_URL="https://app-resize.planttracer.com"
STAGE_URL="https://app-resize-stage.planttracer.com"

export PYTHONDONTWRITEBYTECODE=1

.PHONY: install vend-app lint pytest test
install: .venv/pyvenv.cfg

.venv/pyvenv.cfg: pyproject.toml Makefile
	poetry config virtualenvs.in-project true
	poetry install
	npm install -g browser-sync

src/requirements.txt: pyproject.toml Makefile .venv/pyvenv.cfg
	poetry export -f requirements.txt --output src/requirements.txt

.PHONY: vend-app
vend-app: Makefile
	rsync --verbose --archive ../deploy/app/*.py src/resize_app/deploy/app/

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
	echo make lint
	echo make vend-app
	sam validate --config-file samconfig.toml -t template.yaml --lint
	sam build --parallel --use-container --config-file samconfig.toml -t template.yaml
	sam deploy --config-file "$$(pwd)/samconfig.toml" --no-confirm-changeset -t .aws-sam/build/template.yaml
	curl --silent  https://app-resize.planttracer.com/ | head -3

stage-vbd: template-stage.yaml samconfig-stage.toml src/requirements.txt
	make lint
	make vend-app
	sam validate --config-file samconfig-stage.toml -t template-stage.yaml --lint
	sam build --parallel --use-container --config-file samconfig-stage.toml -t template-stage.yaml
	sam deploy --config-file "$$(pwd)/samconfig-stage.toml" --no-confirm-changeset -t .aws-sam/build/template.yaml
	curl --silent  https://stage.csci-e-11.org/ | head -3

# Show function names
functions:
	@echo "Production function:"
	@aws cloudformation describe-stacks --stack-name $(STACK) --region $(REGION) --profile $(PROFILE) \
		--query 'Stacks[0].Outputs[?OutputKey==`ResizeFunction`].OutputValue' --output text 2>/dev/null || echo "Stack not found"
	@echo "Stage function:"
	@aws cloudformation describe-stacks --stack-name $(STACK_STAGE) --region $(REGION) --profile $(PROFILE) \
		--query 'Stacks[0].Outputs[?OutputKey==`ResizeFunction`].OutputValue' --output text 2>/dev/null || echo "Stack not found"

# Tail logs
prod-tail:
	@echo "Tailing production logs..."
	@aws logs tail "/aws/lambda/$$(aws cloudformation describe-stacks --stack-name $(STACK) --region $(REGION) --profile $(PROFILE) \
		--query 'Stacks[0].Outputs[?OutputKey==`ResizeFunction`].OutputValue' --output text)" \
		--since 15m --follow --region $(REGION) --profile $(PROFILE)

# Tail stage logs (separate stack)
stage-tail:
	@echo "Tailing stage logs..."
	@aws logs tail "/aws/lambda/$$(aws cloudformation describe-stacks --stack-name $(STACK_STAGE) --region $(REGION) --profile $(PROFILE) \
		--query 'Stacks[0].Outputs[?OutputKey==`ResizeFunction`].OutputValue' --output text)" \
		--since 15m --follow --region $(REGION) --profile $(PROFILE)

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
	@echo "Production Stack: $(STACK)"
	@echo "Stage Stack: $(STACK_STAGE)"
	@echo "Region: $(REGION)"
	@echo "Profile: $(PROFILE)"
	@echo ""
	@echo "Environments:"
	@echo "  Production: $(PRODUCTION_URL)"
	@echo "  Stage:    $(STAGE_URL)"
	@echo ""
	@echo "Deployment Options:"
	@echo "  make deploy          - Deploy stage only (default)"
	@echo "  make deploy-prod     - Deploy production only"
	@echo "  make deploy-stage    - Deploy stage only (same as deploy)"
	@echo ""
	@echo "Template Management:"
	@echo "  make template.yaml     - Generate production template"
	@echo "  make template-stage.yaml - Generate stage template"
	@echo ""
	@echo "Debugging:"
	@echo "  make functions      - Show function names from stacks"
	@echo "  make tail           - Tail production logs"
	@echo "  make tail-stage     - Tail stage logs"


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
