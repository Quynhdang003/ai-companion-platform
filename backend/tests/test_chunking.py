import pytest

from app.services.rag.chunking import chunk_text


def sentences(n: int, words: int = 12) -> str:
    return " ".join(f"Câu {i} " + " ".join(["chữ"] * words) + "." for i in range(n))


def test_short_text_is_one_chunk_with_lines_kept() -> None:
    text = "# Số khẩn cấp\n\n- 113: công an.\n- 115: cấp cứu.\r\n\r\nGọi khi cần."

    assert chunk_text(text) == ["# Số khẩn cấp\n- 113: công an.\n- 115: cấp cứu.\nGọi khi cần."]


def test_long_text_is_split_within_the_limit_with_overlap() -> None:
    chunks = chunk_text(sentences(40), max_chars=300, overlap=100)

    assert len(chunks) > 3
    assert all(0 < len(chunk) <= 300 for chunk in chunks)
    for previous, chunk in zip(chunks, chunks[1:], strict=False):
        last_sentence = previous.rsplit(". ", 1)[-1]
        assert chunk.startswith(last_sentence)


def test_every_sentence_survives_in_order() -> None:
    text = sentences(30)

    chunks = chunk_text(text, max_chars=250, overlap=60)

    joined = " ".join(chunks)
    positions = [joined.find(f"Câu {i} ") for i in range(30)]
    assert all(p >= 0 for p in positions)
    assert positions == sorted(positions)


def test_overlong_sentence_is_cut_between_words() -> None:
    sentence = " ".join(f"từ{i}" for i in range(200)) + "."

    chunks = chunk_text(sentence, max_chars=120, overlap=0)

    assert all(len(chunk) <= 120 for chunk in chunks)
    assert " ".join(chunks).split() == sentence.split()


def test_overlong_word_is_cut() -> None:
    chunks = chunk_text("x" * 250, max_chars=100, overlap=0)

    assert chunks == ["x" * 100, "x" * 100, "x" * 50]


def test_blank_text_has_no_chunks() -> None:
    assert chunk_text(" \n\n \n") == []


def test_overlap_must_be_smaller_than_the_limit() -> None:
    with pytest.raises(ValueError):
        chunk_text("abc", max_chars=100, overlap=100)
