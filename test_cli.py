"""Tests for the httpparrot CLI tool."""
import subprocess
import sys

import pytest

CLI = './cli/httpparrot'


def run_cli(*args):
    """Run the CLI and return (stdout, stderr, returncode)."""
    result = subprocess.run(
        [sys.executable, CLI, *args],
        capture_output=True, text=True
    )
    return result.stdout, result.stderr, result.returncode


class TestCLICodeLookup:
    def test_known_code(self):
        out, _, rc = run_cli('404')
        assert rc == 0
        assert '404' in out
        assert 'Not Found' in out

    def test_code_shows_description(self):
        out, _, rc = run_cli('200')
        assert rc == 0
        assert 'request has succeeded' in out

    def test_code_shows_category(self):
        out, _, rc = run_cli('503')
        assert '5xx' in out
        assert 'Server Error' in out

    def test_unknown_code_in_range(self):
        """A code in valid range (100-599) but not listed should fail."""
        out, _, rc = run_cli('299')
        assert rc == 1
        assert 'Unknown' in out

    def test_code_out_of_range(self):
        """A code outside valid range falls through to search."""
        out, _, rc = run_cli('999')
        assert rc == 0
        assert 'No status codes matching' in out

    def test_valid_range_unlisted(self):
        out, _, rc = run_cli('299')
        assert rc == 1
        assert 'Unknown' in out


class TestCLICategory:
    def test_1xx(self):
        out, _, rc = run_cli('1xx')
        assert rc == 0
        assert '100' in out
        assert 'Continue' in out
        assert 'Informational' in out

    def test_4xx(self):
        out, _, rc = run_cli('4xx')
        assert rc == 0
        assert '404' in out
        assert 'Not Found' in out
        assert '418' in out

    def test_5xx(self):
        out, _, rc = run_cli('5xx')
        assert rc == 0
        assert '500' in out
        assert '503' in out

    def test_all(self):
        out, _, rc = run_cli('all')
        assert rc == 0
        assert '1xx' in out
        assert '5xx' in out
        assert '200' in out
        assert '404' in out
        assert '500' in out


class TestCLISearch:
    def test_search_by_name(self):
        out, _, rc = run_cli('teapot')
        assert rc == 0
        assert '418' in out

    def test_search_by_description(self):
        out, _, rc = run_cli('authentication')
        assert rc == 0
        assert '401' in out

    def test_search_no_results(self):
        out, _, rc = run_cli('xyznonexistent')
        assert rc == 0
        assert 'No status codes matching' in out

    def test_search_multiple_words(self):
        out, _, rc = run_cli('not', 'found')
        assert rc == 0
        assert '404' in out

    def test_search_by_partial_code(self):
        out, _, rc = run_cli('40')
        assert rc == 0
        assert '400' in out
        assert '404' in out


class TestCLIUsage:
    def test_no_args_shows_usage(self):
        out, _, rc = run_cli()
        assert rc == 0
        assert 'httpparrot' in out
        assert 'Usage' in out
        assert 'Examples' in out


class TestCLIOutput:
    def test_no_ansi_when_piped(self):
        """Piped output should have no ANSI escape codes."""
        out, _, _ = run_cli('404')
        # subprocess.run captures output (not a tty), so colors should be off
        assert '\033[' not in out
        assert '\x1b[' not in out

    def test_output_is_indented(self):
        out, _, _ = run_cli('200')
        lines = [l for l in out.split('\n') if l.strip()]
        for line in lines:
            assert line.startswith('  '), f"Line not indented: {line!r}"
