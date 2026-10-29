PYTHON ?= python3
.PHONY: all build test
all: build test
build:
	$(PYTHON) scripts/build.py
test:
	$(PYTHON) scripts/verify_compatibility.py
