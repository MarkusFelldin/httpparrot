"""Tests for HTTP Parrots application."""
import re
import socket
import time
from unittest.mock import MagicMock, patch

import pytest
import requests

from index import app, _rate_limit, is_rate_limited, linkify_rfcs, resolve_and_validate


@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


@pytest.fixture(autouse=True)
def clear_rate_limit():
    _rate_limit.clear()


# --- Page routes ---

class TestPages:
    def test_index(self, client):
        resp = client.get('/')
        assert resp.status_code == 200
        assert b'HTTP Parrots' in resp.data

    def test_detail_page_200(self, client):
        resp = client.get('/200')
        assert resp.status_code == 200
        assert b'OK' in resp.data

    def test_detail_page_404_code(self, client):
        resp = client.get('/404')
        assert resp.status_code == 404
        assert b'Not Found' in resp.data

    def test_detail_page_500_code(self, client):
        resp = client.get('/500')
        assert resp.status_code == 500

    def test_detail_page_1xx_returns_200(self, client):
        """1xx codes should return HTTP 200 to avoid breaking the response."""
        resp = client.get('/100')
        assert resp.status_code == 200

    def test_detail_page_3xx_returns_200(self, client):
        """3xx codes should return HTTP 200 to avoid redirect behavior."""
        resp = client.get('/301')
        assert resp.status_code == 200

    def test_invalid_code_returns_404(self, client):
        resp = client.get('/999')
        assert resp.status_code == 404

    def test_non_numeric_returns_404(self, client):
        resp = client.get('/abc')
        assert resp.status_code == 404

    def test_quiz_page(self, client):
        resp = client.get('/quiz')
        assert resp.status_code == 200
        assert b'Quiz' in resp.data

    def test_flowchart_page(self, client):
        resp = client.get('/flowchart')
        assert resp.status_code == 200
        assert b'Which Status Code' in resp.data

    def test_compare_page(self, client):
        resp = client.get('/compare')
        assert resp.status_code == 200

    def test_compare_page_contains_expected_elements(self, client):
        resp = client.get('/compare')
        html = resp.data.decode()
        assert 'Compare Status Codes' in html
        assert 'select-a' in html
        assert 'select-b' in html
        assert 'compare-result' in html
        assert '<option value="200">' in html
        assert '<option value="404">' in html
        assert 'noscript' in html

    def test_compare_page_with_params(self, client):
        resp = client.get('/compare?a=301&b=308')
        assert resp.status_code == 200
        html = resp.data.decode()
        assert 'select-a' in html

    def test_tester_page(self, client):
        resp = client.get('/tester')
        assert resp.status_code == 200
        assert b'Tester' in resp.data

    def test_cheatsheet_page(self, client):
        resp = client.get('/cheatsheet')
        assert resp.status_code == 200
        assert b'Cheat Sheet' in resp.data

    def test_api_docs_page(self, client):
        resp = client.get('/api-docs')
        assert resp.status_code == 200
        assert b'API' in resp.data

    def test_custom_404_page(self, client):
        resp = client.get('/nonexistent-page')
        assert resp.status_code == 404
        assert b'Parrot Not Found' in resp.data


# --- Content negotiation ---

class TestContentNegotiation:
    def test_json_response(self, client):
        resp = client.get('/200', headers={'Accept': 'application/json'})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['code'] == '200'
        assert data['description'] == 'OK'
        assert data['image'] is not None
        assert 'meaning' in data
        assert 'history' in data

    def test_image_response(self, client):
        resp = client.get('/200', headers={'Accept': 'image/*'})
        assert resp.status_code == 200
        assert resp.content_type.startswith('image/')

    def test_html_default(self, client):
        resp = client.get('/200')
        assert resp.status_code == 200
        assert b'<!doctype html>' in resp.data


# --- Direct image endpoint ---

class TestImageEndpoint:
    def test_image_jpg(self, client):
        resp = client.get('/200.jpg')
        assert resp.status_code == 200
        assert resp.content_type.startswith('image/')

    def test_image_missing(self, client):
        resp = client.get('/999.jpg')
        assert resp.status_code == 404


