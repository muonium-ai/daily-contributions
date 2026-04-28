"""Discover and safely clean up git worktrees across tracked repos.

The tool defaults to dry-run. It will only modify filesystem state when
``--apply`` is passed, and even then it refuses to remove worktrees with
uncommitted changes unless ``--force`` is also given.
"""

from __future__ import annotations

import argparse
import fnmatch
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

REPOS_FILE = "config/repos.txt"


@dataclass
class Worktree:
    path: str
    head: str | None = None
    branch: str | None = None
    is_bare: bool = False
    is_detached: bool = False
    is_prunable: bool = False
    is_primary: bool = False


@dataclass
class Classification:
    stale: list[Worktree] = field(default_factory=list)
    prunable: list[Worktree] = field(default_factory=list)
    merged: list[Worktree] = field(default_factory=list)
    dirty: list[Worktree] = field(default_factory=list)
    primary: list[Worktree] = field(default_factory=list)
    unknown: list[Worktree] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def parse_porcelain(text: str) -> list[Worktree]:
    """Parse the output of ``git worktree list --porcelain``.

    Blocks are separated by blank lines. The first block is the primary
    worktree. Each block starts with ``worktree <path>`` and may include
    ``HEAD <sha>``, ``branch <ref>``, ``bare``, ``detached``,
    ``prunable [<reason>]`` and other keys we ignore (e.g. ``locked``).
    """

    worktrees: list[Worktree] = []
    current: Worktree | None = None
    is_first = True

    # Normalize line endings and split on blank lines while keeping order.
    lines = text.replace("\r\n", "\n").split("\n")

    def finalize(wt: Worktree | None, first: bool) -> None:
        if wt is None:
            return
        if first and not worktrees:
            wt.is_primary = True
        worktrees.append(wt)

    for raw in lines:
        line = raw.strip()
        if not line:
            if current is not None:
                finalize(current, is_first)
                is_first = False
                current = None
            continue

        # First token is the key; rest is the value.
        key, _, value = line.partition(" ")

        if key == "worktree":
            # If there is a previous block without a trailing blank line,
            # finalize it before starting a new one.
            if current is not None:
                finalize(current, is_first)
                is_first = False
            current = Worktree(path=value)
            continue

        if current is None:
            # Garbage before the first ``worktree`` key — skip silently.
            continue

        if key == "HEAD":
            current.head = value or None
        elif key == "branch":
            current.branch = value or None
        elif key == "bare":
            current.is_bare = True
        elif key == "detached":
            current.is_detached = True
        elif key == "prunable":
            current.is_prunable = True
        # Other keys (``locked``) are ignored.

    if current is not None:
        finalize(current, is_first)

    return worktrees


# ---------------------------------------------------------------------------
# Subprocess helpers
# ---------------------------------------------------------------------------


def _run_git(
    args: list[str],
    cwd: Path | str | None = None,
    check: bool = False,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd) if cwd is not None else None,
        capture_output=True,
        text=True,
        check=check,
    )


def list_worktrees(repo_path: Path) -> list[Worktree]:
    """Run ``git -C <repo> worktree list --porcelain`` and parse the output."""

    result = _run_git(["worktree", "list", "--porcelain"], cwd=repo_path)
    if result.returncode != 0:
        return []
    return parse_porcelain(result.stdout)


def detect_default_branch(repo_path: Path) -> str | None:
    """Best-effort default branch detection.

    Tries ``git symbolic-ref refs/remotes/origin/HEAD`` first, then falls
    back to ``main`` and ``master`` (only if they actually exist as refs).
    Returns ``None`` if none resolve.
    """

    result = _run_git(
        ["symbolic-ref", "--short", "refs/remotes/origin/HEAD"],
        cwd=repo_path,
    )
    if result.returncode == 0 and result.stdout.strip():
        ref = result.stdout.strip()
        # symbolic-ref gives e.g. ``origin/main`` — strip the remote prefix.
        if ref.startswith("origin/"):
            return ref[len("origin/") :]
        return ref

    for candidate in ("main", "master"):
        check = _run_git(
            ["rev-parse", "--verify", "--quiet", f"refs/heads/{candidate}"],
            cwd=repo_path,
        )
        if check.returncode == 0:
            return candidate

    return None


def _merged_branches(repo_path: Path, default_branch: str) -> set[str]:
    result = _run_git(["branch", "--merged", default_branch], cwd=repo_path)
    if result.returncode != 0:
        return set()
    merged: set[str] = set()
    for line in result.stdout.splitlines():
        name = line.strip()
        if not name:
            continue
        # Strip the ``*`` marker for the current branch.
        if name.startswith("*"):
            name = name[1:].strip()
        # Skip detached-HEAD lines like ``(HEAD detached at abc123)``.
        if name.startswith("("):
            continue
        merged.add(name)
    return merged


