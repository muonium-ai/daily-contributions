import os

from daily_contributions.report import get_unarchived_tickets


def _write_ticket(tmp_path, ticket_id, content):
    tickets_dir = tmp_path / "tickets"
    tickets_dir.mkdir(exist_ok=True)
    path = tickets_dir / f"{ticket_id}.md"
    path.write_text(content)
    return path


def test_well_formed_frontmatter(tmp_path):
    _write_ticket(
        tmp_path,
        "T-000001",
        "---\n"
        "id: T-000001\n"
        "title: \"Add tests\"\n"
        "status: ready\n"
        "---\n"
        "\n"
        "## Body\n",
    )
    results = get_unarchived_tickets(str(tmp_path))
    assert results == [("T-000001", "ready", "Add tests")]


def test_missing_title(tmp_path):
    _write_ticket(
        tmp_path,
        "T-000002",
        "---\n"
        "id: T-000002\n"
        "status: ready\n"
        "---\n"
        "\n"
        "## Body\n",
    )
    results = get_unarchived_tickets(str(tmp_path))
    assert results == [("T-000002", "ready", "")]


def test_missing_status(tmp_path):
    _write_ticket(
        tmp_path,
        "T-000003",
        "---\n"
        "id: T-000003\n"
        "title: \"Some title\"\n"
        "---\n"
        "\n"
        "## Body\n",
    )
    results = get_unarchived_tickets(str(tmp_path))
    assert results == [("T-000003", "", "Some title")]


def test_body_line_mimicking_frontmatter_keys(tmp_path):
    # Lines that look like `title:` / `status:` outside the frontmatter must NOT be picked up
    _write_ticket(
        tmp_path,
        "T-000004",
        "---\n"
        "id: T-000004\n"
        "title: \"Real title\"\n"
        "status: ready\n"
        "---\n"
        "\n"
        "## Acceptance\n"
        "title: not a real title\n"
        "status: not-a-real-status\n",
    )
    results = get_unarchived_tickets(str(tmp_path))
    assert results == [("T-000004", "ready", "Real title")]


def test_body_line_mimicking_keys_with_no_frontmatter_keys(tmp_path):
    # Frontmatter present but title/status missing; body has decoy lines
    # that must NOT be picked up
    _write_ticket(
        tmp_path,
        "T-000005",
        "---\n"
        "id: T-000005\n"
        "---\n"
        "\n"
        "## Body\n"
        "title: decoy\n"
        "status: decoy\n",
    )
    results = get_unarchived_tickets(str(tmp_path))
    assert results == [("T-000005", "", "")]


def test_no_frontmatter_at_all(tmp_path):
    # No `---` delimiters anywhere; body has lines that look like keys
    _write_ticket(
        tmp_path,
        "T-000006",
        "## Body only\n"
        "title: decoy\n"
        "status: decoy\n",
    )
    results = get_unarchived_tickets(str(tmp_path))
    assert results == [("T-000006", "", "")]


def test_directory_with_no_tickets_subfolder(tmp_path):
    # tmp_path has no tickets/ subdir at all
    assert get_unarchived_tickets(str(tmp_path)) == []