# --- Random redirect ---

class TestRandom:
    def test_random_redirects(self, client):
        resp = client.get('/random')
        assert resp.status_code == 302
        assert resp.location is not None

    def test_random_not_cached(self, client):
        resp = client.get('/random')
        assert resp.headers.get('Cache-Control') == 'no-store'


# --- Status code returner ---

class TestReturnStatus:
    def test_return_200(self, client):
        resp = client.get('/return/200')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['code'] == 200
        assert data['description'] == 'OK'

    def test_return_503(self, client):
        resp = client.get('/return/503')
        assert resp.status_code == 503
        data = resp.get_json()
        assert data['code'] == 503

    def test_return_418(self, client):
        resp = client.get('/return/418')
        assert resp.status_code == 418

    def test_return_out_of_range(self, client):
        resp = client.get('/return/600')
        assert resp.status_code == 404

    def test_return_below_range(self, client):
        resp = client.get('/return/99')
        assert resp.status_code == 404


# --- Security headers ---

class TestSecurityHeaders:
    def test_x_content_type_options(self, client):
        resp = client.get('/')
        assert resp.headers.get('X-Content-Type-Options') == 'nosniff'

    def test_x_frame_options(self, client):
        resp = client.get('/')
        assert resp.headers.get('X-Frame-Options') == 'DENY'

    def test_referrer_policy(self, client):
        resp = client.get('/')
        assert resp.headers.get('Referrer-Policy') == 'strict-origin-when-cross-origin'

    def test_permissions_policy(self, client):
        resp = client.get('/')
        assert 'camera=()' in resp.headers.get('Permissions-Policy', '')

    def test_csp(self, client):
        resp = client.get('/')
        csp = resp.headers.get('Content-Security-Policy', '')
        assert "default-src 'self'" in csp
        assert "script-src 'self'" in csp

    def test_hsts(self, client):
        resp = client.get('/')
        assert 'max-age=31536000' in resp.headers.get('Strict-Transport-Security', '')

    def test_cache_control_html(self, client):
        resp = client.get('/')
        assert 'max-age=60' in resp.headers.get('Cache-Control', '')

    def test_cache_control_static(self, client):
        resp = client.get('/static/style.css')
        assert 'max-age=86400' in resp.headers.get('Cache-Control', '')


# --- SSRF protection ---

class TestSSRFProtection:
    def test_blocks_localhost(self):
        result, _ = resolve_and_validate('http://127.0.0.1/')
        assert result is None

    def test_blocks_private_10(self):
        with patch('socket.gethostbyname', return_value='10.0.0.1'):
            result, _ = resolve_and_validate('http://internal.example.com/')
            assert result is None

    def test_blocks_private_172(self):
        with patch('socket.gethostbyname', return_value='172.16.0.1'):
            result, _ = resolve_and_validate('http://internal.example.com/')
            assert result is None

    def test_blocks_private_192(self):
        with patch('socket.gethostbyname', return_value='192.168.1.1'):
            result, _ = resolve_and_validate('http://internal.example.com/')
            assert result is None

    def test_blocks_metadata(self):
        with patch('socket.gethostbyname', return_value='169.254.169.254'):
            result, _ = resolve_and_validate('http://metadata.example.com/')
            assert result is None

    def test_allows_public_ip(self):
        with patch('socket.gethostbyname', return_value='93.184.216.34'):
            result, hostname = resolve_and_validate('http://example.com/')
            assert result is not None
            assert hostname == 'example.com'

    def test_returns_original_url(self):
        with patch('socket.gethostbyname', return_value='93.184.216.34'):
            result, _ = resolve_and_validate('http://example.com/path')
            assert result == 'http://example.com/path'

    def test_blocks_empty_hostname(self):
        result, _ = resolve_and_validate('http://')
        assert result is None

    def test_check_url_no_url(self, client):
        resp = client.get('/api/check-url')
        assert resp.status_code == 400

    def test_check_url_blocked(self, client):
        resp = client.get('/api/check-url?url=http://127.0.0.1/')
        assert resp.status_code == 403
        assert b'not allowed' in resp.data

    def test_check_url_metadata(self, client):
        resp = client.get('/api/check-url?url=http://169.254.169.254/latest/')
        assert resp.status_code == 403


