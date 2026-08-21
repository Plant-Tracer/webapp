PYTHON ?= python3
HTTP_HOST ?= 127.0.0.1
HTTP_PORT ?= 8765
JS_FILES := $(filter-out jquery-3.7.1.min.js mp4box.all.js %.min.js,$(wildcard *.js))

eslint:
	npx eslint --no-ignore --fix --config eslint.config $(JS_FILES)

serve:
	$(PYTHON) -m http.server $(HTTP_PORT) --bind $(HTTP_HOST)
