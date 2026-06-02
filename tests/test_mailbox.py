"""Tests for HTML rendering and header sanitization."""

from doc_worker.mailbox import _sanitize_header, _to_html


def test_to_html_strips_script_tags():
	html = _to_html("Hello <script>alert('xss')</script> world")
	assert "<script>" not in html
	assert "alert" not in html or "<script" not in html
	assert "Hello" in html


def test_to_html_strips_event_handlers_and_dangerous_tags():
	html = _to_html('<img src=x onerror="steal()">\n\n<iframe src="evil"></iframe>')
	assert "onerror" not in html
	assert "<iframe" not in html


def test_to_html_keeps_safe_markdown_formatting():
	html = _to_html("# Title\n\n**bold** and a list:\n\n- one\n- two")
	assert "<h1" in html
	assert "<strong>bold</strong>" in html
	assert "<li>one</li>" in html


def test_to_html_renders_tables():
	md = "| a | b |\n| - | - |\n| 1 | 2 |"
	html = _to_html(md)
	assert "<table>" in html
	assert "<td>1</td>" in html


def test_to_html_adds_rel_to_links():
	html = _to_html("[click](https://example.com)")
	assert 'href="https://example.com"' in html
	assert "noopener" in html


def test_to_html_strips_javascript_url():
	html = _to_html("[click](javascript:alert(1))")
	assert "javascript:" not in html


def test_sanitize_header_removes_crlf():
	assert _sanitize_header("subject\r\nBcc: attacker@evil.com") == "subjectBcc: attacker@evil.com"


def test_sanitize_header_keeps_tabs_and_unicode():
	assert _sanitize_header("Resumen\t(DE): café.pdf") == "Resumen\t(DE): café.pdf"


def test_sanitize_header_strips_other_control_chars():
	assert _sanitize_header("a\x00b\x07c") == "abc"