# --- Rate limiting ---

class TestRateLimiting:
    def test_rate_limit_allows_under_limit(self):
        for _ in range(10):
            assert not is_rate_limited('test-ip')

    def test_rate_limit_blocks_over_limit(self):
        for _ in range(10):
            is_rate_limited('test-ip-2')
        assert is_rate_limited('test-ip-2')

    def test_rate_limit_per_ip(self):
        for _ in range(10):
            is_rate_limited('ip-a')
        assert is_rate_limited('ip-a')
        assert not is_rate_limited('ip-b')

    def test_rate_limit_endpoint(self, client):
        # Exhaust rate limit
        for _ in range(10):
            client.get('/api/check-url?url=http://127.0.0.1/')
        resp = client.get('/api/check-url?url=http://example.com')
        assert resp.status_code == 429
        assert b'Rate limit' in resp.data


# --- Data integrity ---

class TestDataIntegrity:
    def test_all_status_codes_have_descriptions(self):
        from status_descriptions import STATUS_INFO
        from index import status_code_list
        for code_info in status_code_list:
            code = code_info[0]
            assert code in STATUS_INFO, f"Missing description for {code}"

    def test_pruned_codes_are_sorted(self):
        from index import pruned_status_codes
        codes = pruned_status_codes()
        code_numbers = [int(c[0]) for c in codes]
        assert code_numbers == sorted(code_numbers)

    def test_pruned_codes_have_images(self):
        from index import pruned_status_codes
        codes = pruned_status_codes()
        for c in codes:
            assert len(c) >= 3, f"Code {c[0]} missing image filename"
            assert c[2].endswith('.jpg'), f"Code {c[0]} image not .jpg: {c[2]}"


# --- Check-URL success path ---

class TestCheckURLSuccess:
    def test_check_url_success(self, client):
        """Test successful external URL check with mocked request."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {'Content-Type': 'text/html'}
        mock_resp.elapsed.total_seconds.return_value = 0.05
        addrinfo = [(socket.AF_INET, socket.SOCK_STREAM, 0, '', ('93.184.216.34', 0))]
        with patch('index.socket.getaddrinfo', return_value=addrinfo), \
             patch('requests.head', return_value=mock_resp):
            resp = client.get('/api/check-url?url=https://example.com')
            assert resp.status_code == 200
            data = resp.get_json()
            assert data['code'] == 200
            assert data['url'] == 'https://example.com'
            assert 'headers' in data
            assert 'time_ms' in data

    def test_check_url_auto_prefix(self, client):
        """URLs without scheme should get https:// prepended."""
        mock_resp = MagicMock()
        mock_resp.status_code = 301
        mock_resp.headers = {'Location': 'https://www.example.com'}
        mock_resp.elapsed.total_seconds.return_value = 0.1
        addrinfo = [(socket.AF_INET, socket.SOCK_STREAM, 0, '', ('93.184.216.34', 0))]
        with patch('index.socket.getaddrinfo', return_value=addrinfo), \
             patch('requests.head', return_value=mock_resp):
            resp = client.get('/api/check-url?url=example.com')
            assert resp.status_code == 200
            data = resp.get_json()
            assert data['code'] == 301
            assert data['url'] == 'https://example.com'

    def test_check_url_connection_error(self, client):
        """Test that connection errors return 502."""
        addrinfo = [(socket.AF_INET, socket.SOCK_STREAM, 0, '', ('93.184.216.34', 0))]
        with patch('index.socket.getaddrinfo', return_value=addrinfo), \
             patch('requests.head', side_effect=requests.RequestException):
            resp = client.get('/api/check-url?url=https://example.com')
            assert resp.status_code == 502
            assert b'Could not connect' in resp.data


