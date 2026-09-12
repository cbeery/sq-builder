# Stan Quarterly. `just` isn't installed on the production Mac; make is.
# ISSUE defaults to the newest issue directory.
ISSUE ?=
PY := .venv/bin/python

.PHONY: help setup build watch preflight proof test clean distclean

help:
	@echo "make setup      create .venv and install sq"
	@echo "make build      render the print PDF into out/"
	@echo "make watch      rebuild on every save"
	@echo "make preflight  check before upload; non-zero exit on FAIL"
	@echo "make proof      render with crop marks, for screen only"
	@echo "make test       parser and paste-cleaner regression tests"
	@echo "make clean      drop generated files and proof/screen PDFs"
	@echo "make distclean  also empty out/ — refuses if it holds tracked PDFs"
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

# Never `rm -rf out`. In the content repo the print-ready PDFs are
# committed, and a reprint starts from knowing exactly which bytes
# went to Mixam. Only the regenerable scratch goes.
clean:
	rm -rf issues/*/generated
	rm -f out/*_proof.pdf out/*_screen.pdf

# Empties out/ outright, which is right here — the builder's out/ is pure
# scratch — and wrong in the content repo, where the print-ready PDFs are
# committed. The Makefile can't know which tree it was pointed at, so ask
# git: anything tracked under out/ means this is not a tree to wipe.
distclean: clean
	@if [ -n "$$(git ls-files out)" ]; then \
		echo "refusing: out/ holds tracked files — wipe it by hand if you mean it"; \
		exit 1; \
	fi
	rm -rf out
