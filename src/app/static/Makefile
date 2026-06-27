PYTHON ?= python3
HTTP_HOST ?= 127.0.0.1
HTTP_PORT ?= 8765

eslint:
	npx eslint --fix --config eslint.config *.js

serve:
	$(PYTHON) -m http.server $(HTTP_PORT) --bind $(HTTP_HOST)
