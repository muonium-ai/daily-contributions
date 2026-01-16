import os

ROOT_DIR = "~/code/"   # ← CHANGE THIS
OUTPUT_FILE = "config/repos.txt"

git_repos = []

for root, dirs, files in os.walk(ROOT_DIR):
    if ".git" in dirs:
        git_repos.append(root)
        dirs.remove(".git")  # prevent deep recursion

with open(OUTPUT_FILE, "w") as f:
    for repo in git_repos:
        f.write(repo + "\n")

print(f"✅ Found {len(git_repos)} git repositories")
print(f"📄 Saved to {OUTPUT_FILE}")



