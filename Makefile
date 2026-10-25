# Thin wrapper: all logic lives in scripts/tasks.py so it also works without make
# (e.g. `py scripts/tasks.py demo` on Windows).
ifeq ($(OS),Windows_NT)
  VENV_PY := .venv/Scripts/python.exe
  BOOT_PY := py
else
  VENV_PY := .venv/bin/python
  BOOT_PY := python3
endif
PY := $(if $(wildcard $(VENV_PY)),$(VENV_PY),$(BOOT_PY))

.PHONY: setup seed test lint eval web-build web-test demo dev clean

setup:      ; $(PY) scripts/tasks.py setup
seed:       ; $(PY) scripts/tasks.py seed
test:       ; $(PY) scripts/tasks.py test
lint:       ; $(PY) scripts/tasks.py lint
eval:       ; $(PY) scripts/tasks.py eval
web-build:  ; $(PY) scripts/tasks.py web-build
web-test:   ; $(PY) scripts/tasks.py web-test
demo:       ; $(PY) scripts/tasks.py demo
dev:        ; $(PY) scripts/tasks.py dev
clean:      ; $(PY) scripts/tasks.py clean
