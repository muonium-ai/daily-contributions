import subprocess


def run_cmd(cmd, cwd=None):
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def get_repo_url(repo):
    return run_cmd(["git", "config", "--get", "remote.origin.url"], cwd=repo)


def get_repo_created_date(repo):
    return run_cmd(
        ["git", "log", "--reverse", "-n", "1", "--pretty=format:%aI"],
        cwd=repo,
    )


def get_repo_last_commit_date(repo):
    return run_cmd(
        ["git", "log", "-n", "1", "--pretty=format:%aI"],
        cwd=repo,
    )
