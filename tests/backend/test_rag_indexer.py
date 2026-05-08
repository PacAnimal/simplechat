"""Unit tests for the RAG indexer — text extraction and chunking."""
import pytest

from backend.rag.indexer import _is_heading, _tail_sentences, chunk_text, extract_text

# ---------------------------------------------------------------------------
# heading detection
# ---------------------------------------------------------------------------


def test_heading_markdown():
    assert _is_heading("## Section Title")
    assert _is_heading("# Introduction")
    assert not _is_heading("Not a heading")


def test_heading_numbered():
    assert _is_heading("4.2 Torque Specifications")
    assert _is_heading("1. Introduction")
    assert not _is_heading("4.2ghz processor")  # lowercase after digits


def test_heading_all_caps():
    assert _is_heading("TORQUE VALUES")
    assert _is_heading("SERVICE MANUAL SECTION")
    assert not _is_heading("NOTE")       # single word, too short
    assert not _is_heading("AB")         # too short


# ---------------------------------------------------------------------------
# tail sentences
# ---------------------------------------------------------------------------


def test_tail_sentences_basic():
    text = "First sentence. Second sentence. Third sentence."
    tail = _tail_sentences(text, n=2)
    assert "Second sentence" in tail
    assert "Third sentence" in tail
    assert "First sentence" not in tail


def test_tail_sentences_fewer_than_n():
    text = "Only one sentence."
    assert _tail_sentences(text, n=2) == "Only one sentence."


# ---------------------------------------------------------------------------
# chunk_text — basic behaviour
# ---------------------------------------------------------------------------


def test_chunk_empty():
    assert chunk_text("") == []
    assert chunk_text("   \n\n  ") == []


def test_chunk_short_text():
    text = "Hello world."
    chunks = chunk_text(text, chunk_size=512)
    assert len(chunks) == 1
    assert "Hello world." in chunks[0]


def test_chunk_respects_paragraphs():
    para_a = "A" * 200
    para_b = "B" * 200
    text = f"{para_a}\n\n{para_b}"
    chunks = chunk_text(text, chunk_size=512)
    # both paragraphs fit in one chunk
    assert len(chunks) == 1
    assert para_a in chunks[0]
    assert para_b in chunks[0]


def test_chunk_splits_large_paragraphs():
    big = "word " * 200  # ~1000 chars
    chunks = chunk_text(big, chunk_size=100, overlap=10)
    assert len(chunks) > 1
    for c in chunks:
        assert len(c) <= 100


def test_chunk_multiple_paragraphs():
    paras = ["Paragraph " + str(i) + " content here." for i in range(10)]
    text = "\n\n".join(paras)
    chunks = chunk_text(text, chunk_size=50, overlap=5)
    assert len(chunks) >= 1
    combined = " ".join(chunks)
    assert "Paragraph" in combined


# ---------------------------------------------------------------------------
# chunk_text — heading context
# ---------------------------------------------------------------------------


def test_heading_prefix_in_chunk():
    text = "## Torque Specifications\nFront axle: 85 Nm."
    chunks = chunk_text(text, chunk_size=512)
    assert len(chunks) == 1
    assert "[Torque Specifications]" in chunks[0] or "Torque Specifications" in chunks[0]
    assert "85 Nm" in chunks[0]


def test_heading_boundary_flushes_chunk():
    """Content under different headings must land in separate chunks."""
    text = (
        "## Section A\n" + "Alpha content. " * 10 + "\n\n"
        "## Section B\n" + "Beta content. " * 10
    )
    chunks = chunk_text(text, chunk_size=512)
    alpha_chunks = [c for c in chunks if "Alpha" in c]
    beta_chunks = [c for c in chunks if "Beta" in c]
    assert alpha_chunks
    assert beta_chunks
    # no chunk should mix both sections
    for c in chunks:
        assert not ("Alpha" in c and "Beta" in c)


def test_heading_context_carried_to_overflow_chunk():
    """When content under a heading overflows, the heading prefix appears in each chunk."""
    long_content = "This is a sentence about torque. " * 40  # ~1320 chars
    text = f"## Engine Specs\n{long_content}"
    chunks = chunk_text(text, chunk_size=200, overlap=20)
    assert len(chunks) > 1
    assert all("Engine Specs" in c for c in chunks)


def test_numbered_heading_detected():
    text = "4.2 Maintenance Schedule\nOil change every 5000 km."
    chunks = chunk_text(text, chunk_size=512)
    assert any("4.2 Maintenance Schedule" in c or "Maintenance Schedule" in c for c in chunks)


# ---------------------------------------------------------------------------
# extract_text — text types
# ---------------------------------------------------------------------------


def test_extract_plain_text():
    content = b"Hello, world!"
    result = extract_text(content, "text/plain")
    assert result == "Hello, world!"


def test_extract_markdown():
    content = b"# Heading\n\nSome text."
    result = extract_text(content, "text/markdown")
    assert "Heading" in result


def test_extract_csv():
    content = b"col1,col2\nval1,val2"
    result = extract_text(content, "text/csv")
    assert "col1" in result
    assert "val1" in result


def test_extract_json():
    content = b'{"key": "value"}'
    result = extract_text(content, "application/json")
    assert '"key"' in result


def test_extract_utf8_with_errors():
    content = b"valid text \xff invalid byte"
    result = extract_text(content, "text/plain")
    assert "valid text" in result


def test_extract_unknown_mime():
    result = extract_text(b"\x00\x01\x02", "application/octet-stream")
    assert result == ""


# ---------------------------------------------------------------------------
# extract_text — PDF (integration, pypdf required)
# ---------------------------------------------------------------------------


def test_extract_pdf_basic():
    pytest.importorskip("pypdf")
    import io

    from pypdf import PdfWriter

    buf = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    # blank page — extract_text should return empty or whitespace
    writer.write(buf)
    result = extract_text(buf.getvalue(), "application/pdf")
    assert isinstance(result, str)
