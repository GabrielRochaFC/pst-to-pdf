"""Synthetic tests for filter_emails parsing and matching.

No real PST/EML/PDF files. All inputs are crafted in-process.
"""

import tempfile
import unittest
from email.message import EmailMessage
from pathlib import Path

from pst_to_pdf.filter_emails import (
    FILTER_HEADERS,
    extract_participant_addresses,
    filter_fingerprint,
    load_filter_file,
    message_matches,
    normalize_email,
    parse_email_list,
    write_filter_file,
)


class TestNormalizeEmail(unittest.TestCase):
    def test_lowercases(self):
        self.assertEqual(normalize_email("Alice@Example.COM"), "alice@example.com")

    def test_strips_whitespace(self):
        self.assertEqual(normalize_email("  bob@x.io  "), "bob@x.io")

    def test_rejects_missing_at(self):
        self.assertIsNone(normalize_email("not-an-email"))

    def test_rejects_empty_local(self):
        self.assertIsNone(normalize_email("@example.com"))

    def test_rejects_empty_domain(self):
        self.assertIsNone(normalize_email("user@"))

    def test_rejects_blank(self):
        self.assertIsNone(normalize_email(""))
        self.assertIsNone(normalize_email("   "))


class TestParseEmailList(unittest.TestCase):
    def test_comma_separated(self):
        result = parse_email_list("a@x.com, b@y.com,c@z.com")
        self.assertEqual(result, ["a@x.com", "b@y.com", "c@z.com"])

    def test_newline_separated(self):
        result = parse_email_list("a@x.com\nb@y.com\n\nc@z.com")
        self.assertEqual(result, ["a@x.com", "b@y.com", "c@z.com"])

    def test_mixed_separators(self):
        result = parse_email_list("a@x.com, b@y.com\nc@z.com")
        self.assertEqual(result, ["a@x.com", "b@y.com", "c@z.com"])

    def test_dedupe_preserves_order(self):
        result = parse_email_list("a@x.com, A@X.COM, b@y.com, a@x.com")
        self.assertEqual(result, ["a@x.com", "b@y.com"])

    def test_drops_blanks_and_bad(self):
        result = parse_email_list("a@x.com,,not-an-email, b@y.com")
        self.assertEqual(result, ["a@x.com", "b@y.com"])

    def test_empty_returns_empty(self):
        self.assertEqual(parse_email_list(""), [])
        self.assertEqual(parse_email_list("   \n,  ,\n"), [])


class TestLoadFilterFile(unittest.TestCase):
    def test_ignores_blank_and_comment_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "filter.txt"
            path.write_text(
                "# header comment\n"
                "a@x.com\n"
                "\n"
                "  # indented comment treated as comment\n"
                "B@Y.com\n"
                "\n",
                encoding="utf-8",
            )
            self.assertEqual(load_filter_file(path), ["a@x.com", "b@y.com"])

    def test_missing_file_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileNotFoundError):
                load_filter_file(Path(tmp) / "nope.txt")


