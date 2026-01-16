import os
import re
import sqlite3
import subprocess

REPOS_FILE = "config/repos.txt"
EMAILS_FILE = "config/emails.txt"

DB_PATH = "data/contributions.db"

def read_lines(path):
  return [l.strip() for l in open(path) if l.strip()]


def get_author_regex():
  emails = read_lines(EMAILS_FILE)
  return "|".join(re.escape(email) for email in emails)


def run_cmd(cmd, cwd=None):
  result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
  if result.returncode != 0:
    return ""
  return result.stdout.strip()


def get_repo_created_date(repo):
  return run_cmd(
    ["git", "log", "--reverse", "-n", "1", "--pretty=format:%ad", "--date=iso-strict"],
    cwd=repo,
  )


def get_repo_url(repo):
  return run_cmd(["git", "config", "--get", "remote.origin.url"], cwd=repo)


def get_repo_author_stats(repo, author_regex):
  commit_count = run_cmd(
    [
      "git",
      "rev-list",
      "--count",
      "--author=" + author_regex,
      "--extended-regexp",
      "--regexp-ignore-case",
      "HEAD",
    ],
    cwd=repo,
  )

  numstat = run_cmd(
    [
      "git",
      "log",
      "--numstat",
      "--pretty=tformat:",
      "--author=" + author_regex,
      "--extended-regexp",
      "--regexp-ignore-case",
    ],
    cwd=repo,
  )

  additions = 0
  deletions = 0
  for line in numstat.splitlines():
    parts = line.split("\t")
    if len(parts) >= 2:
      try:
        additions += int(parts[0])
        deletions += int(parts[1])
      except ValueError:
        pass

  return commit_count or "0", additions, deletions, additions - deletions


def print_daily_report():
  conn = sqlite3.connect(DB_PATH)
  cur = conn.cursor()

  cur.execute("""
    SELECT date, additions, deletions, net
    FROM daily_loc
    ORDER BY date
  """)

  for date, add, delete, net in cur.fetchall():
    print(f"""
date: {date}
  additions: {add}
  deletions: {delete}
  net: {net}
""".strip())

  conn.close()


def print_repo_summary():
  repos = read_lines(REPOS_FILE)
  author_regex = get_author_regex()

  print("\n=== Per-repo summary (author-filtered) ===")
  for repo in repos:
    if not os.path.isdir(os.path.join(repo, ".git")):
      continue
    created = get_repo_created_date(repo)
    repo_url = get_repo_url(repo)
    commits, additions, deletions, net = get_repo_author_stats(repo, author_regex)
    name = os.path.basename(repo.rstrip(os.sep))
    print(f"""
repo: {name}
  path: {repo}
  url: {repo_url or 'unknown'}
  created: {created or 'unknown'}
  commits: {commits}
  additions: {additions}
  deletions: {deletions}
  net: {net}
""".strip())


if __name__ == "__main__":
  print_daily_report()
  print_repo_summary()
