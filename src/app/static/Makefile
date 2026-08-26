PYTHON ?= python3
HTTP_HOST ?= 127.0.0.1
HTTP_PORT ?= 8765
VENDORED_JS := jquery-3.7.1.min.js mp4box.all.js %.min.js unzipit-worker.module.mjs unzipit.module.mjs rolldown-runtime-%.mjs styp-%.mjs
ESLINT_FILES := $(filter-out $(VENDORED_JS),$(wildcard *.js *.mjs))

eslint:
	npx eslint --no-ignore --fix --config eslint.config.js $(ESLINT_FILES)

serve:
	$(PYTHON) -m http.server $(HTTP_PORT) --bind $(HTTP_HOST)
