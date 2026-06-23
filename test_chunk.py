"""
Tests for the chunk_text() function.

Run with: uv run pytest test_chunk.py -v
"""
import pytest
from misc import chunk_text


# ── Empty / trivial inputs ──────────────────────────────────────────────────

def test_empty_string_returns_empty_list():
    assert chunk_text('', 100, 10) == []

@pytest.mark.timeout(2)
def test_text_shorter_than_chunk_size_returns_unchanged():
    text = 'short text here'
    result = chunk_text(text, 100, 10)
    assert result == [text]

@pytest.mark.timeout(2)
def test_text_exactly_chunk_size_is_single_chunk():
    text = 'x' * 100
    result = chunk_text(text, 100, 0)
    assert len(result) == 1
    assert result[0] == text


# ── Size constraints ────────────────────────────────────────────────────────

def test_no_chunk_exceeds_chunk_size_with_spaces():
    text = ('the quick brown fox jumps over the lazy dog ') * 20
    chunk_size = 100
    for i, chunk in enumerate(chunk_text(text, chunk_size, 20)):
        assert len(chunk) <= chunk_size, f"chunk {i} is {len(chunk)} chars, exceeds {chunk_size}"

def test_no_chunk_exceeds_chunk_size_without_spaces():
    text = 'a' * 500
    chunk_size = 80
    for i, chunk in enumerate(chunk_text(text, chunk_size, 10)):
        assert len(chunk) <= chunk_size, f"chunk {i} is {len(chunk)} chars, exceeds {chunk_size}"


# ── Multiple chunks ─────────────────────────────────────────────────────────

def test_long_text_produces_multiple_chunks():
    text = 'word ' * 200   # ~1000 chars
    result = chunk_text(text, 100, 20)
    assert len(result) > 1


# ── Content coverage ────────────────────────────────────────────────────────

def test_first_chunk_starts_at_beginning_of_text():
    text = 'hello world ' * 50
    chunks = chunk_text(text, 50, 10)
    assert text.startswith(chunks[0])

def test_last_chunk_ends_at_end_of_text():
    text = 'hello world ' * 50
    chunks = chunk_text(text, 50, 10)
    assert text.endswith(chunks[-1])

def test_no_content_lost_when_overlap_is_zero_and_no_spaces():
    # Without spaces, rfind falls back to a hard cut.
    # With overlap=0, concatenation should exactly reconstruct the original.
    text = 'abcdefghijklmnopqrstuvwxyz' * 10  # 260 chars, no spaces
    chunks = chunk_text(text, 50, 0)
    assert ''.join(chunks) == text


# ── Overlap behaviour ───────────────────────────────────────────────────────

def test_overlap_zero_produces_exact_reconstruction():
    # No spaces: hard cuts, no duplication, no gaps.
    text = 'a' * 300
    chunks = chunk_text(text, 50, 0)
    assert ''.join(chunks) == text

def test_adjacent_chunks_share_overlap_content():
    # Use distinct chars so equality can't be coincidental
    text = 'abcdefghijklmnopqrstuvwxyz' * 12  # 312 chars, no spaces
    overlap = 10
    chunks = chunk_text(text, 50, overlap)
    assert len(chunks) > 1
    # Last `overlap` chars of chunk[0] must equal first `overlap` chars of chunk[1]
    assert chunks[0][-overlap:] == chunks[1][:overlap]

def test_overlap_means_adjacent_chunks_share_content_with_spaces():
    # Non-repeating text so substring match can't be coincidental
    text = ' '.join(str(i) for i in range(200))  # '0 1 2 3 4 ... 199'
    overlap = 15
    chunks = chunk_text(text, 60, overlap)
    assert len(chunks) > 1
    # End of chunk[0] should appear at start of chunk[1]
    tail = chunks[0][-overlap:].strip()
    assert tail and tail in chunks[1]


# ── Word boundary splitting ─────────────────────────────────────────────────

def test_known_word_not_split_across_chunks():
    # 'fghij' should appear whole in at least one chunk
    text = 'abcde fghij klmno pqrst uvwxy'
    chunks = chunk_text(text, 10, 0)
    assert any('fghij' in chunk for chunk in chunks)

def test_chunk_does_not_end_mid_word():
    text = ('the quick brown fox jumps over ') * 10
    chunks = chunk_text(text, 30, 0)
    word_set = set(text.split())
    for chunk in chunks[:-1]:  # last chunk may be a short tail
        last_char = chunk[-1]
        assert last_char == ' ' or chunk.split()[-1] in word_set

def test_no_space_fallback_still_produces_multiple_chunks():
    # Even with no spaces, must still chunk — no infinite loop, no single huge chunk.
    text = 'a' * 300
    chunks = chunk_text(text, 50, 0)
    assert len(chunks) > 1
    assert all(len(c) <= 50 for c in chunks)

@pytest.mark.timeout(2)
def test_space_only_at_start_of_chunk_does_not_produce_empty_chunk():
    # If the only space in the slice is at position `start`, walking back
    # would give end=start → empty chunk → start goes backwards → infinite loop.
    # Correct behaviour: fall back to hard cut, produce a non-empty chunk.
    text = ' ' + 'a' * 200   # space at index 0, then solid run of 'a'
    chunks = chunk_text(text, 50, 0)
    assert all(len(c) > 0 for c in chunks)
    assert len(chunks) > 1

