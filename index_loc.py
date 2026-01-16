import re
import subprocess
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

DB_PATH = "data/contributions.db"
REPOS_FILE = "config/repos.txt"
EMAILS_FILE = "config/emails.txt"
START_DATE_FILE = "config/start-date.txt"


def read_lines(path):
    return [l.strip() for l in open(path) if l.strip()]


def get_author_regex():
    emails = read_lines(EMAILS_FILE)
    return "|".join(re.escape(email) for email in emails)


def get_start_date(conn):
    cur = conn.cursor()
    cur.execute("SELECT MAX(date) FROM daily_loc")
    row = cur.fetchone()

    if row[0]:
        return datetime.fromisoformat(row[0]) + timedelta(days=1)

    return datetime.fromisoformat(read_lines(START_DATE_FILE)[0])


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
        "--pretty=tformat:"
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
        return 0, 0

    add, delete = 0, 0
    for line in result.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            try:
                add += int(parts[0])
                delete += int(parts[1])
            except ValueError:
                pass

    return add, delete


def init_db(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS daily_loc (
            date TEXT PRIMARY KEY,
            additions INTEGER NOT NULL,
            deletions INTEGER NOT NULL,
            net INTEGER NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    conn.commit()


def main():
    repos = read_lines(REPOS_FILE)
    author_regex = get_author_regex()

    conn = sqlite3.connect(DB_PATH)
    init_db(conn)

    start = get_start_date(conn)
    today = datetime.now().date()

    current = start
    while current.date() <= today:
        day = current.strftime("%Y-%m-%d")
        total_add, total_del = 0, 0

        for repo in repos:
            a, d = run_git_log(repo, day, author_regex)
            total_add += a
            total_del += d

        net = total_add - total_del

        conn.execute("""
            INSERT OR REPLACE INTO daily_loc
            (date, additions, deletions, net, updated_at)
            VALUES (?, ?, ?, ?, ?)
        """, (
            day,
            total_add,
            total_del,
            net,
            datetime.now(timezone.utc).isoformat()
        ))

        conn.commit()
        print(f"{day} → +{total_add} / -{total_del}")

        current += timedelta(days=1)

    conn.close()


if __name__ == "__main__":
    main()
