# -----------------------------------------------------------------------------
# lambda-resize Makefile
# -----------------------------------------------------------------------------
# This directory holds the Lambda code that processes uploads (S3 -> move to
# final key, update DynamoDB, set MP4 metadata). The Lambda is deployed as part
# of the main webapp stack (see ../template.yaml), not as a separate stack.
#
# Deploy from the repo root:  make sam-build && make sam-deploy
#
# Dependencies and tooling: single pyproject.toml at repo root (group lambda).
# Install/lint/check run from root venv; sam-status and sam-logs delegate to root.
#
# This Makefile: vend-app, install (root install-lambda-deps + vend-app),
# lint/check (delegate to root), sam-status/sam-logs (delegate to root), clean.
# -----------------------------------------------------------------------------

SHELL               := /bin/bash
.SHELLFLAGS         := -eu -o pipefail -c

.PHONY: install vend-app lint check sam-logs sam-status clean info run run-proxy-local run-proxy-app

# --- Local dev and CI (use root venv; root has group lambda) ---
install:
	$(MAKE) -C .. install-lambda-deps
	$(MAKE) vend-app

vend-app: Makefile
	rsync --verbose --archive ../src/app/{odb,schema,constants,mp4_metadata_lib}.py src/resize_app/src/app/

lint:
	$(MAKE) -C .. lambda-resize-lint

check:
	$(MAKE) vend-app
	$(MAKE) -C .. lambda-resize-check

# --- Observability: delegate to root Makefile (single implementation) ---
sam-status:
	$(MAKE) -C .. sam-status

sam-logs:
	$(MAKE) -C .. sam-logs

# --- Clean and info ---
clean:
	/bin/rm -rf .venv
	/bin/rm -rf .aws-sam/build

info:
	@echo "Single pyproject at repo root (group lambda). install/lint/check/sam-status/sam-logs delegate to root."
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