# --- Return status edge cases ---

class TestReturnStatusEdgeCases:
    def test_return_unlisted_code(self, client):
        """Valid range code not in status_code_list should return 'Unknown'."""
        resp = client.get('/return/299')
        assert resp.status_code == 299
        data = resp.get_json()
        assert data['description'] == 'Unknown'

    def test_return_100(self, client):
        resp = client.get('/return/100')
        assert resp.status_code == 100


# --- CSP nonce ---

class TestCSPNonce:
    def test_csp_has_nonce(self, client):
        """CSP should contain a nonce, not unsafe-inline for scripts."""
        resp = client.get('/')
        csp = resp.headers.get('Content-Security-Policy', '')
        assert "'nonce-" in csp
        assert "'unsafe-inline'" not in csp.split('script-src')[1].split(';')[0]

    def test_csp_no_unsafe_inline(self, client):
        """CSP should not contain unsafe-inline for either scripts or styles."""
        resp = client.get('/')
        csp = resp.headers.get('Content-Security-Policy', '')
        assert "'unsafe-inline'" not in csp

    def test_csp_nonce_changes_per_request(self, client):
        """Each request should get a unique nonce."""
        resp1 = client.get('/')
        resp2 = client.get('/')
        csp1 = resp1.headers.get('Content-Security-Policy', '')
        csp2 = resp2.headers.get('Content-Security-Policy', '')
        nonce1 = re.search(r"'nonce-([^']+)'", csp1).group(1)
        nonce2 = re.search(r"'nonce-([^']+)'", csp2).group(1)
        assert nonce1 != nonce2

    def test_script_tags_have_nonce(self, client):
        """Inline scripts should have the nonce attribute."""
        resp = client.get('/')
        csp = resp.headers.get('Content-Security-Policy', '')
        nonce = re.search(r"'nonce-([^']+)'", csp).group(1)
        assert f'nonce="{nonce}"'.encode() in resp.data


# --- Resolve and validate edge cases ---

class TestResolveValidateEdgeCases:
    def test_url_with_port(self):
        addrinfo = [(socket.AF_INET, socket.SOCK_STREAM, 0, '', ('93.184.216.34', 0))]
        with patch('index.socket.getaddrinfo', return_value=addrinfo):
            result, hostname = resolve_and_validate('http://example.com:8080/path')
            assert result == 'http://example.com:8080/path'
            assert hostname == 'example.com'

    def test_unresolvable_hostname(self):
        with patch('index.socket.getaddrinfo', side_effect=socket.gaierror):
            result, _ = resolve_and_validate('http://nonexistent.invalid/')
            assert result is None

    def test_blocks_zero_network(self):
        addrinfo = [(socket.AF_INET, socket.SOCK_STREAM, 0, '', ('0.0.0.1', 0))]
        with patch('index.socket.getaddrinfo', return_value=addrinfo):
            result, _ = resolve_and_validate('http://zero.example.com/')
            assert result is None

    def test_blocks_ipv6_loopback_direct(self):
        """IPv6 loopback address in URL should be blocked."""
        addrinfo = [(socket.AF_INET6, socket.SOCK_STREAM, 0, '', ('::1', 0, 0, 0))]
        with patch('index.socket.getaddrinfo', return_value=addrinfo):
            result, _ = resolve_and_validate('http://evil.example.com/')
            assert result is None

    def test_blocks_ipv6_private(self):
        """IPv6 unique local addresses should be blocked."""
        addrinfo = [(socket.AF_INET6, socket.SOCK_STREAM, 0, '', ('fd00::1', 0, 0, 0))]
        with patch('index.socket.getaddrinfo', return_value=addrinfo):
            result, _ = resolve_and_validate('http://evil.example.com/')
            assert result is None

    def test_blocks_mixed_ipv4_ipv6_with_private(self):
        """If any resolved address is private, the URL should be blocked."""
        addrinfo = [
            (socket.AF_INET, socket.SOCK_STREAM, 0, '', ('93.184.216.34', 0)),
            (socket.AF_INET6, socket.SOCK_STREAM, 0, '', ('::1', 0, 0, 0)),
        ]
        with patch('index.socket.getaddrinfo', return_value=addrinfo):
            result, _ = resolve_and_validate('http://dual.example.com/')
            assert result is None

    def test_blocks_url_with_credentials(self):
        """URLs with embedded user:password should be rejected."""
        result, _ = resolve_and_validate('http://admin:secret@example.com/')
        assert result is None

    def test_blocks_url_with_username_only(self):
        result, _ = resolve_and_validate('http://admin@example.com/')
        assert result is None


