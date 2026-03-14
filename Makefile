.PHONY: all repos index report clean backup

DATE := $(shell date +%Y-%m-%d)
REPORT_FILE := reports/$(DATE).txt

all: report

repos:
	uv run find_git_repos.py $(ROOT_DIR)

index:
	@if [ ! -f config/repos.txt ]; then \
		echo "Error: config/repos.txt not found."; \
		echo "Run: uv run find_git_repos.py <folder>"; \
		exit 1; \
	fi
	uv run index_loc.py

report: index
	@mkdir -p reports
	uv run report_generator.py | tee $(REPORT_FILE)

clean:
	@rm -f data/contributions.db

backup:
	@mkdir -p data/backup
	@cp data/contributions.db data/backup/contributions-$(DATE).db
