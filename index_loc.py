import os
import re
import subprocess
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from constants import DB_PATH, REPOS_FILE, EMAILS_FILE, START_DATE_FILE
from git_utils import get_repo_url, get_repo_created_date, get_repo_last_commit_date


def read_lines(path):
    with open(path) as f:
        return [l.strip() for l in f if l.strip()]


def get_author_regex():
    emails = read_lines(EMAILS_FILE)
    return "|".join(re.escape(email) for email in emails)


def get_start_date(conn):
    cur = conn.cursor()
    cur.execute("SELECT MAX(date) FROM daily_loc")
    row = cur.fetchone()

    if row[0]:
        return datetime.fromisoformat(row[0])

    return datetime.fromisoformat(read_lines(START_DATE_FILE)[0])


def parse_numstat(stdout):
    add, delete, commits = 0, 0, 0
    files = set()
    for line in stdout.splitlines():
        parts = line.split("\t")
        if len(parts) >= 3:
            try:
                add += int(parts[0])
                delete += int(parts[1])
            except ValueError:
                pass
            files.add(parts[2])
        elif line:
            commits += 1

    return add, delete, commits, len(files)


def run_git_log(repo, day, author_regex):
    since = f"{day} 00:00:00"
    until = f"{day} 23:59:59"

    cmd = [
        "git", "log",
        f"--since={since}",
        f"--until={until}",
        f"--author={author_regex}",
        "--extended-regexp",
        "--regexp-ignore-case",
        "--numstat",
        "--pretty=format:%H"
    ]

    try:
        result = subprocess.run(
            cmd,
            cwd=repo,
            capture_output=True,
            text=True,
            check=True
        )
    except subprocess.CalledProcessError:
        return 0, 0, 0, 0

    return parse_numstat(result.stdout)


def init_db(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS daily_loc (
            date TEXT PRIMARY KEY,
            additions INTEGER NOT NULL,
            deletions INTEGER NOT NULL,
            commits INTEGER NOT NULL,
            net INTEGER NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS repos (
            name TEXT PRIMARY KEY,
            path TEXT NOT NULL,
            url TEXT,
            created_date TEXT,
            last_commit_date TEXT,
            updated_at TEXT NOT NULL
        )
    """)
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(daily_loc)")
    columns = {row[1] for row in cur.fetchall()}
    if "commits" not in columns:
        conn.execute("ALTER TABLE daily_loc ADD COLUMN commits INTEGER NOT NULL DEFAULT 0")
    if "files_touched" not in columns:
        conn.execute("ALTER TABLE daily_loc ADD COLUMN files_touched INTEGER NOT NULL DEFAULT 0")
    if "churn" not in columns:
        conn.execute("ALTER TABLE daily_loc ADD COLUMN churn INTEGER NOT NULL DEFAULT 0")
    cur.execute("PRAGMA table_info(repos)")
    repo_columns = {row[1] for row in cur.fetchall()}
    if "last_commit_date" not in repo_columns:
        conn.execute("ALTER TABLE repos ADD COLUMN last_commit_date TEXT")
    conn.commit()


def main():
    repos = read_lines(REPOS_FILE)
    author_regex = get_author_regex()

    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    init_db(conn)

    start = get_start_date(conn)
    today = datetime.now().date()

    current = start
    while current.date() <= today:
        day = current.strftime("%Y-%m-%d")
        total_add, total_del, total_commits, total_files = 0, 0, 0, 0

        for repo in repos:
            a, d, c, f = run_git_log(repo, day, author_regex)
            total_add += a
            total_del += d
            total_commits += c
            total_files += f

        net = total_add - total_del
        churn = min(total_add, total_del)

        conn.execute("""
            INSERT OR REPLACE INTO daily_loc
            (date, additions, deletions, commits, net, files_touched, churn, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            day,
            total_add,
            total_del,
            total_commits,
            net,
            total_files,
            churn,
            datetime.now(timezone.utc).isoformat()
        ))

        conn.commit()
        print(f"{day} → +{total_add} / -{total_del} | commits {total_commits} | files {total_files} | churn {churn}")

        current += timedelta(days=1)

    print("\nIndexing repo metadata...")
    for repo in repos:
        if not os.path.isdir(os.path.join(repo, ".git")):
            continue
        name = os.path.basename(repo.rstrip(os.sep))
        url = get_repo_url(repo)
        created = get_repo_created_date(repo)
        last_commit = get_repo_last_commit_date(repo)
        conn.execute("""
            INSERT OR REPLACE INTO repos (name, path, url, created_date, last_commit_date, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (name, repo, url or None, created or None, last_commit or None, datetime.now(timezone.utc).isoformat()))
    conn.commit()
    print("Done.")

    conn.close()


if __name__ == "__main__":
    main()