# --- Rate limiter pruning ---

class TestRateLimiterPruning:
    def test_all_detail_pages_render(self, client):
        """Every status code detail page should render without errors."""
        from index import pruned_status_codes
        for sc in pruned_status_codes():
            resp = client.get(f'/{sc.code}')
            # 2xx/4xx/5xx return their actual code; 1xx/3xx return 200
            code = int(sc.code)
            if code < 200 or 300 <= code < 400:
                assert resp.status_code == 200, f"/{sc.code} returned {resp.status_code}"
            else:
                assert resp.status_code == code, f"/{sc.code} returned {resp.status_code}"

    def test_stale_entries_pruned(self):
        """Stale rate limit entries should be cleaned up."""
        import index
        old_prune = index._rate_limit_last_prune
        # Add a stale entry
        _rate_limit['stale-ip'] = [time.time() - 120]
        # Force prune by setting last prune far in the past
        index._rate_limit_last_prune = time.time() - 400
        is_rate_limited('fresh-ip')
        assert 'stale-ip' not in _rate_limit
        index._rate_limit_last_prune = old_prune


# --- RFC link filter ---

class TestRFCLinks:
    def test_single_rfc(self):
        result = str(linkify_rfcs('Defined in RFC 1945.'))
        assert 'href="https://datatracker.ietf.org/doc/html/rfc1945"' in result
        assert 'RFC 1945</a>' in result
        assert 'Defined in' in result

    def test_multiple_rfcs(self):
        result = str(linkify_rfcs('See RFC 2068 and RFC 6455.'))
        assert 'rfc2068' in result
        assert 'rfc6455' in result
        assert result.count('<a ') == 2

    def test_no_rfcs(self):
        text = 'No references here.'
        result = str(linkify_rfcs(text))
        assert result == text
        assert '<a ' not in result

    def test_html_escaping(self):
        """Surrounding text with HTML chars should be escaped."""
        result = str(linkify_rfcs('<script>alert("xss")</script> RFC 1945'))
        assert '<script>' not in result
        assert '&lt;script&gt;' in result
        assert 'rfc1945' in result

    def test_rfc_links_in_rendered_page(self, client):
        """Detail pages should contain clickable RFC links."""
        resp = client.get('/404')  # 404 history references RFC 1945
        html = resp.data.decode()
        assert 'datatracker.ietf.org/doc/html/rfc' in html
        assert 'class="rfc-link"' in html
        assert 'target="_blank"' in html
        assert 'rel="noopener"' in html

    def test_rfc_links_open_externally(self, client):
        """RFC links should open in new tab with noopener."""
        resp = client.get('/404')
        html = resp.data.decode()
        rfc_link = re.search(r'<a href="https://datatracker[^"]*"[^>]*>', html)
        assert rfc_link is not None
        assert 'target="_blank"' in rfc_link.group()
        assert 'rel="noopener"' in rfc_link.group()


# --- Keyboard navigation ---

class TestKeyboardNavigation:
    def test_homepage_has_grid_nav_script(self, client):
        """Homepage should contain the keyboard grid navigation code."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'getVisibleCards' in html
        assert 'getColumns' in html
        assert 'grid-focus' in html

    def test_detail_page_has_arrow_nav(self, client):
        """Detail pages should have arrow key navigation."""
        resp = client.get('/200')
        html = resp.data.decode()
        assert 'ArrowLeft' in html
        assert 'ArrowRight' in html

    def test_grid_focus_css_exists(self, client):
        """The grid-focus CSS class should be in the stylesheet."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.parrot-card.grid-focus' in css