def _is_dirty(worktree_path: Path) -> bool:
    result = _run_git(["status", "--porcelain"], cwd=worktree_path)
    if result.returncode != 0:
        # Be conservative: if we cannot probe the worktree, treat it as dirty
        # so we never silently delete it.
        return True
    return bool(result.stdout.strip())


def _branch_short(ref: str | None) -> str | None:
    if not ref:
        return None
    if ref.startswith("refs/heads/"):
        return ref[len("refs/heads/") :]
    return ref


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


def classify_worktrees(
    worktrees: list[Worktree],
    repo_path: Path,
    default_branch: str | None,
    *,
    path_exists: Callable[[str], bool] | None = None,
    merged_branches: Iterable[str] | None = None,
    is_dirty: Callable[[str], bool] | None = None,
) -> Classification:
    """Bucket each worktree into zero-or-more cleanup categories.

    The git-touching probes (``path_exists``, ``merged_branches``,
    ``is_dirty``) are injected so this function is fully testable without
    running git or touching the real filesystem. When called from the CLI
    they default to real implementations.
    """

    if path_exists is None:

        def path_exists(p: str) -> bool:
            return Path(p).exists()

    if is_dirty is None:

        def is_dirty(p: str) -> bool:
            return _is_dirty(Path(p))

    if merged_branches is None:
        merged_set: set[str] = (
            _merged_branches(repo_path, default_branch) if default_branch else set()
        )
    else:
        merged_set = set(merged_branches)

    result = Classification()

    for wt in worktrees:
        if wt.is_primary:
            result.primary.append(wt)
            # Primary is also tracked but never cleaned; do not bucket it
            # into other categories that could imply removal.
            continue

        bucketed = False

        if wt.is_prunable:
            result.prunable.append(wt)
            bucketed = True

        if not path_exists(wt.path):
            result.stale.append(wt)
            bucketed = True

        branch_short = _branch_short(wt.branch)
        if (
            default_branch is not None
            and branch_short
            and branch_short != default_branch
            and branch_short in merged_set
        ):
            result.merged.append(wt)
            bucketed = True

        # Only probe dirtiness if the path still exists.
        if path_exists(wt.path) and is_dirty(wt.path):
            result.dirty.append(wt)
            bucketed = True

        if not bucketed:
            # E.g. detached HEAD with no branch, or a healthy linked worktree
            # we have no opinion about.
            if wt.is_detached or wt.branch is None:
                result.unknown.append(wt)
            # Otherwise it's a clean, present, non-merged worktree — leave it
            # out of every cleanup bucket entirely.

    return result


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------


def _select_targets(
    classification: Classification,
    *,
    prune_stale: bool,
    remove_merged: bool,
    match: str | None,
    all_worktrees: list[Worktree],
) -> list[tuple[Worktree, list[str]]]:
    """Pick worktrees that match any active selector. Returns
    ``(worktree, reasons)`` pairs, never including the primary.
    """

    selected: dict[str, tuple[Worktree, list[str]]] = {}

    def add(wt: Worktree, reason: str) -> None:
        if wt.is_primary:
            return
        existing = selected.get(wt.path)
        if existing is None:
            selected[wt.path] = (wt, [reason])
        elif reason not in existing[1]:
            existing[1].append(reason)

    if prune_stale:
        for wt in classification.stale:
            add(wt, "stale")
        for wt in classification.prunable:
            add(wt, "prunable")

    if remove_merged:
        for wt in classification.merged:
            add(wt, "merged")

    if match:
        for wt in all_worktrees:
            if wt.is_primary:
                continue
            if fnmatch.fnmatch(wt.path, match):
                add(wt, f"match:{match}")

    # Preserve the original worktree ordering for stable output.
    ordered: list[tuple[Worktree, list[str]]] = []
    for wt in all_worktrees:
        if wt.path in selected:
            ordered.append(selected[wt.path])
    return ordered


