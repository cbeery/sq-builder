# Stan Quarterly. `just` isn't installed on the production Mac; make is.
# ISSUE defaults to the newest issue directory.
ISSUE ?=
PY := .venv/bin/python

.PHONY: help setup build watch preflight proof test clean

help:
	@echo "make setup      create .venv and install sq"
	@echo "make build      render the print PDF into out/"
	@echo "make watch      rebuild on every save"
	@echo "make preflight  check before upload; non-zero exit on FAIL"
	@echo "make proof      render with crop marks, for screen only"
	@echo "make test       parser and paste-cleaner regression tests"
	@echo ""
	@echo "Pass an issue with ISSUE=2026-fall; default is the newest."

setup:
	python3 -m venv .venv
	$(PY) -m pip install --quiet --upgrade pip
	$(PY) -m pip install --quiet -e .
	@echo "macOS also needs: brew install pango gdk-pixbuf libffi"

build:
	$(PY) -m sq.cli build $(ISSUE)

watch:
	$(PY) -m sq.cli build $(ISSUE) --watch

preflight:
	$(PY) -m sq.cli preflight $(ISSUE)

proof:
	$(PY) -m sq.cli proof $(ISSUE)

test:
	$(PY) -m pytest -q

clean:
	rm -rf out issues/*/generated
