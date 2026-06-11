PY ?= python3
VENV ?= .venv
PIP := $(VENV)/bin/pip
PYBIN := $(VENV)/bin/python

.PHONY: all venv install install-ml test lint clean run-fetch run-detect run-full

all: install

$(VENV)/bin/activate:
	$(PY) -m venv $(VENV)
	$(PIP) install -U pip wheel

venv: $(VENV)/bin/activate

install: venv
	$(PIP) install -e .[dev]

install-ml: venv
	$(PIP) install -e .[dev,ml]

test:
	$(PYBIN) -m pytest

lint:
	$(VENV)/bin/ruff check src tests

clean:
	rm -rf build dist *.egg-info .pytest_cache .ruff_cache $(VENV)
	find . -name __pycache__ -type d -exec rm -rf {} +

run-fetch:
	$(PYBIN) -m planetar_sat fetch --aoi salish-sea --days 3

run-detect:
	$(PYBIN) -m planetar_sat detect --input data/scenes/*.tif

run-full:
	$(PYBIN) -m planetar_sat run --aoi salish-sea --days 3 --broker 127.0.0.1:12001
