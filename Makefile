# heat1d - build, test and quality gates.  Run `make help` for the list of targets.
# The CI pipeline calls the same targets, so a developer can reproduce any CI job locally.

UNAME_S := $(shell uname -s)
ifeq ($(origin CC),default)
CC      := gcc
endif
# Apple clang (what `gcc` is on macOS) has no OpenMP support out of the box: off by default there.
ifeq ($(UNAME_S),Darwin)
OPENMP  ?= 0
else
OPENMP  ?= 1
endif
SDKROOT := /Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk
OPT     ?= -O2
BUILD   := build
BIN     := $(BUILD)/heat1d

WARN    := -std=c11 -Wall -Wextra -Wpedantic -Werror
ifeq ($(OPENMP),1)
OMPFLAG := -fopenmp
endif
CFLAGS_ALL := $(OPT) $(WARN) $(OMPFLAG) $(CFLAGS) -isysroot $(SDKROOT)
LDLIBS  := -lm

.PHONY: all build test lint sanitize security coverage package reference clean help

all: build

build: $(BIN) ## Compile the solver (CC=gcc|clang, OPENMP=0|1)

$(BIN): src/heat1d.c
	mkdir -p $(BUILD)
	$(CC) $(CFLAGS_ALL) $< -o $@ $(LDLIBS)

test: build ## Run the test-suite on the optimised binary
	./scripts/run_tests.sh

sanitize: ## Run the test-suite on an ASan+UBSan build
	mkdir -p $(BUILD)
	$(CC) -O1 -g -fno-omit-frame-pointer -fsanitize=address,undefined -fno-sanitize-recover=undefined \
		$(WARN) $(OMPFLAG) $(CFLAGS) -isysroot $(SDKROOT) src/heat1d.c -o $(BUILD)/heat1d-san $(LDLIBS)
	HEAT1D_BIN=$(BUILD)/heat1d-san ./scripts/run_tests.sh

lint: ## Static analysis and style: shellcheck, ruff, cppcheck
	shellcheck scripts/*.sh hpc/job.sbatch
	ruff check python tests
	ruff format --check python tests
	cppcheck --enable=warning,style,performance,portability --std=c11 --inline-suppr \
		--suppress=missingIncludeSystem --error-exitcode=1 -q src/

security: ## SAST (bandit), dependency audit (pip-audit), secrets (gitleaks)
	./scripts/security.sh

coverage: build ## Python coverage of the helper module
	HEAT1D_BIN=$(abspath $(BIN)) python3 -m pytest --cov=python --cov-report=term-missing

package: build ## Create dist/heat1d-<version>-<os>-<arch>.tar.gz (+ sha256)
	./scripts/package.sh

reference: build ## Regenerate the regression reference (review the diff!)
	./scripts/make_reference.sh

clean:
	rm -rf $(BUILD) dist .pytest_cache .ruff_cache .coverage

help: ## Show this help
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "%-10s %s\n", $$1, $$2}'