@pytest.mark.timeout(2)
def test_space_near_start_of_chunk_does_not_cause_backward_drift():
    # If the only space in a slice is within `overlap` chars of `start`,
    # rfind returns a boundary <= start + overlap → start moves backwards → infinite loop.
    # Correct behaviour: fall back to hard cut, always make forward progress.
    overlap = 10
    # One space at position 5, then solid run — space is within the overlap window
    text = 'hello' + ' ' + 'a' * 300
    chunks = chunk_text(text, 50, overlap)
    assert len(chunks) > 1
    assert all(len(c) > 0 for c in chunks)

def test_chunks_do_not_start_mid_word():
    # We guard chunk *ends* at word boundaries, but chunk *starts* are set by
    # `end - overlap`, which can land mid-word. This test will fail until that's fixed.
    # e.g. chunk[0] ends at 'superlongword', overlap backs up into the middle of it,
    # and chunk[1] starts at 'longword'.
    text = 'hello superlongword and more text here ' * 5
    word_set = set(text.split())
    chunks = chunk_text(text, 30, 15)
    for i, chunk in enumerate(chunks[1:], 1):
        first_word = chunk.lstrip().split()[0] if chunk.strip() else ''
        assert first_word in word_set, \
            f"chunk[{i}] starts mid-word: {chunk[:25]!r} (first word: {first_word!r})"

def test_start_snap_does_not_skip_content_when_word_too_long():
    # If the snap-forward fix overshoots (next space is at or past `end`),
    # a naive impl creates a gap: positions between end and next_space appear in
    # neither chunk. Correct behaviour: if next_space >= end, don't snap — keep start.
    # Use unique text so text.find(chunk) reliably locates each chunk.
    words = [f'w{i:04d}' for i in range(60)]      # 'w0000' 'w0001' ... all unique
    # Insert a long word ('thisisaverylongword') near a chunk boundary to force overshoot
    words.insert(10, 'thisisaverylongword')
    text = ' '.join(words)
    chunks = chunk_text(text, 30, 12)
    # Invariant: consecutive chunks must overlap in the original text (no gap).
    # i.e. start of chunk[n+1] <= end of chunk[n].
    positions = [text.index(c) for c in chunks]   # text.index finds first (all unique)
    for i in range(len(chunks) - 1):
        end_i = positions[i] + len(chunks[i])
        start_next = positions[i + 1]
        assert start_next <= end_i, \
            f"gap between chunk[{i}] and chunk[{i+1}]: chunk[{i}] ends at {end_i}, " \
            f"chunk[{i+1}] starts at {start_next}"

def test_no_space_in_slice_falls_back_to_hard_cut():
    # A long word (longer than chunk_size) has no space to split on.
    # Must still produce chunks of the right size rather than hanging or crashing.
    text = 'a' * 300
    chunk_size = 50
    chunks = chunk_text(text, chunk_size, 0)
    assert all(len(c) <= chunk_size for c in chunks)
    assert ''.join(chunks) == text   # no content lost


# ── Overlap-vs-chunksize guard (finding #1) ─────────────────────────────────
# Progress each iteration is `chunksize - overlap` chars. If overlap >= chunksize
# that is <= 0, so `start` never advances and the loop spins forever. chunk_text
# should reject this up front rather than hang. Both tests are RED until a guard
# (e.g. `if overlap >= chunksize: raise ValueError`) is added — they currently
# hit the timeout instead of raising.

@pytest.mark.timeout(2)
def test_overlap_equal_to_chunksize_raises():
    with pytest.raises(ValueError):
        chunk_text('a' * 300, 50, 50)

@pytest.mark.timeout(2)
def test_overlap_greater_than_chunksize_raises():
    with pytest.raises(ValueError):
        chunk_text('a' * 300, 50, 80)


# ── No redundant duplicate tail chunk (finding #2) ──────────────────────────

def test_no_chunk_is_wholly_inside_the_previous_one():
    # For certain lengths the loop emits a final chunk whose span is entirely
    # contained in the previous chunk — pure duplicate content, no new coverage.
    # With chunksize=100, overlap=20, length=170 the chunks span [0:100], [80:170],
    # [160:170]; the last is wholly inside the second. Distinct characters (no
    # spaces, so no boundary snapping) let text.index locate each chunk's position.
    # RED until chunk_text stops emitting a chunk that adds no new content.
    text = ''.join(chr(33 + i) for i in range(170))  # 170 distinct non-space chars
    chunks = chunk_text(text, 100, 20)

    positions = [text.index(c) for c in chunks]
    ends = [p + len(c) for p, c in zip(positions, chunks)]
    for i in range(1, len(chunks)):
        assert ends[i] > ends[i - 1], (
            f"chunk[{i}] ends at {ends[i]} but chunk[{i-1}] already reached "
            f"{ends[i-1]} — it adds no new content (redundant duplicate tail)"
        )
