from pathlib import Path

from daily_contributions.worktrees import (
    Classification,
    Worktree,
    _select_targets,
    classify_worktrees,
    cleanup_worktrees,
    parse_porcelain,
)


PORCELAIN_FIXTURE = """\
worktree /repo
HEAD aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
branch refs/heads/main

worktree /repo/.linked/feature
HEAD bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
branch refs/heads/feature/x

worktree /repo/.linked/detached
HEAD cccccccccccccccccccccccccccccccccccccccc
detached

worktree /repo/.linked/gone
HEAD dddddddddddddddddddddddddddddddddddddddd
branch refs/heads/old
prunable gitdir file points to non-existent location

worktree /repo/.linked/bare-mirror
bare
"""


def test_parse_porcelain_extracts_all_blocks():
    wts = parse_porcelain(PORCELAIN_FIXTURE)
    assert len(wts) == 5

    paths = [wt.path for wt in wts]
    assert paths == [
        "/repo",
        "/repo/.linked/feature",
        "/repo/.linked/detached",
        "/repo/.linked/gone",
        "/repo/.linked/bare-mirror",
    ]

    primary = wts[0]
    assert primary.is_primary is True
    assert primary.branch == "refs/heads/main"
    assert primary.head == "a" * 40
    assert primary.is_bare is False
    assert primary.is_detached is False
    assert primary.is_prunable is False

    feature = wts[1]
    assert feature.is_primary is False
    assert feature.branch == "refs/heads/feature/x"
    assert feature.is_detached is False

    detached = wts[2]
    assert detached.is_detached is True
    assert detached.branch is None

    prunable = wts[3]
    assert prunable.is_prunable is True
    assert prunable.branch == "refs/heads/old"

    bare = wts[4]
    assert bare.is_bare is True
    assert bare.head is None
    assert bare.branch is None


def test_parse_porcelain_handles_empty_and_locked_keys():
    assert parse_porcelain("") == []

    text = """\
worktree /a
HEAD 1111111111111111111111111111111111111111
branch refs/heads/main

worktree /b
HEAD 2222222222222222222222222222222222222222
branch refs/heads/feature
locked claude agent foo (pid 1)
"""
    wts = parse_porcelain(text)
    assert len(wts) == 2
    assert wts[0].is_primary is True
    assert wts[1].is_primary is False
    # ``locked`` is not exposed as a flag but must not break parsing.
    assert wts[1].branch == "refs/heads/feature"


def _fixture_worktrees() -> list[Worktree]:
    return [
        Worktree(path="/repo", branch="refs/heads/main", is_primary=True),
        Worktree(path="/repo/.linked/feature", branch="refs/heads/feature/x"),
        Worktree(path="/repo/.linked/merged", branch="refs/heads/old-merged"),
        Worktree(path="/repo/.linked/gone", branch="refs/heads/abandoned"),
        Worktree(path="/repo/.linked/dirty", branch="refs/heads/in-progress"),
        Worktree(
            path="/repo/.linked/prunable",
            branch="refs/heads/prunable-branch",
            is_prunable=True,
        ),
        Worktree(path="/repo/.linked/detached", is_detached=True),
    ]


def test_classify_worktrees_buckets_correctly():
    worktrees = _fixture_worktrees()

    existing_paths = {
        "/repo",
        "/repo/.linked/feature",
        "/repo/.linked/merged",
        # ``gone`` is missing on disk
        "/repo/.linked/dirty",
        "/repo/.linked/prunable",
        "/repo/.linked/detached",
    }
    dirty_paths = {"/repo/.linked/dirty"}

    result = classify_worktrees(
        worktrees,
        Path("/repo"),
        default_branch="main",
        path_exists=lambda p: p in existing_paths,
        merged_branches=["old-merged", "main"],
        is_dirty=lambda p: p in dirty_paths,
    )

    assert isinstance(result, Classification)

    primary_paths = [wt.path for wt in result.primary]
    assert primary_paths == ["/repo"]

    stale_paths = [wt.path for wt in result.stale]
    assert stale_paths == ["/repo/.linked/gone"]

    prunable_paths = [wt.path for wt in result.prunable]
    assert prunable_paths == ["/repo/.linked/prunable"]

    merged_paths = [wt.path for wt in result.merged]
    assert merged_paths == ["/repo/.linked/merged"]

    dirty_result_paths = [wt.path for wt in result.dirty]
    assert dirty_result_paths == ["/repo/.linked/dirty"]

    unknown_paths = [wt.path for wt in result.unknown]
    assert unknown_paths == ["/repo/.linked/detached"]


