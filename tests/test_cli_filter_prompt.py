"""Smoke test: pst_to_pdf.cli imports cleanly and filter helpers are reachable."""

import unittest


class TestCliFilterImports(unittest.TestCase):
    def test_cli_module_imports(self):
        import pst_to_pdf.cli  # noqa: F401

    def test_prompt_email_filter_is_callable(self):
        from pst_to_pdf.cli import prompt_email_filter
        self.assertTrue(callable(prompt_email_filter))

    def test_filter_emails_integration_via_cli_namespace(self):
        from pst_to_pdf.filter_emails import parse_email_list
        self.assertEqual(
            parse_email_list("Alice@Example.COM, bob@x.io"),
            ["alice@example.com", "bob@x.io"],
        )


if __name__ == "__main__":
    unittest.main()
