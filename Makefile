.PHONY: all repos index report test clean backup

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
		echo "Run: uv run find_git_repos.py <folder>"; \
		exit 1; \
	fi
	uv run tools/index.py

report: index
	@mkdir -p reports
	uv run tools/report.py | tee $(REPORT_FILE)

test:
	uv run pytest tests/

clean:
	@rm -f data/contributions.db

backup:
	@mkdir -p data/backup
	@cp data/contributions.db data/backup/contributions-$(DATE).db
