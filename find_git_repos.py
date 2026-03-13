import os

ROOT_DIR = os.path.expanduser("~/code/")   # ← CHANGE THIS
OUTPUT_FILE = "config/repos.txt"
IGNORE_FILE = "config/ignore_repos.txt"

def read_ignore_paths(path):
    if not os.path.exists(path):
        return []
    ignores = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if os.path.isabs(line) or line.startswith("~"):
                resolved = os.path.realpath(os.path.expanduser(line))
            else:
                resolved = os.path.realpath(os.path.join(ROOT_DIR, line))
            ignores.append(resolved)
    return ignores


def is_ignored(path, ignore_paths):
    path = os.path.realpath(path)
    for ignore_path in ignore_paths:
        if path == ignore_path or path.startswith(ignore_path + os.sep):
            return True
    return False


def main():
    git_repos = []
    ignore_paths = read_ignore_paths(IGNORE_FILE)

    for root, dirs, files in os.walk(ROOT_DIR):
        has_git = ".git" in dirs
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        if is_ignored(root, ignore_paths):
            dirs[:] = []
            continue
        if has_git:
            git_repos.append(root)

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)

    with open(OUTPUT_FILE, "w") as f:
        for repo in git_repos:
            f.write(repo + "\n")

    print(f"✅ Found {len(git_repos)} git repositories")
    print(f"📄 Saved to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()