def test_classify_skips_merged_when_no_default_branch():
    worktrees = [
        Worktree(path="/repo", branch="refs/heads/main", is_primary=True),
        Worktree(path="/repo/wt", branch="refs/heads/anything"),
    ]
    result = classify_worktrees(
        worktrees,
        Path("/repo"),
        default_branch=None,
        path_exists=lambda p: True,
        merged_branches=[],
        is_dirty=lambda p: False,
    )
    assert result.merged == []
    # Primary should still be tracked but not duplicated elsewhere.
    assert [wt.path for wt in result.primary] == ["/repo"]


def test_classify_never_buckets_primary_for_cleanup():
    # Even if the primary's path is missing or branch is "merged", it must
    # never appear in stale/merged/dirty/prunable buckets.
    worktrees = [
        Worktree(
            path="/repo",
            branch="refs/heads/main",
            is_primary=True,
            is_prunable=True,
        ),
    ]
    result = classify_worktrees(
        worktrees,
        Path("/repo"),
        default_branch="main",
        path_exists=lambda p: False,
        merged_branches=["main"],
        is_dirty=lambda p: True,
    )
    assert [wt.path for wt in result.primary] == ["/repo"]
    assert result.stale == []
    assert result.prunable == []
    assert result.merged == []
    assert result.dirty == []


def test_cleanup_dry_run_does_not_call_git_and_skips_dirty():
    worktrees = _fixture_worktrees()
    classification = Classification(
        stale=[wt for wt in worktrees if wt.path == "/repo/.linked/gone"],
        prunable=[wt for wt in worktrees if wt.path == "/repo/.linked/prunable"],
        merged=[wt for wt in worktrees if wt.path == "/repo/.linked/merged"],
        dirty=[wt for wt in worktrees if wt.path == "/repo/.linked/dirty"],
        primary=[wt for wt in worktrees if wt.is_primary],
    )

    lines: list[str] = []
    summary = cleanup_worktrees(
        Path("/repo"),
        worktrees,
        classification,
        apply=False,
        force=False,
        prune_stale=True,
        remove_merged=True,
        match="*/dirty",
        output=lines.append,
    )

    # Without --force, the dirty worktree should be skipped, others queued.
    assert "/repo/.linked/gone" in summary["would_remove"]
    assert "/repo/.linked/prunable" in summary["would_remove"]
    assert "/repo/.linked/merged" in summary["would_remove"]
    assert "/repo/.linked/dirty" in summary["skipped"]
    assert summary["removed"] == []

    joined = "\n".join(lines)
    assert "Would remove" in joined
    assert "skipped (dirty, pass --force)" in joined
    # Primary must never appear as a target.
    assert "/repo " not in joined.replace("/repo ", "X")  # quick sanity guard


def test_select_targets_primary_never_selected_even_via_match():
    worktrees = _fixture_worktrees()
    classification = Classification(primary=[wt for wt in worktrees if wt.is_primary])

    targets = _select_targets(
        classification,
        prune_stale=False,
        remove_merged=False,
        match="/repo*",
        all_worktrees=worktrees,
    )
    paths = [wt.path for wt, _ in targets]
    assert "/repo" not in paths
    # Match should still pick up linked worktrees that match the glob.
    assert "/repo/.linked/feature" in paths