def cleanup_worktrees(
    repo_path: Path,
    worktrees: list[Worktree],
    classification: Classification,
    *,
    apply: bool,
    force: bool,
    prune_stale: bool,
    remove_merged: bool,
    match: str | None,
    output: Callable[[str], None] | None = None,
) -> dict[str, list[str]]:
    """Remove worktrees according to the active selectors.

    When ``apply`` is False this is a pure report — the function never
    touches the filesystem. When ``apply`` is True it runs
    ``git worktree remove`` per target and finishes with a single
    ``git worktree prune`` for the repo. Dirty worktrees require ``--force``.
    Primary worktrees are never removed.

    Returns a dict with keys ``removed``, ``would_remove``, ``skipped``.
    """

    if output is None:

        def output(msg: str) -> None:
            print(msg)

    targets = _select_targets(
        classification,
        prune_stale=prune_stale,
        remove_merged=remove_merged,
        match=match,
        all_worktrees=worktrees,
    )

    dirty_paths = {wt.path for wt in classification.dirty}
    summary: dict[str, list[str]] = {
        "removed": [],
        "would_remove": [],
        "skipped": [],
    }

    if not targets:
        return summary

    label = "Would remove" if not apply else "Removing"
    output(f"  {label} {len(targets)} worktree(s):")

    for wt, reasons in targets:
        reason_str = ",".join(reasons)
        is_dirty = wt.path in dirty_paths

        if is_dirty and not force:
            output(f"    - {wt.path} [{reason_str}] skipped (dirty, pass --force)")
            summary["skipped"].append(wt.path)
            continue

        if not apply:
            output(f"    - {wt.path} [{reason_str}]")
            summary["would_remove"].append(wt.path)
            continue

        remove_args = ["worktree", "remove"]
        if force or is_dirty:
            remove_args.append("--force")
        remove_args.append(wt.path)
        result = _run_git(remove_args, cwd=repo_path)
        if result.returncode == 0:
            output(f"    - {wt.path} [{reason_str}] removed")
            summary["removed"].append(wt.path)
        else:
            err = result.stderr.strip() or result.stdout.strip()
            output(f"    - {wt.path} [{reason_str}] FAILED: {err}")
            summary["skipped"].append(wt.path)

    if apply:
        prune = _run_git(["worktree", "prune"], cwd=repo_path)
        if prune.returncode != 0:
            err = prune.stderr.strip() or prune.stdout.strip()
            output(f"  worktree prune FAILED: {err}")

    return summary


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _read_repos_from_config(config_path: Path) -> list[Path]:
    if not config_path.exists():
        return []
    repos: list[Path] = []
    with config_path.open() as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            repos.append(Path(line).expanduser())
    return repos


def _print_repo_summary(
    repo_path: Path,
    worktrees: list[Worktree],
    classification: Classification,
    output: Callable[[str], None],
) -> None:
    output(f"\n== {repo_path} ==")
    output(f"  total worktrees: {len(worktrees)}")
    output(f"  stale (path missing): {len(classification.stale)}")
    output(f"  prunable: {len(classification.prunable)}")
    output(f"  on-merged-branch: {len(classification.merged)}")
    output(f"  with-uncommitted-changes: {len(classification.dirty)}")
    if classification.unknown:
        output(f"  unknown: {len(classification.unknown)}")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Discover git worktrees in tracked repos and offer safe cleanup. "
            "Defaults to dry-run; pass --apply to actually remove."
        ),
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "root",
        nargs="?",
        help="Path to a single git repository to scan.",
    )
    source.add_argument(
        "--from-config",
        action="store_true",
        help=f"Read repo paths from {REPOS_FILE} (one absolute path per line).",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually perform removals. Without this flag the tool is dry-run.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Allow removing worktrees that have uncommitted changes.",
    )
    parser.add_argument(
        "--prune-stale",
        action="store_true",
        help="Select worktrees whose path no longer exists, plus prunable worktrees.",
    )
    parser.add_argument(
        "--remove-merged",
        action="store_true",
        help="Select worktrees whose branch is merged into the default branch.",
    )
    parser.add_argument(
        "--match",
        metavar="GLOB",
        help="Select worktrees whose path matches the given glob (fnmatch).",
    )
    return parser


def _resolve_repos(args: argparse.Namespace) -> list[Path]:
    if args.from_config:
        repos = _read_repos_from_config(Path(REPOS_FILE))
        if not repos:
            print(f"No repos found in {REPOS_FILE} (file missing or empty).")
        return repos
    if args.root is None:
        return []
    return [Path(args.root).expanduser().resolve()]


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    repos = _resolve_repos(args)
    if not repos:
        return 1

    if not args.apply:
        print("(dry-run — no filesystem changes will be made; pass --apply to act)")

    any_failed = False
    for repo in repos:
        if not (repo / ".git").exists() and not repo.joinpath("HEAD").exists():
            # Allow non-existent paths in --from-config mode but report them.
            if not repo.exists():
                print(f"\n== {repo} ==\n  skipped (path missing)")
                any_failed = True
                continue

        worktrees = list_worktrees(repo)
        if not worktrees:
            print(f"\n== {repo} ==\n  skipped (not a git repo or no worktrees)")
            any_failed = True
            continue

        default_branch = detect_default_branch(repo)
        classification = classify_worktrees(worktrees, repo, default_branch)
        _print_repo_summary(repo, worktrees, classification, output=print)

        any_selector = args.prune_stale or args.remove_merged or bool(args.match)
        if any_selector:
            cleanup_worktrees(
                repo,
                worktrees,
                classification,
                apply=args.apply,
                force=args.force,
                prune_stale=args.prune_stale,
                remove_merged=args.remove_merged,
                match=args.match,
                output=print,
            )

    return 0 if not any_failed else 0  # report-style: missing repos don't fail the run


if __name__ == "__main__":
    raise SystemExit(main())
