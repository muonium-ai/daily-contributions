.PHONY: all repos index report test format clean backup node-modules image-sequences worktrees

SHELL := bash
.SHELLFLAGS := -eo pipefail -c

DATE := $(shell date +%Y-%m-%d)
REPORT_FILE := reports/$(DATE).txt

all: report

repos:
	uv run tools/find_repos.py $(ROOT_DIR)

index:
	@if [ ! -f config/repos.txt ]; then \
		echo "Error: config/repos.txt not found."; \
		echo "Run: uv run tools/find_repos.py <folder>"; \
		exit 1; \
	fi
	uv run tools/index.py

report: index
	@mkdir -p reports
	uv run tools/report.py | tee $(REPORT_FILE)

test:
	uv run pytest tests/

format:
	uv run ruff format .

clean:
	@rm -f data/contributions.db

backup:
	@mkdir -p data/backup
	@cp data/contributions.db data/backup/contributions-$(DATE).db

node-modules:
	uv run tools/find_node_modules.py $(ROOT_DIR)

image-sequences:
	uv run tools/image_sequence_detection.py $(ROOT_DIR)

worktrees:
	uv run tools/clean_worktrees.py $(ROOT_DIR)