# --- Related codes ---

class TestRelatedCodes:
    def test_detail_page_with_related_shows_section(self, client):
        """Detail pages that have related codes should show 'Commonly confused with'."""
        from index import RELATED_CODES
        # Pick a code that has related codes
        code = next(iter(RELATED_CODES))
        resp = client.get(f'/{code}')
        html = resp.data.decode()
        assert 'Commonly confused with' in html

    def test_detail_page_without_related_hides_section(self, client):
        """Detail pages without related codes should not show the section."""
        from index import RELATED_CODES, status_code_list
        # Find a code that is NOT in RELATED_CODES
        code_without = None
        for sc in status_code_list:
            if sc.code not in RELATED_CODES:
                code_without = sc.code
                break
        assert code_without is not None, "All codes have related codes, cannot test"
        resp = client.get(f'/{code_without}')
        html = resp.data.decode()
        assert 'Commonly confused with' not in html

    def test_related_code_links_point_to_valid_status_codes(self):
        """Every code referenced in related links should be a valid status code."""
        from index import RELATED_CODES, status_code_list
        valid_codes = {sc.code for sc in status_code_list}
        for source_code, related_list in RELATED_CODES.items():
            for target_code, _desc in related_list:
                assert target_code in valid_codes, (
                    f"Related code {target_code} (from {source_code}) "
                    f"not in status_code_list"
                )

    def test_related_codes_source_codes_exist(self):
        """All keys in RELATED_CODES should be codes that exist in status_code_list."""
        from index import RELATED_CODES, status_code_list
        valid_codes = {sc.code for sc in status_code_list}
        for code in RELATED_CODES:
            assert code in valid_codes, (
                f"RELATED_CODES key {code} not found in status_code_list"
            )


# --- STATUS_EXTRA data ---

class TestStatusExtra:
    def test_all_entries_have_required_keys(self):
        """Every STATUS_EXTRA entry must have examples, headers, and code keys."""
        from status_extra import STATUS_EXTRA
        for code, data in STATUS_EXTRA.items():
            assert 'examples' in data, f"{code} missing 'examples'"
            assert 'headers' in data, f"{code} missing 'headers'"
            assert 'code' in data, f"{code} missing 'code'"

    def test_code_snippets_have_language_keys(self):
        """Code snippets dict should have python, node, and go keys."""
        from status_extra import STATUS_EXTRA
        for code, data in STATUS_EXTRA.items():
            snippets = data['code']
            assert 'python' in snippets, f"{code} code missing 'python'"
            assert 'node' in snippets, f"{code} code missing 'node'"
            assert 'go' in snippets, f"{code} code missing 'go'"

    def test_examples_lists_are_non_empty(self):
        """Every STATUS_EXTRA entry should have at least one example."""
        from status_extra import STATUS_EXTRA
        for code, data in STATUS_EXTRA.items():
            assert len(data['examples']) > 0, f"{code} has empty examples list"


# --- HTTP_EXAMPLES data ---

class TestHTTPExamples:
    def test_all_entries_have_request_and_response(self):
        """Every HTTP_EXAMPLES entry must have request and response keys."""
        from http_examples import HTTP_EXAMPLES
        for code, data in HTTP_EXAMPLES.items():
            assert 'request' in data, f"{code} missing 'request'"
            assert 'response' in data, f"{code} missing 'response'"

    def test_response_contains_status_code_number(self):
        """Response strings should contain the correct status code number."""
        from http_examples import HTTP_EXAMPLES
        for code, data in HTTP_EXAMPLES.items():
            assert code in data['response'], (
                f"Response for {code} does not contain the status code number"
            )

    def test_all_entries_are_non_empty_strings(self):
        """Request and response values must be non-empty strings."""
        from http_examples import HTTP_EXAMPLES
        for code, data in HTTP_EXAMPLES.items():
            assert isinstance(data['request'], str) and len(data['request']) > 0, (
                f"{code} request is empty or not a string"
            )
            assert isinstance(data['response'], str) and len(data['response']) > 0, (
                f"{code} response is empty or not a string"
            )


