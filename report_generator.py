import sqlite3

DB_PATH = "data/contributions.db"

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
