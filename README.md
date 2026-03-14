# daily-contributions

Track daily code contributions across all your git repos. Indexes LOC, commits, file churn, repo metadata, and ticket progress into a SQLite database and generates a single-page text report.

## Setup

```bash
# 1. Configure author email(s)
echo "you@example.com" > config/emails.txt

# 2. Set the start date for indexing
echo "2025-01-01" > config/start-date.txt

# 3. Discover git repos under a folder
uv run find_git_repos.py ~/code
```

## Usage

```bash
# Generate the full report (indexes + prints)
make

# Or run steps individually:
make repos ROOT_DIR=~/code   # discover repos → config/repos.txt
make index                   # index all repos into SQLite
make report                  # index + generate report

make clean                   # delete the database
make backup                  # snapshot the database
```

The report is saved to `reports/YYYY-MM-DD.txt`.

## What the report includes

| Section | Description |
|---------|-------------|
| **Daily contributions** | Per-day additions, deletions, net LOC, files touched, and churn |
| **Per-repo summary** | Each repo's URL, creation date, commits, additions, deletions, net (author-filtered) |
| **Totals** | Aggregate commits, additions, deletions, net across all repos |
| **Non-zero day averages** | Average additions, deletions, net, commits, files touched, churn, and churn ratio |
| **Module Growth Timeline** | Chronological list of repos with creation date, URL, and activity status (active/stale/inactive/dormant) |
| **Cumulative Module Count** | Monthly cumulative count of repos |
| **Repo Activity Summary** | Count of repos by activity status |
| **MuonTickets Summary** | Per-repo archived vs total ticket counts |
| **Ticket Completion** | Overall completion percentage across all repos using MuonTickets |
| **Unarchived Tickets** | Table of every open ticket: repo, ID, status, title |

## Project structure

```
find_git_repos.py      # Walk a directory tree to discover git repos
index_loc.py           # Index daily LOC and repo metadata into SQLite
report_generator.py    # Generate the full text report from the database
constants.py           # Shared config file paths
Makefile               # Build pipeline
config/                # emails.txt, repos.txt, start-date.txt
data/                  # contributions.db (SQLite)
reports/               # Generated daily reports
```
