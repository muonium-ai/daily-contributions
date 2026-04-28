from index_loc import parse_numstat


def test_text_only_commit():
    assert parse_numstat("abc123\n10\t5\tfile.py\n") == (10, 5, 1, 1)


def test_binary_file():
    # binary rows have '-' in numeric columns; they shouldn't add to add/delete
    # but still count as a file touched
    assert parse_numstat("abc123\n-\t-\tfile.bin\n") == (0, 0, 1, 1)


def test_rename():
    assert parse_numstat("abc123\n1\t2\told => new\n") == (1, 2, 1, 1)


def test_commit_with_no_files():
    assert parse_numstat("abc123\n") == (0, 0, 1, 0)


def test_empty_input():
    assert parse_numstat("") == (0, 0, 0, 0)


def test_multiple_commits():
    assert parse_numstat("abc\n10\t5\ta.py\ndef\n3\t1\tb.py\n") == (13, 6, 2, 2)
