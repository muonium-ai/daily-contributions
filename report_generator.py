import os
import re
import sqlite3
import subprocess

from datetime import date

from constants import DB_PATH, REPOS_FILE, EMAILS_FILE

def read_lines(path):
  with open(path) as f:
    return [l.strip() for l in f if l.strip()]


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
  print("=== Daily contributions ===")
  conn = sqlite3.connect(DB_PATH)
  cur = conn.cursor()

  cur.execute("""
    SELECT date, additions, deletions, net, files_touched, churn
    FROM daily_loc
    ORDER BY date
  """)

  rows = cur.fetchall()
  if not rows:
    print("(no daily data found)")
    conn.close()
    return

  for date, add, delete, net, files_touched, churn in rows:
    print(
      f"{date} | +{add} / -{delete} | net {net} | files {files_touched} | churn {churn}"
    )

  conn.close()


def get_non_zero_day_averages():
  conn = sqlite3.connect(DB_PATH)
  cur = conn.cursor()

  cur.execute("""
    SELECT additions, deletions, net, files_touched, churn
    FROM daily_loc
    ORDER BY date
  """)

  rows = cur.fetchall()
  conn.close()

  if not rows:
    return 0, 0.0, 0.0, 0.0, 0.0, 0.0

  non_zero_days = 0
  non_zero_add = 0
  non_zero_del = 0
  non_zero_net = 0
  non_zero_files = 0
  non_zero_churn = 0
  for add, delete, net, files_touched, churn in rows:
    if (add + delete) > 0:
      non_zero_days += 1
      non_zero_add += add
      non_zero_del += delete
      non_zero_net += net
      non_zero_files += files_touched
      non_zero_churn += churn

  if non_zero_days == 0:
    return 0, 0.0, 0.0, 0.0, 0.0, 0.0

  avg_add = non_zero_add / non_zero_days
  avg_del = non_zero_del / non_zero_days
  avg_net = non_zero_net / non_zero_days
  avg_files = non_zero_files / non_zero_days
  avg_churn = non_zero_churn / non_zero_days

  return non_zero_days, avg_add, avg_del, avg_net, avg_files, avg_churn


def print_repo_summary():
  repos = read_lines(REPOS_FILE)
  author_regex = get_author_regex()

  print("\n=== Per-repo summary (author-filtered) ===")
  unknown_url_repos = []
  repo_count = 0
  total_commits = 0
  total_additions = 0
  total_deletions = 0
  for repo in repos:
    if not os.path.isdir(os.path.join(repo, ".git")):
      continue
    repo_count += 1
    created = get_repo_created_date(repo)
    repo_url = get_repo_url(repo)
    if not repo_url:
      unknown_url_repos.append(repo)
    commits, additions, deletions, net = get_repo_author_stats(repo, author_regex)
    try:
      total_commits += int(commits)
    except ValueError:
      pass
    total_additions += additions
    total_deletions += deletions
    name = os.path.basename(repo.rstrip(os.sep))
    print(
      f"""
repo: {name}
  path: {repo}
  url: {repo_url or 'unknown'}
  created: {created or 'unknown'}
  commits: {commits}
  additions: {additions}
  deletions: {deletions}
  net: {net}
""".strip()
    )

  print("\n=== Repos with unknown URL ===")
  if not unknown_url_repos:
    print("(none)")
  for repo in unknown_url_repos:
    print(f"- {repo}")

  print("\n=== Totals (author-filtered) ===")
  print(
    f"repos: {repo_count}\n"
    f"commits: {total_commits}\n"
    f"additions: {total_additions}\n"
    f"deletions: {total_deletions}\n"
    f"net: {total_additions - total_deletions}"
  )

  print("\n=== Non-zero days averages ===")
  days, avg_add, avg_del, avg_net, avg_files, avg_churn = get_non_zero_day_averages()
  if days == 0:
    print("(no non-zero days found)")
  else:
    avg_commits = total_commits / days if days else 0.0
    total_loc = total_additions + total_deletions
    churn_ratio = avg_churn / (avg_add + avg_del) * 100 if (avg_add + avg_del) > 0 else 0.0
    print(
      f"days: {days}\n"
      f"repos: {repo_count}\n"
      f"avg additions: {avg_add:.2f}\n"
      f"avg deletions: {avg_del:.2f}\n"
      f"avg net: {avg_net:.2f}\n"
      f"avg commits: {avg_commits:.2f}\n"
      f"avg files touched: {avg_files:.2f}\n"
      f"avg churn: {avg_churn:.2f}\n"
      f"churn ratio: {churn_ratio:.1f}%"
    )


def classify_activity(last_commit_date):
  if not last_commit_date:
    return "dormant"
  last = date.fromisoformat(last_commit_date[:10])
  days = (date.today() - last).days
  if days <= 7:
    return "active"
  elif days <= 30:
    return "stale"
  elif days <= 90:
    return "inactive"
  else:
    return "dormant"


def print_module_timeline():
  conn = sqlite3.connect(DB_PATH)
  cur = conn.cursor()

  cur.execute("""
    SELECT name, url, created_date, last_commit_date
    FROM repos
    WHERE created_date IS NOT NULL
    ORDER BY created_date
  """)
  rows = cur.fetchall()
  conn.close()

  if not rows:
    print("\n=== Module Growth Timeline ===")
    print("(no repo metadata found \u2014 run index first)")
    return

  print("\n=== Module Growth Timeline ===")
  status_counts = {"active": 0, "stale": 0, "inactive": 0, "dormant": 0}
  for name, url, created, last_commit in rows:
    date_part = created[:10] if created else "unknown"
    status = classify_activity(last_commit)
    status_counts[status] += 1
    print(f"{date_part}  {name:<30} {url or 'unknown':<55} [{status}]")

  print("\n=== Cumulative Module Count ===")
  monthly = {}
  for _, _, created, _ in rows:
    if created:
      month = created[:7]
      monthly[month] = monthly.get(month, 0) + 1

  cumulative = 0
  for month in sorted(monthly):
    cumulative += monthly[month]
    print(f"{month}: {cumulative} modules")

  total = sum(status_counts.values())
  print("\n=== Repo Activity Summary ===")
  print(
    f"active (\u22647 days):     {status_counts['active']}\n"
    f"stale (8-30 days):    {status_counts['stale']}\n"
    f"inactive (31-90 days): {status_counts['inactive']}\n"
    f"dormant (>90 days):   {status_counts['dormant']}\n"
    f"total: {total}"
  )


if __name__ == "__main__":
  print_daily_report()
  print_repo_summary()
  print_module_timeline()
