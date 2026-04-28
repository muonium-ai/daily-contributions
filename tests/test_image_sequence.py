from pathlib import Path

from daily_contributions.image_sequence import (
    extract_frame_number,
    looks_like_sequence,
)


def test_extract_frame_number_simple():
    assert extract_frame_number("frame_0001.png") == 1


def test_extract_frame_number_multi_number_stem():
    assert extract_frame_number("shot01.0104.exr") == 104


def test_extract_frame_number_no_digits():
    assert extract_frame_number("background.png") is None


def test_looks_like_sequence_clearly_sequential():
    files = [Path(f"frame_{n:04d}.png") for n in range(1, 21)]
    is_seq, start, end = looks_like_sequence(files)
    assert is_seq is True
    assert start == 1
    assert end == 20


def test_looks_like_sequence_too_small():
    files = [Path(f"frame_{n:04d}.png") for n in range(1, 4)]
    is_seq, start, end = looks_like_sequence(files)
    assert is_seq is False
    assert start is None
    assert end is None


def test_looks_like_sequence_sparse_low_continuity():
    # 5 frames spread across 1..100 -> continuity_ratio = 5/100 = 0.05 < 0.7
    files = [Path(f"frame_{n:04d}.png") for n in (1, 25, 50, 75, 100)]
    is_seq, start, end = looks_like_sequence(files)
    assert is_seq is False
    assert start == 1
    assert end == 100
