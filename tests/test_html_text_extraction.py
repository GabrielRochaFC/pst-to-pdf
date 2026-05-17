"""Synthetic tests for HTML-to-text extraction in converter.py.

All tests use fake HTML strings only. No real emails, PST files, or file I/O.
"""

import unittest

from pst_to_pdf.converter import html_to_text


class TestHTMLTextExtraction(unittest.TestCase):
    def test_style_content_excluded(self):
        html = (
            "<html><head>"
            "<style>body { color: red; } .cls { font-size: 12px; }</style>"
            "</head><body><p>Hello world</p></body></html>"
        )
        result = html_to_text(html)
        self.assertNotIn("color: red", result)
        self.assertNotIn(".cls", result)
        self.assertNotIn("font-size", result)
        self.assertIn("Hello world", result)

    def test_script_content_excluded(self):
        html = (
            "<html><body>"
            "<script>var x = 1; alert('hi');</script>"
            "<p>Visible text</p>"
            "</body></html>"
        )
        result = html_to_text(html)
        self.assertNotIn("var x", result)
        self.assertNotIn("alert", result)
        self.assertIn("Visible text", result)

    def test_head_content_excluded(self):
        html = (
            "<html><head>"
            "<title>Email Title</title>"
            "<meta charset='utf-8'>"
            "</head><body><p>Body text</p></body></html>"
        )
        result = html_to_text(html)
        self.assertNotIn("Email Title", result)
        self.assertIn("Body text", result)

    def test_html_comments_excluded(self):
        html = (
            "<html><body>"
            "<p>Real text</p>"
            "<!-- This is a comment with some CSS: color:red; -->"
            "</body></html>"
        )
        result = html_to_text(html)
        self.assertNotIn("This is a comment", result)
        self.assertNotIn("color:red", result)
        self.assertIn("Real text", result)

    def test_block_tags_create_line_breaks(self):
        html = (
            "<html><body>"
            "<p>First paragraph</p>"
            "<p>Second paragraph</p>"
            "</body></html>"
        )
        result = html_to_text(html)
        self.assertIn("First paragraph", result)
        self.assertIn("Second paragraph", result)
        self.assertIn("\n", result)

    def test_noscript_excluded(self):
        html = (
            "<html><body>"
            "<noscript>Please enable JavaScript</noscript>"
            "<p>Main content</p>"
            "</body></html>"
        )
        result = html_to_text(html)
        self.assertNotIn("Please enable JavaScript", result)
        self.assertIn("Main content", result)

    def test_inline_style_attribute_ignored(self):
        """Inline style attributes do not produce tag content — text is preserved."""
        html = '<html><body><p style="color:blue">Styled text</p></body></html>'
        result = html_to_text(html)
        self.assertIn("Styled text", result)

    def test_mixed_content(self):
        """Realistic email fragment: style block + body text."""
        html = (
            "<html><head>"
            "<style>.MsoNormal{font-size:11pt;color:#1F497D;}</style>"
            "</head><body>"
            "<div><p>Dear team,</p>"
            "<p>Please find the attached document.</p>"
            "<p>Regards,<br/>John</p>"
            "</div></body></html>"
        )
        result = html_to_text(html)
        self.assertNotIn("MsoNormal", result)
        self.assertNotIn("font-size", result)
        self.assertNotIn("1F497D", result)
        self.assertIn("Dear team", result)
        self.assertIn("attached document", result)
        self.assertIn("Regards", result)
        self.assertIn("John", result)


if __name__ == "__main__":
    unittest.main()
