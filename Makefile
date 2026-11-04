.PHONY: setup test demo sandbox
PY ?= python3

setup:           ## create .venv and install the app with dev + ai extras
	$(PY) -m venv .venv && .venv/bin/pip install -q -e ".[dev,ai]"

test:            ## run the test suite (offline, mock PayPal)
	.venv/bin/python -m pytest -q

demo:            ## run the desk in mock mode on http://127.0.0.1:8077
	MOCK=1 .venv/bin/uvicorn navigator_till.app:app --host 127.0.0.1 --port 8077

sandbox:         ## run against the PayPal sandbox (needs PAYPAL_CLIENT_ID / PAYPAL_SECRET in the environment)
	MOCK=0 .venv/bin/uvicorn navigator_till.app:app --host 127.0.0.1 --port 8077