class TestWriteFilterFile(unittest.TestCase):
    def test_writes_one_per_line_and_creates_parents(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config" / "filter_emails.txt"
            write_filter_file(path, ["a@x.com", "b@y.com"])
            self.assertEqual(
                path.read_text(encoding="utf-8"), "a@x.com\nb@y.com\n"
            )


class TestFilterFingerprint(unittest.TestCase):
    def test_order_independent(self):
        fp1 = filter_fingerprint(["a@x.com", "b@y.com"])
        fp2 = filter_fingerprint(["b@y.com", "a@x.com"])
        self.assertEqual(fp1, fp2)

    def test_case_independent(self):
        fp1 = filter_fingerprint(["A@X.com", "B@Y.com"])
        fp2 = filter_fingerprint(["a@x.com", "b@y.com"])
        self.assertEqual(fp1, fp2)

    def test_duplicate_independent(self):
        fp1 = filter_fingerprint(["a@x.com", "a@x.com", "b@y.com"])
        fp2 = filter_fingerprint(["a@x.com", "b@y.com"])
        self.assertEqual(fp1, fp2)

    def test_different_sets_differ(self):
        fp1 = filter_fingerprint(["a@x.com"])
        fp2 = filter_fingerprint(["a@x.com", "b@y.com"])
        self.assertNotEqual(fp1, fp2)

    def test_empty(self):
        # An empty filter set still returns a real sha256 hex digest.
        fp = filter_fingerprint([])
        self.assertEqual(len(fp), 64)
        self.assertTrue(all(c in "0123456789abcdef" for c in fp))
        self.assertEqual(fp, filter_fingerprint([]))

    def test_whitespace_only_at_symbol_is_excluded(self):
        # "  @  " is not a valid email; it must not affect the fingerprint.
        fp_clean = filter_fingerprint(["a@x.com"])
        fp_with_junk = filter_fingerprint(["a@x.com", "  @  "])
        self.assertEqual(fp_clean, fp_with_junk)


def _build_message(headers: dict[str, str]) -> EmailMessage:
    msg = EmailMessage()
    for name, value in headers.items():
        msg[name] = value
    msg.set_content("body text — never inspected by filter")
    return msg


class TestExtractParticipantAddresses(unittest.TestCase):
    def test_plain_from(self):
        msg = _build_message({"From": "alice@example.com"})
        self.assertEqual(extract_participant_addresses(msg), {"alice@example.com"})

    def test_display_name_format(self):
        msg = _build_message({"From": "Alice <alice@example.com>"})
        self.assertEqual(extract_participant_addresses(msg), {"alice@example.com"})

    def test_multiple_addresses_in_one_header(self):
        msg = _build_message({"To": "a@x.com, b@y.com"})
        self.assertEqual(extract_participant_addresses(msg), {"a@x.com", "b@y.com"})

    def test_collects_across_all_six_headers(self):
        msg = _build_message({
            "From":     "from@x.com",
            "To":       "to@x.com",
            "Cc":       "cc@x.com",
            "Bcc":      "bcc@x.com",
            "Reply-To": "reply@x.com",
            "Sender":   "sender@x.com",
        })
        self.assertEqual(
            extract_participant_addresses(msg),
            {"from@x.com", "to@x.com", "cc@x.com", "bcc@x.com",
             "reply@x.com", "sender@x.com"},
        )

    def test_ignores_subject_and_body(self):
        msg = _build_message({"From": "alice@example.com", "Subject": "bob@x.com"})
        self.assertEqual(extract_participant_addresses(msg), {"alice@example.com"})

    def test_case_insensitive(self):
        msg = _build_message({"From": "Alice@EXAMPLE.COM"})
        self.assertEqual(extract_participant_addresses(msg), {"alice@example.com"})

    def test_filter_headers_constant_shape(self):
        self.assertEqual(
            FILTER_HEADERS,
            ("From", "To", "Cc", "Bcc", "Reply-To", "Sender"),
        )


class TestMessageMatches(unittest.TestCase):
    def test_match_from(self):
        msg = _build_message({"From": "alice@example.com"})
        self.assertTrue(message_matches(msg, frozenset({"alice@example.com"})))

    def test_match_to(self):
        msg = _build_message({"To": "bob@x.com, alice@example.com"})
        self.assertTrue(message_matches(msg, frozenset({"alice@example.com"})))

    def test_match_cc(self):
        msg = _build_message({"Cc": "alice@example.com"})
        self.assertTrue(message_matches(msg, frozenset({"alice@example.com"})))

    def test_match_bcc(self):
        msg = _build_message({"Bcc": "alice@example.com"})
        self.assertTrue(message_matches(msg, frozenset({"alice@example.com"})))

    def test_match_reply_to(self):
        msg = _build_message({"Reply-To": "alice@example.com"})
        self.assertTrue(message_matches(msg, frozenset({"alice@example.com"})))

    def test_match_sender(self):
        msg = _build_message({"Sender": "alice@example.com"})
        self.assertTrue(message_matches(msg, frozenset({"alice@example.com"})))

    def test_no_match(self):
        msg = _build_message({"From": "carol@other.com"})
        self.assertFalse(message_matches(msg, frozenset({"alice@example.com"})))

    def test_case_insensitive_match(self):
        msg = _build_message({"From": "ALICE@EXAMPLE.COM"})
        self.assertTrue(message_matches(msg, frozenset({"alice@example.com"})))

    def test_unparseable_address_does_not_match(self):
        msg = _build_message({"From": "not-an-email"})
        self.assertFalse(message_matches(msg, frozenset({"alice@example.com"})))