# --- Detail page completeness ---

class TestDetailPageCompleteness:
    def test_200_has_all_sections(self, client):
        """The 200 detail page should render all major content sections."""
        resp = client.get('/200')
        html = resp.data.decode()
        assert 'What does it mean?' in html
        assert 'History' in html
        assert 'When would I see this?' in html
        assert 'Typical headers' in html
        assert 'Code examples' in html
        assert 'Example HTTP exchange' in html
        assert 'Commonly confused with' in html

    def test_curl_copy_button_present(self, client):
        """Detail pages should contain the curl copy button."""
        resp = client.get('/200')
        html = resp.data.decode()
        assert 'id="copy-curl"' in html
        assert 'curl -i' in html


# --- Cheat sheet ---

class TestCheatsheet:
    def test_cheatsheet_contains_thumbnails(self, client):
        """The cheat sheet page should contain thumbnail images."""
        resp = client.get('/cheatsheet')
        html = resp.data.decode()
        assert '<img src="/static/' in html
        assert 'cheat-thumb' in html

    def test_cheatsheet_has_all_five_categories(self, client):
        """The cheat sheet should include all five HTTP status code categories."""
        resp = client.get('/cheatsheet')
        html = resp.data.decode()
        assert 'Informational' in html
        assert 'Success' in html
        assert 'Redirection' in html
        assert 'Client Error' in html
        assert 'Server Error' in html


# --- Quiz data integrity ---

class TestQuizDataIntegrity:
    def test_quiz_embeds_valid_data(self, client):
        """Quiz page should contain valid quiz data with required fields."""
        resp = client.get('/quiz')
        assert resp.status_code == 200
        html = resp.data.decode()
        assert 'allCodes' in html
        assert '"code"' in html
        assert '"name"' in html
        assert '"image"' in html

    def test_quiz_has_all_pruned_codes(self, client):
        """Quiz data should include all status codes that have images."""
        from index import pruned_status_codes
        resp = client.get('/quiz')
        html = resp.data.decode()
        codes = pruned_status_codes()
        for sc in codes:
            assert f'"{sc.code}"' in html, f"Quiz missing code {sc.code}"


# --- Flowchart tree validation ---

class TestFlowchartTree:
    def test_flowchart_result_codes_are_valid(self, client):
        """All status codes referenced in the flowchart should exist in the app."""
        resp = client.get('/flowchart')
        assert resp.status_code == 200
        html = resp.data.decode()
        result_codes = re.findall(r'result:\s*["\'](\d{3})["\']', html)
        assert len(result_codes) > 0, "No result codes found in flowchart"
        from index import status_code_list
        valid_codes = {sc.code for sc in status_code_list}
        for code in result_codes:
            assert code in valid_codes, f"Flowchart references invalid code: {code}"


# --- Data consistency (reverse check) ---

class TestDataConsistency:
    def test_extra_data_keys_are_valid_codes(self):
        """STATUS_EXTRA and HTTP_EXAMPLES should only contain valid status codes."""
        from status_extra import STATUS_EXTRA
        from http_examples import HTTP_EXAMPLES
        from index import status_code_list
        valid_codes = {sc.code for sc in status_code_list}
        for code in STATUS_EXTRA:
            assert code in valid_codes, f"STATUS_EXTRA has orphan key: {code}"
        for code in HTTP_EXAMPLES:
            assert code in valid_codes, f"HTTP_EXAMPLES has orphan key: {code}"


# --- Check-URL redirect behavior ---

class TestCheckURLRedirectBehavior:
    def test_does_not_follow_redirects(self, client):
        """URL tester should report first-hop status, not follow redirects."""
        mock_resp = MagicMock()
        mock_resp.status_code = 301
        mock_resp.headers = {'Location': 'http://example.com/new'}
        mock_resp.elapsed.total_seconds.return_value = 0.1
        addrinfo = [(socket.AF_INET, socket.SOCK_STREAM, 0, '', ('93.184.216.34', 0))]
        with patch('index.socket.getaddrinfo', return_value=addrinfo), \
             patch('requests.head', return_value=mock_resp) as mock_head:
            resp = client.get('/api/check-url?url=http://example.com')
            data = resp.get_json()
            assert data['code'] == 301
            call_kwargs = mock_head.call_args
            assert call_kwargs[1].get('allow_redirects') is False


# --- Return status various codes ---

class TestReturnStatusCodes:
    def test_return_various_codes(self, client):
        """Verify /return/ endpoint returns correct status codes."""
        for code in [200, 201, 301, 404, 500]:
            resp = client.get(f'/return/{code}')
            assert resp.status_code == code, f"/return/{code} returned {resp.status_code}"


class TestSEO:
    def test_sitemap_xml(self, client):
        resp = client.get('/sitemap.xml')
        assert resp.status_code == 200
        assert b'<urlset' in resp.data
        assert b'/200' in resp.data
        assert b'/404' in resp.data

    def test_robots_txt(self, client):
        resp = client.get('/robots.txt')
        assert resp.status_code == 200
        assert b'Sitemap:' in resp.data
        assert b'Disallow: /return/' in resp.data

    def test_canonical_url(self, client):
        resp = client.get('/')
        assert b'rel="canonical"' in resp.data

    def test_detail_page_has_structured_data(self, client):
        resp = client.get('/200')
        html = resp.data.decode()
        assert 'application/ld+json' in html
        assert 'DefinedTerm' in html


class TestEcho:
    def test_echo_get(self, client):
        resp = client.get('/echo?foo=bar')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['method'] == 'GET'
        assert data['args']['foo'] == 'bar'

    def test_echo_post(self, client):
        resp = client.post('/echo', json={'key': 'value'})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['method'] == 'POST'
        assert data['json']['key'] == 'value'

    def test_echo_strips_sensitive_headers(self, client):
        """Echo should not mirror back credential-bearing headers."""
        resp = client.get('/echo', headers={
            'Authorization': 'Bearer secret',
            'Cookie': 'session=abc',
            'X-Custom': 'safe',
        })
        data = resp.get_json()
        header_keys = {k.lower() for k in data['headers']}
        assert 'authorization' not in header_keys
        assert 'cookie' not in header_keys
        assert 'x-custom' in header_keys


class TestRedirectChain:
    def test_redirect_chain(self, client):
        resp = client.get('/redirect/2')
        assert resp.status_code == 302
        assert '/redirect/1' in resp.headers['Location']

    def test_redirect_chain_end(self, client):
        resp = client.get('/redirect/0')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['code'] == 200

    def test_redirect_chain_too_many(self, client):
        resp = client.get('/redirect/11')
        assert resp.status_code == 404

    def test_redirect_chain_boundary(self, client):
        """Max value of 10 should redirect (not 404)."""
        resp = client.get('/redirect/10')
        assert resp.status_code == 302


# --- Delay parameter ---

class TestDelayParameter:
    def test_delay_zero_ignored(self, client):
        """delay=0 should be ignored (falsy)."""
        resp = client.get('/return/200?delay=0')
        assert resp.status_code == 200

    def test_delay_negative_ignored(self, client):
        """Negative delay should be ignored."""
        resp = client.get('/return/200?delay=-1')
        assert resp.status_code == 200

    def test_delay_non_numeric_ignored(self, client):
        """Non-numeric delay should be ignored."""
        resp = client.get('/return/200?delay=abc')
        assert resp.status_code == 200

    def test_delay_over_max_ignored(self, client):
        """Delay over 10s should be ignored."""
        resp = client.get('/return/200?delay=11')
        assert resp.status_code == 200
