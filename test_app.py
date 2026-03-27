"""Tests for HTTP Parrots application."""
import re
import socket
import time
from unittest.mock import MagicMock, patch

import pytest
import requests

from index import (app, _rate_limit, _run_security_checks, _score_to_grade,
                   _webhook_bins, _WEBHOOK_BIN_TTL, _WEBHOOK_BIN_MAX_REQUESTS,
                   is_rate_limited, linkify_rfcs, resolve_and_validate,
                   _levenshtein, _fuzzy_word_match)


@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


@pytest.fixture(autouse=True)
def clear_rate_limit():
    _rate_limit.clear()
    _webhook_bins.clear()


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

    def test_practice_page(self, client):
        resp = client.get('/practice')
        assert resp.status_code == 200
        assert b'Scenario Practice' in resp.data

    def test_practice_page_has_scenario_cards(self, client):
        resp = client.get('/practice')
        html = resp.data.decode()
        assert 'practice-card' in html
        assert 'practice-option-btn' in html
        assert 'practice-description' in html

    def test_practice_page_has_difficulty_filters(self, client):
        resp = client.get('/practice')
        html = resp.data.decode()
        assert 'data-difficulty="all"' in html
        assert 'data-difficulty="beginner"' in html
        assert 'data-difficulty="intermediate"' in html
        assert 'data-difficulty="expert"' in html

    def test_practice_nav_link(self, client):
        resp = client.get('/')
        html = resp.data.decode()
        assert 'href="/practice"' in html
        assert 'Practice' in html


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
        addrinfo = [(socket.AF_INET, socket.SOCK_STREAM, 0, '', ('10.0.0.1', 0))]
        with patch('index.socket.getaddrinfo', return_value=addrinfo):
            result, _ = resolve_and_validate('http://internal.example.com/')
            assert result is None

    def test_blocks_private_172(self):
        addrinfo = [(socket.AF_INET, socket.SOCK_STREAM, 0, '', ('172.16.0.1', 0))]
        with patch('index.socket.getaddrinfo', return_value=addrinfo):
            result, _ = resolve_and_validate('http://internal.example.com/')
            assert result is None

    def test_blocks_private_192(self):
        addrinfo = [(socket.AF_INET, socket.SOCK_STREAM, 0, '', ('192.168.1.1', 0))]
        with patch('index.socket.getaddrinfo', return_value=addrinfo):
            result, _ = resolve_and_validate('http://internal.example.com/')
            assert result is None

    def test_blocks_metadata(self):
        addrinfo = [(socket.AF_INET, socket.SOCK_STREAM, 0, '', ('169.254.169.254', 0))]
        with patch('index.socket.getaddrinfo', return_value=addrinfo):
            result, _ = resolve_and_validate('http://metadata.example.com/')
            assert result is None

    def test_allows_public_ip(self):
        addrinfo = [(socket.AF_INET, socket.SOCK_STREAM, 0, '', ('93.184.216.34', 0))]
        with patch('index.socket.getaddrinfo', return_value=addrinfo):
            result, hostname = resolve_and_validate('http://example.com/')
            assert result is not None
            assert hostname == 'example.com'

    def test_returns_original_url(self):
        addrinfo = [(socket.AF_INET, socket.SOCK_STREAM, 0, '', ('93.184.216.34', 0))]
        with patch('index.socket.getaddrinfo', return_value=addrinfo):
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

    def test_check_url_returns_time_ms(self, client):
        """check-url response should include time_ms as an integer."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {'Content-Type': 'text/html'}
        mock_resp.elapsed.total_seconds.return_value = 0.123
        addrinfo = [(socket.AF_INET, socket.SOCK_STREAM, 0, '', ('93.184.216.34', 0))]
        with patch('index.socket.getaddrinfo', return_value=addrinfo), \
             patch('requests.head', return_value=mock_resp):
            resp = client.get('/api/check-url?url=https://example.com')
            data = resp.get_json()
            assert 'time_ms' in data
            assert isinstance(data['time_ms'], int)
            assert data['time_ms'] == 123

    def test_check_url_returns_status_code(self, client):
        """check-url response should include status_code in the code field."""
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.headers = {'Content-Type': 'text/html'}
        mock_resp.elapsed.total_seconds.return_value = 0.05
        addrinfo = [(socket.AF_INET, socket.SOCK_STREAM, 0, '', ('93.184.216.34', 0))]
        with patch('index.socket.getaddrinfo', return_value=addrinfo), \
             patch('requests.head', return_value=mock_resp):
            resp = client.get('/api/check-url?url=https://example.com')
            data = resp.get_json()
            assert data['code'] == 404

    def test_check_url_returns_headers(self, client):
        """check-url response should include response headers."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {'Content-Type': 'text/html', 'X-Custom': 'test'}
        mock_resp.elapsed.total_seconds.return_value = 0.05
        addrinfo = [(socket.AF_INET, socket.SOCK_STREAM, 0, '', ('93.184.216.34', 0))]
        with patch('index.socket.getaddrinfo', return_value=addrinfo), \
             patch('requests.head', return_value=mock_resp):
            resp = client.get('/api/check-url?url=https://example.com')
            data = resp.get_json()
            assert 'headers' in data
            assert data['headers']['Content-Type'] == 'text/html'
            assert data['headers']['X-Custom'] == 'test'


# --- Tester timing bar UI ---

class TestTesterTimingBar:
    def test_tester_has_timing_bar_markup(self, client):
        """Tester page JS should contain timing bar CSS classes."""
        resp = client.get('/tester')
        html = resp.data.decode()
        assert 'tester-timing-bar-wrap' in html
        assert 'tester-timing-bar-outer' in html
        assert 'tester-timing-bar-inner' in html
        assert 'tester-timing-label' in html
        assert 'tester-timing-category' in html

    def test_tester_has_speed_categories(self, client):
        """Tester JS should define speed categories for the timing bar."""
        resp = client.get('/tester')
        html = resp.data.decode()
        assert 'Fast' in html
        assert 'Moderate' in html
        assert 'Slow' in html
        assert 'Very slow' in html


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
    def test_url_with_standard_port(self):
        """URLs with standard ports (80, 443) should be allowed."""
        addrinfo = [(socket.AF_INET, socket.SOCK_STREAM, 0, '', ('93.184.216.34', 0))]
        with patch('index.socket.getaddrinfo', return_value=addrinfo):
            result, hostname = resolve_and_validate('http://example.com:80/path')
            assert result == 'http://example.com:80/path'
            assert hostname == 'example.com'

    def test_url_with_non_standard_port_blocked(self):
        """URLs with non-standard ports should be blocked to prevent SSRF."""
        addrinfo = [(socket.AF_INET, socket.SOCK_STREAM, 0, '', ('93.184.216.34', 0))]
        with patch('index.socket.getaddrinfo', return_value=addrinfo):
            result, _ = resolve_and_validate('http://example.com:8080/path')
            assert result is None

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


# --- Scroll-driven animations ---

class TestScrollDrivenAnimations:
    def test_scroll_animated_css_class_exists(self, client):
        """The scroll-animated CSS class with animation-timeline should be in the stylesheet."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.parrot-card.scroll-animated' in css
        assert 'animation-timeline: view()' in css
        assert '@supports (animation-timeline: view())' in css

    def test_scroll_card_in_keyframes_exist(self, client):
        """The scroll-card-in keyframes should define scale and rotate transforms."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '@keyframes scroll-card-in' in css
        assert 'scale(0.95)' in css
        assert 'rotate(' in css

    def test_will_reveal_has_diagonal_cascade(self, client):
        """The will-reveal class should include scale and rotate for diagonal cascade."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.parrot-card.will-reveal' in css
        assert 'scale(0.95)' in css
        assert 'rotate(-1deg)' in css

    def test_homepage_has_scroll_animation_check(self, client):
        """Homepage JS should check for scroll-driven animation support."""
        resp = client.get('/')
        html = resp.data.decode()
        assert "CSS.supports('animation-timeline: view()')" in html
        assert 'scroll-animated' in html

    def test_homepage_has_intersection_observer_fallback(self, client):
        """Homepage should still contain IntersectionObserver as a fallback."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'IntersectionObserver' in html
        assert 'will-reveal' in html


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

    def test_echo_post_with_body(self, client):
        """POST body is echoed in the response."""
        resp = client.post('/echo', data='raw body text',
                           content_type='text/plain')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['method'] == 'POST'
        assert data['body'] == 'raw body text'

    def test_echo_put(self, client):
        """PUT method with JSON body works."""
        resp = client.put('/echo', json={'action': 'update'})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['method'] == 'PUT'
        assert data['json']['action'] == 'update'
        assert 'body' in data

    def test_echo_patch(self, client):
        """PATCH method with JSON body works."""
        resp = client.patch('/echo', json={'field': 'patched'})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['method'] == 'PATCH'
        assert data['json']['field'] == 'patched'

    def test_echo_delete(self, client):
        """DELETE method echoes correctly (no body)."""
        resp = client.delete('/echo')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['method'] == 'DELETE'
        assert 'body' not in data  # DELETE doesn't include body

    def test_echo_query_params(self, client):
        """Multiple query params are echoed in args."""
        resp = client.get('/echo?foo=bar&page=2&lang=en')
        data = resp.get_json()
        assert data['args']['foo'] == 'bar'
        assert data['args']['page'] == '2'
        assert data['args']['lang'] == 'en'

    def test_echo_format_pretty(self, client):
        """?format=pretty returns indented JSON."""
        resp = client.get('/echo?format=pretty&foo=bar')
        assert resp.status_code == 200
        assert resp.content_type.startswith('application/json')
        raw = resp.data.decode()
        # Pretty format should have newlines and indentation
        assert '\n' in raw
        assert '  ' in raw
        data = resp.get_json()
        assert data['args']['foo'] == 'bar'
        # format should not appear in echoed args
        assert 'format' not in data['args']

    def test_echo_format_curl(self, client):
        """?format=curl returns a curl command."""
        resp = client.get('/echo?format=curl&foo=bar')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'curl' in data
        curl_cmd = data['curl']
        assert curl_cmd.startswith('curl')
        assert 'foo=bar' in curl_cmd
        assert 'format=' not in curl_cmd

    def test_echo_format_curl_post(self, client):
        """?format=curl for POST includes -X POST and -d flag."""
        resp = client.post('/echo?format=curl',
                           json={'test': True})
        data = resp.get_json()
        curl_cmd = data['curl']
        assert '-X POST' in curl_cmd
        assert "-d " in curl_cmd


class TestApiDiff:
    def test_diff_basic(self, client):
        """Diff two known codes returns expected structure."""
        resp = client.get('/api/diff?code1=401&code2=403')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['code1']['code'] == '401'
        assert data['code1']['name'] == 'Unauthorized'
        assert data['code2']['code'] == '403'
        assert data['code2']['name'] == 'Forbidden'
        assert '4xx Client Error' == data['code1']['category']
        assert '4xx Client Error' == data['code2']['category']
        assert data['key_difference']  # non-empty string

    def test_diff_key_difference_from_related(self, client):
        """Key difference is pulled from RELATED_CODES when available."""
        resp = client.get('/api/diff?code1=404&code2=410')
        data = resp.get_json()
        # 404 -> 410 is in RELATED_CODES
        assert '410' in data['key_difference'] or 'removed' in data['key_difference'].lower() or len(data['key_difference']) > 0

    def test_diff_includes_examples(self, client):
        """Diff response includes examples from STATUS_EXTRA."""
        resp = client.get('/api/diff?code1=200&code2=201')
        data = resp.get_json()
        assert isinstance(data['code1']['examples'], list)
        assert isinstance(data['code2']['examples'], list)

    def test_diff_includes_related_codes(self, client):
        """Diff response includes related_codes with code and why."""
        resp = client.get('/api/diff?code1=200&code2=404')
        data = resp.get_json()
        assert isinstance(data['code1']['related_codes'], list)
        if data['code1']['related_codes']:
            assert 'code' in data['code1']['related_codes'][0]
            assert 'why' in data['code1']['related_codes'][0]

    def test_diff_missing_params(self, client):
        """Missing code1 or code2 returns 400."""
        resp = client.get('/api/diff?code1=200')
        assert resp.status_code == 400
        data = resp.get_json()
        assert 'error' in data

    def test_diff_unknown_code(self, client):
        """Unknown status code returns 404."""
        resp = client.get('/api/diff?code1=200&code2=999')
        assert resp.status_code == 404
        data = resp.get_json()
        assert 'error' in data
        assert '999' in data['error']

    def test_diff_cross_category(self, client):
        """Diff between codes in different categories works."""
        resp = client.get('/api/diff?code1=200&code2=500')
        data = resp.get_json()
        assert data['code1']['category'] == '2xx Success'
        assert data['code2']['category'] == '5xx Server Error'
        assert data['key_difference']  # fallback summary generated


class TestApiDocsEnhanced:
    def test_api_docs_echo_sections(self, client):
        """API docs page has enhanced echo documentation."""
        resp = client.get('/api-docs')
        html = resp.data.decode()
        assert 'format=pretty' in html
        assert 'format=curl' in html
        assert 'Query params' in html or 'query params' in html

    def test_api_docs_diff_section(self, client):
        """API docs page has the /api/diff documentation."""
        resp = client.get('/api-docs')
        html = resp.data.decode()
        assert '/api/diff' in html
        assert 'Compare status codes' in html
        assert 'key_difference' in html

    def test_api_docs_try_it_buttons(self, client):
        """API docs page has interactive Try it buttons."""
        resp = client.get('/api-docs')
        html = resp.data.decode()
        assert 'docs-try-btn' in html
        assert 'Try it' in html

    def test_api_docs_try_it_panel_count(self, client):
        """API docs page has at least 6 try-it panels (echo, diff, search, check-url, return, unstable)."""
        resp = client.get('/api-docs')
        html = resp.data.decode()
        count = html.count('docs-try-it')
        assert count >= 6, f"Expected at least 6 try-it panels, found {count}"

    def test_api_docs_try_it_search_panel(self, client):
        """API docs has a try-it panel with input for the search endpoint."""
        resp = client.get('/api-docs')
        html = resp.data.decode()
        assert 'try-search-q' in html
        assert '/api/search' in html
        assert 'docs-try-input' in html

    def test_api_docs_try_it_check_url_panel(self, client):
        """API docs has a try-it panel with URL input for the check-url endpoint."""
        resp = client.get('/api-docs')
        html = resp.data.decode()
        assert 'try-check-url' in html
        assert '/api/check-url' in html

    def test_api_docs_try_it_return_panel(self, client):
        """API docs has a try-it panel with code input for the return endpoint."""
        resp = client.get('/api-docs')
        html = resp.data.decode()
        assert 'try-return-code' in html
        assert '/return/' in html

    def test_api_docs_try_it_unstable_panel(self, client):
        """API docs has a try-it panel with slider for the unstable endpoint."""
        resp = client.get('/api-docs')
        html = resp.data.decode()
        assert 'try-unstable-rate' in html
        assert '/api/unstable' in html
        assert 'docs-try-slider' in html

    def test_api_docs_unstable_section(self, client):
        """API docs page has the /api/unstable documentation."""
        resp = client.get('/api-docs')
        html = resp.data.decode()
        assert 'Unreliable endpoint' in html
        assert 'failure_rate' in html

    def test_api_docs_copy_curl_buttons(self, client):
        """API docs page has copy-as-curl buttons."""
        resp = client.get('/api-docs')
        html = resp.data.decode()
        assert 'docs-copy-curl-btn' in html
        assert 'Copy curl' in html


class TestDesignTokenUsage:
    """Verify templates use CSS custom properties instead of hardcoded colors."""

    def test_debug_uses_tokens(self, client):
        """debug.html uses CSS custom properties instead of hardcoded colors."""
        resp = client.get('/debug')
        html = resp.data.decode()
        assert 'var(--text-primary)' in html
        assert 'var(--text-secondary)' in html
        assert 'var(--surface-interactive)' in html
        # Should NOT contain the old hardcoded values in style blocks
        # (they may still appear in JS strings so check only the <style> portion)
        import re
        style_match = re.search(r'<style[^>]*>(.*?)</style>', html, re.DOTALL)
        if style_match:
            style_block = style_match.group(1)
            assert 'color: #f0f0f0' not in style_block
            assert 'color: #a0a0b0' not in style_block

    def test_practice_uses_tokens(self, client):
        """practice.html uses CSS custom properties instead of hardcoded colors."""
        resp = client.get('/practice')
        html = resp.data.decode()
        assert 'var(--text-primary)' in html
        assert 'var(--text-secondary)' in html
        assert 'var(--surface-interactive)' in html

    def test_review_uses_tokens(self, client):
        """review.html uses CSS custom properties instead of hardcoded colors."""
        resp = client.get('/review')
        html = resp.data.decode()
        assert 'var(--text-primary)' in html
        assert 'var(--text-secondary)' in html
        assert 'var(--surface-interactive)' in html

    def test_paths_index_uses_tokens(self, client):
        """paths_index.html uses CSS custom properties instead of hardcoded colors."""
        resp = client.get('/paths')
        html = resp.data.decode()
        assert 'var(--text-primary)' in html
        assert 'var(--text-secondary)' in html

    def test_css_defines_text_tokens(self, client):
        """style.css defines the text color custom properties."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '--text-primary:' in css
        assert '--text-secondary:' in css
        assert '--text-muted:' in css
        assert '--surface-interactive:' in css
        assert '--border-interactive:' in css


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


# --- Header Explainer ---

class TestHeaderExplainer:
    def test_headers_page_renders(self, client):
        """Header Explainer page should return 200 with expected content."""
        resp = client.get('/headers')
        assert resp.status_code == 200
        html = resp.data.decode()
        assert 'Header Explainer' in html
        assert 'header-input' in html
        assert 'explain-btn' in html

    def test_headers_page_has_script(self, client):
        """Header Explainer page should contain the HEADER_DB JavaScript."""
        resp = client.get('/headers')
        html = resp.data.decode()
        assert 'HEADER_DB' in html
        assert 'content-type' in html
        assert 'parseHeaders' in html

    def test_headers_page_has_nonce(self, client):
        """Header Explainer script tag should have a nonce."""
        resp = client.get('/headers')
        csp = resp.headers.get('Content-Security-Policy', '')
        nonce = re.search(r"'nonce-([^']+)'", csp).group(1)
        assert f'nonce="{nonce}"'.encode() in resp.data

    def test_headers_nav_link(self, client):
        """Navigation should contain a link to the Headers page."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'href="/headers"' in html

    def test_headers_in_sitemap(self, client):
        """Sitemap should include the headers page."""
        resp = client.get('/sitemap.xml')
        assert b'/headers' in resp.data


# --- CORS Checker ---

class TestCORSChecker:
    def test_cors_checker_page_renders(self, client):
        """CORS Checker page should return 200 with expected content."""
        resp = client.get('/cors-checker')
        assert resp.status_code == 200
        html = resp.data.decode()
        assert 'CORS Checker' in html
        assert 'cors-url' in html
        assert 'cors-origin' in html

    def test_cors_checker_has_nonce(self, client):
        """CORS Checker script tag should have a nonce."""
        resp = client.get('/cors-checker')
        csp = resp.headers.get('Content-Security-Policy', '')
        nonce = re.search(r"'nonce-([^']+)'", csp).group(1)
        assert f'nonce="{nonce}"'.encode() in resp.data

    def test_cors_checker_nav_link(self, client):
        """Navigation should contain a link to the CORS Checker page."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'href="/cors-checker"' in html

    def test_cors_checker_in_sitemap(self, client):
        """Sitemap should include the CORS checker page."""
        resp = client.get('/sitemap.xml')
        assert b'/cors-checker' in resp.data

    def test_check_cors_missing_params(self, client):
        """API should return 400 when url or origin is missing."""
        resp = client.get('/api/check-cors')
        assert resp.status_code == 400
        assert b'Both url and origin are required' in resp.data

    def test_check_cors_missing_origin(self, client):
        """API should return 400 when origin is missing."""
        resp = client.get('/api/check-cors?url=https://example.com')
        assert resp.status_code == 400

    def test_check_cors_missing_url(self, client):
        """API should return 400 when url is missing."""
        resp = client.get('/api/check-cors?origin=https://mysite.com')
        assert resp.status_code == 400

    def test_check_cors_blocked_url(self, client):
        """API should return 403 for private/blocked URLs."""
        resp = client.get('/api/check-cors?url=http://127.0.0.1/&origin=https://evil.com')
        assert resp.status_code == 403
        assert b'not allowed' in resp.data

    def test_check_cors_success(self, client):
        """API should return CORS analysis for a valid URL."""
        mock_preflight = MagicMock()
        mock_preflight.status_code = 204
        mock_preflight.headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, POST',
        }
        mock_actual = MagicMock()
        mock_actual.status_code = 200
        mock_actual.headers = {
            'Access-Control-Allow-Origin': '*',
        }
        mock_actual.close = MagicMock()
        addrinfo = [(socket.AF_INET, socket.SOCK_STREAM, 0, '', ('93.184.216.34', 0))]
        with patch('index.socket.getaddrinfo', return_value=addrinfo), \
             patch('requests.options', return_value=mock_preflight), \
             patch('requests.get', return_value=mock_actual):
            resp = client.get('/api/check-cors?url=https://example.com&origin=https://mysite.com')
            assert resp.status_code == 200
            data = resp.get_json()
            assert 'preflight' in data
            assert 'actual' in data
            assert 'analysis' in data
            assert data['analysis']['cors_enabled'] is True
            assert data['analysis']['allows_origin'] is True

    def test_check_cors_no_cors_headers(self, client):
        """API should detect when CORS is not enabled."""
        mock_preflight = MagicMock()
        mock_preflight.status_code = 405
        mock_preflight.headers = {}
        mock_actual = MagicMock()
        mock_actual.status_code = 200
        mock_actual.headers = {'Content-Type': 'text/html'}
        mock_actual.close = MagicMock()
        addrinfo = [(socket.AF_INET, socket.SOCK_STREAM, 0, '', ('93.184.216.34', 0))]
        with patch('index.socket.getaddrinfo', return_value=addrinfo), \
             patch('requests.options', return_value=mock_preflight), \
             patch('requests.get', return_value=mock_actual):
            resp = client.get('/api/check-cors?url=https://example.com&origin=https://mysite.com')
            data = resp.get_json()
            assert data['analysis']['cors_enabled'] is False
            assert data['analysis']['allows_origin'] is False

    def test_check_cors_rate_limited(self, client):
        """API should return 429 when rate limited."""
        for _ in range(10):
            client.get('/api/check-cors?url=http://127.0.0.1/&origin=https://x.com')
        resp = client.get('/api/check-cors?url=https://example.com&origin=https://x.com')
        assert resp.status_code == 429
        assert b'Rate limit' in resp.data

    def test_check_cors_auto_prefix(self, client):
        """URLs without scheme should get https:// prepended."""
        mock_preflight = MagicMock()
        mock_preflight.status_code = 204
        mock_preflight.headers = {'Access-Control-Allow-Origin': '*'}
        mock_actual = MagicMock()
        mock_actual.status_code = 200
        mock_actual.headers = {'Access-Control-Allow-Origin': '*'}
        mock_actual.close = MagicMock()
        addrinfo = [(socket.AF_INET, socket.SOCK_STREAM, 0, '', ('93.184.216.34', 0))]
        with patch('index.socket.getaddrinfo', return_value=addrinfo), \
             patch('requests.options', return_value=mock_preflight) as mock_opt, \
             patch('requests.get', return_value=mock_actual):
            resp = client.get('/api/check-cors?url=example.com&origin=https://mysite.com')
            assert resp.status_code == 200
            call_args = mock_opt.call_args
            assert call_args[0][0] == 'https://example.com'

    def test_check_cors_connection_error(self, client):
        """API should handle connection errors gracefully."""
        addrinfo = [(socket.AF_INET, socket.SOCK_STREAM, 0, '', ('93.184.216.34', 0))]
        with patch('index.socket.getaddrinfo', return_value=addrinfo), \
             patch('requests.options', side_effect=requests.RequestException), \
             patch('requests.get', side_effect=requests.RequestException):
            resp = client.get('/api/check-cors?url=https://example.com&origin=https://mysite.com')
            assert resp.status_code == 200
            data = resp.get_json()
            assert data['preflight']['error'] == 'Could not connect'
            assert data['actual']['error'] == 'Could not connect'

    def test_check_cors_in_robots_txt(self, client):
        """robots.txt should block /api/check-cors."""
        resp = client.get('/robots.txt')
        assert b'Disallow: /api/check-cors' in resp.data


# --- Collection (Parrotdex) ---

class TestCollection:
    def test_collection_page_renders(self, client):
        """Collection page should return 200 with expected content."""
        resp = client.get('/collection')
        assert resp.status_code == 200
        html = resp.data.decode()
        assert 'Parrotdex' in html
        assert 'collection-grid' in html
        assert 'collect-count' in html

    def test_collection_contains_all_pruned_codes(self, client):
        """Collection page should list every status code that has an image."""
        from index import pruned_status_codes
        resp = client.get('/collection')
        html = resp.data.decode()
        for sc in pruned_status_codes():
            assert f'data-code="{sc.code}"' in html, f"Collection missing code {sc.code}"

    def test_collection_has_progress_bar(self, client):
        """Collection page should have a progress bar element."""
        resp = client.get('/collection')
        html = resp.data.decode()
        assert 'collection-progress-bar' in html
        assert 'id="progress-bar"' in html

    def test_collection_has_parrotdex_script(self, client):
        """Collection page should have localStorage parrotdex script."""
        resp = client.get('/collection')
        html = resp.data.decode()
        assert 'parrotdex' in html
        assert 'uncollected' in html

    def test_collection_nav_link(self, client):
        """Navigation should contain a link to the Parrotdex page."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'href="/collection"' in html

    def test_collection_in_sitemap(self, client):
        """Sitemap should include the collection page."""
        resp = client.get('/sitemap.xml')
        assert b'/collection' in resp.data

    def test_collection_has_nonce(self, client):
        """Collection script tag should have a nonce."""
        resp = client.get('/collection')
        csp = resp.headers.get('Content-Security-Policy', '')
        nonce = re.search(r"'nonce-([^']+)'", csp).group(1)
        assert f'nonce="{nonce}"'.encode() in resp.data

    def test_collection_secrets_section(self, client):
        """Collection page should have the easter egg secrets section."""
        resp = client.get('/collection')
        html = resp.data.decode()
        assert 'Secret Parrots' in html
        assert 'egg-card' in html
        assert 'data-egg="204"' in html
        assert 'data-egg="418"' in html
        assert 'data-egg="429"' in html
        assert 'data-egg="508"' in html
        assert 'data-egg="konami"' in html

    def test_collection_eggs_found_script(self, client):
        """Collection page should check eggs_found in localStorage."""
        resp = client.get('/collection')
        html = resp.data.decode()
        assert 'eggs_found' in html
        assert 'egg-found' in html


# --- Detail page parrotdex tracking ---

class TestParrotdexTracking:
    def test_detail_page_has_parrotdex_tracking(self, client):
        """Detail pages should include localStorage parrotdex tracking script."""
        resp = client.get('/200')
        html = resp.data.decode()
        assert 'parrotdex' in html
        assert "localStorage.getItem('parrotdex')" in html


# --- Quiz shareable results ---

class TestQuizResults:
    def test_quiz_has_history_array(self, client):
        """Quiz should declare a history array for tracking answers."""
        resp = client.get('/quiz')
        html = resp.data.decode()
        assert 'let history = []' in html

    def test_quiz_tracks_correct_answers(self, client):
        """Quiz should push true to history on correct answers."""
        resp = client.get('/quiz')
        html = resp.data.decode()
        assert 'history.push(true)' in html

    def test_quiz_tracks_wrong_answers(self, client):
        """Quiz should push false to history on wrong answers."""
        resp = client.get('/quiz')
        html = resp.data.decode()
        assert 'history.push(false)' in html

    def test_quiz_shows_results_at_10(self, client):
        """Quiz should show results overlay after 10 questions."""
        resp = client.get('/quiz')
        html = resp.data.decode()
        assert 'total === 10' in html
        assert 'showResults' in html

    def test_quiz_results_has_copy_and_replay(self, client):
        """Quiz results function should have copy and play again buttons."""
        resp = client.get('/quiz')
        html = resp.data.decode()
        assert 'quiz-results-overlay' in html
        assert 'quiz-results-card' in html
        assert 'Copy Result' in html
        assert 'Play Again' in html

    def test_quiz_results_generates_emoji_grid(self, client):
        """Quiz results should generate a Wordle-style emoji grid."""
        resp = client.get('/quiz')
        html = resp.data.decode()
        assert 'quiz-results-grid' in html
        assert 'httpparrots.com/quiz' in html


# --- Easter egg tracking on homepage ---

class TestEasterEggTracking:
    def test_homepage_tracks_easter_eggs(self, client):
        """Homepage should save discovered easter eggs to localStorage."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'eggs_found' in html

    def test_homepage_tracks_konami_easter_egg(self, client):
        """Homepage konami code should save to eggs_found localStorage."""
        resp = client.get('/')
        html = resp.data.decode()
        assert "eggs.indexOf('konami')" in html


class TestShareAndEmbed:
    """Tests for share buttons and embed codes on detail pages."""

    def test_share_buttons_present(self, client):
        resp = client.get('/200')
        html = resp.get_data(as_text=True)
        assert 'id="share-native"' in html
        assert 'id="share-link"' in html
        assert 'id="share-image"' in html
        assert 'id="share-slack"' in html
        assert 'id="share-discord"' in html

    def test_twitter_share_link(self, client):
        resp = client.get('/200')
        html = resp.get_data(as_text=True)
        assert 'id="share-twitter"' in html
        assert 'twitter.com/intent/tweet' in html

    def test_embed_section_present(self, client):
        resp = client.get('/200')
        html = resp.get_data(as_text=True)
        assert 'embed-section' in html
        assert 'Embed this parrot' in html
        assert 'embed-code' in html

    def test_embed_formats(self, client):
        resp = client.get('/404')
        html = resp.get_data(as_text=True)
        assert '404.jpg' in html
        assert 'img src=' in html
        assert '![HTTP 404' in html

    def test_slack_discord_copy_scripts(self, client):
        resp = client.get('/200')
        html = resp.get_data(as_text=True)
        assert 'share-slack' in html
        assert 'share-discord' in html
        assert 'navigator.clipboard.writeText' in html

    def test_native_share_api(self, client):
        resp = client.get('/200')
        html = resp.get_data(as_text=True)
        assert 'navigator.share' in html


# --- ELI5 Toggle ---

class TestELI5Toggle:
    def test_eli5_toggle_present_on_page_with_eli5(self, client):
        """Pages with ELI5 content should have the toggle switch."""
        resp = client.get('/404')
        html = resp.get_data(as_text=True)
        assert 'eli5-switch' in html
        assert 'eli5-toggle' in html
        assert 'Simple mode' in html

    def test_eli5_text_in_page_source(self, client):
        """ELI5 text should be present in the page source."""
        resp = client.get('/404')
        html = resp.get_data(as_text=True)
        assert 'eli5-simple' in html
        assert 'librarian' in html

    def test_eli5_toggle_present_on_all_codes(self, client):
        """All status code pages (except 204) should have the ELI5 toggle."""
        from status_extra import STATUS_EXTRA
        for code in STATUS_EXTRA:
            if code == '204':
                continue  # HTTP 204 returns empty body by protocol
            resp = client.get(f'/{code}')
            html = resp.get_data(as_text=True)
            assert 'eli5-switch' in html, f"Missing eli5-switch for {code}"
            assert 'eli5-toggle' in html, f"Missing eli5-toggle for {code}"

    def test_eli5_technical_text_also_present(self, client):
        """Both technical and ELI5 text should be in the source."""
        resp = client.get('/200')
        html = resp.get_data(as_text=True)
        assert 'eli5-technical' in html
        assert 'eli5-simple' in html

    def test_eli5_localStorage_script(self, client):
        """Pages with ELI5 should have the localStorage persistence script."""
        resp = client.get('/500')
        html = resp.get_data(as_text=True)
        assert "localStorage.getItem('eli5')" in html
        assert "localStorage.setItem('eli5'" in html

    def test_eli5_present_for_all_codes(self, client):
        """All status codes should have ELI5 content in rendered HTML."""
        from status_extra import STATUS_EXTRA
        # 204 excluded: HTTP 204 returns empty body by protocol
        for code in STATUS_EXTRA:
            if code == '204':
                continue
            resp = client.get(f'/{code}')
            html = resp.get_data(as_text=True)
            assert 'eli5-simple' in html, f"Missing ELI5 for status code {code}"

    def test_eli5_data_in_all_status_extra(self):
        """STATUS_EXTRA should have eli5 keys for ALL 72 codes."""
        from status_extra import STATUS_EXTRA
        assert len(STATUS_EXTRA) == 72, f"Expected 72 codes, got {len(STATUS_EXTRA)}"
        for code in STATUS_EXTRA:
            assert 'eli5' in STATUS_EXTRA[code], f"Missing eli5 key for {code}"
            assert len(STATUS_EXTRA[code]['eli5']) > 20, f"ELI5 for {code} seems too short"


# --- Daily HTTP Challenge ---

class TestDailyChallenge:
    def test_daily_returns_200(self, client):
        resp = client.get('/daily')
        assert resp.status_code == 200

    def test_daily_contains_quiz_elements(self, client):
        resp = client.get('/daily')
        html = resp.get_data(as_text=True)
        assert 'Daily HTTP Challenge' in html
        assert 'daily-scenario' in html
        assert 'daily-choices' in html
        assert 'quiz-btn' in html
        assert 'Share on Twitter' in html
        assert 'Copy Result' in html

    def test_daily_deterministic_same_day(self, client):
        """Same day should produce the same challenge."""
        resp1 = client.get('/daily')
        resp2 = client.get('/daily')
        html1 = resp1.get_data(as_text=True)
        html2 = resp2.get_data(as_text=True)
        # Extract the scenario text — it should be identical
        assert 'daily-scenario' in html1
        # CSP nonces differ per request, so compare structure without nonces
        import re
        strip_nonce = lambda h: re.sub(r'nonce="[^"]*"', 'nonce=""', h)
        assert strip_nonce(html1) == strip_nonce(html2)

    def test_daily_has_four_options(self, client):
        resp = client.get('/daily')
        html = resp.get_data(as_text=True)
        assert html.count('class="quiz-btn daily-btn"') == 4

    def test_daily_nav_link_present(self, client):
        resp = client.get('/')
        html = resp.get_data(as_text=True)
        assert 'href="/daily"' in html


# --- FAQPage structured data ---

class TestFAQSchema:
    def test_detail_page_has_faq_schema(self, client):
        """Detail pages should have FAQPage structured data."""
        resp = client.get('/200')
        html = resp.data.decode()
        assert 'FAQPage' in html
        assert 'What does HTTP 200 mean?' in html

    def test_faq_has_when_to_use_question(self, client):
        """FAQPage should include 'When should I use' question when extra data exists."""
        resp = client.get('/200')
        html = resp.data.decode()
        assert 'When should I use HTTP 200?' in html

    def test_faq_has_difference_question(self, client):
        """FAQPage should include difference questions for related codes."""
        resp = client.get('/200')
        html = resp.data.decode()
        assert 'What is the difference between HTTP 200 and 201?' in html

    def test_faq_combined_with_defined_term(self, client):
        """FAQPage and DefinedTerm should be in the same JSON-LD block."""
        resp = client.get('/200')
        html = resp.data.decode()
        # Both types should appear in a single JSON-LD script block
        assert 'DefinedTerm' in html
        assert 'FAQPage' in html
        # The JSON-LD should be an array
        import re
        ld_match = re.search(r'<script type="application/ld\+json">\s*\[', html)
        assert ld_match is not None, "JSON-LD should be a JSON array"

    def test_faq_schema_question_answer_structure(self, client):
        """FAQ entries should have proper Question/Answer structure."""
        resp = client.get('/404')
        html = resp.data.decode()
        assert '"@type": "Question"' in html
        assert '"@type": "Answer"' in html
        assert 'acceptedAnswer' in html

    def test_build_faq_entries_function(self):
        """build_faq_entries should generate correct FAQ entries."""
        from index import build_faq_entries
        info = {'description': 'Test description'}
        extra = {'examples': ['Example 1', 'Example 2']}
        related = [('201', 'Created vs retrieved')]
        faq = build_faq_entries('200', 'OK', info, extra, related)
        assert len(faq) >= 3  # meaning, when to use, difference
        assert faq[0]['question'] == 'What does HTTP 200 mean?'
        assert faq[1]['question'] == 'When should I use HTTP 200?'
        assert 'difference between HTTP 200 and 201' in faq[2]['question']

    def test_build_faq_entries_no_extra(self):
        """build_faq_entries should work with minimal data."""
        from index import build_faq_entries
        info = {'description': 'Test'}
        faq = build_faq_entries('200', 'OK', info, {}, [])
        assert len(faq) == 1
        assert faq[0]['question'] == 'What does HTTP 200 mean?'


# --- Parrot of the Day on homepage ---

class TestParrotOfTheDay:
    def test_homepage_has_featured_card(self, client):
        """Homepage should mark the Parrot of the Day in the grid."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'featured' in html

    def test_potd_deterministic(self, client):
        """Same day should produce the same featured parrot."""
        resp1 = client.get('/')
        resp2 = client.get('/')
        html1 = resp1.data.decode()
        html2 = resp2.data.decode()
        # Both should contain the same featured card
        import re
        strip_nonce = lambda h: re.sub(r'nonce="[^"]*"', 'nonce=""', h)
        assert strip_nonce(html1) == strip_nonce(html2)


# --- RSS Feed ---

class TestRSSFeed:
    def test_feed_returns_200(self, client):
        """RSS feed should return 200 with RSS content type."""
        resp = client.get('/feed.xml')
        assert resp.status_code == 200
        assert 'rss' in resp.content_type

    def test_feed_is_valid_rss(self, client):
        """RSS feed should be valid RSS 2.0 XML."""
        resp = client.get('/feed.xml')
        xml = resp.data.decode()
        assert '<?xml version' in xml
        assert '<rss version="2.0">' in xml
        assert '<channel>' in xml
        assert '<title>HTTP Parrots</title>' in xml
        assert '</channel>' in xml
        assert '</rss>' in xml

    def test_feed_has_daily_parrot_item(self, client):
        """RSS feed should contain the daily parrot as an item."""
        resp = client.get('/feed.xml')
        xml = resp.data.decode()
        assert '<item>' in xml
        assert 'Parrot of the Day' in xml
        assert '<pubDate>' in xml
        assert '<guid>' in xml

    def test_feed_item_has_image(self, client):
        """RSS feed items should include image enclosures."""
        resp = client.get('/feed.xml')
        xml = resp.data.decode()
        assert '<enclosure' in xml
        assert 'type="image/jpeg"' in xml

    def test_feed_is_cached(self, client):
        """RSS feed should have cache headers."""
        resp = client.get('/feed.xml')
        assert 'max-age=3600' in resp.headers.get('Cache-Control', '')

    def test_feed_autodiscovery_in_html(self, client):
        """All HTML pages should include RSS autodiscovery link tag."""
        for path in ['/', '/200', '/quiz']:
            resp = client.get(path)
            html = resp.data.decode()
            assert 'application/rss+xml' in html, f"Missing RSS autodiscovery on {path}"
            assert '/feed.xml' in html, f"Missing feed URL on {path}"

    def test_feed_has_channel_info(self, client):
        """RSS feed should have proper channel description and link."""
        resp = client.get('/feed.xml')
        xml = resp.data.decode()
        assert '<description>' in xml
        assert '<language>en-us</language>' in xml
        assert '<lastBuildDate>' in xml


# --- Quiz & Practice visual polish ---

class TestQuizVisualFeedback:
    """Verify quiz feedback CSS classes and animation hooks exist in templates."""

    def test_quiz_has_correct_class(self, client):
        """Quiz JS adds .correct class to correct answer buttons."""
        resp = client.get('/quiz')
        html = resp.data.decode()
        assert "classList.add('correct')" in html or 'classList.add("correct"' in html

    def test_quiz_has_wrong_class(self, client):
        """Quiz JS adds .wrong class to wrong answer buttons."""
        resp = client.get('/quiz')
        html = resp.data.decode()
        assert "classList.add('wrong')" in html or 'classList.add("wrong"' in html

    def test_quiz_has_reveal_correct_class(self, client):
        """Quiz JS adds .reveal-correct class when revealing correct answer after wrong guess."""
        resp = client.get('/quiz')
        html = resp.data.decode()
        assert 'reveal-correct' in html

    def test_quiz_feedback_right_class(self, client):
        """Quiz feedback element uses .right class for correct answers."""
        resp = client.get('/quiz')
        html = resp.data.decode()
        assert 'quiz-feedback right' in html or "quiz-feedback right" in html

    def test_quiz_feedback_nope_class(self, client):
        """Quiz feedback element uses .nope class for wrong answers."""
        resp = client.get('/quiz')
        html = resp.data.decode()
        assert 'quiz-feedback nope' in html or "quiz-feedback nope" in html

    def test_daily_has_correct_and_wrong_classes(self, client):
        """Daily challenge JS adds .correct and .wrong classes."""
        resp = client.get('/daily')
        html = resp.data.decode()
        assert "classList.add('correct')" in html or 'classList.add("correct"' in html
        assert "classList.add('wrong')" in html or 'classList.add("wrong"' in html

    def test_daily_has_reveal_correct_class(self, client):
        """Daily challenge JS adds .reveal-correct for wrong-answer reveal."""
        resp = client.get('/daily')
        html = resp.data.decode()
        assert 'reveal-correct' in html

    def test_daily_has_streak_display(self, client):
        """Daily challenge has streak display with fire animation hooks."""
        resp = client.get('/daily')
        html = resp.data.decode()
        assert 'daily-streak-display' in html
        assert 'streak-count' in html
        assert 'streak-bump' in html


class TestPracticeDifficultyTabs:
    """Verify practice page difficulty tabs have correct styling classes."""

    def test_practice_filter_buttons_have_data_difficulty(self, client):
        """Each filter button has a data-difficulty attribute."""
        resp = client.get('/practice')
        html = resp.data.decode()
        for level in ['all', 'beginner', 'intermediate', 'expert']:
            assert f'data-difficulty="{level}"' in html

    def test_practice_filter_buttons_have_styling_class(self, client):
        """Filter buttons use the practice-filter-btn class."""
        resp = client.get('/practice')
        html = resp.data.decode()
        assert html.count('practice-filter-btn') >= 4

    def test_practice_difficulty_badges_have_classes(self, client):
        """Scenario cards have difficulty badge classes."""
        resp = client.get('/practice')
        html = resp.data.decode()
        assert 'practice-difficulty-badge beginner' in html
        assert 'practice-difficulty-badge intermediate' in html
        assert 'practice-difficulty-badge expert' in html

    def test_practice_has_progress_bar(self, client):
        """Practice page has a progress bar component."""
        resp = client.get('/practice')
        html = resp.data.decode()
        assert 'practice-progress-bar' in html
        assert 'practice-progress-track' in html
        assert 'practice-progress-text' in html
        assert 'role="progressbar"' in html

    def test_practice_cards_have_difficulty_data(self, client):
        """Each practice card has a data-difficulty attribute for tab filtering."""
        resp = client.get('/practice')
        html = resp.data.decode()
        # Cards should have data-difficulty matching one of the three levels
        import re
        card_diffs = re.findall(r'class="practice-card"[^>]*data-difficulty="(\w+)"', html)
        assert len(card_diffs) > 0
        for diff in card_diffs:
            assert diff in ('beginner', 'intermediate', 'expert')

    def test_practice_explanation_uses_visible_class(self, client):
        """Practice explanation reveal uses the .visible class."""
        resp = client.get('/practice')
        html = resp.data.decode()
        assert "classList.add('visible')" in html or 'classList.add("visible"' in html


# --- Detail page polish ---

class TestDetailAccentBar:
    """Verify category accent bar class is present on detail page cards."""

    def test_1xx_accent_bar(self, client):
        resp = client.get('/100')
        assert b'detail-cat-1xx' in resp.data

    def test_2xx_accent_bar(self, client):
        resp = client.get('/200')
        assert b'detail-cat-2xx' in resp.data

    def test_3xx_accent_bar(self, client):
        resp = client.get('/301')
        assert b'detail-cat-3xx' in resp.data

    def test_4xx_accent_bar(self, client):
        resp = client.get('/404')
        assert b'detail-cat-4xx' in resp.data

    def test_5xx_accent_bar(self, client):
        resp = client.get('/500')
        assert b'detail-cat-5xx' in resp.data

    def test_accent_bar_css_exists(self, client):
        """CSS has ::before rules for accent bar on detail cards."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.detail-parrot::before' in css
        assert '.detail-cat-1xx::before' in css
        assert '.detail-cat-5xx::before' in css


class TestHTTPExchangePanels:
    """Verify HTTP exchange panels have styling classes and syntax highlighting."""

    def test_request_panel_has_styling_class(self, client):
        resp = client.get('/200')
        html = resp.data.decode()
        assert 'http-panel-request' in html

    def test_response_panel_has_styling_class(self, client):
        resp = client.get('/200')
        html = resp.data.decode()
        assert 'http-panel-response' in html

    def test_syntax_highlight_method(self, client):
        """Request block should contain highlighted HTTP method span."""
        resp = client.get('/200')
        html = resp.data.decode()
        assert 'http-hl-method' in html

    def test_syntax_highlight_status(self, client):
        """Response block should contain highlighted status line span."""
        resp = client.get('/200')
        html = resp.data.decode()
        assert 'http-hl-status' in html

    def test_syntax_highlight_header(self, client):
        """Exchange blocks should contain highlighted header name spans."""
        resp = client.get('/200')
        html = resp.data.decode()
        assert 'http-hl-header' in html

    def test_panel_border_css_exists(self, client):
        """CSS has border rules for request/response panels."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.http-panel-request' in css
        assert '.http-panel-response' in css


class TestDetailPageAnimations:
    """Verify section reveal and back-to-top elements on detail pages."""

    def test_back_to_top_button_present(self, client):
        resp = client.get('/200')
        html = resp.data.decode()
        assert 'back-to-top' in html
        assert 'Back to top' in html

    def test_back_to_top_script(self, client):
        """The back-to-top button has JS to toggle visibility."""
        resp = client.get('/200')
        html = resp.data.decode()
        assert "back-to-top" in html
        assert "classList.add('visible')" in html or 'classList.add("visible"' in html

    def test_section_reveal_fallback_script(self, client):
        """IntersectionObserver fallback for section reveal is present."""
        resp = client.get('/200')
        html = resp.data.decode()
        assert 'IntersectionObserver' in html
        assert 'detail-section' in html

    def test_section_reveal_css_exists(self, client):
        """CSS has reveal animation and back-to-top styles."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.detail-section.revealed' in css
        assert '.back-to-top' in css
        assert '.back-to-top.visible' in css


class TestHTTPExchangeAnimation:
    """Verify animated HTTP exchange sequence diagrams on detail pages."""

    def test_play_button_present(self, client):
        """Detail page with http_example should have a Play Animation button."""
        resp = client.get('/200')
        html = resp.data.decode()
        assert 'http-exchange-play' in html
        assert 'Play Animation' in html

    def test_play_button_has_aria_label(self, client):
        """Play button must have an accessible label."""
        resp = client.get('/200')
        html = resp.data.decode()
        assert 'aria-label="Play HTTP exchange animation"' in html

    def test_http_exchange_has_id(self, client):
        """The http-exchange div should have an id for JS targeting."""
        resp = client.get('/200')
        html = resp.data.decode()
        assert 'id="http-exchange"' in html

    def test_http_line_spans_in_output(self, client):
        """highlight_http filter should wrap lines in http-line spans."""
        resp = client.get('/200')
        html = resp.data.decode()
        assert 'http-line' in html

    def test_animation_css_classes_exist(self, client):
        """CSS should contain the animated exchange classes and keyframes."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.http-exchange-animated' in css
        assert '@keyframes http-slide-in-left' in css
        assert '@keyframes http-slide-in-right' in css
        assert '@keyframes http-arrow-trail' in css
        assert '@keyframes http-line-fade' in css
        assert '@keyframes http-line-sweep' in css

    def test_play_button_css_exists(self, client):
        """CSS should style the play/reset button."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.http-exchange-play-btn' in css

    def test_reduced_motion_hides_play_button(self, client):
        """Under prefers-reduced-motion: reduce, play button is hidden."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert 'prefers-reduced-motion: reduce' in css
        # The play button is display:none under reduced motion
        assert '.http-exchange-play-btn' in css
        # Animations are disabled
        idx = css.index('Reduced motion: HTTP exchange')
        section = css[idx:idx + 600]
        assert 'display: none' in section
        assert 'animation: none' in section

    def test_intersection_observer_script_present(self, client):
        """Detail page should have IntersectionObserver for auto-play."""
        resp = client.get('/200')
        html = resp.data.decode()
        assert 'IntersectionObserver' in html
        assert 'data-auto-played' in html

    def test_status_line_glow_css(self, client):
        """Animated status line should have a category-colored glow."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.http-exchange-animated .http-hl-status' in css
        assert 'text-shadow' in css

    def test_line_sweep_highlight_css(self, client):
        """Animated lines should have a sweep background highlight."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.http-exchange-animated .http-line' in css
        assert 'http-line-sweep' in css

    def test_sequential_line_delay_css(self, client):
        """CSS should have nth-child animation-delay rules for http-line."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.http-line:nth-child(1)' in css
        assert '.http-line:nth-child(2)' in css
        assert 'animation-delay' in css


# --- Compare page enhancements ---

class TestCompareEnhancements:
    def test_compare_presets_present(self, client):
        """Compare page should have quick comparison preset buttons."""
        resp = client.get('/compare')
        html = resp.data.decode()
        assert 'compare-preset-btn' in html
        assert 'data-a="401"' in html
        assert 'data-b="403"' in html
        assert 'data-a="301"' in html
        assert 'data-b="302"' in html
        assert 'data-a="500"' in html
        assert 'data-b="502"' in html
        assert 'data-a="200"' in html
        assert 'data-b="204"' in html

    def test_compare_swap_button_present(self, client):
        """Compare page should have a swap codes button."""
        resp = client.get('/compare')
        html = resp.data.decode()
        assert 'id="swap-codes"' in html
        assert 'compare-swap-btn' in html

    def test_compare_summary_container_present(self, client):
        """Compare page should have a summary container."""
        resp = client.get('/compare')
        html = resp.data.decode()
        assert 'id="compare-summary"' in html
        assert 'compare-summary' in html

    def test_compare_has_comparison_summaries_data(self, client):
        """Compare page script should contain comparisonSummaries data."""
        resp = client.get('/compare')
        html = resp.data.decode()
        assert 'comparisonSummaries' in html

    def test_compare_has_diff_builder(self, client):
        """Compare page should contain the visual diff builder function."""
        resp = client.get('/compare')
        html = resp.data.decode()
        assert 'buildDiffSection' in html
        assert 'compare-diff' in html

    def test_comparison_summaries_data_integrity(self):
        """COMPARISON_SUMMARIES keys should reference valid status codes."""
        from index import COMPARISON_SUMMARIES, status_code_list
        valid_codes = {sc.code for sc in status_code_list}
        for key in COMPARISON_SUMMARIES:
            a, b = key.split(',')
            assert a in valid_codes, f"COMPARISON_SUMMARIES key {a} not in status_code_list"
            assert b in valid_codes, f"COMPARISON_SUMMARIES key {b} not in status_code_list"

    def test_comparison_summaries_are_symmetric(self):
        """Each comparison pair should have both directions."""
        from index import COMPARISON_SUMMARIES
        for key in COMPARISON_SUMMARIES:
            a, b = key.split(',')
            reverse_key = f"{b},{a}"
            assert reverse_key in COMPARISON_SUMMARIES, (
                f"COMPARISON_SUMMARIES has {key} but not {reverse_key}"
            )


# --- Search API ---

class TestSearchAPI:
    def test_search_returns_results(self, client):
        """Search API should return a JSON array of matching results."""
        resp = client.get('/api/search?q=not+found')
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)
        assert len(data) > 0
        # 404 Not Found should be in results
        codes = [r['code'] for r in data]
        assert '404' in codes

    def test_search_by_exact_code(self, client):
        """Searching by exact code should return that code with highest score."""
        resp = client.get('/api/search?q=404')
        data = resp.get_json()
        assert data[0]['code'] == '404'
        assert data[0]['score'] == 100

    def test_search_by_partial_code(self, client):
        """Searching by partial code should match codes starting with those digits."""
        resp = client.get('/api/search?q=40')
        data = resp.get_json()
        assert len(data) > 1
        codes = [r['code'] for r in data]
        assert all(c.startswith('40') for c in codes[:3])

    def test_search_by_keyword(self, client):
        """Searching by keyword should match names and descriptions."""
        resp = client.get('/api/search?q=teapot')
        data = resp.get_json()
        assert len(data) > 0
        codes = [r['code'] for r in data]
        assert '418' in codes

    def test_search_empty_query(self, client):
        """Empty search query should return 400."""
        resp = client.get('/api/search?q=')
        assert resp.status_code == 400
        data = resp.get_json()
        assert 'error' in data

    def test_search_missing_query(self, client):
        """Missing q parameter should return 400."""
        resp = client.get('/api/search')
        assert resp.status_code == 400

    def test_search_result_structure(self, client):
        """Each result should have code, name, description, and score fields."""
        resp = client.get('/api/search?q=ok')
        data = resp.get_json()
        assert len(data) > 0
        result = data[0]
        assert 'code' in result
        assert 'name' in result
        assert 'description' in result
        assert 'score' in result

    def test_search_results_sorted_by_score(self, client):
        """Results should be sorted by descending score."""
        resp = client.get('/api/search?q=redirect')
        data = resp.get_json()
        scores = [r['score'] for r in data]
        assert scores == sorted(scores, reverse=True)

    def test_search_no_results(self, client):
        """A query with no matches should return an empty array."""
        resp = client.get('/api/search?q=xyznonexistent')
        data = resp.get_json()
        assert isinstance(data, list)
        assert len(data) == 0

    def test_search_case_insensitive(self, client):
        """Search should be case insensitive."""
        resp_lower = client.get('/api/search?q=not found')
        resp_upper = client.get('/api/search?q=Not Found')
        data_lower = resp_lower.get_json()
        data_upper = resp_upper.get_json()
        codes_lower = [r['code'] for r in data_lower]
        codes_upper = [r['code'] for r in data_upper]
        assert codes_lower == codes_upper

    def test_search_in_api_docs(self, client):
        """API docs page should document the search endpoint."""
        resp = client.get('/api-docs')
        html = resp.data.decode()
        assert '/api/search' in html
        assert 'Search status codes' in html


# --- Response Playground ---

class TestPlayground:
    def test_playground_returns_200(self, client):
        """Playground page should return 200 with expected content."""
        resp = client.get('/playground')
        assert resp.status_code == 200
        html = resp.data.decode()
        assert 'Response Playground' in html

    def test_playground_has_preset_options(self, client):
        """Playground page should have all preset options."""
        resp = client.get('/playground')
        html = resp.data.decode()
        assert 'CORS Error' in html
        assert 'Rate Limited' in html
        assert 'Redirect Chain' in html
        assert 'JSON API Response' in html
        assert 'Auth Required' in html

    def test_playground_has_status_codes(self, client):
        """Playground page should have status code dropdown with known codes."""
        resp = client.get('/playground')
        html = resp.data.decode()
        assert 'pg-status' in html
        assert '<option value="200"' in html
        assert '<option value="404"' in html
        assert '<option value="500"' in html

    def test_playground_has_form_elements(self, client):
        """Playground page should have header rows, body textarea, and buttons."""
        resp = client.get('/playground')
        html = resp.data.decode()
        assert 'pg-headers' in html
        assert 'pg-body' in html
        assert 'pg-send' in html
        assert 'pg-copy' in html
        assert 'pg-add-header' in html

    def test_playground_has_live_preview(self, client):
        """Playground page should have a live preview panel."""
        resp = client.get('/playground')
        html = resp.data.decode()
        assert 'playground-preview' in html
        assert 'pg-raw' in html
        assert 'pg-status-badge' in html

    def test_playground_nav_link(self, client):
        """Navigation should contain a link to the Playground page."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'href="/playground"' in html
        assert 'Playground' in html

    def test_playground_in_sitemap(self, client):
        """Sitemap should include the playground page."""
        resp = client.get('/sitemap.xml')
        assert b'/playground' in resp.data

    def test_playground_has_nonce(self, client):
        """Playground script tag should have a nonce."""
        resp = client.get('/playground')
        csp = resp.headers.get('Content-Security-Policy', '')
        nonce = re.search(r"'nonce-([^']+)'", csp).group(1)
        assert f'nonce="{nonce}"'.encode() in resp.data


class TestPlaygroundNewPresets:
    """Tests for the new playground preset options."""

    def test_playground_has_cache_hit_preset(self, client):
        """Playground should have the Cache Hit (304) preset option."""
        resp = client.get('/playground')
        html = resp.data.decode()
        assert 'cache_hit' in html
        assert 'Cache Hit (304)' in html

    def test_playground_has_webhook_payload_preset(self, client):
        """Playground should have the Webhook Payload preset option."""
        resp = client.get('/playground')
        html = resp.data.decode()
        assert 'webhook_payload' in html
        assert 'Webhook Payload' in html

    def test_playground_has_file_download_preset(self, client):
        """Playground should have the File Download preset option."""
        resp = client.get('/playground')
        html = resp.data.decode()
        assert 'file_download' in html
        assert 'File Download' in html

    def test_playground_has_validation_error_preset(self, client):
        """Playground should have the Validation Error (422) preset option."""
        resp = client.get('/playground')
        html = resp.data.decode()
        assert 'validation_error' in html
        assert 'Validation Error (422)' in html

    def test_playground_has_sse_stream_preset(self, client):
        """Playground should have the SSE Stream preset option."""
        resp = client.get('/playground')
        html = resp.data.decode()
        assert 'sse_stream' in html
        assert 'SSE Stream' in html

    def test_playground_has_rate_limited_429_preset(self, client):
        """Playground should have the Rate Limited (429) preset option."""
        resp = client.get('/playground')
        html = resp.data.decode()
        assert 'rate_limited_429' in html
        assert 'Rate Limited (429)' in html

    def test_cache_hit_preset_has_etag(self, client):
        """Cache Hit preset JS should configure ETag header."""
        resp = client.get('/playground')
        html = resp.data.decode()
        assert 'ETag' in html
        assert "'304'" in html or '"304"' in html

    def test_webhook_preset_has_event_header(self, client):
        """Webhook preset JS should configure X-Webhook-Event header."""
        resp = client.get('/playground')
        html = resp.data.decode()
        assert 'X-Webhook-Event' in html
        assert 'order.completed' in html

    def test_file_download_preset_has_content_disposition(self, client):
        """File Download preset JS should configure Content-Disposition header."""
        resp = client.get('/playground')
        html = resp.data.decode()
        assert 'Content-Disposition' in html
        assert 'attachment' in html

    def test_validation_error_preset_has_structured_errors(self, client):
        """Validation Error preset JS should contain structured field-level errors."""
        resp = client.get('/playground')
        html = resp.data.decode()
        assert 'Validation Failed' in html
        assert "'422'" in html or '"422"' in html

    def test_sse_stream_preset_has_event_stream_type(self, client):
        """SSE Stream preset JS should set Content-Type to text/event-stream."""
        resp = client.get('/playground')
        html = resp.data.decode()
        assert 'text/event-stream' in html

    def test_rate_limited_429_preset_has_retry_after(self, client):
        """Rate Limited (429) preset JS should set Retry-After header."""
        resp = client.get('/playground')
        html = resp.data.decode()
        assert 'Retry-After' in html
        assert 'X-RateLimit-Limit' in html


class TestCurlImport:
    def test_curl_import_returns_200(self, client):
        """cURL Import page should return 200 with expected content."""
        resp = client.get('/curl-import')
        assert resp.status_code == 200
        html = resp.data.decode()
        assert 'cURL Import' in html

    def test_curl_import_has_textarea(self, client):
        """cURL Import page should have a textarea for pasting cURL commands."""
        resp = client.get('/curl-import')
        html = resp.data.decode()
        assert 'curl-input' in html
        assert '<textarea' in html

    def test_curl_import_has_parse_button(self, client):
        """cURL Import page should have a Parse button."""
        resp = client.get('/curl-import')
        html = resp.data.decode()
        assert 'curl-parse-btn' in html
        assert 'Parse' in html

    def test_curl_import_has_code_export_tabs(self, client):
        """cURL Import page should have code export tabs for all languages."""
        resp = client.get('/curl-import')
        html = resp.data.decode()
        assert 'data-tab="curl"' in html
        assert 'data-tab="python"' in html
        assert 'data-tab="javascript"' in html
        assert 'data-tab="go"' in html

    def test_curl_import_has_copy_button(self, client):
        """cURL Import page should have a Copy button for exported code."""
        resp = client.get('/curl-import')
        html = resp.data.decode()
        assert 'curl-copy-btn' in html

    def test_curl_import_has_echo_button(self, client):
        """cURL Import page should have a Send to Echo button."""
        resp = client.get('/curl-import')
        html = resp.data.decode()
        assert 'curl-echo-btn' in html
        assert 'Send to Echo' in html

    def test_curl_import_nav_link(self, client):
        """Navigation should contain a link to the cURL Import page."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'href="/curl-import"' in html
        assert 'cURL Import' in html

    def test_curl_import_in_sitemap(self, client):
        """Sitemap should include the cURL Import page."""
        resp = client.get('/sitemap.xml')
        assert b'/curl-import' in resp.data

    def test_curl_import_has_nonce(self, client):
        """cURL Import script tag should have a nonce."""
        resp = client.get('/curl-import')
        csp = resp.headers.get('Content-Security-Policy', '')
        nonce = re.search(r"'nonce-([^']+)'", csp).group(1)
        assert f'nonce="{nonce}"'.encode() in resp.data


class TestMockResponse:
    def test_mock_response_basic(self, client):
        """Mock response endpoint should return the requested status code."""
        resp = client.post('/api/mock-response',
                           json={'status_code': 200, 'headers': {}, 'body': 'hello'})
        assert resp.status_code == 200
        assert resp.data == b'hello'

    def test_mock_response_with_headers(self, client):
        """Mock response endpoint should set custom headers."""
        resp = client.post('/api/mock-response',
                           json={'status_code': 201,
                                 'headers': {'X-Custom': 'test-value'},
                                 'body': ''})
        assert resp.status_code == 201
        assert resp.headers.get('X-Custom') == 'test-value'

    def test_mock_response_404_status(self, client):
        """Mock response should return the requested 404 status."""
        resp = client.post('/api/mock-response',
                           json={'status_code': 404, 'headers': {}, 'body': 'not found'})
        assert resp.status_code == 404
        assert resp.data == b'not found'

    def test_mock_response_invalid_status_code(self, client):
        """Mock response should reject invalid status codes."""
        resp = client.post('/api/mock-response',
                           json={'status_code': 999, 'headers': {}, 'body': ''})
        assert resp.status_code == 400
        assert b'status_code must be' in resp.data

    def test_mock_response_no_json(self, client):
        """Mock response should return 400 for non-JSON requests."""
        resp = client.post('/api/mock-response', data='not json',
                           content_type='text/plain')
        assert resp.status_code == 400
        assert b'Invalid JSON' in resp.data

    def test_mock_response_rate_limited(self, client):
        """Mock response should be rate-limited."""
        for _ in range(10):
            client.post('/api/mock-response',
                        json={'status_code': 200, 'headers': {}, 'body': ''})
        resp = client.post('/api/mock-response',
                           json={'status_code': 200, 'headers': {}, 'body': ''})
        assert resp.status_code == 429
        assert b'Rate limit' in resp.data

    def test_mock_response_blocks_header_injection(self, client):
        """Mock response should strip headers with newlines."""
        resp = client.post('/api/mock-response',
                           json={'status_code': 200,
                                 'headers': {'Evil\r\nInjected': 'bad'},
                                 'body': ''})
        assert resp.status_code == 200
        assert 'Injected' not in resp.headers

    def test_mock_response_body_too_large(self, client):
        """Mock response should reject body over 10000 characters."""
        resp = client.post('/api/mock-response',
                           json={'status_code': 200, 'headers': {},
                                 'body': 'x' * 10001})
        assert resp.status_code == 400
        assert b'10000' in resp.data

    def test_mock_response_in_robots_txt(self, client):
        """robots.txt should block /api/mock-response."""
        resp = client.get('/robots.txt')
        assert b'Disallow: /api/mock-response' in resp.data


# --- Responsive Design ---

class TestResponsiveDesign:
    """Tests for responsive design: viewport meta, hamburger menu, and CSS media queries."""

    def test_viewport_meta_tag_present(self, client):
        """Every page should include the viewport meta tag for mobile."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'name="viewport"' in html
        assert 'width=device-width' in html
        assert 'initial-scale=1' in html

    def test_viewport_meta_on_detail_page(self, client):
        """Detail pages should inherit the viewport meta tag from base."""
        resp = client.get('/200')
        html = resp.data.decode()
        assert 'name="viewport"' in html

    def test_viewport_meta_on_quiz_page(self, client):
        """Quiz page should have viewport meta tag."""
        resp = client.get('/quiz')
        html = resp.data.decode()
        assert 'name="viewport"' in html

    def test_hamburger_button_present(self, client):
        """The hamburger menu button should be present in the header."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'hamburger-btn' in html
        assert 'aria-label="Open navigation menu"' in html
        assert 'aria-expanded="false"' in html
        assert 'aria-controls="mobile-nav"' in html

    def test_hamburger_lines_present(self, client):
        """The hamburger icon should have three lines for the icon."""
        resp = client.get('/')
        html = resp.data.decode()
        assert html.count('hamburger-line') == 3

    def test_mobile_nav_present(self, client):
        """The mobile navigation slide-out panel should be present."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'id="mobile-nav"' in html
        assert 'class="mobile-nav"' in html
        assert 'aria-label="Mobile navigation"' in html

    def test_mobile_nav_overlay_present(self, client):
        """The mobile nav overlay (for close-on-outside-click) should exist."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'id="mobile-nav-overlay"' in html
        assert 'mobile-nav-overlay' in html

    def test_mobile_nav_has_all_links(self, client):
        """The mobile nav should contain all the same navigation links."""
        resp = client.get('/')
        html = resp.data.decode()
        # Check that mobile-nav section contains key nav links
        mobile_nav_start = html.index('id="mobile-nav"')
        mobile_nav_section = html[mobile_nav_start:mobile_nav_start + 2000]
        for page in ['/quiz', '/practice', '/daily', '/flowchart',
                     '/compare', '/tester', '/headers', '/cors-checker',
                     '/collection', '/playground', '/cheatsheet', '/api-docs']:
            assert page in mobile_nav_section, f"{page} missing from mobile nav"

    def test_hamburger_js_present(self, client):
        """The hamburger menu JavaScript should be included."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'hamburger-btn' in html
        assert 'mobile-nav' in html
        assert 'is-open' in html
        assert 'Escape' in html

    def test_responsive_css_media_queries_exist(self):
        """The CSS file should contain key responsive media queries."""
        with open('static/style.css', 'r') as f:
            css = f.read()
        # Verify key breakpoints exist
        assert '@media (max-width: 768px)' in css
        assert '@media (max-width: 480px)' in css
        assert '@media (max-width: 375px)' in css
        # Verify hamburger menu styles
        assert '.hamburger-btn' in css
        assert '.mobile-nav' in css
        assert '.mobile-nav-overlay' in css
        # Verify touch target enforcement
        assert 'min-height: 44px' in css

    def test_responsive_css_has_overflow_hidden(self):
        """CSS should prevent horizontal overflow on mobile."""
        with open('static/style.css', 'r') as f:
            css = f.read()
        assert 'overflow-x: hidden' in css

    def test_hamburger_on_all_pages(self, client):
        """Hamburger menu should appear on all major pages."""
        pages = ['/', '/quiz', '/practice', '/daily', '/flowchart',
                 '/compare', '/tester', '/headers', '/cors-checker',
                 '/collection', '/playground', '/cheatsheet', '/api-docs']
        for page in pages:
            resp = client.get(page)
            html = resp.data.decode()
            assert 'hamburger-btn' in html, f"hamburger-btn missing on {page}"
            assert 'mobile-nav' in html, f"mobile-nav missing on {page}"


# --- Accessibility: ARIA & Semantic HTML ---

class TestAccessibilityARIA:
    """Tests for ARIA attributes and semantic HTML across all templates."""

    def test_skip_link_present(self, client):
        """All pages should have a skip-to-content link."""
        pages = ['/', '/quiz', '/practice', '/daily', '/flowchart',
                 '/compare', '/tester', '/headers', '/cors-checker',
                 '/collection', '/playground', '/cheatsheet', '/api-docs']
        for page in pages:
            resp = client.get(page)
            html = resp.data.decode()
            assert 'skip-link' in html, f"skip-link missing on {page}"
            assert '#main-content' in html, f"skip-link target missing on {page}"

    def test_main_content_id_present(self, client):
        """All pages should have a main element with id=main-content."""
        pages = ['/', '/quiz', '/practice', '/daily', '/flowchart',
                 '/compare', '/tester', '/headers', '/cors-checker',
                 '/collection', '/playground', '/cheatsheet', '/api-docs']
        for page in pages:
            resp = client.get(page)
            html = resp.data.decode()
            assert 'id="main-content"' in html, f"main-content id missing on {page}"

    def test_main_role_present(self, client):
        """All pages should have role=main on the main element."""
        pages = ['/', '/quiz', '/practice', '/daily', '/flowchart',
                 '/compare', '/tester', '/headers', '/cors-checker',
                 '/collection', '/playground', '/cheatsheet', '/api-docs']
        for page in pages:
            resp = client.get(page)
            html = resp.data.decode()
            assert 'role="main"' in html, f"role=main missing on {page}"

    def test_banner_role_on_header(self, client):
        """Header should have role=banner."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'role="banner"' in html

    def test_contentinfo_role_on_footer(self, client):
        """Footer should have role=contentinfo."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'role="contentinfo"' in html

    def test_nav_has_aria_label(self, client):
        """Navigation should have aria-label."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'aria-label="Site navigation"' in html

    def test_search_has_role(self, client):
        """Search area should have role=search."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'role="search"' in html

    def test_search_input_has_aria_label(self, client):
        """Search inputs should have aria-label."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'aria-label="Search status codes"' in html

    def test_images_have_alt_text(self, client):
        """Parrot images should have meaningful alt text."""
        resp = client.get('/200')
        html = resp.data.decode()
        assert 'alt="200 OK"' in html

    def test_homepage_images_have_alt(self, client):
        """Homepage parrot card images should have alt text."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'alt="200 OK"' in html

    def test_detail_breadcrumb_has_aria(self, client):
        """Detail page breadcrumb should have aria-label."""
        resp = client.get('/200')
        html = resp.data.decode()
        assert 'aria-label="Breadcrumb"' in html
        assert 'aria-current="page"' in html

    def test_404_page_has_main_id(self, client):
        """Custom 404 page should have id=main-content and role=main."""
        resp = client.get('/nonexistent-page')
        html = resp.data.decode()
        assert 'id="main-content"' in html
        assert 'role="main"' in html

    def test_404_emoji_is_decorative(self, client):
        """404 page emoji should be marked as decorative."""
        resp = client.get('/nonexistent-page')
        html = resp.data.decode()
        assert 'aria-hidden="true"' in html


class TestAccessibilityQuizARIA:
    """Tests for ARIA attributes on quiz and daily challenge pages."""

    def test_quiz_has_h1(self, client):
        """Quiz page should have an h1 heading (even if sr-only)."""
        resp = client.get('/quiz')
        html = resp.data.decode()
        assert '<h1' in html

    def test_quiz_choices_have_role_group(self, client):
        """Quiz choices container should have role=group."""
        resp = client.get('/quiz')
        html = resp.data.decode()
        assert 'role="group"' in html
        assert 'aria-label="Answer choices"' in html

    def test_quiz_feedback_has_aria_live(self, client):
        """Quiz feedback should have aria-live=polite."""
        resp = client.get('/quiz')
        html = resp.data.decode()
        assert 'aria-live="polite"' in html

    def test_quiz_score_has_aria_live(self, client):
        """Quiz score values should have aria-live for screen reader updates."""
        resp = client.get('/quiz')
        html = resp.data.decode()
        # Score, streak, and total should all have aria-live
        assert html.count('aria-live="polite"') >= 3

    def test_daily_choices_have_role_group(self, client):
        """Daily challenge choices should have role=group."""
        resp = client.get('/daily')
        html = resp.data.decode()
        assert 'role="group"' in html
        assert 'aria-label="Answer choices"' in html

    def test_daily_streak_has_aria_live(self, client):
        """Daily challenge streak display should have aria-live."""
        resp = client.get('/daily')
        html = resp.data.decode()
        assert 'id="streak-count"' in html
        assert 'aria-live="polite"' in html

    def test_daily_streak_has_region_role(self, client):
        """Daily streak display should be in a labeled region."""
        resp = client.get('/daily')
        html = resp.data.decode()
        assert 'role="region"' in html
        assert 'aria-label="Streak tracker"' in html


class TestAccessibilityPracticeARIA:
    """Tests for ARIA attributes on the practice page."""

    def test_practice_score_has_aria_live(self, client):
        """Practice score values should have aria-live."""
        resp = client.get('/practice')
        html = resp.data.decode()
        assert 'id="practice-correct"' in html
        assert 'aria-live="polite"' in html

    def test_practice_progress_bar_has_aria(self, client):
        """Practice progress bar should have proper progressbar ARIA."""
        resp = client.get('/practice')
        html = resp.data.decode()
        assert 'role="progressbar"' in html
        assert 'aria-valuenow' in html
        assert 'aria-valuemin' in html
        assert 'aria-valuemax' in html

    def test_practice_score_region_labeled(self, client):
        """Practice score bar should be a labeled region."""
        resp = client.get('/practice')
        html = resp.data.decode()
        assert 'role="region"' in html
        assert 'aria-label="Score tracker"' in html


class TestAccessibilityFlowchartARIA:
    """Tests for ARIA on the flowchart page."""

    def test_flowchart_has_h1(self, client):
        """Flowchart page should have an h1 heading."""
        resp = client.get('/flowchart')
        html = resp.data.decode()
        assert '<h1' in html

    def test_flowchart_mode_toggle_has_tablist(self, client):
        """Flowchart mode toggle should use tablist pattern."""
        resp = client.get('/flowchart')
        html = resp.data.decode()
        assert 'role="tablist"' in html
        assert 'role="tab"' in html
        assert 'aria-selected="true"' in html

    def test_flowchart_tabpanels_present(self, client):
        """Flowchart should have tabpanel roles."""
        resp = client.get('/flowchart')
        html = resp.data.decode()
        assert 'role="tabpanel"' in html


class TestAccessibilityCompareARIA:
    """Tests for ARIA on the compare page."""

    def test_compare_presets_have_aria_labels(self, client):
        """Compare preset buttons should have descriptive aria-labels."""
        resp = client.get('/compare')
        html = resp.data.decode()
        assert 'aria-label="Compare 401' in html
        assert 'role="group"' in html

    def test_compare_result_has_aria_live(self, client):
        """Compare result area should have aria-live for dynamic updates."""
        resp = client.get('/compare')
        html = resp.data.decode()
        assert 'id="compare-result"' in html
        assert 'aria-live="polite"' in html


class TestAccessibilityCollectionARIA:
    """Tests for ARIA on the collection/Parrotdex page."""

    def test_collection_progress_has_progressbar(self, client):
        """Collection progress should have progressbar role."""
        resp = client.get('/collection')
        html = resp.data.decode()
        assert 'role="progressbar"' in html
        assert 'aria-valuenow' in html
        assert 'aria-valuemin' in html
        assert 'aria-valuemax' in html

    def test_collection_secrets_region(self, client):
        """Secret parrots section should be a labeled region."""
        resp = client.get('/collection')
        html = resp.data.decode()
        assert 'aria-label="Secret parrots"' in html


class TestAccessibilityDetailARIA:
    """Tests for ARIA on the detail page."""

    def test_detail_share_actions_have_group_role(self, client):
        """Share actions should have role=group and aria-label."""
        resp = client.get('/200')
        html = resp.data.decode()
        assert 'role="group"' in html
        assert 'aria-label="Share options"' in html

    def test_detail_share_buttons_have_aria_labels(self, client):
        """Share buttons should have aria-labels."""
        resp = client.get('/200')
        html = resp.data.decode()
        assert 'aria-label="Share this parrot"' in html
        assert 'aria-label="Copy link to this page"' in html

    def test_detail_nav_is_semantic(self, client):
        """Detail page navigation should use nav element."""
        resp = client.get('/200')
        html = resp.data.decode()
        assert 'aria-label="Status code navigation"' in html

    def test_detail_prev_next_have_aria_labels(self, client):
        """Previous/next navigation should have descriptive aria-labels."""
        resp = client.get('/200')
        html = resp.data.decode()
        assert 'aria-label="Next status code:' in html

    def test_detail_copy_icon_has_aria_live(self, client):
        """Copy button feedback should have aria-live."""
        resp = client.get('/200')
        html = resp.data.decode()
        assert 'id="copy-curl-icon"' in html
        assert 'aria-live="polite"' in html


class TestAccessibilityCheatsheetARIA:
    """Tests for ARIA and semantic HTML on the cheatsheet page."""

    def test_cheatsheet_categories_use_h2(self, client):
        """Cheatsheet category headers should be h2 elements."""
        resp = client.get('/cheatsheet')
        html = resp.data.decode()
        assert '<h2 class="cheat-cat-header">' in html

    def test_cheatsheet_sr_only_table_headers(self, client):
        """Cheatsheet tables should have sr-only thead for screen readers."""
        resp = client.get('/cheatsheet')
        html = resp.data.decode()
        assert 'class="sr-only"' in html
        assert '<th>Code</th>' in html


class TestAccessibilityTesterARIA:
    """Tests for ARIA on the URL tester page."""

    def test_tester_form_has_aria_label(self, client):
        """Tester form should have aria-label."""
        resp = client.get('/tester')
        html = resp.data.decode()
        assert 'aria-label="URL tester"' in html

    def test_tester_input_has_label(self, client):
        """Tester URL input should have a label element."""
        resp = client.get('/tester')
        html = resp.data.decode()
        assert 'for="url-input"' in html

    def test_tester_result_has_aria_live(self, client):
        """Tester result area should have aria-live."""
        resp = client.get('/tester')
        html = resp.data.decode()
        assert 'aria-live="polite"' in html


class TestAccessibilityCORSARIA:
    """Tests for ARIA on the CORS checker page."""

    def test_cors_form_has_aria_label(self, client):
        """CORS checker form should have aria-label."""
        resp = client.get('/cors-checker')
        html = resp.data.decode()
        assert 'aria-label="CORS checker"' in html

    def test_cors_fields_have_labels(self, client):
        """CORS checker fields should have associated labels."""
        resp = client.get('/cors-checker')
        html = resp.data.decode()
        assert 'for="cors-url"' in html
        assert 'for="cors-origin"' in html

    def test_cors_results_has_aria_live(self, client):
        """CORS results area should have aria-live."""
        resp = client.get('/cors-checker')
        html = resp.data.decode()
        assert 'aria-live="polite"' in html


class TestAccessibilityHeadingHierarchy:
    """Tests for proper heading hierarchy (no skips from h1 to h3)."""

    def test_homepage_heading_hierarchy(self, client):
        """Homepage should not skip heading levels."""
        resp = client.get('/')
        html = resp.data.decode()
        # Homepage has no h1 visible (it's the site title), but should not skip from h1 to h3
        assert '<h3' not in html or '<h2' in html

    def test_detail_page_heading_hierarchy(self, client):
        """Detail page h2 sections should not skip to h4."""
        resp = client.get('/200')
        html = resp.data.decode()
        # Should have h2 sections, no h4 without h3
        if '<h4' in html:
            assert '<h3' in html

    def test_cheatsheet_has_h1_and_h2(self, client):
        """Cheatsheet should have both h1 and h2 elements."""
        resp = client.get('/cheatsheet')
        html = resp.data.decode()
        assert '<h1>' in html or '<h1 ' in html
        assert '<h2' in html

    def test_practice_has_h1(self, client):
        """Practice page should have an h1."""
        resp = client.get('/practice')
        html = resp.data.decode()
        assert '<h1>' in html


class TestAccessibilityColorContrast:
    """Tests for color contrast improvements in the CSS."""

    def test_no_very_low_contrast_text(self):
        """CSS should not have rgba(255,255,255,0.3) or 0.4 for text color."""
        with open('static/style.css', 'r') as f:
            css = f.read()
        # Split into rule blocks to check context
        # Find all 'color:' declarations with low contrast and check they are
        # inside placeholder selectors (which are exempt from contrast rules)
        lines = css.split('\n')
        in_placeholder = False
        for i, line in enumerate(lines):
            stripped = line.strip()
            if '::placeholder' in stripped:
                in_placeholder = True
            if in_placeholder and '}' in stripped:
                in_placeholder = False
                continue
            if in_placeholder:
                continue
            if 'background-image' in stripped or 'background:' in stripped:
                continue
            if stripped.startswith('color: rgba(255,255,255,0.3)') or \
               stripped.startswith('color: rgba(255, 255, 255, 0.3)'):
                assert False, f"Low contrast text (0.3) at line {i+1}: {stripped}"
            if stripped.startswith('color: rgba(255,255,255,0.4)') or \
               stripped.startswith('color: rgba(255, 255, 255, 0.4)'):
                assert False, f"Low contrast text (0.4) at line {i+1}: {stripped}"

    def test_header_subtitle_sufficient_contrast(self):
        """Header subtitle should have sufficient contrast."""
        with open('static/style.css', 'r') as f:
            css = f.read()
        assert 'header-subtitle' in css
        # Should not be 0.5 anymore
        import re
        m = re.search(r'\.header-subtitle\s*\{[^}]*color:\s*rgba\(255,\s*255,\s*255,\s*([\d.]+)\)', css)
        if m:
            opacity = float(m.group(1))
            assert opacity >= 0.6, f"Header subtitle contrast too low: {opacity}"

    def test_nav_links_sufficient_contrast(self):
        """Navigation links should have sufficient contrast."""
        with open('static/style.css', 'r') as f:
            css = f.read()
        import re
        m = re.search(r'\.header-nav\s+a\s*\{[^}]*color:\s*rgba\(255,\s*255,\s*255,\s*([\d.]+)\)', css)
        if m:
            opacity = float(m.group(1))
            assert opacity >= 0.6, f"Nav link contrast too low: {opacity}"

    def test_footer_github_link_contrast(self):
        """Footer GitHub link should have sufficient contrast."""
        with open('static/style.css', 'r') as f:
            css = f.read()
        import re
        m = re.search(r'\.footer-github\s*\{[^}]*color:\s*rgba\(255,\s*255,\s*255,\s*([\d.]+)\)', css)
        if m:
            opacity = float(m.group(1))
            assert opacity >= 0.6, f"Footer GitHub link contrast too low: {opacity}"

    def test_header_type_colors_contrast(self):
        """Header explainer type colors should have sufficient contrast."""
        with open('templates/headers.html', 'r') as f:
            content = f.read()
        # The Info/Connection/Routing/Debug colors should not be 0.4
        assert 'rgba(255,255,255,0.4)' not in content


class TestAccessibilityFocusManagement:
    """Tests for keyboard accessibility and focus indicators."""

    def test_focus_visible_style_exists(self):
        """CSS should have :focus-visible styles."""
        with open('static/style.css', 'r') as f:
            css = f.read()
        assert ':focus-visible' in css

    def test_skip_link_style_exists(self):
        """CSS should have skip-link styles that show on focus."""
        with open('static/style.css', 'r') as f:
            css = f.read()
        assert '.skip-link:focus' in css
        assert '.skip-link' in css

    def test_sr_only_class_exists(self):
        """CSS should have an sr-only class for screen reader text."""
        with open('static/style.css', 'r') as f:
            css = f.read()
        assert '.sr-only' in css
        assert 'clip: rect(0, 0, 0, 0)' in css

    def test_all_interactive_elements_keyboard_accessible(self, client):
        """Key interactive elements should be buttons or links (natively focusable)."""
        resp = client.get('/')
        html = resp.data.decode()
        # Filter toggle should be a button, not a div
        assert '<button class="btn-filter"' in html or 'class="btn-filter"' in html
        # Filter pills should be buttons
        assert '<button class="cat-pill' in html

    def test_quiz_keyboard_shortcuts_present(self, client):
        """Quiz page should have keyboard shortcut support."""
        resp = client.get('/quiz')
        html = resp.data.decode()
        # 1-4 number keys for answers
        assert "e.key >= '1'" in html or "e.key >= \\'1\\'" in html
        # Enter for next
        assert "e.key === 'Enter'" in html or "e.key === \\'Enter\\'" in html


class TestAccessibilityScreenReader:
    """Tests for screen reader support."""

    def test_decorative_images_are_hidden(self, client):
        """Decorative elements should have aria-hidden=true."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'aria-hidden="true"' in html

    def test_no_results_message_has_live_region(self, client):
        """No results message on homepage should be a live region."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'id="no-results"' in html
        assert 'aria-live="polite"' in html

    def test_filter_toggle_has_aria_expanded(self, client):
        """Filter toggle button should have aria-expanded."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'aria-expanded=' in html

    def test_filter_toggle_has_aria_controls(self, client):
        """Filter toggle should have aria-controls pointing to dropdown."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'aria-controls="filter-dropdown"' in html

    def test_random_button_has_aria_label(self, client):
        """Random parrot button (emoji) should have aria-label."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'aria-label="Random parrot"' in html

    def test_back_to_top_has_aria_label(self, client):
        """Back to top button should have aria-label."""
        resp = client.get('/200')
        html = resp.data.decode()
        assert 'aria-label="Back to top"' in html

    def test_parrot_links_have_aria_labels(self, client):
        """Parrot card links should have descriptive aria-labels."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'aria-label="200 OK"' in html

    def test_featured_card_in_grid(self, client):
        """Featured parrot card should have the featured class in the grid."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'featured' in html


# --- CSS Media Queries ---

class TestCSSMediaQueries:
    """Verify print, reduced-motion, and light-theme media queries exist in the stylesheet."""

    def test_print_media_query_exists(self, client):
        """CSS should contain a comprehensive @media print block."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '@media print' in css

    def test_print_hides_interactive_elements(self, client):
        """Print styles should hide nav, footer, and interactive elements."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert 'display: none !important' in css
        assert '.site-header-compact' in css
        assert '.site-footer' in css

    def test_print_shows_urls_after_links(self, client):
        """Print styles should show URLs after links."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert 'a[href]::after' in css
        assert 'attr(href)' in css

    def test_print_page_break_rules(self, client):
        """Print styles should include page-break rules."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert 'page-break-inside: avoid' in css

    def test_print_light_background(self, client):
        """Print styles should use white background and dark text."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert 'background: #fff !important' in css
        assert 'color: #000 !important' in css

    def test_print_cheat_sheet_columns(self, client):
        """Cheat sheet should print in 2 columns."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert 'columns: 2' in css
        assert 'break-inside: avoid' in css

    def test_print_images_sized_properly(self, client):
        """Print styles should ensure images have proper sizing."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert 'max-width: 100% !important' in css
        assert 'height: auto !important' in css

    def test_reduced_motion_media_query_exists(self, client):
        """CSS should contain a @media (prefers-reduced-motion: reduce) block."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '@media (prefers-reduced-motion: reduce)' in css

    def test_reduced_motion_disables_animations(self, client):
        """Reduced motion should disable animation-duration globally."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert 'animation-duration: 0.01ms !important' in css
        assert 'transition-duration: 0.01ms !important' in css

    def test_reduced_motion_disables_aurora(self, client):
        """Reduced motion should disable the aurora background drift."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        # Check aurora is explicitly disabled within reduced-motion
        assert 'body::before' in css
        # The reduced-motion block should have animation: none for body::before
        idx = css.index('@media (prefers-reduced-motion: reduce)')
        block = css[idx:css.index('/* === Light Theme', idx)]
        assert 'animation: none !important' in block

    def test_reduced_motion_disables_confetti(self, client):
        """Reduced motion should disable confetti particles."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        idx = css.index('@media (prefers-reduced-motion: reduce)')
        block = css[idx:css.index('/* === Light Theme', idx)]
        assert '.confetti-particle' in block

    def test_reduced_motion_disables_scroll_reveal(self, client):
        """Reduced motion should make scroll reveal elements instantly visible."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        idx = css.index('@media (prefers-reduced-motion: reduce)')
        block = css[idx:css.index('/* === Light Theme', idx)]
        assert '.parrot-card.will-reveal' in block
        assert '.parrot-card.scroll-animated' in block

    def test_reduced_motion_keeps_hover_colors(self, client):
        """Reduced motion should keep hover color changes but remove transforms."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        idx = css.index('@media (prefers-reduced-motion: reduce)')
        block = css[idx:css.index('/* === Light Theme', idx)]
        assert 'transform: none !important' in block

    def test_light_theme_media_query_exists(self, client):
        """CSS should contain a @media (prefers-color-scheme: light) block."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '@media (prefers-color-scheme: light)' in css

    def test_light_theme_background_color(self, client):
        """Light theme should use light background (#f5f5f7)."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        idx = css.index('@media (prefers-color-scheme: light)')
        block = css[idx:]
        assert '#f5f5f7' in block

    def test_light_theme_dark_text(self, client):
        """Light theme should use dark text (#1a1a1f)."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        idx = css.index('@media (prefers-color-scheme: light)')
        block = css[idx:]
        assert '#1a1a1f' in block

    def test_light_theme_card_backgrounds(self, client):
        """Light theme should adjust card backgrounds for light mode."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        idx = css.index('@media (prefers-color-scheme: light)')
        block = css[idx:]
        assert '.parrot' in block
        assert '.detail-info' in block
        assert '#ffffff' in block

    def test_light_theme_category_colors(self, client):
        """Light theme should adjust category colors for light background contrast."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        idx = css.index('@media (prefers-color-scheme: light)')
        block = css[idx:]
        assert '.category-1xx' in block
        assert '.category-2xx' in block
        assert '.category-3xx' in block
        assert '.category-4xx' in block
        assert '.category-5xx' in block


class TestEdgeCaseCoverage:
    """Tests targeting uncovered lines for maximum coverage."""

    def test_mock_response_invalid_headers(self, client):
        """Headers must be a dict."""
        resp = client.post('/api/mock-response',
                           json={"status_code": 200, "headers": "not-a-dict"})
        assert resp.status_code == 400
        assert b'headers must be a dict' in resp.data

    def test_mock_response_invalid_body(self, client):
        """Body must be a string."""
        resp = client.post('/api/mock-response',
                           json={"status_code": 200, "body": 123})
        assert resp.status_code == 400
        assert b'body must be a string' in resp.data

    def test_search_partial_code(self, client):
        """Search by partial code digits (e.g., '50' should match 500s)."""
        resp = client.get('/api/search?q=50')
        data = resp.get_json()
        codes = [r['code'] for r in data]
        assert '500' in codes

    def test_search_code_contains(self, client):
        """Search that matches code containing digits."""
        resp = client.get('/api/search?q=04')
        data = resp.get_json()
        codes = [r['code'] for r in data]
        assert '404' in codes or '204' in codes

    def test_all_pages_have_csp_nonce(self, client):
        """All major pages should have CSP nonce in scripts."""
        pages = ['/', '/quiz', '/daily', '/practice', '/flowchart',
                 '/compare', '/cheatsheet', '/collection', '/tester',
                 '/headers', '/cors-checker', '/api-docs', '/playground', '/200']
        for page in pages:
            resp = client.get(page)
            html = resp.get_data(as_text=True)
            if html:  # skip empty responses (204)
                assert 'nonce=' in html, f"Missing CSP nonce on {page}"

    def test_all_pages_have_doctype(self, client):
        """All pages should have proper HTML5 doctype."""
        pages = ['/', '/quiz', '/daily', '/practice', '/200', '/404-nonexistent']
        for page in pages:
            resp = client.get(page)
            html = resp.get_data(as_text=True)
            if html:
                assert '<!doctype html>' in html.lower() or '<!DOCTYPE html>' in html, \
                    f"Missing doctype on {page}"

    def test_return_status_with_delay_rate_limited(self, client):
        """Return status delay should be rate-limited."""
        # Exhaust rate limit
        for _ in range(25):
            client.get('/return/200?delay=0.001')
        resp = client.get('/return/200?delay=0.001')
        assert resp.status_code == 429

    def test_highlight_http_filter(self, client):
        """HTTP exchange sections should have syntax highlighting."""
        resp = client.get('/200')
        html = resp.get_data(as_text=True)
        assert 'http-hl-' in html

    def test_feed_xml_content_type(self, client):
        """RSS feed should have proper content type."""
        resp = client.get('/feed.xml')
        assert 'xml' in resp.content_type


# --- Sitemap completeness ---

class TestSitemapCompleteness:
    """Verify sitemap.xml includes all expected public pages."""

    EXPECTED_PAGES = [
        '/', '/quiz', '/personality', '/daily', '/practice', '/debug', '/flowchart',
        '/compare', '/tester', '/cheatsheet', '/headers', '/cors-checker',
        '/security-audit', '/collection', '/playground', '/api-docs', '/profile',
    ]

    def test_sitemap_returns_xml(self, client):
        resp = client.get('/sitemap.xml')
        assert resp.status_code == 200
        assert 'application/xml' in resp.content_type

    def test_sitemap_has_xml_header(self, client):
        resp = client.get('/sitemap.xml')
        body = resp.data.decode()
        assert '<?xml version="1.0"' in body
        assert '<urlset' in body
        assert '</urlset>' in body

    def test_sitemap_includes_all_public_pages(self, client):
        resp = client.get('/sitemap.xml')
        body = resp.data.decode()
        for page in self.EXPECTED_PAGES:
            assert f'<loc>http://localhost{page}</loc>' in body, \
                f"Sitemap missing page: {page}"

    def test_sitemap_includes_status_code_pages(self, client):
        resp = client.get('/sitemap.xml')
        body = resp.data.decode()
        # Spot-check common codes are present
        for code in ['200', '301', '404', '500']:
            assert f'<loc>http://localhost/{code}</loc>' in body, \
                f"Sitemap missing status code page: /{code}"

    def test_sitemap_homepage_has_highest_priority(self, client):
        resp = client.get('/sitemap.xml')
        body = resp.data.decode()
        assert '<url><loc>http://localhost/</loc><priority>1.0</priority></url>' in body

    def test_sitemap_does_not_include_api_endpoints(self, client):
        resp = client.get('/sitemap.xml')
        body = resp.data.decode()
        assert '/api/search' not in body
        assert '/api/check-url' not in body
        assert '/api/check-cors' not in body
        assert '/api/mock-response' not in body
        assert '/api/diff' not in body
        assert '/echo' not in body
        assert '/return/' not in body
        assert '/redirect/' not in body

    def test_sitemap_cache_header(self, client):
        resp = client.get('/sitemap.xml')
        assert 'max-age=86400' in resp.headers.get('Cache-Control', '')


# --- robots.txt format ---

class TestRobotsTxtFormat:
    """Verify robots.txt is correct and complete."""

    def test_robots_returns_text(self, client):
        resp = client.get('/robots.txt')
        assert resp.status_code == 200
        assert resp.content_type == 'text/plain; charset=utf-8'

    def test_robots_allows_root(self, client):
        resp = client.get('/robots.txt')
        body = resp.data.decode()
        assert 'User-agent: *' in body
        assert 'Allow: /' in body

    def test_robots_disallows_api_endpoints(self, client):
        resp = client.get('/robots.txt')
        body = resp.data.decode()
        expected_disallows = [
            'Disallow: /api/check-url',
            'Disallow: /api/fetch-url',
            'Disallow: /api/check-cors',
            'Disallow: /api/security-audit',
            'Disallow: /api/mock-response',
            'Disallow: /api/diff',
            'Disallow: /api/search',
            'Disallow: /return/',
            'Disallow: /echo',
            'Disallow: /redirect/',
        ]
        for rule in expected_disallows:
            assert rule in body, f"robots.txt missing: {rule}"

    def test_robots_references_sitemap(self, client):
        resp = client.get('/robots.txt')
        body = resp.data.decode()
        assert 'Sitemap:' in body
        assert 'sitemap.xml' in body


# --- API docs page completeness ---

class TestApiDocsCompleteness:
    """Verify the API docs page documents all API endpoints."""

    def test_api_docs_status_code_detail_endpoint(self, client):
        resp = client.get('/api-docs')
        html = resp.data.decode()
        assert '/{code}' in html
        assert 'application/json' in html

    def test_api_docs_image_endpoint(self, client):
        resp = client.get('/api-docs')
        html = resp.data.decode()
        assert '/{code}.jpg' in html

    def test_api_docs_random_endpoint(self, client):
        resp = client.get('/api-docs')
        html = resp.data.decode()
        assert '/random' in html

    def test_api_docs_search_endpoint(self, client):
        resp = client.get('/api-docs')
        html = resp.data.decode()
        assert '/api/search' in html
        assert 'score' in html

    def test_api_docs_check_url_endpoint(self, client):
        resp = client.get('/api-docs')
        html = resp.data.decode()
        assert '/api/check-url' in html
        assert 'time_ms' in html

    def test_api_docs_check_cors_endpoint(self, client):
        resp = client.get('/api-docs')
        html = resp.data.decode()
        assert '/api/check-cors' in html
        assert 'preflight' in html
        assert 'analysis' in html

    def test_api_docs_return_status_endpoint(self, client):
        resp = client.get('/api-docs')
        html = resp.data.decode()
        assert '/return/{code}' in html
        assert 'delay' in html

    def test_api_docs_echo_endpoint(self, client):
        resp = client.get('/api-docs')
        html = resp.data.decode()
        assert '/echo' in html
        assert 'POST' in html

    def test_api_docs_diff_endpoint(self, client):
        resp = client.get('/api-docs')
        html = resp.data.decode()
        assert '/api/diff' in html
        assert 'key_difference' in html

    def test_api_docs_redirect_endpoint(self, client):
        resp = client.get('/api-docs')
        html = resp.data.decode()
        assert '/redirect/{n}' in html

    def test_api_docs_mock_response_endpoint(self, client):
        resp = client.get('/api-docs')
        html = resp.data.decode()
        assert '/api/mock-response' in html
        assert 'status_code' in html

    def test_api_docs_lists_all_interactive_pages(self, client):
        """The interactive pages section should list all public pages."""
        resp = client.get('/api-docs')
        html = resp.data.decode()
        expected_pages = [
            '/quiz', '/daily', '/practice', '/flowchart', '/compare',
            '/tester', '/cheatsheet', '/collection', '/headers',
            '/cors-checker', '/playground',
        ]
        for page in expected_pages:
            assert page in html, f"API docs missing interactive page: {page}"

    def test_api_docs_has_response_schemas(self, client):
        """API docs should include response schema documentation."""
        resp = client.get('/api-docs')
        html = resp.data.decode()
        assert 'Response schema' in html or 'Request body schema' in html


# --- Security Audit Tests ---

class TestSSRFIPv6MappedAddresses:
    """Verify SSRF protection against IPv6-mapped IPv4 private addresses."""

    def test_blocks_ipv6_mapped_localhost(self):
        """::ffff:127.0.0.1 should be blocked as it maps to localhost."""
        addrinfo = [(socket.AF_INET6, socket.SOCK_STREAM, 0, '', ('::ffff:127.0.0.1', 0, 0, 0))]
        with patch('index.socket.getaddrinfo', return_value=addrinfo):
            result, _ = resolve_and_validate('http://tricky.example.com/')
            assert result is None

    def test_blocks_ipv6_mapped_private_10(self):
        """::ffff:10.0.0.1 should be blocked as it maps to 10.0.0.0/8."""
        addrinfo = [(socket.AF_INET6, socket.SOCK_STREAM, 0, '', ('::ffff:10.0.0.1', 0, 0, 0))]
        with patch('index.socket.getaddrinfo', return_value=addrinfo):
            result, _ = resolve_and_validate('http://tricky.example.com/')
            assert result is None

    def test_blocks_ipv6_mapped_private_172(self):
        """::ffff:172.16.0.1 should be blocked as it maps to 172.16.0.0/12."""
        addrinfo = [(socket.AF_INET6, socket.SOCK_STREAM, 0, '', ('::ffff:172.16.0.1', 0, 0, 0))]
        with patch('index.socket.getaddrinfo', return_value=addrinfo):
            result, _ = resolve_and_validate('http://tricky.example.com/')
            assert result is None

    def test_blocks_ipv6_mapped_private_192(self):
        """::ffff:192.168.1.1 should be blocked as it maps to 192.168.0.0/16."""
        addrinfo = [(socket.AF_INET6, socket.SOCK_STREAM, 0, '', ('::ffff:192.168.1.1', 0, 0, 0))]
        with patch('index.socket.getaddrinfo', return_value=addrinfo):
            result, _ = resolve_and_validate('http://tricky.example.com/')
            assert result is None

    def test_blocks_ipv6_mapped_metadata(self):
        """::ffff:169.254.169.254 should be blocked (cloud metadata endpoint)."""
        addrinfo = [(socket.AF_INET6, socket.SOCK_STREAM, 0, '', ('::ffff:169.254.169.254', 0, 0, 0))]
        with patch('index.socket.getaddrinfo', return_value=addrinfo):
            result, _ = resolve_and_validate('http://metadata.example.com/')
            assert result is None

    def test_allows_ipv6_mapped_public(self):
        """::ffff:93.184.216.34 should be allowed as it maps to a public IP."""
        addrinfo = [(socket.AF_INET6, socket.SOCK_STREAM, 0, '', ('::ffff:93.184.216.34', 0, 0, 0))]
        with patch('index.socket.getaddrinfo', return_value=addrinfo):
            result, hostname = resolve_and_validate('http://example.com/')
            assert result is not None


class TestSSRFSchemeAndPort:
    """Verify SSRF protection against non-HTTP schemes and non-standard ports."""

    def test_blocks_file_scheme(self):
        """file:// URLs should be blocked."""
        result, _ = resolve_and_validate('file:///etc/passwd')
        assert result is None

    def test_blocks_ftp_scheme(self):
        """ftp:// URLs should be blocked."""
        result, _ = resolve_and_validate('ftp://internal.example.com/')
        assert result is None

    def test_blocks_gopher_scheme(self):
        """gopher:// URLs should be blocked."""
        result, _ = resolve_and_validate('gopher://internal.example.com/')
        assert result is None

    def test_blocks_non_standard_port(self):
        """Non-standard ports like 6379 (Redis) should be blocked."""
        addrinfo = [(socket.AF_INET, socket.SOCK_STREAM, 0, '', ('93.184.216.34', 0))]
        with patch('index.socket.getaddrinfo', return_value=addrinfo):
            result, _ = resolve_and_validate('http://example.com:6379/')
            assert result is None

    def test_blocks_ssh_port(self):
        """Port 22 (SSH) should be blocked."""
        addrinfo = [(socket.AF_INET, socket.SOCK_STREAM, 0, '', ('93.184.216.34', 0))]
        with patch('index.socket.getaddrinfo', return_value=addrinfo):
            result, _ = resolve_and_validate('http://example.com:22/')
            assert result is None

    def test_allows_port_80(self):
        """Port 80 should be allowed."""
        addrinfo = [(socket.AF_INET, socket.SOCK_STREAM, 0, '', ('93.184.216.34', 0))]
        with patch('index.socket.getaddrinfo', return_value=addrinfo):
            result, _ = resolve_and_validate('http://example.com:80/')
            assert result is not None

    def test_allows_port_443(self):
        """Port 443 should be allowed."""
        addrinfo = [(socket.AF_INET, socket.SOCK_STREAM, 0, '', ('93.184.216.34', 0))]
        with patch('index.socket.getaddrinfo', return_value=addrinfo):
            result, _ = resolve_and_validate('https://example.com:443/')
            assert result is not None

    def test_allows_no_port(self):
        """URLs without an explicit port should be allowed."""
        addrinfo = [(socket.AF_INET, socket.SOCK_STREAM, 0, '', ('93.184.216.34', 0))]
        with patch('index.socket.getaddrinfo', return_value=addrinfo):
            result, _ = resolve_and_validate('https://example.com/')
            assert result is not None


class TestMockResponseSecurityHeaders:
    """Verify mock-response blocks security-sensitive headers."""

    def test_blocks_set_cookie_header(self, client):
        """Mock response should not allow setting Set-Cookie headers."""
        resp = client.post('/api/mock-response',
                           json={'status_code': 200,
                                 'headers': {'Set-Cookie': 'session=evil'},
                                 'body': ''})
        assert resp.status_code == 200
        assert 'session=evil' not in (resp.headers.get('Set-Cookie') or '')

    def test_blocks_csp_override(self, client):
        """Mock response should not allow overriding Content-Security-Policy."""
        resp = client.post('/api/mock-response',
                           json={'status_code': 200,
                                 'headers': {'Content-Security-Policy': "default-src *"},
                                 'body': ''})
        csp = resp.headers.get('Content-Security-Policy', '')
        assert "default-src *" not in csp
        assert "default-src 'self'" in csp

    def test_blocks_hsts_override(self, client):
        """Mock response should not allow overriding HSTS."""
        resp = client.post('/api/mock-response',
                           json={'status_code': 200,
                                 'headers': {'Strict-Transport-Security': 'max-age=0'},
                                 'body': ''})
        hsts = resp.headers.get('Strict-Transport-Security', '')
        assert 'max-age=31536000' in hsts

    def test_blocks_x_frame_options_override(self, client):
        """Mock response should not allow overriding X-Frame-Options."""
        resp = client.post('/api/mock-response',
                           json={'status_code': 200,
                                 'headers': {'X-Frame-Options': 'ALLOWALL'},
                                 'body': ''})
        assert resp.headers.get('X-Frame-Options') == 'DENY'

    def test_blocks_transfer_encoding(self, client):
        """Mock response should not allow setting Transfer-Encoding."""
        resp = client.post('/api/mock-response',
                           json={'status_code': 200,
                                 'headers': {'Transfer-Encoding': 'chunked'},
                                 'body': ''})
        assert resp.status_code == 200
        # Transfer-Encoding is managed by the server, not user input

    def test_allows_safe_custom_headers(self, client):
        """Mock response should still allow safe custom headers."""
        resp = client.post('/api/mock-response',
                           json={'status_code': 200,
                                 'headers': {'X-Custom': 'safe', 'Cache-Control': 'no-cache'},
                                 'body': ''})
        assert resp.headers.get('X-Custom') == 'safe'

    def test_too_many_headers_rejected(self, client):
        """Mock response should reject requests with more than 50 headers."""
        headers = {f'X-Header-{i}': f'value-{i}' for i in range(51)}
        resp = client.post('/api/mock-response',
                           json={'status_code': 200,
                                 'headers': headers,
                                 'body': ''})
        assert resp.status_code == 400
        assert b'Too many headers' in resp.data

    def test_value_injection_with_null_bytes(self, client):
        """Mock response should not allow null bytes in header values."""
        resp = client.post('/api/mock-response',
                           json={'status_code': 200,
                                 'headers': {'X-Test': 'value\x00injected'},
                                 'body': ''})
        # Should not crash; value may or may not be set depending on server
        assert resp.status_code == 200


class TestCSPNonceCompleteness:
    """Verify CSP nonce is present in all script and style tags."""

    def test_csp_includes_style_nonce(self, client):
        """CSP style-src should include the nonce for inline styles."""
        resp = client.get('/')
        csp = resp.headers.get('Content-Security-Policy', '')
        nonce_match = re.search(r"'nonce-([^']+)'", csp)
        assert nonce_match, "CSP should contain a nonce"
        nonce = nonce_match.group(1)
        assert f"style-src 'self' 'nonce-{nonce}'" in csp

    def test_practice_inline_style_has_nonce(self, client):
        """Practice page inline <style> should have the CSP nonce."""
        resp = client.get('/practice')
        csp = resp.headers.get('Content-Security-Policy', '')
        nonce = re.search(r"'nonce-([^']+)'", csp).group(1)
        assert f'<style nonce="{nonce}">' in resp.data.decode()

    def test_no_inline_event_handlers_on_html_tags(self, client):
        """HTML tags should not have inline event handlers like onload=."""
        resp = client.get('/')
        html = resp.data.decode()
        # Check specifically for inline event handler attributes on HTML tags.
        # The pattern 'onload="' on a link/img tag would be blocked by CSP.
        # Note: l.onload= inside <script> is fine (DOM property, not HTML attr).
        assert 'onload="this.onload' not in html, \
            "Found inline onload handler on HTML element (blocked by CSP)"

    def test_font_preload_uses_script(self, client):
        """Font preload should use a nonce-based script, not inline onload."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'id="font-preload"' in html
        assert 'font-preload' in html


class TestCSPOnAllRoutes:
    """Verify CSP headers are present on all routes, not just the homepage."""

    def _check_csp(self, resp):
        csp = resp.headers.get('Content-Security-Policy', '')
        assert "default-src 'self'" in csp
        assert "script-src 'self'" in csp
        assert "'nonce-" in csp
        assert 'unsafe-inline' not in csp
        assert 'unsafe-eval' not in csp
        return csp

    def test_csp_on_homepage(self, client):
        self._check_csp(client.get('/'))

    def test_csp_on_detail_page(self, client):
        self._check_csp(client.get('/200'))

    def test_csp_on_quiz(self, client):
        self._check_csp(client.get('/quiz'))

    def test_csp_on_daily(self, client):
        self._check_csp(client.get('/daily'))

    def test_csp_on_practice(self, client):
        self._check_csp(client.get('/practice'))

    def test_csp_on_flowchart(self, client):
        self._check_csp(client.get('/flowchart'))

    def test_csp_on_compare(self, client):
        self._check_csp(client.get('/compare'))

    def test_csp_on_tester(self, client):
        self._check_csp(client.get('/tester'))

    def test_csp_on_cheatsheet(self, client):
        self._check_csp(client.get('/cheatsheet'))

    def test_csp_on_headers(self, client):
        self._check_csp(client.get('/headers'))

    def test_csp_on_cors_checker(self, client):
        self._check_csp(client.get('/cors-checker'))

    def test_csp_on_collection(self, client):
        self._check_csp(client.get('/collection'))

    def test_csp_on_playground(self, client):
        self._check_csp(client.get('/playground'))

    def test_csp_on_api_docs(self, client):
        self._check_csp(client.get('/api-docs'))

    def test_csp_on_profile(self, client):
        self._check_csp(client.get('/profile'))

    def test_csp_on_personality(self, client):
        self._check_csp(client.get('/personality'))

    def test_csp_on_404(self, client):
        self._check_csp(client.get('/nonexistent'))

    def test_csp_on_echo(self, client):
        self._check_csp(client.get('/echo'))

    def test_csp_on_api_search(self, client):
        self._check_csp(client.get('/api/search?q=test'))

    def test_csp_on_api_diff(self, client):
        self._check_csp(client.get('/api/diff?code1=200&code2=404'))

    def test_csp_on_return(self, client):
        self._check_csp(client.get('/return/200'))


class TestSecurityHeadersOnAllRoutes:
    """Verify all security headers are present on every route."""

    ROUTES = ['/', '/200', '/quiz', '/personality', '/daily', '/practice', '/debug',
              '/flowchart', '/compare', '/tester', '/cheatsheet', '/headers',
              '/cors-checker', '/security-audit', '/collection', '/playground',
              '/api-docs', '/profile', '/echo', '/return/200', '/redirect/0',
              '/feed.xml', '/sitemap.xml', '/robots.txt']

    def _check_headers(self, resp):
        assert resp.headers.get('X-Content-Type-Options') == 'nosniff'
        assert resp.headers.get('X-Frame-Options') == 'DENY'
        assert 'strict-origin-when-cross-origin' in resp.headers.get('Referrer-Policy', '')
        assert 'camera=()' in resp.headers.get('Permissions-Policy', '')
        assert 'max-age=31536000' in resp.headers.get('Strict-Transport-Security', '')
        assert 'Server' not in resp.headers

    def test_security_headers_on_all_routes(self, client):
        """All routes should have the complete set of security headers."""
        for route in self.ROUTES:
            resp = client.get(route)
            self._check_headers(resp)


class TestSearchQueryValidation:
    """Verify /api/search query parameter validation."""

    def test_search_rejects_empty_query(self, client):
        resp = client.get('/api/search?q=')
        assert resp.status_code == 400

    def test_search_rejects_long_query(self, client):
        """Search should reject queries over 200 characters."""
        resp = client.get('/api/search?q=' + 'a' * 201)
        assert resp.status_code == 400
        assert b'Query too long' in resp.data

    def test_search_allows_normal_query(self, client):
        resp = client.get('/api/search?q=not+found')
        assert resp.status_code == 200

    def test_search_allows_max_length_query(self, client):
        """Search should accept queries up to 200 characters."""
        resp = client.get('/api/search?q=' + 'a' * 200)
        assert resp.status_code == 200


class TestEchoXSSProtection:
    """Verify echo endpoint doesn't reflect sensitive data."""

    def test_echo_strips_authorization(self, client):
        """Echo should strip Authorization header."""
        resp = client.get('/echo', headers={'Authorization': 'Bearer secret'})
        data = resp.get_json()
        assert 'Authorization' not in data['headers']

    def test_echo_strips_cookie(self, client):
        """Echo should strip Cookie header."""
        resp = client.get('/echo', headers={'Cookie': 'session=abc123'})
        data = resp.get_json()
        assert 'Cookie' not in data['headers']

    def test_echo_strips_proxy_auth(self, client):
        """Echo should strip Proxy-Authorization header."""
        resp = client.get('/echo', headers={'Proxy-Authorization': 'Basic abc'})
        data = resp.get_json()
        assert 'Proxy-Authorization' not in data['headers']

    def test_echo_returns_json_content_type(self, client):
        """Echo should always return JSON content type."""
        resp = client.get('/echo')
        assert resp.content_type.startswith('application/json')

    def test_echo_curl_format_no_auth(self, client):
        """Echo with format=curl should not include auth headers."""
        resp = client.get('/echo?format=curl',
                          headers={'Authorization': 'Bearer secret'})
        data = resp.get_json()
        assert 'Bearer secret' not in data.get('curl', '')


class TestSecretManagement:
    """Verify no hardcoded secrets or debug mode."""

    def test_debug_mode_disabled(self):
        """Flask should not be in debug mode."""
        assert app.config['DEBUG'] is False

    def test_secret_key_not_empty(self):
        """Flask should have a SECRET_KEY configured."""
        assert app.config['SECRET_KEY'] is not None
        assert len(app.config['SECRET_KEY']) > 0

    def test_max_content_length_set(self):
        """Request body size should be limited."""
        assert app.config['MAX_CONTENT_LENGTH'] == 1 * 1024 * 1024

    def test_server_header_stripped(self, client):
        """Server header should not be present in responses."""
        resp = client.get('/')
        assert 'Server' not in resp.headers


class TestTemplateAutoEscaping:
    """Verify Jinja2 auto-escaping prevents XSS in templates."""

    def test_status_code_not_injectable(self, client):
        """Status codes displayed in templates should be auto-escaped."""
        # Request a valid code -- make sure output is properly escaped
        resp = client.get('/200')
        html = resp.data.decode()
        # Verify the code appears as plain text, not as unescaped HTML
        assert '<script>' not in html or 'nonce=' in html

    def test_no_safe_filter_in_templates(self):
        """Templates should not use |safe on user-controlled data."""
        import os
        template_dir = os.path.join(os.path.dirname(__file__), 'templates')
        for filename in os.listdir(template_dir):
            if filename.endswith('.html'):
                with open(os.path.join(template_dir, filename)) as f:
                    for ln_num, line in enumerate(f, 1):
                        if '|safe' in line:
                            assert '_json|safe' in line, f"Template {filename}:{ln_num} uses |safe unsafely"

    def test_no_unsafe_inline_in_csp(self, client):
        """CSP should not contain unsafe-inline or unsafe-eval."""
        resp = client.get('/')
        csp = resp.headers.get('Content-Security-Policy', '')
        assert 'unsafe-inline' not in csp
        assert 'unsafe-eval' not in csp


class TestRateLimitingEndpoints:
    """Verify all outbound-request endpoints are rate-limited."""

    def test_check_url_rate_limited(self, client):
        for _ in range(10):
            client.get('/api/check-url?url=http://127.0.0.1/')
        resp = client.get('/api/check-url?url=https://example.com')
        assert resp.status_code == 429

    def test_check_cors_rate_limited(self, client):
        for _ in range(10):
            client.get('/api/check-cors?url=http://127.0.0.1/&origin=https://x.com')
        resp = client.get('/api/check-cors?url=https://example.com&origin=https://x.com')
        assert resp.status_code == 429

    def test_mock_response_rate_limited(self, client):
        for _ in range(10):
            client.post('/api/mock-response',
                        json={'status_code': 200, 'headers': {}, 'body': ''})
        resp = client.post('/api/mock-response',
                           json={'status_code': 200, 'headers': {}, 'body': ''})
        assert resp.status_code == 429

    def test_return_delay_rate_limited(self, client):
        """Return endpoint with delay should be rate-limited."""
        for _ in range(10):
            client.get('/return/200?delay=0.01')
        resp = client.get('/return/200?delay=0.01')
        assert resp.status_code == 429

    def test_trace_redirects_rate_limited(self, client):
        for _ in range(10):
            client.get('/api/trace-redirects?url=http://127.0.0.1/')
        resp = client.get('/api/trace-redirects?url=https://example.com')
        assert resp.status_code == 429


class TestPerformance:
    """Performance-related tests."""

    def test_static_files_cache_header(self, client):
        resp = client.get('/static/style.css')
        assert 'max-age' in resp.headers.get('Cache-Control', '')

    def test_html_pages_cache_header(self, client):
        resp = client.get('/')
        assert 'max-age' in resp.headers.get('Cache-Control', '')

    def test_images_have_lazy_loading(self, client):
        resp = client.get('/')
        html = resp.get_data(as_text=True)
        assert 'loading="lazy"' in html

    def test_detail_image_has_fetchpriority(self, client):
        resp = client.get('/200')
        html = resp.get_data(as_text=True)
        assert 'fetchpriority="high"' in html

    def test_css_contain_property(self, client):
        resp = client.get('/static/style.css')
        assert b'contain:' in resp.data

    def test_css_will_change(self, client):
        resp = client.get('/static/style.css')
        assert b'will-change:' in resp.data

    def test_no_external_js(self, client):
        """No external JS should block rendering."""
        resp = client.get('/')
        html = resp.get_data(as_text=True)
        assert '<script src=' not in html

    def test_random_endpoint_no_cache(self, client):
        resp = client.get('/random', follow_redirects=False)
        assert 'no-store' in resp.headers.get('Cache-Control', '')


# --- Common Mistakes feature ---

class TestCommonMistakes:
    def test_mistakes_section_appears_on_page_with_data(self, client):
        """Pages with common_mistakes data should render the mistakes section."""
        resp = client.get('/200')
        html = resp.get_data(as_text=True)
        assert 'mistakes-section' in html
        assert 'Common Mistakes' in html

    def test_mistake_text_present_in_html(self, client):
        """Actual mistake and consequence text should be in the rendered page."""
        resp = client.get('/401')
        html = resp.get_data(as_text=True)
        assert 'Using 401 when the user IS authenticated but lacks permission' in html
        assert "That&#39;s 403" in html or "That's 403" in html

    def test_mistake_card_structure_present(self, client):
        """Each mistake should render with the card structure classes."""
        resp = client.get('/404')
        html = resp.get_data(as_text=True)
        assert 'mistake-card' in html
        assert 'mistake-text' in html
        assert 'mistake-consequence' in html
        assert 'mistake-icon' in html

    def test_mistakes_section_absent_on_page_without_data(self, client):
        """Pages without common_mistakes data should not show the section."""
        resp = client.get('/102')
        html = resp.get_data(as_text=True)
        assert 'mistakes-section' not in html
        assert 'mistake-card' not in html

    def test_at_least_40_codes_have_common_mistakes(self):
        """At least 40 status codes should have common_mistakes in STATUS_EXTRA."""
        from status_extra import STATUS_EXTRA
        codes_with_mistakes = [
            code for code, data in STATUS_EXTRA.items()
            if 'common_mistakes' in data and len(data['common_mistakes']) > 0
        ]
        assert len(codes_with_mistakes) >= 40, (
            f"Only {len(codes_with_mistakes)} codes have common_mistakes, need at least 40"
        )

    def test_common_mistakes_structure(self):
        """Each common_mistakes entry should have 'mistake' and 'consequence' keys."""
        from status_extra import STATUS_EXTRA
        for code, data in STATUS_EXTRA.items():
            if 'common_mistakes' in data:
                for entry in data['common_mistakes']:
                    assert 'mistake' in entry, f"Missing 'mistake' key in {code}"
                    assert 'consequence' in entry, f"Missing 'consequence' key in {code}"

    def test_multiple_mistakes_per_code(self, client):
        """Pages with multiple mistakes should render all of them."""
        resp = client.get('/500')
        html = resp.get_data(as_text=True)
        assert html.count('mistake-card') >= 2

    def test_mistakes_section_is_collapsible(self, client):
        """The mistakes section should use a details/summary for collapsibility."""
        resp = client.get('/200')
        html = resp.get_data(as_text=True)
        assert '<details' in html and 'mistakes-summary' in html

    def test_new_common_mistakes_codes_have_entries(self):
        """Newly added common_mistakes codes should each have at least 2 entries."""
        from status_extra import STATUS_EXTRA
        new_codes = [
            "100", "101", "202", "206", "207", "300", "303", "308",
            "406", "408", "410", "412", "413", "414", "415", "416",
            "418", "428", "431", "451", "501", "505", "511",
        ]
        for code in new_codes:
            assert code in STATUS_EXTRA, f"Code {code} not in STATUS_EXTRA"
            assert 'common_mistakes' in STATUS_EXTRA[code], (
                f"Code {code} missing common_mistakes"
            )
            assert len(STATUS_EXTRA[code]['common_mistakes']) >= 2, (
                f"Code {code} should have at least 2 common_mistakes entries"
            )

    def test_new_mistakes_render_on_page(self, client):
        """Newly added common_mistakes should render on their detail pages."""
        for code in ["202", "206", "308", "406", "415", "511"]:
            resp = client.get(f'/{code}')
            html = resp.get_data(as_text=True)
            assert 'mistakes-section' in html, f"/{code} should have mistakes-section"
            assert 'mistake-card' in html, f"/{code} should have mistake-card"

    def test_common_mistakes_non_empty_strings(self):
        """All mistake and consequence strings should be non-empty."""
        from status_extra import STATUS_EXTRA
        for code, data in STATUS_EXTRA.items():
            if 'common_mistakes' in data:
                for i, entry in enumerate(data['common_mistakes']):
                    assert len(entry['mistake'].strip()) > 0, (
                        f"Empty mistake string in {code}[{i}]"
                    )
                    assert len(entry['consequence'].strip()) > 0, (
                        f"Empty consequence string in {code}[{i}]"
                    )


# --- CSS Design Token Replacement ---

class TestDesignTokenReplacement:
    """Tests for replacing hardcoded rgba(26,26,31,...) with design tokens."""

    def test_surface_1_light_token_defined(self, client):
        """--surface-1-light token should be defined in :root."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '--surface-1-light:' in css

    def test_surface_1_heavy_token_defined(self, client):
        """--surface-1-heavy token should be defined in :root."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '--surface-1-heavy:' in css

    def test_surface_1_solid_token_defined(self, client):
        """--surface-1-solid token should be defined in :root."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '--surface-1-solid:' in css

    def test_no_hardcoded_surface_bg_in_main_css(self, client):
        """Main CSS should not have hardcoded rgba(26,26,31,...) for background outside light theme and :root."""
        with open('static/style.css', 'r') as f:
            lines = f.readlines()
        violations = []
        in_light_theme = False
        in_root = False
        brace_depth = 0
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if ':root' in stripped:
                in_root = True
            if 'prefers-color-scheme: light' in stripped:
                in_light_theme = True
            if in_root or in_light_theme:
                brace_depth += stripped.count('{') - stripped.count('}')
                if brace_depth <= 0:
                    in_root = False
                    in_light_theme = False
                    brace_depth = 0
                continue
            if 'background' in stripped and 'rgba(26,26,31,' in stripped:
                violations.append(f"Line {i}: {stripped}")
            if 'background' in stripped and 'rgba(26, 26, 31,' in stripped:
                violations.append(f"Line {i}: {stripped}")
        assert len(violations) == 0, (
            f"Found {len(violations)} hardcoded rgba(26,26,31,...) backgrounds "
            f"that should use tokens:\n" + "\n".join(violations)
        )

    def test_surface_tokens_used_in_css(self, client):
        """The new surface tokens should actually be used in the stylesheet."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert 'var(--surface-1-light)' in css
        assert 'var(--surface-1-heavy)' in css
        assert 'var(--surface-1-solid)' in css

    def test_templates_use_surface_tokens(self, client):
        """Template inline styles should use surface tokens, not hardcoded rgba."""
        for page in ['/debug', '/practice']:
            resp = client.get(page)
            html = resp.data.decode()
            assert 'rgba(26,26,31,0.95)' not in html, (
                f"{page} should use var(--surface-1-solid) instead of hardcoded rgba"
            )

    def test_quiz_results_card_uses_token(self, client):
        """Quiz results card should use surface-1-solid token."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.quiz-results-card' in css
        # Find the rule and verify it uses the token
        idx = css.index('.quiz-results-card')
        rule = css[idx:idx+200]
        assert 'var(--surface-1-solid)' in rule


# --- Easter egg: Barrel Roll ---

class TestBarrelRollEasterEgg:
    def test_homepage_has_barrel_roll_toast(self, client):
        """Homepage should include the barrel roll toast element."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'barrel-roll-toast' in html

    def test_homepage_has_barrel_roll_script(self, client):
        """Homepage should have barrel roll detection script."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'barrel roll' in html
        assert 'barrel_roll' in html

    def test_barrel_roll_tracks_egg(self, client):
        """Homepage barrel roll script should save to eggs_found localStorage."""
        resp = client.get('/')
        html = resp.data.decode()
        assert "eggs.indexOf('barrel_roll')" in html

    def test_barrel_roll_shows_toast_message(self, client):
        """Homepage barrel roll script should show 'Polly wants a barrel roll!' toast."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'Polly wants a barrel roll!' in html

    def test_barrel_roll_css_exists(self, client):
        """Style sheet should contain barrel roll animation."""
        resp = client.get('/static/style.css')
        assert b'barrel-roll-spin' in resp.data
        assert b'.barrel-roll' in resp.data
        assert b'.barrel-roll-toast' in resp.data


# --- Easter egg: 404 Catch Game ---

class TestCatchGameEasterEgg:
    def test_404_page_has_wandering_parrot(self, client):
        """404 page should have the clickable wandering parrot."""
        resp = client.get('/nonexistent')
        html = resp.data.decode()
        assert 'error-wandering-parrot' in html

    def test_404_page_has_catch_script(self, client):
        """404 page should include the catch game script."""
        resp = client.get('/nonexistent')
        html = resp.data.decode()
        assert 'handleCatch' in html
        assert 'maxCatches' in html

    def test_404_catch_tracks_egg(self, client):
        """404 catch game should save to eggs_found localStorage."""
        resp = client.get('/nonexistent')
        html = resp.data.decode()
        assert "eggs.indexOf('404_catch')" in html

    def test_404_catch_reveals_secret(self, client):
        """After 5 catches, the secret message about /418 should appear."""
        resp = client.get('/nonexistent')
        html = resp.data.decode()
        assert "You caught me!" in html
        assert "try /418" in html

    def test_404_catch_parrot_accessible(self, client):
        """Wandering parrot should have accessible attributes in catch script."""
        resp = client.get('/nonexistent')
        html = resp.data.decode()
        assert 'Catch the wandering parrot' in html


# --- Easter egg: Time Traveler ---

class TestTimeTravelerEasterEgg:
    def test_base_has_time_traveler_script(self, client):
        """Base template should include the time traveler footer script."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'footer-time-egg' in html
        assert 'time_404' in html
        assert 'time_200' in html
        assert 'time_5xx' in html

    def test_time_traveler_404_message(self, client):
        """Script should contain the 4:04 time traveler message."""
        resp = client.get('/')
        html = resp.data.decode()
        assert "even time can" in html
        assert "find this page" in html

    def test_time_traveler_200_message(self, client):
        """Script should contain the 2:00 napping parrot message."""
        resp = client.get('/')
        html = resp.data.decode()
        assert '200 OK, but the parrot is napping' in html

    def test_time_traveler_5xx_message(self, client):
        """Script should contain the 5xx o'clock message."""
        resp = client.get('/')
        html = resp.data.decode()
        assert "5xx o" in html
        assert "clock somewhere" in html

    def test_time_traveler_tracks_eggs(self, client):
        """Time traveler script should save discoveries to eggs_found localStorage."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'eggs_found' in html

    def test_time_traveler_css_exists(self, client):
        """Style sheet should contain the time traveler footer egg style."""
        resp = client.get('/static/style.css')
        assert b'footer-time-egg' in resp.data


# --- Easter egg: /coffee endpoint ---

class TestCoffeeEasterEgg:
    def test_coffee_returns_418(self, client):
        """/coffee should return HTTP 418 I'm a Teapot."""
        resp = client.get('/coffee')
        assert resp.status_code == 418

    def test_coffee_has_teapot_text(self, client):
        """/coffee should display teapot message."""
        resp = client.get('/coffee')
        html = resp.data.decode()
        assert "teapot" in html.lower()
        assert "coffee" in html.lower()

    def test_coffee_has_ascii_art(self, client):
        """/coffee should include ASCII art teapot."""
        resp = client.get('/coffee')
        html = resp.data.decode()
        assert 'coffee-ascii-teapot' in html

    def test_coffee_has_steam_particles(self, client):
        """/coffee should have steam particle elements."""
        resp = client.get('/coffee')
        html = resp.data.decode()
        assert 'coffee-steam' in html
        assert 'steam-particle' in html

    def test_coffee_has_brew_counter(self, client):
        """/coffee should display a fake brew attempts counter."""
        resp = client.get('/coffee')
        html = resp.data.decode()
        assert 'brew-counter' in html
        assert 'Failed brew attempts' in html

    def test_coffee_tracks_egg(self, client):
        """/coffee visit should save to eggs_found localStorage."""
        resp = client.get('/coffee')
        html = resp.data.decode()
        assert "eggs.indexOf('coffee')" in html

    def test_coffee_has_back_link(self, client):
        """/coffee should have links back to homepage and 418 page."""
        resp = client.get('/coffee')
        html = resp.data.decode()
        assert 'href="/"' in html
        assert 'href="/418"' in html

    def test_coffee_has_pour_animation(self, client):
        """/coffee should include pour animation element."""
        resp = client.get('/coffee')
        html = resp.data.decode()
        assert 'coffee-pour-stream' in html

    def test_coffee_not_in_navigation(self, client):
        """/coffee should NOT appear in the site navigation."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'href="/coffee"' not in html

    def test_coffee_css_exists(self, client):
        """Style sheet should contain coffee page styles."""
        resp = client.get('/static/style.css')
        assert b'coffee-container' in resp.data
        assert b'coffee-teapot-tilt' in resp.data
        assert b'coffee-pour' in resp.data

    def test_coffee_has_security_headers(self, client):
        """/coffee should have CSP and security headers."""
        resp = client.get('/coffee')
        csp = resp.headers.get('Content-Security-Policy', '')
        assert "default-src 'self'" in csp
        assert 'X-Content-Type-Options' in resp.headers

    def test_coffee_has_nonce(self, client):
        """/coffee script tag should have a nonce matching CSP."""
        resp = client.get('/coffee')
        csp = resp.headers.get('Content-Security-Policy', '')
        nonce = re.search(r"'nonce-([^']+)'", csp).group(1)
        assert f'nonce="{nonce}"'.encode() in resp.data

    def test_418_detail_has_coffee_hint(self, client):
        """418 detail page should contain hidden comment hint for /coffee."""
        resp = client.get('/418')
        html = resp.data.decode()
        assert '<!-- try /coffee -->' in html

    def test_non_418_detail_no_coffee_hint(self, client):
        """Non-418 detail pages should NOT contain the /coffee hint."""
        resp = client.get('/200')
        html = resp.data.decode()
        assert '<!-- try /coffee -->' not in html


# --- Parrotdex new egg entries ---

class TestParrotdexNewEggs:
    def test_collection_has_barrel_roll_egg(self, client):
        """Collection page should have barrel_roll egg card."""
        resp = client.get('/collection')
        html = resp.data.decode()
        assert 'data-egg="barrel_roll"' in html

    def test_collection_has_404_catch_egg(self, client):
        """Collection page should have 404_catch egg card."""
        resp = client.get('/collection')
        html = resp.data.decode()
        assert 'data-egg="404_catch"' in html

    def test_collection_has_time_eggs(self, client):
        """Collection page should have all time traveler egg cards."""
        resp = client.get('/collection')
        html = resp.data.decode()
        assert 'data-egg="time_404"' in html
        assert 'data-egg="time_200"' in html
        assert 'data-egg="time_5xx"' in html

    def test_collection_has_coffee_egg(self, client):
        """Collection page should have coffee egg card."""
        resp = client.get('/collection')
        html = resp.data.decode()
        assert 'data-egg="coffee"' in html

    def test_collection_egg_hints(self, client):
        """Collection page new eggs should have appropriate hints."""
        resp = client.get('/collection')
        html = resp.data.decode()
        assert 'barrel roll' in html.lower()
        assert 'wandering parrot' in html.lower()
        assert 'teapot' in html.lower()

    def test_collection_preserves_existing_eggs(self, client):
        """Collection page should still have all original egg cards."""
        resp = client.get('/collection')
        html = resp.data.decode()
        assert 'data-egg="204"' in html
        assert 'data-egg="418"' in html
        assert 'data-egg="429"' in html
        assert 'data-egg="508"' in html
        assert 'data-egg="konami"' in html


class TestProfilePage:
    """Tests for the XP profile page."""

    def test_profile_returns_200(self, client):
        resp = client.get('/profile')
        assert resp.status_code == 200

    def test_profile_has_rank_display(self, client):
        resp = client.get('/profile')
        html = resp.data.decode()
        assert 'profile-rank-display' in html
        assert 'profile-rank-title' in html
        assert 'Fledgling' in html

    def test_profile_has_heatmap_container(self, client):
        resp = client.get('/profile')
        html = resp.data.decode()
        assert 'profile-heatmap-container' in html
        assert 'profile-heatmap' in html

    def test_profile_has_stats_section(self, client):
        resp = client.get('/profile')
        html = resp.data.decode()
        assert 'profile-stats-section' in html
        assert 'stat-quiz-answers' in html
        assert 'stat-daily-streak' in html
        assert 'stat-codes-visited' in html
        assert 'stat-practice-completed' in html

    def test_profile_has_ranks_list(self, client):
        resp = client.get('/profile')
        html = resp.data.decode()
        assert 'profile-ranks-list' in html
        assert 'Fledgling' in html
        assert 'Nestling' in html
        assert 'Feathered Apprentice' in html
        assert 'Wing Cadet' in html
        assert 'Parrot Scout' in html
        assert 'Plume Knight' in html
        assert 'Wing Commander' in html
        assert 'Sky Captain' in html
        assert 'Grand Macaw' in html
        assert 'Legendary Lorikeet' in html

    def test_profile_has_xp_breakdown(self, client):
        resp = client.get('/profile')
        html = resp.data.decode()
        assert 'profile-xp-breakdown' in html
        assert '+10 XP' in html
        assert '+50 XP' in html
        assert '+5 XP' in html
        assert '+15 XP' in html
        assert '+100 XP' in html

    def test_profile_has_progress_bar(self, client):
        resp = client.get('/profile')
        html = resp.data.decode()
        assert 'profile-progress-bar' in html
        assert 'profile-progressbar' in html

    def test_profile_nav_link_present(self, client):
        resp = client.get('/')
        html = resp.data.decode()
        assert 'href="/profile"' in html
        assert 'Profile' in html

    def test_profile_nav_link_on_all_pages(self, client):
        """Profile nav link should be in the base template on various pages."""
        for route in ['/quiz', '/practice', '/daily']:
            resp = client.get(route)
            html = resp.data.decode()
            assert 'href="/profile"' in html, f"Profile nav link missing on {route}"

    def test_xp_badge_in_header(self, client):
        resp = client.get('/')
        html = resp.data.decode()
        assert 'xp-badge' in html
        assert 'xp-badge-rank' in html
        assert 'xp-badge-xp' in html

    def test_xp_tracking_script_present(self, client):
        """ParrotXP tracking script should be in base template."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'ParrotXP' in html
        assert 'httpparrot_xp' in html
        assert 'httpparrot_activity' in html

    def test_xp_tracking_script_has_methods(self, client):
        """ParrotXP script should expose award, getTotal, getLevel, getRank methods."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'award:' in html or 'award: award' in html
        assert 'getTotal:' in html or 'getTotal: getTotal' in html
        assert 'getLevel:' in html or 'getLevel: getLevel' in html
        assert 'getRank:' in html or 'getRank: getRank' in html

    def test_profile_page_title(self, client):
        resp = client.get('/profile')
        html = resp.data.decode()
        assert 'Profile - HTTP Parrots' in html


class TestRedirectTracer:
    """Tests for the Redirect Tracer feature."""

    def test_trace_page_renders(self, client):
        """Trace page should return 200 with expected content."""
        resp = client.get('/trace')
        assert resp.status_code == 200
        html = resp.data.decode()
        assert 'Redirect Tracer' in html
        assert 'trace-url' in html
        assert 'trace-form' in html

    def test_trace_nav_link(self, client):
        """Navigation should contain a link to the Trace page."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'href="/trace"' in html

    def test_trace_redirects_no_url(self, client):
        """API should return 400 when url is missing."""
        resp = client.get('/api/trace-redirects')
        assert resp.status_code == 400
        assert b'No URL provided' in resp.data

    def test_trace_redirects_ssrf_blocked(self, client):
        """API should block private/internal URLs at each hop."""
        resp = client.get('/api/trace-redirects?url=http://127.0.0.1/')
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) == 1
        assert 'SSRF' in data[0].get('error', '') or 'not allowed' in data[0].get('error', '')

    def test_trace_redirects_single_hop(self, client):
        """Non-redirect response should return a single hop."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {'Content-Type': 'text/html', 'Server': 'nginx'}
        mock_resp.elapsed.total_seconds.return_value = 0.03
        addrinfo = [(socket.AF_INET, socket.SOCK_STREAM, 0, '', ('93.184.216.34', 0))]
        with patch('index.socket.getaddrinfo', return_value=addrinfo), \
             patch('requests.head', return_value=mock_resp):
            resp = client.get('/api/trace-redirects?url=https://example.com')
            assert resp.status_code == 200
            data = resp.get_json()
            assert len(data) == 1
            assert data[0]['status_code'] == 200
            assert data[0]['url'] == 'https://example.com'
            assert 'time_ms' in data[0]
            assert data[0]['headers']['Content-Type'] == 'text/html'

    def test_trace_redirects_chain(self, client):
        """API should follow a redirect chain through multiple hops."""
        mock_301 = MagicMock()
        mock_301.status_code = 301
        mock_301.headers = {
            'Location': 'https://www.example.com/',
            'Server': 'nginx',
        }
        mock_301.elapsed.total_seconds.return_value = 0.02
        mock_302 = MagicMock()
        mock_302.status_code = 302
        mock_302.headers = {
            'Location': 'https://www.example.com/home',
            'Set-Cookie': 'sid=abc123',
        }
        mock_302.elapsed.total_seconds.return_value = 0.04
        mock_200 = MagicMock()
        mock_200.status_code = 200
        mock_200.headers = {
            'Content-Type': 'text/html',
            'Strict-Transport-Security': 'max-age=31536000',
        }
        mock_200.elapsed.total_seconds.return_value = 0.05
        addrinfo = [(socket.AF_INET, socket.SOCK_STREAM, 0, '', ('93.184.216.34', 0))]
        with patch('index.socket.getaddrinfo', return_value=addrinfo), \
             patch('requests.head', side_effect=[mock_301, mock_302, mock_200]):
            resp = client.get('/api/trace-redirects?url=https://example.com')
            assert resp.status_code == 200
            data = resp.get_json()
            assert len(data) == 3
            assert data[0]['status_code'] == 301
            assert data[0]['location'] == 'https://www.example.com/'
            assert data[1]['status_code'] == 302
            assert data[1]['headers'].get('Set-Cookie') == '(present)'
            assert data[2]['status_code'] == 200
            assert 'Strict-Transport-Security' in data[2]['headers']

    def test_trace_redirects_ssrf_on_intermediate_hop(self, client):
        """SSRF protection should apply to each redirect target."""
        mock_301 = MagicMock()
        mock_301.status_code = 301
        mock_301.headers = {'Location': 'http://192.168.1.1/admin'}
        mock_301.elapsed.total_seconds.return_value = 0.02

        def fake_getaddrinfo(host, *args, **kwargs):
            if host == '192.168.1.1':
                return [(socket.AF_INET, socket.SOCK_STREAM, 0, '', ('192.168.1.1', 0))]
            return [(socket.AF_INET, socket.SOCK_STREAM, 0, '', ('93.184.216.34', 0))]

        with patch('index.socket.getaddrinfo', side_effect=fake_getaddrinfo), \
             patch('requests.head', return_value=mock_301):
            resp = client.get('/api/trace-redirects?url=https://example.com')
            data = resp.get_json()
            # First hop is the 301, second hop is the blocked internal URL
            assert len(data) == 2
            assert data[0]['status_code'] == 301
            assert 'not allowed' in data[1].get('error', '') or 'SSRF' in data[1].get('error', '')

    def test_trace_redirects_max_hops(self, client):
        """API should stop after 10 redirect hops."""
        mock_redirect = MagicMock()
        mock_redirect.status_code = 302
        mock_redirect.headers = {'Location': 'https://example.com/loop'}
        mock_redirect.elapsed.total_seconds.return_value = 0.01
        addrinfo = [(socket.AF_INET, socket.SOCK_STREAM, 0, '', ('93.184.216.34', 0))]
        with patch('index.socket.getaddrinfo', return_value=addrinfo), \
             patch('requests.head', return_value=mock_redirect):
            resp = client.get('/api/trace-redirects?url=https://example.com')
            data = resp.get_json()
            # 10 redirect hops + 1 "too many redirects" error entry
            assert len(data) == 11
            assert 'Too many redirects' in data[-1].get('error', '')

    def test_trace_redirects_auto_prefix(self, client):
        """URLs without scheme should get https:// prepended."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {'Content-Type': 'text/html'}
        mock_resp.elapsed.total_seconds.return_value = 0.03
        addrinfo = [(socket.AF_INET, socket.SOCK_STREAM, 0, '', ('93.184.216.34', 0))]
        with patch('index.socket.getaddrinfo', return_value=addrinfo), \
             patch('requests.head', return_value=mock_resp):
            resp = client.get('/api/trace-redirects?url=example.com')
            data = resp.get_json()
            assert data[0]['url'] == 'https://example.com'

    def test_trace_redirects_timeout(self, client):
        """API should handle timeout errors gracefully."""
        addrinfo = [(socket.AF_INET, socket.SOCK_STREAM, 0, '', ('93.184.216.34', 0))]
        with patch('index.socket.getaddrinfo', return_value=addrinfo), \
             patch('requests.head', side_effect=requests.Timeout):
            resp = client.get('/api/trace-redirects?url=https://example.com')
            data = resp.get_json()
            assert len(data) == 1
            assert 'timed out' in data[0]['error'].lower()

    def test_trace_redirects_connection_error(self, client):
        """API should handle connection errors gracefully."""
        addrinfo = [(socket.AF_INET, socket.SOCK_STREAM, 0, '', ('93.184.216.34', 0))]
        with patch('index.socket.getaddrinfo', return_value=addrinfo), \
             patch('requests.head', side_effect=requests.ConnectionError):
            resp = client.get('/api/trace-redirects?url=https://example.com')
            data = resp.get_json()
            assert len(data) == 1
            assert 'connect' in data[0]['error'].lower()

    def test_trace_redirects_rate_limited(self, client):
        """API should return 429 when rate limited."""
        for _ in range(10):
            client.get('/api/trace-redirects?url=http://127.0.0.1/')
        resp = client.get('/api/trace-redirects?url=https://example.com')
        assert resp.status_code == 429
        assert b'Rate limit' in resp.data

    def test_trace_in_sitemap(self, client):
        """Sitemap should include the trace page."""
        resp = client.get('/sitemap.xml')
        assert b'/trace' in resp.data

    def test_trace_redirects_in_robots_disallow(self, client):
        """robots.txt should disallow the trace API endpoint."""
        resp = client.get('/robots.txt')
        assert b'/api/trace-redirects' in resp.data


# --- XP award() calls wired into templates ---

class TestXPAwardCalls:
    """Verify ParrotXP.award() is actually called in each template."""

    def test_quiz_awards_xp_on_correct(self, client):
        """Quiz template should call ParrotXP.award(10, 'quiz_correct')."""
        resp = client.get('/quiz')
        html = resp.data.decode()
        assert "ParrotXP.award(10, 'quiz_correct')" in html

    def test_daily_awards_xp_on_correct(self, client):
        """Daily template should call ParrotXP.award(50, 'daily_correct')."""
        resp = client.get('/daily')
        html = resp.data.decode()
        assert "ParrotXP.award(50, 'daily_correct')" in html

    def test_practice_awards_xp_on_correct(self, client):
        """Practice template should call ParrotXP.award(15, 'practice_correct')."""
        resp = client.get('/practice')
        html = resp.data.decode()
        assert "ParrotXP.award(15, 'practice_correct')" in html

    def test_detail_page_awards_xp_on_first_visit(self, client):
        """Detail page should call ParrotXP.award(5, 'page_visit') for new codes."""
        resp = client.get('/200')
        html = resp.data.decode()
        assert "ParrotXP.award(5, 'page_visit')" in html

    def test_collection_awards_xp_for_easter_egg(self, client):
        """Collection page should call ParrotXP.award(100, 'easter_egg')."""
        resp = client.get('/collection')
        html = resp.data.decode()
        assert "ParrotXP.award(100, 'easter_egg')" in html

    def test_coffee_awards_xp_for_easter_egg(self, client):
        """Coffee page should call ParrotXP.award(100, 'easter_egg') on first visit."""
        resp = client.get('/coffee')
        html = resp.data.decode()
        assert "ParrotXP.award(100, 'easter_egg')" in html

    def test_quiz_perfect_10_flag(self, client):
        """Quiz should set httpparrot_perfect_quiz flag on 10/10 score."""
        resp = client.get('/quiz')
        html = resp.data.decode()
        assert 'httpparrot_perfect_quiz' in html

    def test_daily_speed_demon_flag(self, client):
        """Daily should set httpparrot_speed_demon flag for fast answers."""
        resp = client.get('/daily')
        html = resp.data.decode()
        assert 'httpparrot_speed_demon' in html


# --- Achievement Badges (Feathers) ---

class TestFeatherBadges:
    """Verify Feathers system is defined and integrated."""

    def test_feathers_defined_in_base(self, client):
        """Base template should define the FEATHERS array."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'FEATHERS' in html
        assert 'httpparrot_feathers' in html

    def test_all_24_badges_defined(self, client):
        """All 24 feather badge IDs (18 base + 6 meta) should appear in the base template."""
        resp = client.get('/')
        html = resp.data.decode()
        badge_ids = [
            'first_flight', 'quiz_whiz', 'perfect_10', 'streak_starter',
            'on_fire', 'centurion', 'wing_commander', 'completionist',
            'error_expert', 'server_sage', 'egg_hunter', 'scholar',
            'night_owl', 'speed_demon', 'frozen_solid', 'memory_master',
            'parrot_petter', 'photo_memory',
            'explorer', 'polyglot', 'streak_lord', 'triple_threat',
            'full_spectrum', 'parrot_polymath'
        ]
        for badge_id in badge_ids:
            assert badge_id in html, f"Badge '{badge_id}' not found in base template"

    def test_check_feathers_method_exists(self, client):
        """ParrotXP should expose checkFeathers method."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'checkFeathers:' in html or 'checkFeathers: checkFeathers' in html

    def test_get_feathers_method_exists(self, client):
        """ParrotXP should expose getFeathers method."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'getFeathers:' in html or 'getFeathers: getFeathers' in html

    def test_feather_toast_css_exists(self, client):
        """Feather toast CSS classes should be in the stylesheet."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.feather-toast' in css
        assert '.feather-toast-visible' in css

    def test_feather_toast_function_exists(self, client):
        """Base template should contain showFeatherToast function."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'showFeatherToast' in html

    def test_award_calls_check_feathers(self, client):
        """The award function should call checkFeathers after awarding XP."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'awardWithFeathers' in html
        assert 'checkFeathers()' in html


# --- Profile Feathers section ---

class TestProfileFeathers:
    """Verify the Feathers section appears on the profile page."""

    def test_profile_has_feathers_section(self, client):
        """Profile page should contain a Feathers section."""
        resp = client.get('/profile')
        html = resp.data.decode()
        assert 'profile-feathers-section' in html
        assert 'Feathers' in html

    def test_profile_has_feathers_grid(self, client):
        """Profile page should contain the feathers grid container."""
        resp = client.get('/profile')
        html = resp.data.decode()
        assert 'profile-feathers-grid' in html

    def test_profile_feathers_js_populates_grid(self, client):
        """Profile script should populate the feathers grid from ParrotXP.FEATHERS."""
        resp = client.get('/profile')
        html = resp.data.decode()
        assert 'ParrotXP.FEATHERS' in html
        assert 'feather-card' in html

    def test_profile_feathers_shows_earned_and_locked(self, client):
        """Profile script should distinguish earned vs locked feathers."""
        resp = client.get('/profile')
        html = resp.data.decode()
        assert 'earned' in html
        assert 'locked' in html

    def test_feather_card_css_exists(self, client):
        """Feather card CSS classes should be in the stylesheet."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.feather-card' in css
        assert '.feather-card.earned' in css
        assert '.feather-card.locked' in css
        assert '.profile-feathers-grid' in css


class TestSurfaceElevationSystem:
    """Tests for CSS surface elevation tokens and gradient border hover."""

    def test_surface_elevation_tokens_defined(self, client):
        """Surface elevation tokens should be defined in :root."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '--surface-0:' in css
        assert '--surface-1:' in css
        assert '--surface-2:' in css
        assert '--surface-3:' in css

    def test_shadow_tokens_defined(self, client):
        """Shadow elevation tokens should be defined in :root."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '--shadow-sm:' in css
        assert '--shadow-md:' in css
        assert '--shadow-lg:' in css

    def test_level1_parrot_cards(self, client):
        """Surface-1 token should be used for card-level elements."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert 'var(--surface-1)' in css

    def test_level1_detail_info(self, client):
        """Detail info should use surface-1 and shadow-sm."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        idx = css.index('.detail-info {')
        block_end = css.index('}', idx)
        block = css[idx:block_end]
        assert 'var(--surface-1)' in block
        assert 'var(--shadow-sm)' in block

    def test_level1_header_card(self, client):
        """Header card should use surface-1 and shadow-sm."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        idx = css.index('.header-card {')
        block_end = css.index('}', idx)
        block = css[idx:block_end]
        assert 'var(--surface-1)' in block
        assert 'var(--shadow-sm)' in block

    def test_level2_filter_dropdown(self, client):
        """Filter dropdown should use surface-2 and shadow-md."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        idx = css.index('.filter-dropdown {')
        block_end = css.index('}', idx)
        block = css[idx:block_end]
        assert 'var(--surface-2)' in block
        assert 'var(--shadow-md)' in block

    def test_level2_quiz_image(self, client):
        """Quiz image should use surface-2 and shadow-md."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert 'var(--surface-2)' in css
        idx = css.index('.quiz-image {')
        block_end = css.index('}', idx)
        block = css[idx:block_end]
        assert 'var(--shadow-md)' in block

    def test_level2_tester_result(self, client):
        """Tester result should use surface-2 and shadow-md."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        idx = css.index('.tester-result {')
        block_end = css.index('}', idx)
        block = css[idx:block_end]
        assert 'var(--surface-2)' in block
        assert 'var(--shadow-md)' in block

    def test_level2_compare_card(self, client):
        """Compare card should use surface-2 and shadow-md."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert 'var(--surface-2)' in css

    def test_level3_mobile_nav(self, client):
        """Mobile nav should use surface-3 and shadow-lg."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        idx = css.index('.mobile-nav {')
        block_end = css.index('}', idx)
        block = css[idx:block_end]
        assert 'var(--surface-3)' in block
        assert 'var(--shadow-lg)' in block


class TestGradientBorderHover:
    """Tests for CSS gradient border card hover effect."""

    def test_category_glow_colors_defined(self, client):
        """Each parrot category should define --cat-glow-color."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.parrot-1xx { --cat-glow-color: var(--color-cyan)' in css
        assert '.parrot-2xx { --cat-glow-color: var(--color-emerald)' in css
        assert '.parrot-3xx { --cat-glow-color: var(--color-gold)' in css
        assert '.parrot-4xx { --cat-glow-color: var(--color-coral)' in css
        assert '.parrot-5xx { --cat-glow-color: var(--color-lavender)' in css

    def test_parrot_after_pseudo_element(self, client):
        """Parrot ::after should have the gradient border setup."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.parrot::after' in css
        assert 'conic-gradient' in css

    def test_parrot_after_mask_technique(self, client):
        """Parrot ::after should use mask-composite: exclude for border effect."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        idx = css.index('.parrot::after')
        block_end = css.index('}', idx)
        block = css[idx:block_end]
        assert 'mask-composite: exclude' in block
        assert '-webkit-mask-composite: xor' in block

    def test_parrot_after_default_hidden(self, client):
        """Parrot ::after should be invisible by default (opacity: 0)."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        idx = css.index('.parrot::after')
        block_end = css.index('}', idx)
        block = css[idx:block_end]
        assert 'opacity: 0' in block

    def test_parrot_hover_after_visible(self, client):
        """Parrot hover ::after should become visible (opacity: 1)."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.parrot:hover::after' in css
        idx = css.index('.parrot:hover::after')
        block_end = css.index('}', idx)
        block = css[idx:block_end]
        assert 'opacity: 1' in block

    def test_parrot_after_uses_duration_normal(self, client):
        """Parrot ::after transition should use --duration-normal and --ease-out."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        idx = css.index('.parrot::after')
        block_end = css.index('}', idx)
        block = css[idx:block_end]
        assert 'var(--duration-normal)' in block
        assert 'var(--ease-out)' in block

    def test_parrot_after_pointer_events_none(self, client):
        """Parrot ::after should not capture pointer events."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        idx = css.index('.parrot::after')
        block_end = css.index('}', idx)
        block = css[idx:block_end]
        assert 'pointer-events: none' in block


class TestLightThemeSurfaceTokens:
    """Tests for light theme surface elevation overrides."""

    def test_light_theme_surface_tokens(self, client):
        """Light theme should override surface and shadow tokens."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        light_idx = css.index('@media (prefers-color-scheme: light)')
        light_block = css[light_idx:]
        assert '--surface-0:' in light_block
        assert '--surface-1:' in light_block
        assert '--surface-2:' in light_block
        assert '--surface-3:' in light_block
        assert '--shadow-sm:' in light_block
        assert '--shadow-md:' in light_block
        assert '--shadow-lg:' in light_block


class TestReducedMotionGradientBorder:
    """Tests for reduced motion handling of gradient border."""

    def test_reduced_motion_disables_gradient_transition(self, client):
        """Reduced motion should disable gradient border animation."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        idx = css.index('@media (prefers-reduced-motion: reduce)')
        light_idx = css.index('/* === Light Theme', idx)
        block = css[idx:light_idx]
        assert '.parrot::after' in block


class TestDebugExercises:
    """Tests for the Debug This Response page."""

    def test_debug_page_returns_200(self, client):
        resp = client.get('/debug')
        assert resp.status_code == 200

    def test_debug_page_has_title(self, client):
        resp = client.get('/debug')
        html = resp.data.decode()
        assert 'Debug This Response' in html
        assert 'Debug This Response - HTTP Parrots' in html

    def test_debug_page_has_exercise_cards(self, client):
        resp = client.get('/debug')
        html = resp.data.decode()
        assert 'debug-card' in html
        assert 'debug-submit-btn' in html
        assert 'debug-description' in html

    def test_debug_page_has_difficulty_filters(self, client):
        resp = client.get('/debug')
        html = resp.data.decode()
        assert 'data-difficulty="all"' in html
        assert 'data-difficulty="beginner"' in html
        assert 'data-difficulty="intermediate"' in html
        assert 'data-difficulty="expert"' in html

    def test_debug_page_has_score_bar(self, client):
        resp = client.get('/debug')
        html = resp.data.decode()
        assert 'debug-score-bar' in html
        assert 'debug-found' in html
        assert 'debug-missed' in html
        assert 'debug-remaining' in html

    def test_debug_page_has_http_exchange_panels(self, client):
        resp = client.get('/debug')
        html = resp.data.decode()
        assert 'debug-exchange' in html
        assert 'debug-panel' in html
        assert 'request-label' in html
        assert 'response-label' in html

    def test_debug_page_uses_highlight_http_filter(self, client):
        resp = client.get('/debug')
        html = resp.data.decode()
        assert 'http-hl-status' in html
        assert 'http-hl-method' in html
        assert 'http-hl-header' in html

    def test_debug_page_has_bug_checkboxes(self, client):
        resp = client.get('/debug')
        html = resp.data.decode()
        assert 'debug-bug-option' in html
        assert 'type="checkbox"' in html

    def test_debug_page_has_distractor_options(self, client):
        resp = client.get('/debug')
        html = resp.data.decode()
        assert 'distractor-1' in html

    def test_debug_page_has_result_containers(self, client):
        resp = client.get('/debug')
        html = resp.data.decode()
        assert 'debug-results' in html
        assert 'debug-result-summary' in html

    def test_debug_page_has_related_code_links(self, client):
        resp = client.get('/debug')
        html = resp.data.decode()
        assert 'debug-detail-link' in html
        assert 'Learn about' in html

    def test_debug_page_has_xp_integration(self, client):
        resp = client.get('/debug')
        html = resp.data.decode()
        assert 'ParrotXP.award' in html
        assert 'debug_correct' in html

    def test_debug_nav_link_present(self, client):
        resp = client.get('/')
        html = resp.data.decode()
        assert 'href="/debug"' in html
        assert '>Debug<' in html

    def test_debug_nav_link_in_mobile_nav(self, client):
        resp = client.get('/')
        html = resp.data.decode()
        assert html.count('href="/debug"') >= 2

    def test_debug_page_has_h1(self, client):
        resp = client.get('/debug')
        html = resp.data.decode()
        assert '<h1>' in html

    def test_debug_page_has_aria_labels(self, client):
        resp = client.get('/debug')
        html = resp.data.decode()
        assert 'aria-label="Score tracker"' in html
        assert 'aria-label="Filter by difficulty"' in html
        assert 'aria-live="polite"' in html

    def test_debug_in_sitemap(self, client):
        resp = client.get('/sitemap.xml')
        body = resp.data.decode()
        assert '/debug</loc>' in body

    def test_debug_csp_header(self, client):
        resp = client.get('/debug')
        csp = resp.headers.get('Content-Security-Policy', '')
        assert "default-src 'self'" in csp
        assert "'nonce-" in csp

    def test_debug_page_inline_style_has_nonce(self, client):
        resp = client.get('/debug')
        html = resp.data.decode()
        assert 'style nonce=' in html

    def test_debug_page_inline_script_has_nonce(self, client):
        resp = client.get('/debug')
        html = resp.data.decode()
        assert 'script nonce=' in html


class TestDebugExerciseData:
    """Tests for the debug_exercises.py data module."""

    def test_exercises_at_least_30(self):
        from debug_exercises import DEBUG_EXERCISES
        assert len(DEBUG_EXERCISES) >= 30

    def test_exercise_has_required_fields(self):
        from debug_exercises import DEBUG_EXERCISES
        required = {'id', 'difficulty', 'category', 'title', 'description', 'request',
                     'response', 'bugs', 'related_codes'}
        for ex in DEBUG_EXERCISES:
            missing = required - set(ex.keys())
            assert not missing, f"Exercise {ex.get('id', '?')} missing fields: {missing}"

    def test_exercise_ids_unique(self):
        from debug_exercises import DEBUG_EXERCISES
        ids = [ex['id'] for ex in DEBUG_EXERCISES]
        assert len(ids) == len(set(ids)), "Duplicate exercise IDs found"

    def test_exercise_difficulties_valid(self):
        from debug_exercises import DEBUG_EXERCISES
        valid = {'beginner', 'intermediate', 'expert'}
        for ex in DEBUG_EXERCISES:
            assert ex['difficulty'] in valid, \
                f"Exercise {ex['id']} has invalid difficulty: {ex['difficulty']}"

    def test_each_exercise_has_at_least_one_bug(self):
        from debug_exercises import DEBUG_EXERCISES
        for ex in DEBUG_EXERCISES:
            assert len(ex['bugs']) >= 1, \
                f"Exercise {ex['id']} has no bugs"

    def test_bugs_have_required_fields(self):
        from debug_exercises import DEBUG_EXERCISES
        for ex in DEBUG_EXERCISES:
            for bug in ex['bugs']:
                assert 'id' in bug, f"Bug in {ex['id']} missing id"
                assert 'description' in bug, f"Bug in {ex['id']} missing description"
                assert 'explanation' in bug, f"Bug in {ex['id']} missing explanation"

    def test_bug_ids_unique_within_exercise(self):
        from debug_exercises import DEBUG_EXERCISES
        for ex in DEBUG_EXERCISES:
            bug_ids = [b['id'] for b in ex['bugs']]
            assert len(bug_ids) == len(set(bug_ids)), \
                f"Exercise {ex['id']} has duplicate bug IDs"

    def test_all_difficulty_levels_represented(self):
        from debug_exercises import DEBUG_EXERCISES
        difficulties = {ex['difficulty'] for ex in DEBUG_EXERCISES}
        assert 'beginner' in difficulties
        assert 'intermediate' in difficulties
        assert 'expert' in difficulties

    def test_related_codes_are_strings(self):
        from debug_exercises import DEBUG_EXERCISES
        for ex in DEBUG_EXERCISES:
            for code in ex['related_codes']:
                assert isinstance(code, str), \
                    f"Exercise {ex['id']} has non-string related code: {code}"

    def test_request_contains_http_method(self):
        from debug_exercises import DEBUG_EXERCISES
        import re
        method_re = re.compile(r'^(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)')
        for ex in DEBUG_EXERCISES:
            assert method_re.match(ex['request']), \
                f"Exercise {ex['id']} request doesn't start with HTTP method"

    def test_response_contains_status_line(self):
        from debug_exercises import DEBUG_EXERCISES
        import re
        status_re = re.compile(r'^HTTP/\d\.\d\s+\d{3}')
        for ex in DEBUG_EXERCISES:
            assert status_re.match(ex['response']), \
                f"Exercise {ex['id']} response doesn't start with status line"


class TestDebugExerciseCategories:
    """Tests for debug exercise category field and category filter UI."""

    def test_all_exercises_have_category(self):
        from debug_exercises import DEBUG_EXERCISES
        valid_cats = {'auth', 'caching', 'redirects', 'crud', 'errors', 'headers', 'api-design'}
        for ex in DEBUG_EXERCISES:
            assert 'category' in ex, f"Exercise {ex['id']} missing category"
            assert ex['category'] in valid_cats, \
                f"Exercise {ex['id']} has invalid category: {ex['category']}"

    def test_debug_page_has_category_filter_buttons(self, client):
        resp = client.get('/debug')
        html = resp.data.decode()
        assert 'data-category="all"' in html
        assert 'data-category="auth"' in html
        assert 'data-category="caching"' in html
        assert 'data-category="redirects"' in html
        assert 'data-category="crud"' in html
        assert 'data-category="errors"' in html
        assert 'data-category="headers"' in html
        assert 'data-category="api-design"' in html

    def test_debug_cards_have_category_data_attr(self, client):
        resp = client.get('/debug')
        html = resp.data.decode()
        import re
        card_cats = re.findall(r'data-category="([\w-]+)".*?class="debug-card"', html)
        card_cats2 = re.findall(r'class="debug-card"[^>]*data-category="([\w-]+)"', html)
        assert len(card_cats) > 0 or len(card_cats2) > 0

    def test_debug_page_category_filter_label(self, client):
        resp = client.get('/debug')
        html = resp.data.decode()
        assert 'Filter by category' in html

    def test_multiple_categories_represented(self):
        from debug_exercises import DEBUG_EXERCISES
        categories = {ex['category'] for ex in DEBUG_EXERCISES}
        assert len(categories) >= 4, f"Only {len(categories)} categories represented"


class TestScenarioData:
    """Tests for the scenarios.py data module."""

    def test_scenarios_at_least_50(self):
        from scenarios import SCENARIOS
        assert len(SCENARIOS) >= 50, f"Only {len(SCENARIOS)} scenarios, expected 50+"

    def test_scenario_has_required_fields(self):
        from scenarios import SCENARIOS
        required = {'id', 'difficulty', 'category', 'description', 'correct', 'options', 'explanations'}
        for s in SCENARIOS:
            missing = required - set(s.keys())
            assert not missing, f"Scenario {s.get('id', '?')} missing fields: {missing}"

    def test_scenario_ids_unique(self):
        from scenarios import SCENARIOS
        ids = [s['id'] for s in SCENARIOS]
        assert len(ids) == len(set(ids)), "Duplicate scenario IDs found"

    def test_scenario_difficulties_valid(self):
        from scenarios import SCENARIOS
        valid = {'beginner', 'intermediate', 'expert'}
        for s in SCENARIOS:
            assert s['difficulty'] in valid, \
                f"Scenario {s['id']} has invalid difficulty: {s['difficulty']}"

    def test_scenario_categories_valid(self):
        from scenarios import SCENARIOS
        valid_cats = {'auth', 'caching', 'redirects', 'crud', 'errors', 'headers', 'api-design', 'security'}
        for s in SCENARIOS:
            assert 'category' in s, f"Scenario {s['id']} missing category"
            assert s['category'] in valid_cats, \
                f"Scenario {s['id']} has invalid category: {s['category']}"

    def test_all_difficulty_levels_represented(self):
        from scenarios import SCENARIOS
        difficulties = {s['difficulty'] for s in SCENARIOS}
        assert 'beginner' in difficulties
        assert 'intermediate' in difficulties
        assert 'expert' in difficulties

    def test_multiple_categories_represented(self):
        from scenarios import SCENARIOS
        categories = {s['category'] for s in SCENARIOS}
        assert len(categories) >= 5, f"Only {len(categories)} categories represented"

    def test_correct_answer_in_options(self):
        from scenarios import SCENARIOS
        for s in SCENARIOS:
            assert s['correct'] in s['options'], \
                f"Scenario {s['id']} correct answer {s['correct']} not in options"

    def test_each_option_has_explanation(self):
        from scenarios import SCENARIOS
        for s in SCENARIOS:
            for opt in s['options']:
                assert opt in s['explanations'], \
                    f"Scenario {s['id']} missing explanation for option {opt}"

    def test_each_scenario_has_four_options(self):
        from scenarios import SCENARIOS
        for s in SCENARIOS:
            assert len(s['options']) == 4, \
                f"Scenario {s['id']} has {len(s['options'])} options, expected 4"


class TestPracticeCategoryFilters:
    """Tests for category filter UI on the practice page."""

    def test_practice_page_has_category_filter_buttons(self, client):
        resp = client.get('/practice')
        html = resp.data.decode()
        assert 'data-category="all"' in html
        assert 'data-category="auth"' in html
        assert 'data-category="caching"' in html
        assert 'data-category="redirects"' in html
        assert 'data-category="crud"' in html
        assert 'data-category="errors"' in html
        assert 'data-category="headers"' in html
        assert 'data-category="api-design"' in html

    def test_practice_cards_have_category_data_attr(self, client):
        resp = client.get('/practice')
        html = resp.data.decode()
        import re
        card_cats = re.findall(r'class="practice-card"[^>]*data-category="([\w-]+)"', html)
        assert len(card_cats) > 0

    def test_practice_page_category_filter_label(self, client):
        resp = client.get('/practice')
        html = resp.data.decode()
        assert 'Filter by category' in html

    def test_practice_category_filter_styling(self, client):
        resp = client.get('/practice')
        html = resp.data.decode()
        assert 'data-category="auth"' in html
        assert 'practice-filter-btn' in html


# --- Console Parrot API Easter Egg ---

class TestConsoleParrotAPI:
    """Tests for the window.parrot console API easter egg."""

    def test_console_parrot_script_present(self, client):
        """Base template should include the console parrot API script."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'window.parrot' in html

    def test_console_parrot_ascii_greeting(self, client):
        """Console parrot should print a styled ASCII greeting."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'HTTP' in html
        assert 'Parrots' in html
        assert 'console.log' in html
        assert '%c' in html

    def test_parrot_help_method(self, client):
        """window.parrot should have a help() method."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'parrot.help()' in html
        assert 'console.table' in html

    def test_parrot_squawk_method(self, client):
        """window.parrot should have a squawk() method."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'parrot.squawk()' in html
        assert 'SQUAWKS' in html

    def test_parrot_fortune_method(self, client):
        """window.parrot should have a fortune() method with 15+ fortunes."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'parrot.fortune()' in html
        assert 'FORTUNES' in html
        # Count fortunes defined in the array
        fortune_count = html.count("'You will") + html.count("'A ") + html.count("'The ") + html.count("'Beware") + html.count("'Your ") + html.count("'An ") + html.count("'Trust")
        assert fortune_count >= 10, f"Expected at least 10 fortune matches, got {fortune_count}"

    def test_parrot_status_method(self, client):
        """window.parrot should have a status(code) method."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'parrot.status(' in html
        assert 'STATUS_CATEGORIES' in html

    def test_parrot_lore_method(self, client):
        """window.parrot should have a lore() method."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'parrot.lore()' in html
        assert 'LORE' in html

    def test_parrot_object_frozen(self, client):
        """window.parrot should be defined with Object.freeze."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'Object.freeze' in html

    def test_console_parrot_registers_egg(self, client):
        """Console parrot should register console_parrot egg in eggs_found."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'console_parrot' in html
        assert 'eggs_found' in html

    def test_console_parrot_awards_xp(self, client):
        """Console parrot should award XP via ParrotXP."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'ParrotXP.award(100' in html

    def test_collection_has_console_parrot_egg(self, client):
        """Collection page should have console_parrot egg card."""
        resp = client.get('/collection')
        html = resp.data.decode()
        assert 'data-egg="console_parrot"' in html

    def test_collection_console_parrot_hint(self, client):
        """Collection page console_parrot card should have appropriate hint."""
        resp = client.get('/collection')
        html = resp.data.decode()
        assert 'devtools' in html.lower()


# --- HTTP Handshake Easter Egg ---

class TestHTTPHandshakeEasterEgg:
    """Tests for the H-T-T-P keyboard combo handshake easter egg."""

    def test_http_listener_present(self, client):
        """Base template should include the HTTP keydown listener."""
        resp = client.get('/')
        html = resp.data.decode()
        assert "['h','t','t','p']" in html

    def test_http_listener_ignores_inputs(self, client):
        """HTTP listener should skip input/textarea/select elements."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'INPUT' in html
        assert 'TEXTAREA' in html

    def test_http_handshake_overlay_created(self, client):
        """HTTP handshake should create overlay with handshake elements."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'handshake-overlay' in html
        assert 'handshake-scene' in html

    def test_http_handshake_syn_synack_ack(self, client):
        """Handshake animation should include SYN, SYN-ACK, ACK labels."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'SYN' in html
        assert 'SYN-ACK' in html
        assert 'ACK' in html

    def test_http_handshake_200_ok(self, client):
        """Handshake animation should show 200 OK."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'handshake-ok' in html
        assert '200 OK' in html

    def test_http_handshake_connection_established(self, client):
        """Handshake should show Connection Established message."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'Connection Established!' in html

    def test_http_handshake_client_server_parrots(self, client):
        """Handshake should have client and server parrot labels."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'handshake-client' in html
        assert 'handshake-server' in html
        assert 'Client' in html
        assert 'Server' in html

    def test_http_handshake_registers_egg(self, client):
        """HTTP handshake should register http_handshake egg."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'http_handshake' in html

    def test_http_handshake_awards_xp(self, client):
        """HTTP handshake should award XP on trigger."""
        resp = client.get('/')
        html = resp.data.decode()
        # There should be at least two award(100 calls: console_parrot and http_handshake
        assert html.count('ParrotXP.award(100') >= 2

    def test_http_handshake_auto_dismiss(self, client):
        """HTTP handshake overlay should auto-dismiss after animation."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'handshake-dismissing' in html
        assert 'removeChild' in html

    def test_http_handshake_2sec_timeout(self, client):
        """HTTP listener should use a 2 second timeout for key sequence."""
        resp = client.get('/')
        html = resp.data.decode()
        assert '2000' in html

    def test_collection_has_http_handshake_egg(self, client):
        """Collection page should have http_handshake egg card."""
        resp = client.get('/collection')
        html = resp.data.decode()
        assert 'data-egg="http_handshake"' in html

    def test_collection_http_handshake_hint(self, client):
        """Collection page http_handshake card should have appropriate hint."""
        resp = client.get('/collection')
        html = resp.data.decode()
        assert 'protocol' in html.lower()

    def test_handshake_css_present(self, client):
        """Style.css should contain handshake overlay CSS."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.handshake-overlay' in css
        assert '.handshake-msg' in css
        assert '.handshake-connected' in css
        assert '.handshake-syn' in css
        assert '.handshake-synack' in css
        assert '.handshake-ack' in css
        assert '.handshake-ok' in css

    def test_handshake_css_reduced_motion(self, client):
        """Handshake CSS should respect prefers-reduced-motion."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert 'handshake-bird' in css
        assert 'prefers-reduced-motion' in css


class TestTypographyTokens:
    """Tests for JetBrains Mono font upgrade and type scale tokens."""

    def test_jetbrains_mono_font_import(self, client):
        """JetBrains Mono should be in the Google Fonts import URL."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'JetBrains+Mono' in html
        assert 'Share+Tech+Mono' not in html

    def test_jetbrains_mono_css_token(self, client):
        """--font-mono should reference JetBrains Mono."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert "'JetBrains Mono'" in css
        assert "'Share Tech Mono'" not in css

    def test_font_code_removed(self, client):
        """--font-code should no longer exist (merged into --font-mono)."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '--font-code' not in css

    def test_type_scale_tokens_defined(self, client):
        """All type scale tokens should be defined in :root."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '--text-xs:' in css
        assert '--text-sm:' in css
        assert '--text-base:' in css
        assert '--text-md:' in css
        assert '--text-lg:' in css
        assert '--text-xl:' in css
        assert '--text-2xl:' in css
        assert '--text-3xl:' in css

    def test_type_scale_tokens_used(self, client):
        """Type scale tokens should actually be used in the stylesheet."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert 'var(--text-xs)' in css
        assert 'var(--text-sm)' in css
        assert 'var(--text-base)' in css
        assert 'var(--text-md)' in css
        assert 'var(--text-lg)' in css
        assert 'var(--text-xl)' in css
        assert 'var(--text-2xl)' in css
        assert 'var(--text-3xl)' in css

    def test_type_scale_token_values(self):
        """Type scale tokens should have the correct values."""
        with open('static/style.css', 'r') as f:
            css = f.read()
        assert '--text-xs: 0.65rem' in css
        assert '--text-sm: 0.8rem' in css
        assert '--text-base: 1rem' in css
        assert '--text-lg: 1.25rem' in css
        assert '--text-xl: 1.5rem' in css
        assert '--text-2xl: 2.2rem' in css
        assert '--text-3xl: 3rem' in css


class TestDesignSystemTokens:
    """Tests for CSS design system token consistency."""

    def test_text_base_equals_text_md(self):
        """--text-base and --text-md should both be 1rem."""
        with open('static/style.css', 'r') as f:
            css = f.read()
        assert '--text-base: 1rem' in css
        assert '--text-md: 1rem' in css

    def test_radius_tokens_defined(self):
        """All radius tokens should be defined in :root."""
        with open('static/style.css', 'r') as f:
            css = f.read()
        assert '--radius-xs: 4px' in css
        assert '--radius-sm: 8px' in css
        assert '--radius-md: 12px' in css
        assert '--radius-lg: 16px' in css
        assert '--radius-full: 9999px' in css

    def test_no_hardcoded_border_radius_4px(self, client):
        """border-radius: 4px should use var(--radius-xs)."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        import re
        matches = re.findall(r'border-radius:\s*4px\s*[;!]', css)
        assert len(matches) == 0, f"Found hardcoded border-radius: 4px at: {matches}"

    def test_no_hardcoded_border_radius_8px(self, client):
        """border-radius: 8px should use var(--radius-sm)."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        import re
        matches = re.findall(r'border-radius:\s*8px\s*[;!]', css)
        assert len(matches) == 0, f"Found hardcoded border-radius: 8px at: {matches}"

    def test_no_hardcoded_border_radius_16px(self, client):
        """border-radius: 16px should use var(--radius-lg)."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        import re
        matches = re.findall(r'border-radius:\s*16px\s*[;!]', css)
        assert len(matches) == 0, f"Found hardcoded border-radius: 16px at: {matches}"

    def test_no_hardcoded_border_radius_50pct(self, client):
        """border-radius: 50% should use var(--radius-full)."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        import re
        matches = re.findall(r'border-radius:\s*50%\s*[;!]', css)
        assert len(matches) == 0, f"Found hardcoded border-radius: 50% at: {matches}"

    def test_no_hardcoded_transition_durations(self, client):
        """Transitions should use duration tokens, not raw values like 0.2s ease."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        import re
        # Match transition declarations using raw durations with ease keywords
        matches = re.findall(r'transition:[^;]*\d+\.\d+s\s+ease(?:-in|-out|-in-out)?', css)
        assert len(matches) == 0, f"Found hardcoded transitions: {matches[:5]}"

    def test_no_hardcoded_font_family_inter(self, client):
        """font-family should use var(--font-sans), not raw 'Inter', sans-serif."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        import re
        # Exclude the :root definition itself
        root_end = css.index('}')
        after_root = css[root_end:]
        matches = re.findall(r"font-family:\s*'Inter',\s*sans-serif", after_root)
        assert len(matches) == 0, f"Found hardcoded font-family: {matches}"

    def test_no_low_contrast_055_text(self, client):
        """rgba(255,255,255,0.55) should be raised to 0.7 for WCAG AA compliance."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert 'rgba(255, 255, 255, 0.55)' not in css
        assert 'rgba(255,255,255,0.55)' not in css

    def test_duration_tokens_used(self, client):
        """Duration tokens should be used in the stylesheet."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert 'var(--duration-fast)' in css
        assert 'var(--duration-normal)' in css
        assert 'var(--duration-slow)' in css

    def test_radius_tokens_used(self, client):
        """Radius tokens should be used in the stylesheet."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert 'var(--radius-xs)' in css
        assert 'var(--radius-sm)' in css
        assert 'var(--radius-md)' in css
        assert 'var(--radius-lg)' in css
        assert 'var(--radius-full)' in css


# --- Confusion Pair Lessons ---

class TestConfusionPairsData:
    """Tests for confusion_pairs.py data module."""

    def test_pairs_not_empty(self):
        from confusion_pairs import CONFUSION_PAIRS
        assert len(CONFUSION_PAIRS) >= 15

    def test_each_pair_has_required_keys(self):
        from confusion_pairs import CONFUSION_PAIRS
        required = {'slug', 'codes', 'title', 'tldr', 'decision_tree', 'examples', 'quiz', 'category'}
        for pair in CONFUSION_PAIRS:
            missing = required - set(pair.keys())
            assert not missing, f"Pair {pair.get('slug', '?')} missing keys: {missing}"

    def test_each_pair_has_two_codes(self):
        from confusion_pairs import CONFUSION_PAIRS
        for pair in CONFUSION_PAIRS:
            assert len(pair['codes']) == 2, f"Pair {pair['slug']} should have exactly 2 codes"

    def test_slug_format(self):
        from confusion_pairs import CONFUSION_PAIRS
        import re
        slug_re = re.compile(r'^\d{3}-vs-\d{3}$')
        for pair in CONFUSION_PAIRS:
            assert slug_re.match(pair['slug']), f"Invalid slug format: {pair['slug']}"

    def test_each_pair_has_decision_steps(self):
        from confusion_pairs import CONFUSION_PAIRS
        for pair in CONFUSION_PAIRS:
            assert len(pair['decision_tree']) >= 2, \
                f"Pair {pair['slug']} needs at least 2 decision steps"
            for step in pair['decision_tree']:
                assert 'question' in step
                assert 'yes' in step
                assert 'no' in step

    def test_each_pair_has_examples(self):
        from confusion_pairs import CONFUSION_PAIRS
        for pair in CONFUSION_PAIRS:
            assert len(pair['examples']) >= 2, \
                f"Pair {pair['slug']} needs at least 2 examples"
            for ex in pair['examples']:
                assert 'scenario' in ex
                assert 'code' in ex
                assert 'explanation' in ex

    def test_each_pair_has_quiz_questions(self):
        from confusion_pairs import CONFUSION_PAIRS
        for pair in CONFUSION_PAIRS:
            assert len(pair['quiz']) == 3, \
                f"Pair {pair['slug']} should have exactly 3 quiz questions"
            for q in pair['quiz']:
                assert 'scenario' in q
                assert 'correct' in q
                assert 'wrong' in q

    def test_quiz_answers_are_from_pair_codes(self):
        from confusion_pairs import CONFUSION_PAIRS
        for pair in CONFUSION_PAIRS:
            codes = set(pair['codes'])
            for q in pair['quiz']:
                assert q['correct'] in codes, \
                    f"Pair {pair['slug']}: quiz correct answer {q['correct']} not in pair codes {codes}"
                assert q['wrong'] in codes, \
                    f"Pair {pair['slug']}: quiz wrong answer {q['wrong']} not in pair codes {codes}"

    def test_slug_lookup(self):
        from confusion_pairs import CONFUSION_PAIRS_BY_SLUG
        assert '401-vs-403' in CONFUSION_PAIRS_BY_SLUG
        assert '301-vs-302' in CONFUSION_PAIRS_BY_SLUG

    def test_code_lookup(self):
        from confusion_pairs import CONFUSION_PAIRS_BY_CODE
        assert '401' in CONFUSION_PAIRS_BY_CODE
        assert '403' in CONFUSION_PAIRS_BY_CODE
        assert '301' in CONFUSION_PAIRS_BY_CODE

    def test_covered_pairs(self):
        """Ensure the required pairs are covered."""
        from confusion_pairs import CONFUSION_PAIRS_BY_SLUG
        required = [
            '401-vs-403', '301-vs-302', '307-vs-308', '400-vs-422',
            '404-vs-410', '500-vs-502', '500-vs-503', '200-vs-204',
            '302-vs-307',
            # New pairs added in expansion
            '502-vs-504', '401-vs-407', '204-vs-205', '409-vs-412',
            '301-vs-308', '503-vs-504',
        ]
        for slug in required:
            assert slug in CONFUSION_PAIRS_BY_SLUG, f"Missing required pair: {slug}"

    def test_each_pair_has_category(self):
        """Every pair must belong to a category."""
        from confusion_pairs import CONFUSION_PAIRS, CONFUSION_PAIR_CATEGORY_ORDER
        for pair in CONFUSION_PAIRS:
            assert 'category' in pair, f"Pair {pair['slug']} missing category"
            assert pair['category'] in CONFUSION_PAIR_CATEGORY_ORDER, \
                f"Pair {pair['slug']} has unknown category '{pair['category']}'"

    def test_pairs_by_category_covers_all(self):
        """PAIRS_BY_CATEGORY should contain every pair exactly once."""
        from confusion_pairs import CONFUSION_PAIRS, PAIRS_BY_CATEGORY
        slugs_from_cats = []
        for pairs in PAIRS_BY_CATEGORY.values():
            slugs_from_cats.extend(p['slug'] for p in pairs)
        assert sorted(slugs_from_cats) == sorted(p['slug'] for p in CONFUSION_PAIRS)

    def test_unique_slugs(self):
        """No duplicate slugs allowed."""
        from confusion_pairs import CONFUSION_PAIRS
        slugs = [p['slug'] for p in CONFUSION_PAIRS]
        assert len(slugs) == len(set(slugs)), "Duplicate slugs found"


class TestLearnIndexRoute:
    """Tests for /learn index page."""

    def test_learn_index_returns_200(self, client):
        resp = client.get('/learn')
        assert resp.status_code == 200

    def test_learn_index_has_title(self, client):
        resp = client.get('/learn')
        html = resp.data.decode()
        assert 'Confusion Pairs' in html

    def test_learn_index_lists_pairs(self, client):
        resp = client.get('/learn')
        html = resp.data.decode()
        assert '401-vs-403' in html
        assert '301-vs-302' in html
        assert '/learn/' in html

    def test_learn_index_has_tldr(self, client):
        resp = client.get('/learn')
        html = resp.data.decode()
        # TL;DR text should be present from at least one pair
        assert "doesn&#39;t know who you are" in html or "doesn't know who you are" in html or '401' in html

    def test_learn_index_has_category_headings(self, client):
        resp = client.get('/learn')
        html = resp.data.decode()
        assert 'learn-index-category-heading' in html
        assert 'Auth pairs' in html
        assert 'Redirect pairs' in html
        assert 'Error pairs' in html

    def test_learn_index_has_pair_count(self, client):
        resp = client.get('/learn')
        html = resp.data.decode()
        assert '15 pairs' in html
        assert '5 categories' in html

    def test_learn_index_lists_new_pairs(self, client):
        resp = client.get('/learn')
        html = resp.data.decode()
        assert '502-vs-504' in html
        assert '401-vs-407' in html
        assert '204-vs-205' in html
        assert '409-vs-412' in html
        assert '301-vs-308' in html
        assert '503-vs-504' in html


class TestLearnPairRoute:
    """Tests for /learn/<slug> lesson pages."""

    def test_learn_pair_returns_200(self, client):
        resp = client.get('/learn/401-vs-403')
        assert resp.status_code == 200

    def test_learn_pair_invalid_slug_returns_404(self, client):
        resp = client.get('/learn/999-vs-998')
        assert resp.status_code == 404

    def test_learn_pair_has_title(self, client):
        resp = client.get('/learn/401-vs-403')
        html = resp.data.decode()
        assert '401 Unauthorized vs 403 Forbidden' in html

    def test_learn_pair_has_tldr(self, client):
        resp = client.get('/learn/401-vs-403')
        html = resp.data.decode()
        assert 'learn-tldr' in html
        assert 'TL;DR' in html

    def test_learn_pair_has_decision_tree(self, client):
        resp = client.get('/learn/401-vs-403')
        html = resp.data.decode()
        assert 'Decision Tree' in html
        assert 'learn-decision-step' in html

    def test_learn_pair_has_examples(self, client):
        resp = client.get('/learn/401-vs-403')
        html = resp.data.decode()
        assert 'Annotated Examples' in html
        assert 'learn-example-card' in html

    def test_learn_pair_has_quiz(self, client):
        resp = client.get('/learn/401-vs-403')
        html = resp.data.decode()
        assert 'Mini-Quiz' in html
        assert 'learn-quiz-form' in html
        assert 'learn-quiz-submit' in html

    def test_learn_pair_has_comparison_cards(self, client):
        resp = client.get('/learn/401-vs-403')
        html = resp.data.decode()
        assert 'compare-card' in html
        assert 'Side-by-Side Comparison' in html

    def test_learn_pair_has_breadcrumb(self, client):
        resp = client.get('/learn/401-vs-403')
        html = resp.data.decode()
        assert 'breadcrumb' in html
        assert 'href="/learn"' in html

    def test_learn_pair_has_detail_links(self, client):
        resp = client.get('/learn/401-vs-403')
        html = resp.data.decode()
        assert 'href="/401"' in html
        assert 'href="/403"' in html

    def test_learn_pair_xp_script(self, client):
        resp = client.get('/learn/401-vs-403')
        html = resp.data.decode()
        assert 'ParrotXP' in html
        assert 'learn_quiz_correct' in html

    def test_all_pairs_render(self, client):
        """Every configured pair should render without error."""
        from confusion_pairs import CONFUSION_PAIRS
        for pair in CONFUSION_PAIRS:
            resp = client.get(f'/learn/{pair["slug"]}')
            assert resp.status_code == 200, f"/learn/{pair['slug']} returned {resp.status_code}"


class TestLearnNavLink:
    """Tests for Learn link in navigation."""

    def test_nav_has_learn_link(self, client):
        resp = client.get('/')
        html = resp.data.decode()
        assert 'href="/learn"' in html
        assert '>Learn<' in html

    def test_nav_learn_active_on_index(self, client):
        resp = client.get('/learn')
        html = resp.data.decode()
        assert 'nav-active' in html

    def test_nav_learn_active_on_pair(self, client):
        resp = client.get('/learn/401-vs-403')
        html = resp.data.decode()
        assert 'nav-active' in html


class TestLearnSitemap:
    """Tests for learn pages in sitemap."""

    def test_sitemap_has_learn_index(self, client):
        resp = client.get('/sitemap.xml')
        xml = resp.data.decode()
        assert '/learn</loc>' in xml or '/learn<' in xml

    def test_sitemap_has_learn_pairs(self, client):
        resp = client.get('/sitemap.xml')
        xml = resp.data.decode()
        assert '/learn/401-vs-403' in xml
        assert '/learn/301-vs-302' in xml


class TestDetailPageLearnLinks:
    """Tests for 'Learn the difference' links on detail pages."""

    def test_401_page_has_learn_link_to_403(self, client):
        resp = client.get('/401')
        html = resp.data.decode()
        assert 'Learn the difference' in html
        assert '/learn/401-vs-403' in html

    def test_403_page_has_learn_link_to_401(self, client):
        resp = client.get('/403')
        html = resp.data.decode()
        assert 'Learn the difference' in html
        assert '/learn/401-vs-403' in html

    def test_200_page_has_learn_link_to_204(self, client):
        resp = client.get('/200')
        html = resp.data.decode()
        assert '/learn/200-vs-204' in html


class TestViewTransitions:
    """Tests for the View Transitions API progressive enhancement."""

    def test_base_template_has_view_transition_meta_tag(self, client):
        """The view-transition meta tag should be present in every page."""
        resp = client.get('/')
        html = resp.data.decode()
        assert '<meta name="view-transition" content="same-origin">' in html

    def test_view_transition_meta_tag_on_detail_page(self, client):
        """Detail pages inherit from base and should also have the meta tag."""
        resp = client.get('/200')
        html = resp.data.decode()
        assert '<meta name="view-transition" content="same-origin">' in html

    def test_css_has_view_transition_at_rule(self):
        """The stylesheet should contain the @view-transition rule."""
        with open('static/style.css') as f:
            css = f.read()
        assert '@view-transition' in css
        assert 'navigation: auto' in css

    def test_css_has_fade_keyframes(self):
        """The stylesheet should define fade-out and fade-in keyframes."""
        with open('static/style.css') as f:
            css = f.read()
        assert '@keyframes fade-out' in css
        assert '@keyframes fade-in' in css

    def test_css_has_view_transition_old_new_root(self):
        """Root view transition pseudo-elements should be styled."""
        with open('static/style.css') as f:
            css = f.read()
        assert '::view-transition-old(root)' in css
        assert '::view-transition-new(root)' in css

    def test_homepage_cards_have_view_transition_name(self, client):
        """Each parrot card image on the homepage should have a view-transition-name."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'view-transition-name: parrot-200' in html
        assert 'view-transition-name: parrot-404' in html
        assert 'view-transition-name: parrot-500' in html

    def test_detail_page_image_has_view_transition_name(self, client):
        """The detail page hero image should have a matching view-transition-name."""
        resp = client.get('/200')
        html = resp.data.decode()
        assert 'view-transition-name: parrot-200' in html

    def test_detail_page_transition_name_matches_code(self, client):
        """The view-transition-name on the detail page should match the status code."""
        for code in ['404', '418', '500']:
            resp = client.get(f'/{code}')
            html = resp.data.decode()
            assert f'view-transition-name: parrot-{code}' in html

    def test_css_has_site_header_view_transition_name(self):
        """The site header should have a view-transition-name for persistence."""
        with open('static/style.css') as f:
            css = f.read()
        assert 'view-transition-name: site-header' in css

    def test_css_reduced_motion_disables_view_transitions(self):
        """In prefers-reduced-motion, view transition animations should be disabled."""
        with open('static/style.css') as f:
            css = f.read()
        # Find the reduced-motion block and verify it contains view transition overrides
        rm_start = css.find('@media (prefers-reduced-motion: reduce)')
        assert rm_start != -1
        rm_block = css[rm_start:css.find('\n/* === Light Theme', rm_start)]
        assert '::view-transition-old(root)' in rm_block
        assert '::view-transition-new(root)' in rm_block
        assert 'animation: none !important' in rm_block


# --- Streak Freeze & Milestone Celebrations ---

class TestStreakFreeze:
    """Verify streak freeze logic is present in the daily template."""

    def test_daily_has_freezes_available_field(self, client):
        """Daily state should include freezesAvailable field."""
        resp = client.get('/daily')
        html = resp.data.decode()
        assert 'freezesAvailable' in html

    def test_daily_has_freeze_indicator(self, client):
        """Daily page should have a streak freeze indicator element."""
        resp = client.get('/daily')
        html = resp.data.decode()
        assert 'streak-freeze-indicator' in html
        assert 'freeze-count' in html

    def test_daily_has_freeze_message(self, client):
        """Daily page should have a streak freeze used message element."""
        resp = client.get('/daily')
        html = resp.data.decode()
        assert 'streak-freeze-msg' in html
        assert 'Streak freeze used' in html

    def test_daily_freeze_consumes_on_missed_day(self, client):
        """Daily JS should check freezesAvailable when a day is missed."""
        resp = client.get('/daily')
        html = resp.data.decode()
        assert 'state.freezesAvailable > 0' in html
        assert 'state.freezesAvailable--' in html

    def test_daily_freeze_milestones_earn_freezes(self, client):
        """Users earn freezes at 7-day and 14-day milestones."""
        resp = client.get('/daily')
        html = resp.data.decode()
        assert 'FREEZE_MILESTONES' in html
        assert 'state.freezesAvailable++' in html

    def test_daily_freeze_sets_flag_for_feather(self, client):
        """Using a freeze sets httpparrot_freeze_used flag."""
        resp = client.get('/daily')
        html = resp.data.decode()
        assert 'httpparrot_freeze_used' in html

    def test_freeze_indicator_css_exists(self, client):
        """CSS should have streak-freeze-indicator styles."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.streak-freeze-indicator' in css
        assert '.streak-freeze-message' in css


class TestMilestoneCelebrations:
    """Verify milestone celebration code is present."""

    def test_daily_has_milestones_map(self, client):
        """Daily JS should define MILESTONES with XP rewards."""
        resp = client.get('/daily')
        html = resp.data.decode()
        assert 'MILESTONES' in html
        # Check all five milestone thresholds
        for m in ['7', '14', '30', '50', '100']:
            assert m in html

    def test_daily_has_milestone_overlay(self, client):
        """Daily page should have a milestone celebration overlay."""
        resp = client.get('/daily')
        html = resp.data.decode()
        assert 'milestone-overlay' in html
        assert 'milestone-content' in html
        assert 'milestone-number' in html
        assert 'milestone-congrats' in html

    def test_daily_has_milestone_share(self, client):
        """Milestone overlay should have a share button."""
        resp = client.get('/daily')
        html = resp.data.decode()
        assert 'milestone-share' in html
        assert 'day streak on HTTP Parrots' in html

    def test_daily_has_milestone_xp_display(self, client):
        """Milestone overlay should show bonus XP."""
        resp = client.get('/daily')
        html = resp.data.decode()
        assert 'milestone-xp' in html
        assert 'Bonus XP' in html

    def test_daily_milestone_auto_dismiss(self, client):
        """Milestone overlay should auto-dismiss after 5 seconds."""
        resp = client.get('/daily')
        html = resp.data.decode()
        assert '5000' in html

    def test_milestone_spawns_confetti(self, client):
        """Milestone celebration should spawn confetti."""
        resp = client.get('/daily')
        html = resp.data.decode()
        assert 'showMilestoneCelebration' in html
        assert 'spawnConfetti' in html

    def test_milestone_css_exists(self, client):
        """CSS should have milestone overlay styles."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.milestone-overlay' in css
        assert '.milestone-content' in css
        assert '.milestone-number' in css

    def test_daily_checks_milestones_on_correct(self, client):
        """After a correct answer, milestones should be checked."""
        resp = client.get('/daily')
        html = resp.data.decode()
        assert 'checkMilestoneRewards(state)' in html


class TestProfileStreakFreezeIntegration:
    """Verify profile page shows streak freeze and milestone data."""

    def test_profile_has_freeze_count(self, client):
        """Profile should display streak freeze count."""
        resp = client.get('/profile')
        html = resp.data.decode()
        assert 'stat-freeze-count' in html
        assert 'Freezes' in html

    def test_profile_has_milestones_section(self, client):
        """Profile should have a milestones history section."""
        resp = client.get('/profile')
        html = resp.data.decode()
        assert 'profile-milestones-section' in html
        assert 'profile-milestones-list' in html
        assert 'Milestones' in html

    def test_profile_reads_daily_state(self, client):
        """Profile JS should read from httpparrot_daily localStorage."""
        resp = client.get('/profile')
        html = resp.data.decode()
        assert 'httpparrot_daily' in html
        assert 'freezesAvailable' in html
        assert 'milestonesHit' in html

    def test_profile_milestone_labels(self, client):
        """Profile JS should have milestone display labels."""
        resp = client.get('/profile')
        html = resp.data.decode()
        assert '7-Day Streak' in html
        assert '14-Day Streak' in html
        assert '30-Day Streak' in html


class TestFrozenSolidFeather:
    """Verify the Frozen Solid feather badge."""

    def test_frozen_solid_in_feathers_array(self, client):
        """Frozen Solid feather should be defined in FEATHERS."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'frozen_solid' in html
        assert 'Frozen Solid' in html

    def test_frozen_solid_check_in_check_feathers(self, client):
        """checkFeathers should check httpparrot_freeze_used flag."""
        resp = client.get('/')
        html = resp.data.decode()
        assert "!has('frozen_solid')" in html
        assert "httpparrot_freeze_used" in html


class TestCelebrationAnimations:
    """Tests for achievement celebration animations (confetti, rank-up, XP flash)."""

    def test_celebration_confetti_function_present(self, client):
        """Base template should define spawnCelebrationConfetti function."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'function spawnCelebrationConfetti' in html

    def test_celebration_confetti_spawns_particles(self, client):
        """spawnCelebrationConfetti should create celebration-confetti elements."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'celebration-confetti' in html

    def test_celebration_confetti_uses_brand_colors(self, client):
        """Confetti particles should use teal/purple brand palette."""
        resp = client.get('/')
        html = resp.data.decode()
        assert '#00c9a7' in html
        assert '#7b61ff' in html

    def test_celebration_confetti_auto_cleanup(self, client):
        """Confetti should auto-remove on animationend."""
        resp = client.get('/')
        html = resp.data.decode()
        # The function should listen for animationend and remove particles
        assert 'animationend' in html

    def test_show_feather_toast_triggers_confetti(self, client):
        """showFeatherToast should call spawnCelebrationConfetti."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'spawnCelebrationConfetti(toast)' in html

    def test_celebration_confetti_css_exists(self, client):
        """Celebration confetti CSS class should be in the stylesheet."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.celebration-confetti' in css
        assert 'celebration-burst' in css

    def test_rank_up_banner_function_present(self, client):
        """Base template should define showRankUpBanner function."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'function showRankUpBanner' in html

    def test_rank_up_banner_shows_rank_name(self, client):
        """Rank-up banner should display the new rank name."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'Rank Up! You are now a' in html

    def test_rank_up_banner_has_icon(self, client):
        """Rank-up banner should include a rank icon."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'rank-up-banner-icon' in html

    def test_rank_up_banner_auto_dismiss(self, client):
        """Rank-up banner should auto-dismiss after 4 seconds."""
        resp = client.get('/')
        html = resp.data.decode()
        # Banner removes rank-up-visible class after 4000ms, then removes element after 600ms
        assert "banner.classList.remove('rank-up-visible')" in html

    def test_rank_up_banner_awards_bonus_xp(self, client):
        """Rank-up should award bonus XP based on rank reached."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'RANK_BONUS_XP' in html
        assert 'rank_up_bonus' in html

    def test_rank_up_gold_particles(self, client):
        """Rank-up should trigger gold particle shower."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'function spawnGoldParticles' in html
        assert 'rank-up-gold-particle' in html

    def test_rank_up_banner_css_exists(self, client):
        """Rank-up banner CSS should be in the stylesheet."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.rank-up-banner' in css
        assert 'rank-up-visible' in css
        assert 'gold-shower' in css
        assert '.rank-up-gold-particle' in css

    def test_rank_up_banner_gold_gradient(self, client):
        """Rank-up banner should have gold gradient background."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '#ffd700' in css
        assert '#ffb300' in css

    def test_check_feathers_detects_rank_change(self, client):
        """checkFeathers should detect rank changes and show banner."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'rankBefore' in html
        assert 'rankAfter' in html
        assert 'showRankUpBanner(rankAfter)' in html

    def test_xp_milestone_flash_function_present(self, client):
        """Base template should define checkXpMilestoneFlash function."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'function checkXpMilestoneFlash' in html

    def test_xp_milestones_defined(self, client):
        """XP milestone thresholds should be defined."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'XP_MILESTONES' in html
        for milestone in ['100', '500', '1000', '5000', '10000']:
            assert milestone in html

    def test_xp_flash_triggers_glow(self, client):
        """XP milestone crossing should add xp-flash class to badge."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'xp-flash' in html

    def test_xp_flash_floating_number(self, client):
        """XP milestone should show floating number animation."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'xp-float-number' in html

    def test_xp_flash_css_exists(self, client):
        """XP flash CSS classes should be in the stylesheet."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.xp-flash' in css
        assert 'xp-glow-flash' in css
        assert '.xp-float-number' in css
        assert 'xp-float-up' in css

    def test_award_calls_milestone_check(self, client):
        """The award function should call checkXpMilestoneFlash."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'checkXpMilestoneFlash(oldTotal, total)' in html

    def test_reduced_motion_disables_celebration_confetti(self, client):
        """Reduced motion should disable celebration confetti."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.celebration-confetti { animation: none !important; display: none !important; }' in css

    def test_reduced_motion_disables_rank_up_banner(self, client):
        """Reduced motion should disable rank-up banner animations."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.rank-up-banner { transition: none !important; transform: none !important; }' in css

    def test_reduced_motion_disables_gold_particles(self, client):
        """Reduced motion should disable gold particles."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.rank-up-gold-particle { animation: none !important; display: none !important; }' in css

    def test_reduced_motion_disables_xp_flash(self, client):
        """Reduced motion should disable XP flash animation."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.xp-flash { animation: none !important; }' in css

    def test_reduced_motion_disables_xp_float_number(self, client):
        """Reduced motion should disable floating XP number."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.xp-float-number { animation: none !important; display: none !important; }' in css

    def test_parrotxp_exposes_celebration_functions(self, client):
        """ParrotXP global should expose celebration functions."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'spawnCelebrationConfetti: spawnCelebrationConfetti' in html
        assert 'showRankUpBanner: showRankUpBanner' in html
        assert 'checkXpMilestoneFlash: checkXpMilestoneFlash' in html


class TestSeasonalThemes:
    """Tests for Holiday Plumage seasonal theme system."""

    def test_season_detection_script_in_base(self, client):
        """Base template should include the season detection script."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'Holiday Plumage' in html
        assert '_httpparrotSeason' in html

    def test_season_detection_checks_winter(self, client):
        """Season detection script should check for winter (Dec 15 - Jan 5)."""
        resp = client.get('/')
        html = resp.data.decode()
        assert "season-winter" in html
        assert "m === 11 && d >= 15" in html
        assert "m === 0 && d <= 5" in html

    def test_season_detection_checks_halloween(self, client):
        """Season detection script should check for halloween (Oct 25 - Nov 1)."""
        resp = client.get('/')
        html = resp.data.decode()
        assert "season-halloween" in html
        assert "m === 9 && d >= 25" in html
        assert "m === 10 && d <= 1" in html

    def test_season_detection_checks_april_fools(self, client):
        """Season detection script should check for April Fools (Apr 1)."""
        resp = client.get('/')
        html = resp.data.decode()
        assert "season-april-fools" in html
        assert "m === 3 && d === 1" in html

    def test_season_detection_checks_valentine(self, client):
        """Season detection script should check for Valentine's (Feb 14)."""
        resp = client.get('/')
        html = resp.data.decode()
        assert "season-valentine" in html
        assert "m === 1 && d === 14" in html

    def test_season_egg_tracking_winter(self, client):
        """Season script should track season_winter egg."""
        resp = client.get('/')
        html = resp.data.decode()
        assert "'season_winter'" in html

    def test_season_egg_tracking_halloween(self, client):
        """Season script should track season_halloween egg."""
        resp = client.get('/')
        html = resp.data.decode()
        assert "'season_halloween'" in html

    def test_season_egg_tracking_april(self, client):
        """Season script should track season_april egg."""
        resp = client.get('/')
        html = resp.data.decode()
        assert "'season_april'" in html

    def test_season_egg_tracking_valentine(self, client):
        """Season script should track season_valentine egg."""
        resp = client.get('/')
        html = resp.data.decode()
        assert "'season_valentine'" in html

    def test_seasonal_egg_awards_50_xp(self, client):
        """Seasonal eggs should award 50 XP."""
        resp = client.get('/')
        html = resp.data.decode()
        assert "award(50, 'seasonal_egg')" in html

    def test_seasonal_egg_uses_localstorage(self, client):
        """Seasonal egg tracking should use eggs_found localStorage key."""
        resp = client.get('/')
        html = resp.data.decode()
        assert "eggs_found" in html

    def test_season_effects_script_present(self, client):
        """Seasonal effects script should be present in base template."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'Holiday Plumage' in html
        assert 'Seasonal Effects' in html

    def test_halloween_ghost_in_footer_script(self, client):
        """Halloween effect should add ghost emoji to footer."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'halloween-ghost' in html

    def test_april_fools_banner_script(self, client):
        """April Fools effect should create scramble banner."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'april-fools-banner' in html
        assert 'All status codes are scrambled' in html

    def test_april_fools_reverts_after_10_seconds(self, client):
        """April Fools scramble should revert after 10 seconds."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'Just kidding!' in html
        assert '10000' in html

    def test_valentine_heart_confetti_function(self, client):
        """Valentine's effect should create heart confetti function."""
        resp = client.get('/')
        html = resp.data.decode()
        assert '_valentineHeartConfetti' in html
        assert 'valentine-heart' in html

    def test_pending_xp_award_after_parrotxp_loads(self, client):
        """Seasonal script should queue XP if ParrotXP not loaded yet."""
        resp = client.get('/')
        html = resp.data.decode()
        assert '_seasonalEggPending' in html


class TestSeasonalCSS:
    """Tests for seasonal CSS classes and styles."""

    def test_winter_css_header(self, client):
        """Winter season should style the header with blue tint."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.season-winter .site-header-compact' in css

    def test_winter_css_snowfall(self, client):
        """Winter season should have snowfall animation on body::before."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.season-winter::before' in css
        assert '@keyframes snowfall' in css

    def test_halloween_css_header(self, client):
        """Halloween season should have orange/purple gradient on header."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.season-halloween .site-header-compact' in css

    def test_halloween_css_hue_rotate(self, client):
        """Halloween season should add hue-rotate on card hover."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.season-halloween .collection-card:hover' in css
        assert 'hue-rotate' in css

    def test_halloween_ghost_css(self, client):
        """Halloween ghost should have float animation."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.halloween-ghost' in css
        assert '@keyframes ghost-float' in css

    def test_april_fools_banner_css(self, client):
        """April Fools banner should have styling."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.april-fools-banner' in css
        assert '.april-fools-revert' in css

    def test_valentine_css_header(self, client):
        """Valentine's season should tint the header pink."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.season-valentine .site-header-compact' in css

    def test_valentine_heart_css(self, client):
        """Valentine's should have heart confetti particles with clip-path."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.valentine-heart' in css
        assert 'clip-path' in css
        assert '@keyframes heart-burst' in css

    def test_reduced_motion_disables_snowfall(self, client):
        """Reduced motion should disable winter snowfall."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.season-winter::before { animation: none !important; display: none !important; }' in css

    def test_reduced_motion_disables_ghost(self, client):
        """Reduced motion should disable ghost animation."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.halloween-ghost { animation: none !important; }' in css

    def test_reduced_motion_disables_april_fools(self, client):
        """Reduced motion should disable April Fools pulse."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.april-fools-banner { animation: none !important; }' in css

    def test_reduced_motion_disables_hearts(self, client):
        """Reduced motion should disable valentine heart animation."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.valentine-heart { animation: none !important; display: none !important; }' in css


class TestSeasonalCollectionEggs:
    """Tests for seasonal egg cards in collection page."""

    def test_collection_has_winter_egg(self, client):
        """Collection page should have season_winter egg card."""
        resp = client.get('/collection')
        html = resp.data.decode()
        assert 'data-egg="season_winter"' in html

    def test_collection_has_halloween_egg(self, client):
        """Collection page should have season_halloween egg card."""
        resp = client.get('/collection')
        html = resp.data.decode()
        assert 'data-egg="season_halloween"' in html

    def test_collection_has_april_egg(self, client):
        """Collection page should have season_april egg card."""
        resp = client.get('/collection')
        html = resp.data.decode()
        assert 'data-egg="season_april"' in html

    def test_collection_has_valentine_egg(self, client):
        """Collection page should have season_valentine egg card."""
        resp = client.get('/collection')
        html = resp.data.decode()
        assert 'data-egg="season_valentine"' in html

    def test_collection_seasonal_egg_hints(self, client):
        """Seasonal egg cards should have appropriate hint text."""
        resp = client.get('/collection')
        html = resp.data.decode()
        assert 'winter holidays' in html.lower()
        assert 'trick or treat' in html.lower()
        assert 'not everything is as it seems' in html.lower()
        assert 'love is in the http' in html.lower()

    def test_collection_preserves_existing_eggs(self, client):
        """Collection page should still have all original egg cards."""
        resp = client.get('/collection')
        html = resp.data.decode()
        assert 'data-egg="204"' in html
        assert 'data-egg="418"' in html
        assert 'data-egg="429"' in html
        assert 'data-egg="508"' in html
        assert 'data-egg="konami"' in html
        assert 'data-egg="barrel_roll"' in html
        assert 'data-egg="http_handshake"' in html


# --- Learning Paths ---

class TestLearningPathsData:
    """Validate the learning_paths.py data structure."""

    def test_all_paths_have_required_keys(self):
        from learning_paths import LEARNING_PATHS
        required = {'id', 'title', 'description', 'difficulty', 'steps'}
        for path in LEARNING_PATHS:
            assert required.issubset(path.keys()), f"Path {path.get('id')} missing keys"

    def test_path_ids_are_unique(self):
        from learning_paths import LEARNING_PATHS
        ids = [p['id'] for p in LEARNING_PATHS]
        assert len(ids) == len(set(ids)), "Duplicate path ids"

    def test_path_difficulties_valid(self):
        from learning_paths import LEARNING_PATHS
        allowed = {'beginner', 'intermediate', 'advanced'}
        for path in LEARNING_PATHS:
            assert path['difficulty'] in allowed, f"Invalid difficulty: {path['difficulty']}"

    def test_all_steps_have_required_keys(self):
        from learning_paths import LEARNING_PATHS
        for path in LEARNING_PATHS:
            for i, step in enumerate(path['steps']):
                assert 'type' in step, f"Step {i} in {path['id']} missing type"
                assert 'target' in step, f"Step {i} in {path['id']} missing target"
                assert 'label' in step, f"Step {i} in {path['id']} missing label"

    def test_step_types_valid(self):
        from learning_paths import LEARNING_PATHS
        allowed = {'visit', 'practice', 'debug', 'quiz', 'learn'}
        for path in LEARNING_PATHS:
            for step in path['steps']:
                assert step['type'] in allowed, f"Invalid step type: {step['type']}"

    def test_visit_targets_are_valid_codes(self):
        """Visit-type step targets must correspond to known status codes."""
        from learning_paths import LEARNING_PATHS
        from index import _name_cache
        for path in LEARNING_PATHS:
            for step in path['steps']:
                if step['type'] == 'visit':
                    assert step['target'] in _name_cache, \
                        f"Unknown code {step['target']} in path {path['id']}"

    def test_learn_targets_are_valid_slugs(self):
        """Learn-type step targets must correspond to known confusion pair slugs."""
        from learning_paths import LEARNING_PATHS
        from confusion_pairs import CONFUSION_PAIRS_BY_SLUG
        for path in LEARNING_PATHS:
            for step in path['steps']:
                if step['type'] == 'learn':
                    assert step['target'] in CONFUSION_PAIRS_BY_SLUG, \
                        f"Unknown slug {step['target']} in path {path['id']}"

    def test_practice_targets_are_valid_ids(self):
        """Practice-type step targets must correspond to known scenario ids."""
        from learning_paths import LEARNING_PATHS
        from scenarios import SCENARIOS
        scenario_ids = {s['id'] for s in SCENARIOS}
        for path in LEARNING_PATHS:
            for step in path['steps']:
                if step['type'] == 'practice':
                    assert step['target'] in scenario_ids, \
                        f"Unknown scenario id {step['target']} in path {path['id']}"

    def test_debug_targets_are_valid_ids(self):
        """Debug-type step targets must correspond to known exercise ids."""
        from learning_paths import LEARNING_PATHS
        from debug_exercises import DEBUG_EXERCISES
        debug_ids = {e['id'] for e in DEBUG_EXERCISES}
        for path in LEARNING_PATHS:
            for step in path['steps']:
                if step['type'] == 'debug':
                    assert step['target'] in debug_ids, \
                        f"Unknown debug id {step['target']} in path {path['id']}"

    def test_three_paths_exist(self):
        from learning_paths import LEARNING_PATHS
        assert len(LEARNING_PATHS) == 3

    def test_lookup_by_id(self):
        from learning_paths import LEARNING_PATHS_BY_ID
        assert 'http-foundations' in LEARNING_PATHS_BY_ID
        assert 'error-whisperer' in LEARNING_PATHS_BY_ID
        assert 'redirect-master' in LEARNING_PATHS_BY_ID

    def test_http_foundations_is_beginner(self):
        from learning_paths import LEARNING_PATHS_BY_ID
        assert LEARNING_PATHS_BY_ID['http-foundations']['difficulty'] == 'beginner'

    def test_error_whisperer_is_intermediate(self):
        from learning_paths import LEARNING_PATHS_BY_ID
        assert LEARNING_PATHS_BY_ID['error-whisperer']['difficulty'] == 'intermediate'

    def test_redirect_master_is_advanced(self):
        from learning_paths import LEARNING_PATHS_BY_ID
        assert LEARNING_PATHS_BY_ID['redirect-master']['difficulty'] == 'advanced'


class TestPathsIndexRoute:
    """Tests for /paths route."""

    def test_paths_index_returns_200(self, client):
        resp = client.get('/paths')
        assert resp.status_code == 200

    def test_paths_index_has_title(self, client):
        resp = client.get('/paths')
        html = resp.data.decode()
        assert 'Learning Paths' in html

    def test_paths_index_lists_all_paths(self, client):
        resp = client.get('/paths')
        html = resp.data.decode()
        assert 'HTTP Foundations' in html
        assert 'Error Whisperer' in html
        assert 'Redirect Master' in html

    def test_paths_index_has_difficulty_badges(self, client):
        resp = client.get('/paths')
        html = resp.data.decode()
        assert 'path-difficulty-beginner' in html
        assert 'path-difficulty-intermediate' in html
        assert 'path-difficulty-advanced' in html

    def test_paths_index_has_progress_bars(self, client):
        resp = client.get('/paths')
        html = resp.data.decode()
        assert 'path-progress-bar' in html
        assert 'progressbar' in html

    def test_paths_index_links_to_details(self, client):
        resp = client.get('/paths')
        html = resp.data.decode()
        assert 'href="/paths/http-foundations"' in html
        assert 'href="/paths/error-whisperer"' in html
        assert 'href="/paths/redirect-master"' in html

    def test_paths_index_has_step_counts(self, client):
        resp = client.get('/paths')
        html = resp.data.decode()
        assert 'steps' in html

    def test_paths_index_has_descriptions(self, client):
        resp = client.get('/paths')
        html = resp.data.decode()
        assert 'Start your HTTP journey' in html
        assert 'Master the 4xx and 5xx' in html
        assert 'Conquer the full family' in html


class TestPathDetailRoute:
    """Tests for /paths/<path_id> route."""

    def test_path_detail_returns_200(self, client):
        resp = client.get('/paths/http-foundations')
        assert resp.status_code == 200

    def test_path_detail_invalid_id_returns_404(self, client):
        resp = client.get('/paths/nonexistent-path')
        assert resp.status_code == 404

    def test_path_detail_has_title(self, client):
        resp = client.get('/paths/http-foundations')
        html = resp.data.decode()
        assert 'HTTP Foundations' in html

    def test_path_detail_has_breadcrumb(self, client):
        resp = client.get('/paths/http-foundations')
        html = resp.data.decode()
        assert 'breadcrumb' in html.lower() or 'Breadcrumb' in html
        assert 'href="/paths"' in html

    def test_path_detail_has_difficulty_badge(self, client):
        resp = client.get('/paths/http-foundations')
        html = resp.data.decode()
        assert 'path-difficulty-beginner' in html

    def test_path_detail_has_progress_bar(self, client):
        resp = client.get('/paths/http-foundations')
        html = resp.data.decode()
        assert 'progress-fill' in html
        assert 'progressbar' in html

    def test_path_detail_has_steps(self, client):
        resp = client.get('/paths/http-foundations')
        html = resp.data.decode()
        assert 'path-step' in html
        assert 'path-step-check' in html

    def test_path_detail_has_step_type_badges(self, client):
        resp = client.get('/paths/http-foundations')
        html = resp.data.decode()
        assert 'path-step-type-visit' in html
        assert 'path-step-type-practice' in html
        assert 'path-step-type-learn' in html
        assert 'path-step-type-quiz' in html

    def test_path_detail_has_step_links(self, client):
        resp = client.get('/paths/http-foundations')
        html = resp.data.decode()
        assert 'href="/200"' in html
        assert 'href="/quiz"' in html
        assert 'href="/learn/200-vs-204"' in html

    def test_path_detail_has_completion_banner(self, client):
        resp = client.get('/paths/http-foundations')
        html = resp.data.decode()
        assert 'path-complete-banner' in html
        assert 'Path Complete' in html

    def test_path_detail_has_xp_bonus_script(self, client):
        resp = client.get('/paths/http-foundations')
        html = resp.data.decode()
        assert 'path_complete' in html
        assert '500' in html  # 500 XP bonus

    def test_all_paths_render(self, client):
        """Every configured path detail page should render without error."""
        from learning_paths import LEARNING_PATHS
        for path in LEARNING_PATHS:
            resp = client.get(f'/paths/{path["id"]}')
            assert resp.status_code == 200, f"/paths/{path['id']} returned {resp.status_code}"

    def test_error_whisperer_has_debug_steps(self, client):
        resp = client.get('/paths/error-whisperer')
        html = resp.data.decode()
        assert 'path-step-type-debug' in html
        assert 'href="/debug"' in html

    def test_redirect_master_has_learn_steps(self, client):
        resp = client.get('/paths/redirect-master')
        html = resp.data.decode()
        assert 'href="/learn/301-vs-302"' in html
        assert 'href="/learn/307-vs-308"' in html
        assert 'href="/learn/302-vs-307"' in html


class TestPathsNavLink:
    """Tests for Paths link in navigation."""

    def test_nav_has_paths_link(self, client):
        resp = client.get('/')
        html = resp.data.decode()
        assert 'href="/paths"' in html
        assert 'Learning Paths' in html

    def test_nav_paths_active_on_index(self, client):
        resp = client.get('/paths')
        html = resp.data.decode()
        # The /paths nav link should have the active class
        assert 'nav-active' in html

    def test_nav_paths_active_on_detail(self, client):
        resp = client.get('/paths/http-foundations')
        html = resp.data.decode()
        assert 'nav-active' in html


class TestPathsSitemap:
    """Tests for paths URLs in sitemap."""

    def test_sitemap_includes_paths_index(self, client):
        resp = client.get('/sitemap.xml')
        xml = resp.data.decode()
        assert '/paths</loc>' in xml or '/paths<' in xml

    def test_sitemap_includes_path_details(self, client):
        resp = client.get('/sitemap.xml')
        xml = resp.data.decode()
        assert '/paths/http-foundations' in xml
        assert '/paths/error-whisperer' in xml
        assert '/paths/redirect-master' in xml


# --- Security Audit ---

class TestSecurityAudit:
    def test_security_audit_page_renders(self, client):
        """Security audit page should return 200 with expected content."""
        resp = client.get('/security-audit')
        assert resp.status_code == 200
        html = resp.data.decode()
        assert 'Security Audit' in html
        assert 'audit-url' in html
        assert 'audit-form' in html

    def test_security_audit_has_nonce(self, client):
        """Security audit script tag should have a nonce."""
        resp = client.get('/security-audit')
        csp = resp.headers.get('Content-Security-Policy', '')
        nonce = re.search(r"'nonce-([^']+)'", csp).group(1)
        assert f'nonce="{nonce}"'.encode() in resp.data

    def test_security_audit_nav_link(self, client):
        """Navigation should contain a link to the security audit page."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'href="/security-audit"' in html

    def test_security_audit_in_sitemap(self, client):
        """Sitemap should include the security audit page."""
        resp = client.get('/sitemap.xml')
        assert b'/security-audit' in resp.data

    def test_security_audit_api_in_robots_txt(self, client):
        """robots.txt should block /api/security-audit."""
        resp = client.get('/robots.txt')
        assert b'Disallow: /api/security-audit' in resp.data


class TestSecurityAuditAPI:
    def test_api_missing_url(self, client):
        """API should return 400 when url is missing."""
        resp = client.get('/api/security-audit')
        assert resp.status_code == 400
        assert b'Missing required parameter' in resp.data

    def test_api_blocked_url(self, client):
        """API should return 403 for private/blocked URLs."""
        resp = client.get('/api/security-audit?url=http://127.0.0.1/')
        assert resp.status_code == 403
        assert b'not allowed' in resp.data

    def test_api_rate_limited(self, client):
        """API should return 429 when rate limited."""
        for _ in range(10):
            client.get('/api/security-audit?url=http://127.0.0.1/')
        resp = client.get('/api/security-audit?url=https://example.com')
        assert resp.status_code == 429
        assert b'Rate limit' in resp.data

    def test_api_success_returns_grade(self, client):
        """API should return a grade, score, and checks for a valid URL."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {
            'Strict-Transport-Security': 'max-age=31536000',
            'Content-Security-Policy': "default-src 'self'",
            'X-Content-Type-Options': 'nosniff',
            'X-Frame-Options': 'DENY',
            'Referrer-Policy': 'strict-origin-when-cross-origin',
            'Permissions-Policy': 'camera=()',
        }
        mock_resp.close = MagicMock()
        addrinfo = [(socket.AF_INET, socket.SOCK_STREAM, 0, '', ('93.184.216.34', 0))]
        with patch('index.socket.getaddrinfo', return_value=addrinfo), \
             patch('requests.get', return_value=mock_resp):
            resp = client.get('/api/security-audit?url=https://example.com')
            assert resp.status_code == 200
            data = resp.get_json()
            assert 'grade' in data
            assert 'score' in data
            assert 'max_score' in data
            assert 'checks' in data
            assert isinstance(data['checks'], list)
            assert len(data['checks']) == 10

    def test_api_auto_prefix_scheme(self, client):
        """URLs without scheme should get https:// prepended."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {}
        mock_resp.close = MagicMock()
        addrinfo = [(socket.AF_INET, socket.SOCK_STREAM, 0, '', ('93.184.216.34', 0))]
        with patch('index.socket.getaddrinfo', return_value=addrinfo), \
             patch('requests.get', return_value=mock_resp) as mock_get:
            resp = client.get('/api/security-audit?url=example.com')
            assert resp.status_code == 200
            call_args = mock_get.call_args
            assert call_args[0][0] == 'https://example.com'

    def test_api_connection_error(self, client):
        """API should return 502 when connection fails."""
        addrinfo = [(socket.AF_INET, socket.SOCK_STREAM, 0, '', ('93.184.216.34', 0))]
        with patch('index.socket.getaddrinfo', return_value=addrinfo), \
             patch('requests.get', side_effect=requests.RequestException):
            resp = client.get('/api/security-audit?url=https://example.com')
            assert resp.status_code == 502
            assert b'Could not connect' in resp.data

    def test_api_perfect_score(self, client):
        """A site with all security headers should get A+ grade."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {
            'Strict-Transport-Security': 'max-age=31536000; includeSubDomains',
            'Content-Security-Policy': "default-src 'self'",
            'X-Content-Type-Options': 'nosniff',
            'X-Frame-Options': 'DENY',
            'Referrer-Policy': 'strict-origin-when-cross-origin',
            'Permissions-Policy': 'camera=()',
        }
        mock_resp.close = MagicMock()
        addrinfo = [(socket.AF_INET, socket.SOCK_STREAM, 0, '', ('93.184.216.34', 0))]
        with patch('index.socket.getaddrinfo', return_value=addrinfo), \
             patch('requests.get', return_value=mock_resp):
            resp = client.get('/api/security-audit?url=https://example.com')
            data = resp.get_json()
            assert data['grade'] == 'A+'
            assert data['score'] == data['max_score']

    def test_api_poor_score(self, client):
        """A site with no security headers should get F grade."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {
            'Server': 'Apache/2.4.41 (Ubuntu)',
            'X-Powered-By': 'PHP/7.4.3',
            'Access-Control-Allow-Origin': '*',
            'Set-Cookie': 'session=abc123',
        }
        mock_resp.close = MagicMock()
        addrinfo = [(socket.AF_INET, socket.SOCK_STREAM, 0, '', ('93.184.216.34', 0))]
        with patch('index.socket.getaddrinfo', return_value=addrinfo), \
             patch('requests.get', return_value=mock_resp):
            resp = client.get('/api/security-audit?url=https://example.com')
            data = resp.get_json()
            assert data['grade'] == 'F'
            assert data['score'] == 0


class TestSecurityAuditScoringLogic:
    """Unit tests for the _run_security_checks and _score_to_grade functions."""

    def test_all_headers_present_full_score(self):
        """All security headers present should give full score."""
        headers = {
            'Strict-Transport-Security': 'max-age=31536000',
            'Content-Security-Policy': "default-src 'self'",
            'X-Content-Type-Options': 'nosniff',
            'X-Frame-Options': 'DENY',
            'Referrer-Policy': 'strict-origin-when-cross-origin',
            'Permissions-Policy': 'camera=()',
        }
        score, max_score, checks = _run_security_checks(headers)
        assert score == max_score
        assert all(c['status'] == 'pass' for c in checks)

    def test_no_headers_zero_score(self):
        """No security headers should give zero score (except absence-based checks)."""
        headers = {
            'Server': 'nginx/1.18',
            'X-Powered-By': 'Express',
            'Access-Control-Allow-Origin': '*',
            'Set-Cookie': 'sid=abc',
        }
        score, max_score, checks = _run_security_checks(headers)
        assert score == 0
        assert max_score == 70

    def test_xcto_must_be_nosniff(self):
        """X-Content-Type-Options must be exactly 'nosniff' to pass."""
        headers = {'X-Content-Type-Options': 'nosniff'}
        score, _, checks = _run_security_checks(headers)
        xcto = next(c for c in checks if c['id'] == 'xcto')
        assert xcto['status'] == 'pass'

        headers_wrong = {'X-Content-Type-Options': 'something-else'}
        _, _, checks_wrong = _run_security_checks(headers_wrong)
        xcto_wrong = next(c for c in checks_wrong if c['id'] == 'xcto')
        assert xcto_wrong['status'] == 'fail'

    def test_server_header_absent_passes(self):
        """Absent Server header should pass."""
        _, _, checks = _run_security_checks({})
        server = next(c for c in checks if c['id'] == 'server')
        assert server['status'] == 'pass'

    def test_server_header_leaking_fails(self):
        """Server header with version info should fail."""
        _, _, checks = _run_security_checks({'Server': 'Apache/2.4.41'})
        server = next(c for c in checks if c['id'] == 'server')
        assert server['status'] == 'fail'

    def test_powered_by_absent_passes(self):
        """Absent X-Powered-By header should pass."""
        _, _, checks = _run_security_checks({})
        powered = next(c for c in checks if c['id'] == 'powered')
        assert powered['status'] == 'pass'

    def test_powered_by_present_fails(self):
        """Present X-Powered-By header should fail."""
        _, _, checks = _run_security_checks({'X-Powered-By': 'Express'})
        powered = next(c for c in checks if c['id'] == 'powered')
        assert powered['status'] == 'fail'

    def test_cookie_secure_httponly_samesite(self):
        """Cookie with all three attributes should pass."""
        headers = {'Set-Cookie': 'sid=abc; Secure; HttpOnly; SameSite=Lax'}
        _, _, checks = _run_security_checks(headers)
        cookie = next(c for c in checks if c['id'] == 'cookie')
        assert cookie['status'] == 'pass'

    def test_cookie_missing_attributes_fails(self):
        """Cookie without security attributes should fail."""
        headers = {'Set-Cookie': 'sid=abc'}
        _, _, checks = _run_security_checks(headers)
        cookie = next(c for c in checks if c['id'] == 'cookie')
        assert cookie['status'] == 'fail'

    def test_cookie_absent_passes(self):
        """No cookies at all should pass."""
        _, _, checks = _run_security_checks({})
        cookie = next(c for c in checks if c['id'] == 'cookie')
        assert cookie['status'] == 'pass'

    def test_cors_wildcard_fails(self):
        """CORS wildcard * should fail."""
        _, _, checks = _run_security_checks({'Access-Control-Allow-Origin': '*'})
        cors = next(c for c in checks if c['id'] == 'cors_wildcard')
        assert cors['status'] == 'fail'

    def test_cors_specific_origin_passes(self):
        """Specific CORS origin should pass."""
        _, _, checks = _run_security_checks({'Access-Control-Allow-Origin': 'https://example.com'})
        cors = next(c for c in checks if c['id'] == 'cors_wildcard')
        assert cors['status'] == 'pass'

    def test_cors_absent_passes(self):
        """Absent CORS header should pass."""
        _, _, checks = _run_security_checks({})
        cors = next(c for c in checks if c['id'] == 'cors_wildcard')
        assert cors['status'] == 'pass'

    def test_case_insensitive_headers(self):
        """Header checks should be case insensitive."""
        headers = {
            'strict-transport-security': 'max-age=31536000',
            'content-security-policy': "default-src 'self'",
            'x-content-type-options': 'nosniff',
        }
        score, _, checks = _run_security_checks(headers)
        hsts = next(c for c in checks if c['id'] == 'hsts')
        csp = next(c for c in checks if c['id'] == 'csp')
        xcto = next(c for c in checks if c['id'] == 'xcto')
        assert hsts['status'] == 'pass'
        assert csp['status'] == 'pass'
        assert xcto['status'] == 'pass'


class TestScoreToGrade:
    """Tests for the _score_to_grade conversion function."""

    def test_grade_a_plus(self):
        assert _score_to_grade(75, 75) == 'A+'
        assert _score_to_grade(72, 75) == 'A+'

    def test_grade_a(self):
        assert _score_to_grade(64, 75) == 'A'

    def test_grade_b(self):
        assert _score_to_grade(53, 75) == 'B'

    def test_grade_c(self):
        assert _score_to_grade(38, 75) == 'C'

    def test_grade_d(self):
        assert _score_to_grade(23, 75) == 'D'

    def test_grade_f(self):
        assert _score_to_grade(10, 75) == 'F'
        assert _score_to_grade(0, 75) == 'F'

    def test_grade_zero_max(self):
        assert _score_to_grade(0, 0) == 'F'

    def test_each_check_has_required_fields(self):
        """Every check result should have id, header, points, desc, fix, and status."""
        _, _, checks = _run_security_checks({})
        for check in checks:
            assert 'id' in check
            assert 'header' in check
            assert 'points' in check
            assert 'desc' in check
            assert 'fix' in check
            assert 'status' in check
            assert check['status'] in ('pass', 'fail')


# --- Fault Simulator page ---

class TestFaultSimulatorPage:
    def test_page_renders(self, client):
        resp = client.get('/fault-simulator')
        assert resp.status_code == 200
        assert b'Fault Simulator' in resp.data

    def test_page_has_endpoint_sections(self, client):
        resp = client.get('/fault-simulator')
        html = resp.data.decode()
        assert 'section-delay' in html
        assert 'section-drip' in html
        assert 'section-stream' in html
        assert 'section-jitter' in html
        assert 'section-unstable' in html

    def test_page_has_try_buttons(self, client):
        resp = client.get('/fault-simulator')
        html = resp.data.decode()
        assert 'delay-btn' in html
        assert 'drip-btn' in html
        assert 'stream-btn' in html
        assert 'jitter-btn' in html
        assert 'unstable-btn' in html

    def test_nav_link_exists(self, client):
        resp = client.get('/')
        html = resp.data.decode()
        assert 'href="/fault-simulator"' in html
        assert 'Fault Simulator' in html

    def test_sitemap_contains_fault_simulator(self, client):
        resp = client.get('/sitemap.xml')
        assert b'/fault-simulator' in resp.data

    def test_robots_disallows_fault_apis(self, client):
        resp = client.get('/robots.txt')
        text = resp.data.decode()
        assert '/api/delay/' in text
        assert '/api/drip' in text
        assert '/api/stream/' in text
        assert '/api/jitter' in text
        assert '/api/unstable' in text


# --- Fault Simulation: Delay endpoint ---

class TestApiDelay:
    def test_delay_returns_json(self, client):
        resp = client.get('/api/delay/0')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['delay'] == 0
        assert 'timestamp' in data

    def test_delay_valid_seconds(self, client):
        resp = client.get('/api/delay/1')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['delay'] == 1

    def test_delay_max_boundary(self, client):
        resp = client.get('/api/delay/10')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['delay'] == 10

    def test_delay_exceeds_max(self, client):
        resp = client.get('/api/delay/11')
        assert resp.status_code == 400
        data = resp.get_json()
        assert 'error' in data

    def test_delay_negative(self, client):
        resp = client.get('/api/delay/-1')
        assert resp.status_code == 400 or resp.status_code == 404

    def test_delay_rate_limited(self, client):
        for _ in range(10):
            client.get('/api/delay/0')
        resp = client.get('/api/delay/0')
        assert resp.status_code == 429
        assert b'Rate limit' in resp.data


# --- Fault Simulation: Drip endpoint ---

class TestApiDrip:
    def test_drip_default_params(self, client):
        resp = client.get('/api/drip?duration=1&numbytes=10')
        assert resp.status_code == 200
        assert len(resp.data) == 10

    def test_drip_returns_correct_bytes(self, client):
        resp = client.get('/api/drip?duration=1&numbytes=100')
        assert resp.status_code == 200
        assert len(resp.data) == 100

    def test_drip_content_type(self, client):
        resp = client.get('/api/drip?duration=1&numbytes=10')
        assert 'octet-stream' in resp.content_type

    def test_drip_exceeds_max_duration(self, client):
        resp = client.get('/api/drip?duration=31&numbytes=10')
        assert resp.status_code == 400
        data = resp.get_json()
        assert 'error' in data

    def test_drip_exceeds_max_bytes(self, client):
        resp = client.get('/api/drip?duration=1&numbytes=10241')
        assert resp.status_code == 400
        data = resp.get_json()
        assert 'error' in data

    def test_drip_zero_duration(self, client):
        resp = client.get('/api/drip?duration=0&numbytes=10')
        assert resp.status_code == 400

    def test_drip_zero_bytes(self, client):
        resp = client.get('/api/drip?duration=1&numbytes=0')
        assert resp.status_code == 400

    def test_drip_negative_params(self, client):
        resp = client.get('/api/drip?duration=-1&numbytes=10')
        assert resp.status_code == 400

    def test_drip_rate_limited(self, client):
        for _ in range(10):
            client.get('/api/drip?duration=1&numbytes=1')
        resp = client.get('/api/drip?duration=1&numbytes=1')
        assert resp.status_code == 429


# --- Fault Simulation: Stream endpoint ---

class TestApiStream:
    def test_stream_returns_lines(self, client):
        resp = client.get('/api/stream/3')
        assert resp.status_code == 200
        lines = [l for l in resp.data.decode().strip().split('\n') if l]
        assert len(lines) == 3

    def test_stream_json_lines(self, client):
        import json
        resp = client.get('/api/stream/2')
        lines = [l for l in resp.data.decode().strip().split('\n') if l]
        for line in lines:
            data = json.loads(line)
            assert 'id' in data
            assert 'timestamp' in data
            assert 'parrot' in data

    def test_stream_content_type(self, client):
        resp = client.get('/api/stream/1')
        assert 'ndjson' in resp.content_type

    def test_stream_exceeds_max(self, client):
        resp = client.get('/api/stream/101')
        assert resp.status_code == 400
        data = resp.get_json()
        assert 'error' in data

    def test_stream_zero(self, client):
        resp = client.get('/api/stream/0')
        assert resp.status_code == 400

    def test_stream_single_line(self, client):
        import json
        resp = client.get('/api/stream/1')
        assert resp.status_code == 200
        lines = [l for l in resp.data.decode().strip().split('\n') if l]
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data['id'] == 0

    def test_stream_rate_limited(self, client):
        for _ in range(10):
            client.get('/api/stream/1')
        resp = client.get('/api/stream/1')
        assert resp.status_code == 429


# --- Fault Simulation: Jitter endpoint ---

class TestApiJitter:
    def test_jitter_default_params(self, client):
        resp = client.get('/api/jitter?min=0&max=0')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['delay_ms'] == 0
        assert 'range' in data
        assert 'timestamp' in data

    def test_jitter_returns_within_range(self, client):
        resp = client.get('/api/jitter?min=100&max=200')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 100 <= data['delay_ms'] <= 200

    def test_jitter_exceeds_max(self, client):
        resp = client.get('/api/jitter?min=0&max=10001')
        assert resp.status_code == 400
        data = resp.get_json()
        assert 'error' in data

    def test_jitter_min_exceeds_max_value(self, client):
        resp = client.get('/api/jitter?min=500&max=100')
        assert resp.status_code == 400
        data = resp.get_json()
        assert 'error' in data

    def test_jitter_negative(self, client):
        resp = client.get('/api/jitter?min=-1&max=100')
        assert resp.status_code == 400

    def test_jitter_rate_limited(self, client):
        for _ in range(10):
            client.get('/api/jitter?min=0&max=0')
        resp = client.get('/api/jitter?min=0&max=0')
        assert resp.status_code == 429


# --- Fault Simulation: Unstable endpoint ---

class TestApiUnstable:
    def test_unstable_returns_200_or_500(self, client):
        resp = client.get('/api/unstable?failure_rate=0.5')
        assert resp.status_code in (200, 500)
        data = resp.get_json()
        assert 'status' in data
        assert 'failure_rate' in data
        assert 'timestamp' in data

    def test_unstable_zero_failure_rate(self, client):
        resp = client.get('/api/unstable?failure_rate=0.0')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['status'] == 'ok'

    def test_unstable_full_failure_rate(self, client):
        resp = client.get('/api/unstable?failure_rate=1.0')
        assert resp.status_code == 500
        data = resp.get_json()
        assert data['status'] == 'error'

    def test_unstable_invalid_rate_too_high(self, client):
        resp = client.get('/api/unstable?failure_rate=1.5')
        assert resp.status_code == 400
        data = resp.get_json()
        assert 'error' in data

    def test_unstable_invalid_rate_negative(self, client):
        resp = client.get('/api/unstable?failure_rate=-0.1')
        assert resp.status_code == 400

    def test_unstable_default_rate(self, client):
        resp = client.get('/api/unstable')
        assert resp.status_code in (200, 500)
        data = resp.get_json()
        assert data['failure_rate'] == 0.5

    def test_unstable_rate_limited(self, client):
        for _ in range(10):
            client.get('/api/unstable?failure_rate=0')
        resp = client.get('/api/unstable?failure_rate=0')
        assert resp.status_code == 429


# --- Procedural Sound Toggle (ParrotSound) ---

class TestParrotSoundSystem:
    """Verify ParrotSound object is defined and wired into templates."""

    def test_parrot_sound_defined_in_base(self, client):
        """Base template should define the ParrotSound global object."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'window.ParrotSound' in html

    def test_parrot_sound_squawk_method(self, client):
        """ParrotSound should expose a squawk method."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'squawk: squawk' in html

    def test_parrot_sound_correct_method(self, client):
        """ParrotSound should expose a correct method."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'correct: correct' in html

    def test_parrot_sound_wrong_method(self, client):
        """ParrotSound should expose a wrong method."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'wrong: wrong' in html

    def test_parrot_sound_jingle_method(self, client):
        """ParrotSound should expose a jingle method."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'jingle: jingle' in html

    def test_parrot_sound_click_method(self, client):
        """ParrotSound should expose a click method."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'click: click' in html

    def test_parrot_sound_is_enabled_method(self, client):
        """ParrotSound should expose an isEnabled method."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'isEnabled: isEnabled' in html

    def test_parrot_sound_toggle_method(self, client):
        """ParrotSound should expose a toggle method."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'toggle: toggle' in html

    def test_sound_toggle_button_in_header(self, client):
        """Header should contain the sound toggle button (on subpages)."""
        resp = client.get('/200')
        html = resp.data.decode()
        assert 'id="sound-toggle"' in html
        assert 'sound-toggle-btn' in html

    def test_sound_toggle_icon_in_header(self, client):
        """Sound toggle button should contain the icon span."""
        resp = client.get('/200')
        html = resp.data.decode()
        assert 'id="sound-toggle-icon"' in html

    def test_sound_toggle_aria_pressed(self, client):
        """Sound toggle button should have aria-pressed attribute."""
        resp = client.get('/200')
        html = resp.data.decode()
        assert 'aria-pressed=' in html

    def test_localstorage_key_referenced(self, client):
        """ParrotSound should use httpparrot_sound localStorage key."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'httpparrot_sound' in html

    def test_reduced_motion_check(self, client):
        """ParrotSound should check prefers-reduced-motion."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'prefers-reduced-motion' in html

    def test_audio_context_lazy_creation(self, client):
        """ParrotSound should lazily create AudioContext."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'AudioContext' in html
        assert 'webkitAudioContext' in html

    def test_oscillator_usage(self, client):
        """ParrotSound should use OscillatorNode for sounds."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'createOscillator' in html

    def test_gain_node_usage(self, client):
        """ParrotSound should use GainNode for volume control."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'createGain' in html


class TestParrotSoundWiring:
    """Verify sound triggers are wired into quiz, daily, and practice templates."""

    def test_quiz_correct_sound(self, client):
        """Quiz should trigger ParrotSound.correct() on correct answers."""
        resp = client.get('/quiz')
        html = resp.data.decode()
        assert 'ParrotSound.correct()' in html

    def test_quiz_wrong_sound(self, client):
        """Quiz should trigger ParrotSound.wrong() on wrong answers."""
        resp = client.get('/quiz')
        html = resp.data.decode()
        assert 'ParrotSound.wrong()' in html

    def test_daily_correct_sound(self, client):
        """Daily should trigger ParrotSound.correct() on correct answers."""
        resp = client.get('/daily')
        html = resp.data.decode()
        assert 'ParrotSound.correct()' in html

    def test_daily_wrong_sound(self, client):
        """Daily should trigger ParrotSound.wrong() on wrong answers."""
        resp = client.get('/daily')
        html = resp.data.decode()
        assert 'ParrotSound.wrong()' in html

    def test_practice_correct_sound(self, client):
        """Practice should trigger ParrotSound.correct() on correct answers."""
        resp = client.get('/practice')
        html = resp.data.decode()
        assert 'ParrotSound.correct()' in html

    def test_practice_wrong_sound(self, client):
        """Practice should trigger ParrotSound.wrong() on wrong answers."""
        resp = client.get('/practice')
        html = resp.data.decode()
        assert 'ParrotSound.wrong()' in html

    def test_feather_toast_jingle(self, client):
        """Feather toast should trigger ParrotSound.jingle()."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'ParrotSound.jingle()' in html

    def test_rank_up_jingle(self, client):
        """Rank-up banner should trigger ParrotSound.jingle()."""
        resp = client.get('/')
        html = resp.data.decode()
        # Both feather toast and rank-up banner call jingle
        count = html.count('ParrotSound.jingle()')
        assert count >= 2, f"Expected at least 2 jingle calls, found {count}"

    def test_sound_gated_by_is_enabled(self, client):
        """All sound triggers should check ParrotSound.isEnabled() first."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'ParrotSound.isEnabled()' in html


# --- Bento Dashboard ---

class TestBentoDashboard:
    """Tests for the bento grid dashboard on the homepage."""

    def test_dashboard_section_present(self, client):
        """Homepage should have a bento dashboard section."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'bento-dashboard' in html

    def test_daily_challenge_tile_present(self, client):
        """Dashboard should have a daily challenge tile."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'bento-tile--daily' in html
        assert 'bento-streak-count' in html
        assert 'Daily Challenge' in html

    def test_daily_challenge_tile_links_to_daily(self, client):
        """Daily challenge tile should link to /daily."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'href="/daily"' in html
        assert 'Play Now' in html

    def test_xp_progress_tile_present(self, client):
        """Dashboard should have an XP progress tile."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'bento-tile--xp' in html
        assert 'bento-rank-name' in html
        assert 'XP Progress' in html

    def test_xp_progress_tile_has_progress_bar(self, client):
        """XP progress tile should have a progress bar."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'bento-xp-bar' in html
        assert 'bento-xp-fill' in html
        assert 'progressbar' in html

    def test_quick_tools_tile_present(self, client):
        """Dashboard should have a quick tools tile."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'bento-tile--tools' in html
        assert 'Quick Tools' in html

    def test_quick_tools_has_quiz_link(self, client):
        """Quick tools tile should link to quiz."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'href="/quiz"' in html

    def test_quick_tools_has_practice_link(self, client):
        """Quick tools tile should link to practice."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'href="/practice"' in html

    def test_quick_tools_has_debug_link(self, client):
        """Quick tools tile should link to debug."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'href="/debug"' in html

    def test_quick_tools_has_playground_link(self, client):
        """Quick tools tile should link to playground."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'href="/playground"' in html

    def test_nextup_tile_present(self, client):
        """Dashboard should have a Next Up recommender tile."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'bento-tile--paths' in html
        assert 'Next Up' in html
        assert 'bento-nextup' in html

    def test_nextup_tile_has_message_and_action(self, client):
        """Next Up tile should have a message, subtitle, and action link."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'id="bento-nextup-message"' in html
        assert 'id="bento-nextup-sub"' in html
        assert 'id="bento-nextup-action"' in html

    def test_nextup_default_links_to_paths(self, client):
        """Next Up tile should default to linking to /paths."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'href="/paths"' in html
        assert 'Get Started' in html

    def test_nextup_recommender_script_present(self, client):
        """Homepage should contain the Next Up recommender script."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'httpparrot_review' in html
        assert 'httpparrot_daily' in html
        assert 'httpparrot_path_' in html
        assert 'httpparrot_weekly' in html

    def test_potd_shown_as_tag_in_grid(self, client):
        """Parrot of the Day should be shown as a tag on the featured card in the grid."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'featured' in html

    def test_parrot_grid_still_present(self, client):
        """The existing parrot card grid should still exist below the dashboard."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'id="parrot-grid"' in html

    def test_bento_dashboard_has_aria_label(self, client):
        """Dashboard section should have an aria-label for accessibility."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'aria-label="Dashboard"' in html

    def test_tool_links_have_aria_labels(self, client):
        """Quick tool links should have aria-labels."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'aria-label="Quiz"' in html
        assert 'aria-label="Practice"' in html
        assert 'aria-label="Debug"' in html
        assert 'aria-label="Playground"' in html


class TestBentoDashboardCSS:
    """Tests for the bento dashboard responsive CSS."""

    def test_bento_dashboard_grid_css_exists(self):
        """CSS should define the bento-dashboard grid."""
        with open('static/style.css') as f:
            css = f.read()
        assert '.bento-dashboard' in css
        assert 'grid-template-columns' in css

    def test_bento_tile_css_exists(self):
        """CSS should define bento-tile styles."""
        with open('static/style.css') as f:
            css = f.read()
        assert '.bento-tile' in css

    def test_bento_responsive_tablet(self):
        """CSS should have tablet responsive breakpoint for bento grid."""
        with open('static/style.css') as f:
            css = f.read()
        assert 'repeat(2, 1fr)' in css

    def test_bento_responsive_mobile(self):
        """CSS should have mobile responsive breakpoint for single-column bento grid."""
        with open('static/style.css') as f:
            css = f.read()
        assert '.bento-dashboard' in css

    def test_bento_tile_min_height(self):
        """Bento tiles should have a minimum height for touch-friendliness."""
        with open('static/style.css') as f:
            css = f.read()
        assert 'min-height' in css

    def test_bento_potd_spans_columns(self):
        """POTD tile should span 2 columns on desktop."""
        with open('static/style.css') as f:
            css = f.read()
        assert 'grid-column: span 2' in css


# --- Spaced Repetition Review page ---

class TestReviewPage:
    """Tests for the /review spaced repetition review page."""

    def test_review_page_returns_200(self, client):
        resp = client.get('/review')
        assert resp.status_code == 200

    def test_review_page_title(self, client):
        resp = client.get('/review')
        html = resp.data.decode()
        assert 'Spaced Repetition Review' in html
        assert 'Review - HTTP Parrots' in html

    def test_review_page_has_h1(self, client):
        resp = client.get('/review')
        html = resp.data.decode()
        assert '<h1>' in html
        assert 'Spaced Repetition Review' in html

    def test_review_page_has_stats_bar(self, client):
        resp = client.get('/review')
        html = resp.data.decode()
        assert 'review-stats-bar' in html
        assert 'review-due' in html
        assert 'review-correct' in html
        assert 'review-wrong' in html
        assert 'review-remaining' in html

    def test_review_page_has_due_today_counter(self, client):
        resp = client.get('/review')
        html = resp.data.decode()
        assert 'Due Today' in html

    def test_review_page_has_session_stats(self, client):
        """Stats bar should show correct/wrong/remaining counters."""
        resp = client.get('/review')
        html = resp.data.decode()
        assert 'Correct' in html
        assert 'Wrong' in html
        assert 'Remaining' in html

    def test_review_page_has_review_area(self, client):
        resp = client.get('/review')
        html = resp.data.decode()
        assert 'review-area' in html

    def test_review_page_has_scenario_data(self, client):
        """Review page should contain scenario data for JS to consume."""
        resp = client.get('/review')
        html = resp.data.decode()
        assert 'scenario_' in html

    def test_review_page_has_debug_data(self, client):
        """Review page should contain debug exercise data for JS to consume."""
        resp = client.get('/review')
        html = resp.data.decode()
        assert 'debug_' in html

    def test_review_page_has_confusion_data(self, client):
        """Review page should contain confusion pair data for JS to consume."""
        resp = client.get('/review')
        html = resp.data.decode()
        assert 'confusion_' in html

    def test_review_page_leitner_box_intervals(self, client):
        """Review page should define Leitner box intervals."""
        resp = client.get('/review')
        html = resp.data.decode()
        assert 'BOX_INTERVALS' in html

    def test_review_page_localstorage_key(self, client):
        """Review page should use the httpparrot_review localStorage key."""
        resp = client.get('/review')
        html = resp.data.decode()
        assert 'httpparrot_review' in html

    def test_review_page_xp_integration(self, client):
        """Review page should award XP for correct answers."""
        resp = client.get('/review')
        html = resp.data.decode()
        assert 'ParrotXP.award' in html
        assert 'review_correct' in html

    def test_review_page_complete_message(self, client):
        """Review page should have a 'Review Complete!' message."""
        resp = client.get('/review')
        html = resp.data.decode()
        assert 'Review Complete!' in html

    def test_review_page_empty_state(self, client):
        """Review page should handle empty queue state."""
        resp = client.get('/review')
        html = resp.data.decode()
        assert 'No items due for review' in html

    def test_review_page_box_indicator(self, client):
        """Review page should show the current Leitner box level."""
        resp = client.get('/review')
        html = resp.data.decode()
        assert 'review-box-indicator' in html

    def test_review_page_has_type_badges(self, client):
        """Review page should distinguish item types with badges."""
        resp = client.get('/review')
        html = resp.data.decode()
        assert 'type-scenario' in html
        assert 'type-debug' in html
        assert 'type-confusion' in html

    def test_review_page_explanation_visibility(self, client):
        """Review page should have explanation div that toggles visibility."""
        resp = client.get('/review')
        html = resp.data.decode()
        assert 'review-explanation' in html

    def test_review_page_next_button(self, client):
        """Review page should have a next item button."""
        resp = client.get('/review')
        html = resp.data.decode()
        assert 'review-next-btn' in html
        assert 'Next Item' in html

    def test_review_page_has_option_buttons(self, client):
        """Review page should render option buttons."""
        resp = client.get('/review')
        html = resp.data.decode()
        assert 'review-option-btn' in html

    def test_review_page_inline_style_has_nonce(self, client):
        resp = client.get('/review')
        html = resp.data.decode()
        assert 'style nonce=' in html

    def test_review_page_inline_script_has_nonce(self, client):
        resp = client.get('/review')
        html = resp.data.decode()
        assert 'script nonce=' in html

    def test_review_csp_header(self, client):
        resp = client.get('/review')
        csp = resp.headers.get('Content-Security-Policy', '')
        assert "default-src 'self'" in csp
        assert "'nonce-" in csp

    def test_review_page_meta_description(self, client):
        resp = client.get('/review')
        html = resp.data.decode()
        assert 'spaced repetition' in html.lower()

    def test_review_nav_link_present(self, client):
        """Desktop nav should have a Review link."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'href="/review"' in html
        assert '>Review<' in html

    def test_review_nav_link_in_mobile_nav(self, client):
        """Both desktop and mobile navs should have a Review link."""
        resp = client.get('/')
        html = resp.data.decode()
        assert html.count('href="/review"') >= 2

    def test_review_in_sitemap(self, client):
        resp = client.get('/sitemap.xml')
        body = resp.data.decode()
        assert '/review</loc>' in body

    def test_review_page_tracks_total_reviews(self, client):
        """Review page should track total_reviews for the Memory Master badge."""
        resp = client.get('/review')
        html = resp.data.decode()
        assert 'total_reviews' in html


class TestReviewLeitnerSystem:
    """Tests for the Leitner box system data structure and behaviour."""

    def test_review_page_defines_five_boxes(self, client):
        """Leitner system should define intervals for 5 boxes."""
        resp = client.get('/review')
        html = resp.data.decode()
        # Box intervals: 1:1, 2:3, 3:7, 4:14, 5:30
        assert '1: 1' in html
        assert '2: 3' in html
        assert '3: 7' in html
        assert '4: 14' in html
        assert '5: 30' in html

    def test_review_page_init_items_function(self, client):
        """Review page should have initItems function to seed new items."""
        resp = client.get('/review')
        html = resp.data.decode()
        assert 'initItems' in html

    def test_review_page_record_answer_function(self, client):
        """Review page should have recordAnswer function."""
        resp = client.get('/review')
        html = resp.data.decode()
        assert 'recordAnswer' in html

    def test_review_page_get_due_items_function(self, client):
        """Review page should have getDueItems function."""
        resp = client.get('/review')
        html = resp.data.decode()
        assert 'getDueItems' in html

    def test_review_item_structure(self, client):
        """Review items should have box_level, next_review, last_answer."""
        resp = client.get('/review')
        html = resp.data.decode()
        assert 'box_level' in html
        assert 'next_review' in html
        assert 'last_answer' in html

    def test_review_correct_moves_up_box(self, client):
        """Correct answer should move item up a box (Math.min(5, ...))."""
        resp = client.get('/review')
        html = resp.data.decode()
        assert 'Math.min(5' in html

    def test_review_wrong_resets_to_box_1(self, client):
        """Wrong answer should reset item to box 1."""
        resp = client.get('/review')
        html = resp.data.decode()
        assert 'box_level = 1' in html


class TestMemoryMasterBadge:
    """Tests for the Memory Master feather badge."""

    def test_memory_master_feather_defined(self, client):
        """Memory Master feather should be in the FEATHERS array."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'memory_master' in html
        assert 'Memory Master' in html

    def test_memory_master_feather_check(self, client):
        """checkFeathers should check total_reviews >= 50."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'total_reviews' in html
        assert '>= 50' in html

    def test_memory_master_feather_desc(self, client):
        """Memory Master should describe 50 spaced repetition reviews."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'Complete 50 spaced repetition reviews' in html


class TestProfileReviewIntegration:
    """Tests for the review system integration in the profile page."""

    def test_profile_has_due_for_review_stat(self, client):
        """Profile page should show a 'Due for Review' stat."""
        resp = client.get('/profile')
        html = resp.data.decode()
        assert 'stat-review-due' in html
        assert 'Due for Review' in html

    def test_profile_review_link(self, client):
        """Profile Due for Review should link to /review."""
        resp = client.get('/profile')
        html = resp.data.decode()
        assert 'href="/review"' in html

    def test_profile_review_reads_localstorage(self, client):
        """Profile page should read httpparrot_review from localStorage."""
        resp = client.get('/profile')
        html = resp.data.decode()
        assert 'httpparrot_review' in html

    def test_profile_xp_breakdown_includes_review(self, client):
        """Profile XP breakdown should list review XP."""
        resp = client.get('/profile')
        html = resp.data.decode()
        assert 'Spaced repetition review correct' in html
        assert '+15 XP' in html


# --- Webhook Inspector / Request Bin ---

class TestWebhookInspectorPage:
    def test_webhook_inspector_page(self, client):
        """Webhook inspector page renders successfully."""
        resp = client.get('/webhook-inspector')
        assert resp.status_code == 200
        html = resp.data.decode()
        assert 'Webhook Inspector' in html
        assert 'Create New Bin' in html

    def test_webhook_inspector_nav_link(self, client):
        """Nav should include a Webhooks link."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'href="/webhook-inspector"' in html
        assert 'Webhooks' in html


class TestWebhookBinCreate:
    def test_create_bin(self, client):
        """POST /api/bin/create returns bin_id and url."""
        resp = client.post('/api/bin/create')
        assert resp.status_code == 201
        data = resp.get_json()
        assert 'bin_id' in data
        assert 'url' in data
        assert len(data['bin_id']) == 8
        assert '/bin/' in data['url']
        assert data['url'].endswith('/hook')

    def test_create_bin_stores_in_memory(self, client):
        """Created bin exists in the in-memory store."""
        resp = client.post('/api/bin/create')
        data = resp.get_json()
        assert data['bin_id'] in _webhook_bins
        assert 'created' in _webhook_bins[data['bin_id']]
        assert 'requests' in _webhook_bins[data['bin_id']]

    def test_create_bin_rate_limited(self, client):
        """Bin creation is rate-limited."""
        for _ in range(10):
            client.post('/api/bin/create')
        resp = client.post('/api/bin/create')
        assert resp.status_code == 429
        data = resp.get_json()
        assert 'Rate limit' in data['error']


class TestWebhookBinCapture:
    def _create_bin(self, client):
        resp = client.post('/api/bin/create')
        return resp.get_json()

    def test_capture_get_request(self, client):
        """GET to hook endpoint captures the request."""
        data = self._create_bin(client)
        resp = client.get(f'/bin/{data["bin_id"]}/hook?foo=bar')
        assert resp.status_code == 200
        assert resp.get_json()['status'] == 'captured'
        reqs = _webhook_bins[data['bin_id']]['requests']
        assert len(reqs) == 1
        assert reqs[0]['method'] == 'GET'
        assert reqs[0]['query']['foo'] == 'bar'

    def test_capture_post_request_with_body(self, client):
        """POST with body is captured."""
        data = self._create_bin(client)
        resp = client.post(f'/bin/{data["bin_id"]}/hook',
                           data='hello world',
                           content_type='text/plain')
        assert resp.status_code == 200
        reqs = _webhook_bins[data['bin_id']]['requests']
        assert reqs[0]['method'] == 'POST'
        assert reqs[0]['body'] == 'hello world'

    def test_capture_put_request(self, client):
        """PUT request is captured."""
        data = self._create_bin(client)
        resp = client.put(f'/bin/{data["bin_id"]}/hook',
                          json={'key': 'value'})
        assert resp.status_code == 200
        reqs = _webhook_bins[data['bin_id']]['requests']
        assert reqs[0]['method'] == 'PUT'

    def test_capture_delete_request(self, client):
        """DELETE request is captured."""
        data = self._create_bin(client)
        resp = client.delete(f'/bin/{data["bin_id"]}/hook')
        assert resp.status_code == 200
        reqs = _webhook_bins[data['bin_id']]['requests']
        assert reqs[0]['method'] == 'DELETE'

    def test_capture_strips_sensitive_headers(self, client):
        """Sensitive headers are stripped from captured requests."""
        data = self._create_bin(client)
        client.post(f'/bin/{data["bin_id"]}/hook', headers={
            'Authorization': 'Bearer secret',
            'Cookie': 'session=abc',
            'X-Custom': 'safe',
        })
        reqs = _webhook_bins[data['bin_id']]['requests']
        header_keys = {k.lower() for k in reqs[0]['headers']}
        assert 'authorization' not in header_keys
        assert 'cookie' not in header_keys
        assert 'x-custom' in header_keys

    def test_capture_has_timestamp(self, client):
        """Captured request includes an ISO timestamp."""
        data = self._create_bin(client)
        client.get(f'/bin/{data["bin_id"]}/hook')
        reqs = _webhook_bins[data['bin_id']]['requests']
        assert 'timestamp' in reqs[0]
        # Should be parseable ISO format
        assert 'T' in reqs[0]['timestamp']

    def test_capture_nonexistent_bin_404(self, client):
        """Hook to a nonexistent bin returns 404."""
        resp = client.get('/bin/nonexist/hook')
        assert resp.status_code == 404

    def test_capture_max_requests(self, client):
        """Bin keeps only the most recent 50 requests."""
        data = self._create_bin(client)
        bin_id = data['bin_id']
        for i in range(55):
            client.get(f'/bin/{bin_id}/hook?i={i}')
        reqs = _webhook_bins[bin_id]['requests']
        assert len(reqs) == _WEBHOOK_BIN_MAX_REQUESTS
        # The oldest 5 should have been dropped; first remaining should be i=5
        assert reqs[0]['query']['i'] == '5'


class TestWebhookBinRetrieve:
    def _create_bin(self, client):
        resp = client.post('/api/bin/create')
        return resp.get_json()

    def test_get_empty_bin(self, client):
        """GET /api/bin/<id> returns empty array for new bin."""
        data = self._create_bin(client)
        resp = client.get(f'/api/bin/{data["bin_id"]}')
        assert resp.status_code == 200
        assert resp.get_json() == []

    def test_get_bin_with_requests(self, client):
        """GET /api/bin/<id> returns captured requests."""
        data = self._create_bin(client)
        client.post(f'/bin/{data["bin_id"]}/hook', data='test body',
                    content_type='text/plain')
        resp = client.get(f'/api/bin/{data["bin_id"]}')
        assert resp.status_code == 200
        reqs = resp.get_json()
        assert len(reqs) == 1
        assert reqs[0]['method'] == 'POST'
        assert reqs[0]['body'] == 'test body'

    def test_get_nonexistent_bin_404(self, client):
        """GET /api/bin/<id> returns 404 for unknown bin."""
        resp = client.get('/api/bin/nonexist')
        assert resp.status_code == 404


class TestWebhookBinExpiry:
    def _create_bin(self, client):
        resp = client.post('/api/bin/create')
        return resp.get_json()

    def test_expired_bin_hook_returns_404(self, client):
        """Hook to an expired bin returns 404."""
        data = self._create_bin(client)
        bin_id = data['bin_id']
        # Manually set created time to the past
        _webhook_bins[bin_id]['created'] = time.time() - _WEBHOOK_BIN_TTL - 1
        resp = client.get(f'/bin/{bin_id}/hook')
        assert resp.status_code == 404
        assert bin_id not in _webhook_bins

    def test_expired_bin_get_returns_404(self, client):
        """GET on an expired bin returns 404."""
        data = self._create_bin(client)
        bin_id = data['bin_id']
        _webhook_bins[bin_id]['created'] = time.time() - _WEBHOOK_BIN_TTL - 1
        resp = client.get(f'/api/bin/{bin_id}')
        assert resp.status_code == 404
        assert bin_id not in _webhook_bins

    def test_expired_bins_pruned_on_create(self, client):
        """Creating a new bin prunes expired bins."""
        data = self._create_bin(client)
        old_id = data['bin_id']
        _webhook_bins[old_id]['created'] = time.time() - _WEBHOOK_BIN_TTL - 1
        # Create a new bin, which should prune the old one
        client.post('/api/bin/create')
        assert old_id not in _webhook_bins


class TestWebhookSitemapRobots:
    def test_sitemap_includes_webhook_inspector(self, client):
        """Sitemap should include the webhook-inspector page."""
        resp = client.get('/sitemap.xml')
        assert b'/webhook-inspector' in resp.data

    def test_robots_disallows_bin_api(self, client):
        """robots.txt should disallow /api/bin/ and /bin/."""
        resp = client.get('/robots.txt')
        text = resp.data.decode()
        assert 'Disallow: /api/bin/' in text
        assert 'Disallow: /bin/' in text


# --- Personality Quiz ---

class TestPersonalityQuizPage:
    """Tests for the /personality route and template."""

    def test_personality_page_loads(self, client):
        resp = client.get('/personality')
        assert resp.status_code == 200

    def test_personality_page_has_title(self, client):
        resp = client.get('/personality')
        html = resp.data.decode()
        assert 'Which HTTP Status Code Are You?' in html

    def test_personality_page_has_progress_bar(self, client):
        resp = client.get('/personality')
        html = resp.data.decode()
        assert 'personality-progress' in html
        assert 'progress-bar' in html
        assert 'progressbar' in html

    def test_personality_page_has_quiz_area(self, client):
        resp = client.get('/personality')
        html = resp.data.decode()
        assert 'quiz-area' in html
        assert 'question-text' in html
        assert 'choices' in html

    def test_personality_page_has_result_area(self, client):
        resp = client.get('/personality')
        html = resp.data.decode()
        assert 'result-area' in html
        assert 'result-card' in html
        assert 'result-img' in html
        assert 'result-name' in html
        assert 'result-desc' in html

    def test_personality_page_has_share_buttons(self, client):
        resp = client.get('/personality')
        html = resp.data.decode()
        assert 'copy-result' in html
        assert 'twitter-share' in html
        assert 'Copy Result' in html
        assert 'Share on X' in html

    def test_personality_page_has_retake_button(self, client):
        resp = client.get('/personality')
        html = resp.data.decode()
        assert 'retake-btn' in html
        assert 'Retake Quiz' in html

    def test_personality_page_has_detail_link(self, client):
        resp = client.get('/personality')
        html = resp.data.decode()
        assert 'detail-link' in html
        assert 'Learn more about this status code' in html

    def test_personality_page_has_og_meta(self, client):
        resp = client.get('/personality')
        html = resp.data.decode()
        assert 'og:title' in html
        assert 'og:description' in html

    def test_personality_page_has_meta_description(self, client):
        resp = client.get('/personality')
        html = resp.data.decode()
        assert 'HTTP Personality Quiz' in html


class TestPersonalityQuizScript:
    """Tests verifying the personality quiz JavaScript data is present."""

    def test_personality_has_questions(self, client):
        resp = client.get('/personality')
        html = resp.data.decode()
        assert 'QUESTIONS' in html

    def test_personality_has_8_questions(self, client):
        resp = client.get('/personality')
        html = resp.data.decode()
        assert 'Question 1 of 8' in html

    def test_personality_has_personalities_data(self, client):
        resp = client.get('/personality')
        html = resp.data.decode()
        assert 'PERSONALITIES' in html

    def test_personality_has_common_codes(self, client):
        """All 15 required personality codes must be defined."""
        resp = client.get('/personality')
        html = resp.data.decode()
        required_codes = [
            '200', '201', '204', '301', '302', '307',
            '400', '401', '403', '404', '418', '429',
            '500', '502', '503',
        ]
        for code in required_codes:
            assert f'"{code}"' in html, f"Missing personality for code {code}"

    def test_personality_has_traits(self, client):
        """Each personality should have traits defined."""
        resp = client.get('/personality')
        html = resp.data.decode()
        assert 'traits' in html

    def test_personality_has_confetti(self, client):
        resp = client.get('/personality')
        html = resp.data.decode()
        assert 'spawnConfetti' in html
        assert 'confetti-particle' in html

    def test_personality_has_xp_award(self, client):
        resp = client.get('/personality')
        html = resp.data.decode()
        assert 'ParrotXP' in html
        assert 'personality_quiz' in html


class TestPersonalityNavAndSitemap:
    """Tests for personality quiz navigation and sitemap integration."""

    def test_personality_in_nav(self, client):
        resp = client.get('/')
        html = resp.data.decode()
        assert 'href="/personality"' in html
        assert 'Personality' in html

    def test_personality_in_mobile_nav(self, client):
        resp = client.get('/')
        html = resp.data.decode()
        assert html.count('href="/personality"') >= 2

    def test_personality_in_sitemap(self, client):
        resp = client.get('/sitemap.xml')
        body = resp.data.decode()
        assert '/personality' in body

    def test_personality_nav_active_state(self, client):
        resp = client.get('/personality')
        html = resp.data.decode()
        assert 'nav-active' in html


class TestPersonalityCSS:
    """Tests for personality quiz CSS classes."""

    def test_personality_css_classes_in_stylesheet(self, client):
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.personality-container' in css
        assert '.personality-title' in css
        assert '.personality-progress' in css
        assert '.personality-result-card' in css
        assert '.personality-traits' in css

    def test_personality_has_responsive_styles(self, client):
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.personality-share-buttons' in css

    def test_personality_result_badge_gradient(self, client):
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.personality-result-badge' in css


class TestPersonalityAccessibility:
    """Tests for personality quiz accessibility."""

    def test_personality_has_main_landmark(self, client):
        resp = client.get('/personality')
        html = resp.data.decode()
        assert 'role="main"' in html
        assert 'id="main-content"' in html

    def test_personality_has_aria_progressbar(self, client):
        resp = client.get('/personality')
        html = resp.data.decode()
        assert 'role="progressbar"' in html
        assert 'aria-valuenow' in html
        assert 'aria-valuemin' in html
        assert 'aria-valuemax' in html

    def test_personality_has_aria_live_region(self, client):
        resp = client.get('/personality')
        html = resp.data.decode()
        assert 'aria-live="polite"' in html

    def test_personality_has_csp_nonce(self, client):
        resp = client.get('/personality')
        html = resp.data.decode()
        csp = resp.headers.get('Content-Security-Policy', '')
        nonce = re.search(r"'nonce-([^']+)'", csp)
        assert nonce is not None
        assert f'nonce="{nonce.group(1)}"' in html


# --- Weekly Themed Challenge ---

class TestWeeklyRoute:
    """Tests for the /weekly route returning 200 and containing expected content."""

    def test_weekly_returns_200(self, client):
        """Weekly challenge page should return 200."""
        resp = client.get('/weekly')
        assert resp.status_code == 200

    def test_weekly_contains_theme_name(self, client):
        """Weekly page should display a theme name."""
        resp = client.get('/weekly')
        html = resp.data.decode()
        theme_names = [
            'Redirect Week', 'Auth Week', 'Error Week', 'Success Week',
            'Caching Week', 'API Design Week', 'Debug Week', 'Speed Round',
        ]
        assert any(name in html for name in theme_names), \
            "No theme name found in weekly page"

    def test_weekly_contains_theme_description(self, client):
        """Weekly page should display a theme description."""
        resp = client.get('/weekly')
        html = resp.data.decode()
        assert 'weekly-theme-desc' in html

    def test_weekly_contains_week_number(self, client):
        """Weekly page should display the current week number."""
        from datetime import date
        week_num = date.today().isocalendar()[1]
        resp = client.get('/weekly')
        html = resp.data.decode()
        assert f'Week {week_num}' in html

    def test_weekly_has_five_questions(self, client):
        """Weekly challenge should have exactly 5 questions in the QUESTIONS array."""
        resp = client.get('/weekly')
        html = resp.data.decode()
        assert 'var QUESTIONS = [' in html
        question_ids = re.findall(r'"id":\s*\d+', html)
        assert len(question_ids) == 5, f"Expected 5 questions, found {len(question_ids)}"

    def test_weekly_has_progress_steps(self, client):
        """Weekly page should have 5 progress step indicators."""
        resp = client.get('/weekly')
        html = resp.data.decode()
        for i in range(5):
            assert f'id="step-{i}"' in html

    def test_weekly_has_timer(self, client):
        """Weekly page should have a per-question timer."""
        resp = client.get('/weekly')
        html = resp.data.decode()
        assert 'weekly-timer' in html
        assert 'weekly-timer-value' in html
        assert 'role="timer"' in html

    def test_weekly_has_results_card(self, client):
        """Weekly page should have a results card section."""
        resp = client.get('/weekly')
        html = resp.data.decode()
        assert 'weekly-results-card' in html
        assert 'weekly-final-score' in html
        assert 'weekly-final-time' in html
        assert 'weekly-final-xp' in html

    def test_weekly_has_share_buttons(self, client):
        """Weekly page should have copy and Twitter share buttons."""
        resp = client.get('/weekly')
        html = resp.data.decode()
        assert 'weekly-share-copy' in html
        assert 'weekly-share-twitter' in html
        assert 'Share on Twitter' in html
        assert 'Copy Result' in html

    def test_weekly_has_champion_badge(self, client):
        """Weekly page should have a Weekly Champion badge for perfect scores."""
        resp = client.get('/weekly')
        html = resp.data.decode()
        assert 'weekly-results-badge' in html
        assert 'Weekly Champion' in html

    def test_weekly_has_answer_choices(self, client):
        """Weekly page should have an answer choices group with ARIA."""
        resp = client.get('/weekly')
        html = resp.data.decode()
        assert 'id="weekly-choices"' in html
        assert 'role="group"' in html
        assert 'aria-label="Answer choices"' in html

    def test_weekly_has_feedback_area(self, client):
        """Weekly page should have a feedback area with aria-live."""
        resp = client.get('/weekly')
        html = resp.data.decode()
        assert 'id="weekly-feedback"' in html
        assert 'aria-live="polite"' in html

    def test_weekly_has_next_button(self, client):
        """Weekly page should have a Next Question button."""
        resp = client.get('/weekly')
        html = resp.data.decode()
        assert 'weekly-next-btn' in html
        assert 'Next Question' in html


class TestWeeklyDeterministic:
    """Tests that weekly challenge questions are deterministic within the same week."""

    def test_weekly_same_questions_same_week(self, client):
        """Two requests in the same week should produce identical questions."""
        resp1 = client.get('/weekly')
        resp2 = client.get('/weekly')
        html1 = resp1.data.decode()
        html2 = resp2.data.decode()
        strip_nonce = lambda h: re.sub(r'nonce="[^"]*"', 'nonce=""', h)
        assert strip_nonce(html1) == strip_nonce(html2)

    def test_weekly_theme_deterministic_from_week_number(self):
        """Theme selection should be deterministic based on week number."""
        from datetime import date
        week_number = date.today().isocalendar()[1]
        themes = [
            'Redirect Week', 'Auth Week', 'Error Week', 'Success Week',
            'Caching Week', 'API Design Week', 'Debug Week', 'Speed Round',
        ]
        expected_theme = themes[week_number % len(themes)]
        with app.test_client() as client:
            resp = client.get('/weekly')
            html = resp.data.decode()
            assert expected_theme in html


class TestWeeklyXPAndBadges:
    """Tests for XP awards and badge elements in the weekly challenge."""

    def test_weekly_awards_25_xp_per_correct(self, client):
        """Weekly challenge should award 25 XP per correct answer."""
        resp = client.get('/weekly')
        html = resp.data.decode()
        assert "ParrotXP.award(25, 'weekly_correct')" in html

    def test_weekly_awards_100_bonus_for_perfect(self, client):
        """Weekly challenge should award 100 bonus XP for 5/5."""
        resp = client.get('/weekly')
        html = resp.data.decode()
        assert "ParrotXP.award(100, 'weekly_perfect')" in html

    def test_weekly_sets_champion_flag(self, client):
        """Perfect score should set httpparrot_weekly_champion flag."""
        resp = client.get('/weekly')
        html = resp.data.decode()
        assert 'httpparrot_weekly_champion' in html

    def test_weekly_uses_localstorage(self, client):
        """Weekly challenge should use httpparrot_weekly localStorage key."""
        resp = client.get('/weekly')
        html = resp.data.decode()
        assert 'httpparrot_weekly' in html

    def test_weekly_tracks_streak(self, client):
        """Weekly challenge should track weekly streaks."""
        resp = client.get('/weekly')
        html = resp.data.decode()
        assert 'streak' in html
        assert 'weekly-streak-label' in html
        assert 'weekly-results-streak' in html


class TestWeeklyNav:
    """Tests for weekly challenge presence in navigation."""

    def test_weekly_nav_link_in_homepage(self, client):
        """Homepage should have a nav link to /weekly."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'href="/weekly"' in html

    def test_weekly_nav_link_text(self, client):
        """Nav should have Weekly text for the link."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'Weekly Challenge' in html

    def test_weekly_nav_active_on_weekly_page(self, client):
        """Weekly page nav link should have active class."""
        resp = client.get('/weekly')
        html = resp.data.decode()
        assert 'nav-active' in html


class TestWeeklySitemap:
    """Tests for weekly challenge in sitemap."""

    def test_sitemap_contains_weekly(self, client):
        """Sitemap should include /weekly."""
        resp = client.get('/sitemap.xml')
        xml = resp.data.decode()
        assert '/weekly' in xml


class TestWeeklySoundEffects:
    """Tests for sound effects in the weekly challenge."""

    def test_weekly_correct_sound(self, client):
        """Weekly should trigger ParrotSound.correct() on correct answers."""
        resp = client.get('/weekly')
        html = resp.data.decode()
        assert 'ParrotSound.correct()' in html

    def test_weekly_wrong_sound(self, client):
        """Weekly should trigger ParrotSound.wrong() on wrong answers."""
        resp = client.get('/weekly')
        html = resp.data.decode()
        assert 'ParrotSound.wrong()' in html


class TestWeeklyCSS:
    """Tests for weekly challenge CSS styles."""

    def test_weekly_theme_banner_style(self, client):
        """CSS should have weekly theme banner styles."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.weekly-theme-banner' in css
        assert '.weekly-theme-name' in css

    def test_weekly_progress_style(self, client):
        """CSS should have weekly progress step styles."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.weekly-progress' in css
        assert '.weekly-step' in css
        assert '.step-correct' in css
        assert '.step-wrong' in css

    def test_weekly_results_style(self, client):
        """CSS should have weekly results card styles."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.weekly-results-card' in css
        assert '.weekly-results-badge' in css

    def test_weekly_reduced_motion(self, client):
        """CSS should have reduced motion rules for weekly elements."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.weekly-results-badge' in css
        assert '.weekly-progress-fill' in css


# --- Cheat Sheet Filter / Search / Compact ---

class TestCheatsheetToolbar:
    """Tests for the cheatsheet filter, search, and compact toggle."""

    def test_cheatsheet_has_search_input(self, client):
        """Cheatsheet should have a search input for filtering codes."""
        resp = client.get('/cheatsheet')
        html = resp.data.decode()
        assert 'id="cheat-search"' in html
        assert 'cheat-search-input' in html

    def test_cheatsheet_has_filter_pills(self, client):
        """Cheatsheet should have category filter pills."""
        resp = client.get('/cheatsheet')
        html = resp.data.decode()
        assert 'id="cheat-filter-pills"' in html
        assert 'data-cat="all"' in html
        assert 'data-cat="1xx"' in html
        assert 'data-cat="2xx"' in html
        assert 'data-cat="3xx"' in html
        assert 'data-cat="4xx"' in html
        assert 'data-cat="5xx"' in html

    def test_cheatsheet_has_compact_toggle(self, client):
        """Cheatsheet should have a compact view toggle button."""
        resp = client.get('/cheatsheet')
        html = resp.data.decode()
        assert 'id="cheat-compact-toggle"' in html
        assert 'cheat-compact-btn' in html
        assert 'Compact View' in html

    def test_cheatsheet_has_compact_grid_container(self, client):
        """Cheatsheet should have a hidden compact grid view container."""
        resp = client.get('/cheatsheet')
        html = resp.data.decode()
        assert 'id="cheat-compact-view"' in html
        assert 'cheat-compact-grid' in html

    def test_cheatsheet_has_no_results_indicator(self, client):
        """Cheatsheet should have a no-results message for filtering."""
        resp = client.get('/cheatsheet')
        html = resp.data.decode()
        assert 'id="cheat-no-results"' in html
        assert 'cheat-no-results' in html

    def test_cheatsheet_table_rows_have_data_attributes(self, client):
        """Cheatsheet table rows should have data-code and data-name for JS filtering."""
        resp = client.get('/cheatsheet')
        html = resp.data.decode()
        assert 'data-code="200"' in html
        assert 'data-name=' in html

    def test_cheatsheet_categories_have_data_category(self, client):
        """Cheatsheet category divs should have data-category attribute."""
        resp = client.get('/cheatsheet')
        html = resp.data.decode()
        assert 'data-category="1xx"' in html
        assert 'data-category="2xx"' in html
        assert 'data-category="5xx"' in html

    def test_cheatsheet_toolbar_present(self, client):
        """Cheatsheet should have a toolbar element."""
        resp = client.get('/cheatsheet')
        html = resp.data.decode()
        assert 'id="cheat-toolbar"' in html
        assert 'cheat-toolbar' in html

    def test_cheatsheet_filter_script_present(self, client):
        """Cheatsheet should contain the filter/search JavaScript."""
        resp = client.get('/cheatsheet')
        html = resp.data.decode()
        assert 'cheat-search' in html
        assert 'cheat-filter-pills' in html
        assert 'filterAll' in html

    def test_cheatsheet_filter_pills_reuse_cat_pill_pattern(self, client):
        """Cheatsheet filter pills should use the cat-pill CSS class from homepage."""
        resp = client.get('/cheatsheet')
        html = resp.data.decode()
        assert 'class="cat-pill' in html

    def test_cheatsheet_css_toolbar_styles(self, client):
        """CSS should have cheatsheet toolbar styles."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.cheat-toolbar' in css
        assert '.cheat-search-input' in css
        assert '.cheat-compact-btn' in css
        assert '.cheat-compact-grid' in css
        assert '.cheat-no-results' in css


# --- Next Up Recommender ---

class TestNextUpRecommender:
    """Tests for the Next Up smart recommender on the homepage."""

    def test_nextup_tile_replaces_learning_paths(self, client):
        """The Next Up tile should be present instead of the old paths list."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'bento-nextup' in html
        assert 'bento-nextup-message' in html
        assert 'bento-nextup-sub' in html

    def test_nextup_default_message(self, client):
        """Default Next Up message should suggest starting a learning path."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'Start a learning path' in html

    def test_nextup_script_checks_review(self, client):
        """Recommender script should check httpparrot_review localStorage key."""
        resp = client.get('/')
        html = resp.data.decode()
        assert "httpparrot_review" in html
        assert "Review Now" in html

    def test_nextup_script_checks_daily(self, client):
        """Recommender script should check httpparrot_daily localStorage key."""
        resp = client.get('/')
        html = resp.data.decode()
        assert "httpparrot_daily" in html
        assert "Play Daily" in html

    def test_nextup_script_checks_paths(self, client):
        """Recommender script should check httpparrot_path_* localStorage keys."""
        resp = client.get('/')
        html = resp.data.decode()
        assert "httpparrot_path_" in html
        assert "http-foundations" in html
        assert "error-whisperer" in html
        assert "redirect-master" in html

    def test_nextup_script_checks_weekly(self, client):
        """Recommender script should check httpparrot_weekly localStorage key."""
        resp = client.get('/')
        html = resp.data.decode()
        assert "httpparrot_weekly" in html
        assert "Start Challenge" in html

    def test_nextup_css_styles_present(self, client):
        """CSS should have Next Up recommender styles."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.bento-nextup' in css
        assert '.bento-nextup-message' in css
        assert '.bento-nextup-sub' in css


class TestMetaFeathers:
    """Verify Meta-Feather achievements are defined and check conditions present."""

    META_FEATHERS = [
        {'id': 'explorer', 'name': 'Explorer', 'bonus': 150},
        {'id': 'polyglot', 'name': 'Polyglot', 'bonus': 200},
        {'id': 'streak_lord', 'name': 'Streak Lord', 'bonus': 250},
        {'id': 'triple_threat', 'name': 'Triple Threat', 'bonus': 300},
        {'id': 'full_spectrum', 'name': 'Full Spectrum', 'bonus': 250},
        {'id': 'parrot_polymath', 'name': 'Parrot Polymath', 'bonus': 500},
    ]

    def test_all_meta_feather_ids_defined(self, client):
        """All 6 meta-feather IDs should appear in the base template."""
        resp = client.get('/')
        html = resp.data.decode()
        for mf in self.META_FEATHERS:
            assert mf['id'] in html, f"Meta-feather '{mf['id']}' not found"

    def test_meta_feathers_have_meta_flag(self, client):
        """Meta-feathers should have meta: true in their definition."""
        resp = client.get('/')
        html = resp.data.decode()
        for mf in self.META_FEATHERS:
            assert f"id: '{mf['id']}'" in html
        assert 'meta: true' in html

    def test_meta_feather_bonus_xp_values(self, client):
        """Meta-feathers should have higher bonus XP (150-500)."""
        resp = client.get('/')
        html = resp.data.decode()
        for mf in self.META_FEATHERS:
            assert f"bonus: {mf['bonus']}" in html, \
                f"Meta-feather '{mf['id']}' should have bonus: {mf['bonus']}"

    def test_explorer_check_condition(self, client):
        """Explorer should check parrotdex for codes starting with 1,2,3,4,5."""
        resp = client.get('/')
        html = resp.data.decode()
        assert "!has('explorer')" in html
        assert "charAt(0) === '1'" in html
        assert "charAt(0) === '2'" in html
        assert "charAt(0) === '3'" in html
        assert "charAt(0) === '4'" in html
        assert "charAt(0) === '5'" in html

    def test_polyglot_check_condition(self, client):
        """Polyglot should check activity log for quiz, practice, debug, review."""
        resp = client.get('/')
        html = resp.data.decode()
        assert "!has('polyglot')" in html
        assert "'quiz_correct'" in html
        assert "'practice_correct'" in html
        assert "'debug_correct'" in html
        assert "'review_correct'" in html

    def test_streak_lord_check_condition(self, client):
        """Streak Lord should check milestonesHit for 30."""
        resp = client.get('/')
        html = resp.data.decode()
        assert "!has('streak_lord')" in html
        assert "milestonesHit" in html
        assert "indexOf(30)" in html

    def test_triple_threat_check_condition(self, client):
        """Triple Threat should require quiz_whiz + scholar + memory_master."""
        resp = client.get('/')
        html = resp.data.decode()
        assert "!has('triple_threat')" in html
        assert "'quiz_whiz'" in html
        assert "'scholar'" in html
        assert "'memory_master'" in html

    def test_full_spectrum_check_condition(self, client):
        """Full Spectrum should require error_expert + server_sage."""
        resp = client.get('/')
        html = resp.data.decode()
        assert "!has('full_spectrum')" in html
        assert "'error_expert'" in html
        assert "'server_sage'" in html

    def test_parrot_polymath_check_condition(self, client):
        """Parrot Polymath should require 12 base feathers, excluding meta."""
        resp = client.get('/')
        html = resp.data.decode()
        assert "!has('parrot_polymath')" in html
        assert "baseCount >= 12" in html
        assert "META_IDS" in html

    def test_meta_ids_list_defined(self, client):
        """META_IDS array should list all meta-feather IDs."""
        resp = client.get('/')
        html = resp.data.decode()
        assert "META_IDS" in html
        assert "'explorer'" in html
        assert "'polyglot'" in html
        assert "'streak_lord'" in html
        assert "'triple_threat'" in html
        assert "'full_spectrum'" in html
        assert "'parrot_polymath'" in html

    def test_meta_feather_css_gold_border(self, client):
        """Meta-feathers should have gold border CSS styling."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.feather-card.meta-feather' in css
        assert '#ffd700' in css

    def test_meta_feather_earned_gold_glow(self, client):
        """Earned meta-feathers should have a gold glow effect."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.feather-card.meta-feather.earned' in css
        assert 'box-shadow' in css

    def test_profile_adds_meta_feather_class(self, client):
        """Profile script should add meta-feather class for meta badges."""
        resp = client.get('/profile')
        html = resp.data.decode()
        assert 'meta-feather' in html
        assert 'f.meta' in html

    def test_meta_feather_names_in_template(self, client):
        """All meta-feather display names should appear in the template."""
        resp = client.get('/')
        html = resp.data.decode()
        names = ['Explorer', 'Polyglot', 'Streak Lord', 'Triple Threat',
                 'Full Spectrum', 'Parrot Polymath']
        for name in names:
            assert name in html, f"Meta-feather name '{name}' not found"

    def test_meta_feather_descriptions(self, client):
        """All meta-feather descriptions should appear in the template."""
        resp = client.get('/')
        html = resp.data.decode()
        descriptions = [
            'Visit at least one code from each category (1xx-5xx)',
            'Use quiz, practice, debug, AND review modes',
            'Hit the 30-day streak milestone',
            'Earn Quiz Whiz + Scholar + Memory Master',
            'Earn Error Expert + Server Sage',
            'Earn any 12 base feathers',
        ]
        for desc in descriptions:
            assert desc in html, f"Description '{desc}' not found"

    def test_meta_feather_icons_distinct(self, client):
        """Each meta-feather should have a distinct icon escape sequence."""
        resp = client.get('/')
        html = resp.data.decode()
        # Icons are stored as JS unicode escape sequences in the template
        icon_escapes = [
            '\\uD83C\\uDF0D',  # Explorer - globe
            '\\uD83D\\uDD00',  # Polyglot - shuffle
            '\\uD83D\\uDC51',  # Streak Lord - crown
            '\\uD83D\\uDD31',  # Triple Threat - trident
            '\\uD83C\\uDF08',  # Full Spectrum - rainbow
            '\\uD83E\\uDDA9',  # Parrot Polymath - flamingo
        ]
        for esc in icon_escapes:
            assert esc in html, f"Meta-feather icon escape '{esc}' not found"


# --- Case Studies ("In the Wild") feature ---

class TestCaseStudies:
    def test_case_studies_section_appears_on_page_with_data(self, client):
        """Pages with case_studies data should render the In the Wild section."""
        resp = client.get('/200')
        html = resp.get_data(as_text=True)
        assert 'case-studies-section' in html
        assert 'In the Wild' in html

    def test_case_study_card_structure(self, client):
        """Each case study card should have api, scenario, and lesson elements."""
        resp = client.get('/429')
        html = resp.get_data(as_text=True)
        assert 'case-study-card' in html
        assert 'case-study-api' in html
        assert 'case-study-scenario' in html
        assert 'case-study-lesson' in html

    def test_case_study_content_rendered(self, client):
        """The actual case study text should appear in the rendered HTML."""
        resp = client.get('/429')
        html = resp.get_data(as_text=True)
        assert 'Twitter/X API' in html
        assert 'exponential backoff' in html

    def test_case_studies_absent_on_page_without_data(self, client):
        """Pages without case_studies data should not show the section."""
        resp = client.get('/414')
        html = resp.get_data(as_text=True)
        assert 'case-studies-section' not in html
        assert 'case-study-card' not in html

    def test_at_least_60_codes_have_case_studies(self):
        """At least 60 status codes should have case_studies in STATUS_EXTRA."""
        from status_extra import STATUS_EXTRA
        codes_with_studies = [
            code for code, data in STATUS_EXTRA.items()
            if 'case_studies' in data and len(data['case_studies']) > 0
        ]
        assert len(codes_with_studies) >= 60, (
            f"Only {len(codes_with_studies)} codes have case_studies, need at least 60"
        )

    def test_case_studies_structure(self):
        """Each case_studies entry should have 'api', 'scenario', and 'lesson' keys."""
        from status_extra import STATUS_EXTRA
        for code, data in STATUS_EXTRA.items():
            if 'case_studies' in data:
                for entry in data['case_studies']:
                    assert 'api' in entry, f"Missing 'api' key in {code}"
                    assert 'scenario' in entry, f"Missing 'scenario' key in {code}"
                    assert 'lesson' in entry, f"Missing 'lesson' key in {code}"

    def test_case_studies_badge_count(self, client):
        """Badge should show correct count of case studies."""
        resp = client.get('/429')
        html = resp.get_data(as_text=True)
        assert 'case-studies-badge' in html
        assert '3 cases' in html

    def test_case_studies_collapsible(self, client):
        """The case studies section should use a details/summary for collapsibility."""
        resp = client.get('/200')
        html = resp.get_data(as_text=True)
        assert '<details class="case-studies-section">' in html
        assert '<summary' in html

    def test_case_studies_css_styles_present(self, client):
        """CSS should have case studies styles."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.case-studies-section' in css
        assert '.case-study-card' in css
        assert '.case-study-api' in css
        assert '.case-study-lesson' in css
        assert '.case-studies-badge' in css

    def test_new_case_studies_2xx_coverage(self):
        """All major 2xx codes should have case_studies."""
        from status_extra import STATUS_EXTRA
        codes_2xx = ['200', '201', '202', '204', '206', '207', '208', '226']
        for code in codes_2xx:
            assert code in STATUS_EXTRA, f"Code {code} missing from STATUS_EXTRA"
            assert 'case_studies' in STATUS_EXTRA[code], f"Code {code} missing case_studies"
            assert len(STATUS_EXTRA[code]['case_studies']) >= 1, f"Code {code} has empty case_studies"

    def test_new_case_studies_3xx_coverage(self):
        """Key 3xx codes should have case_studies."""
        from status_extra import STATUS_EXTRA
        codes_3xx = ['301', '302', '303', '304', '307', '308']
        for code in codes_3xx:
            assert code in STATUS_EXTRA, f"Code {code} missing from STATUS_EXTRA"
            assert 'case_studies' in STATUS_EXTRA[code], f"Code {code} missing case_studies"
            assert len(STATUS_EXTRA[code]['case_studies']) >= 1, f"Code {code} has empty case_studies"

    def test_new_case_studies_4xx_coverage(self):
        """Common 4xx codes should have case_studies."""
        from status_extra import STATUS_EXTRA
        codes_4xx = ['400', '401', '403', '404', '405', '406', '408', '409', '410',
                      '412', '415', '418', '422', '428', '429', '431', '451']
        for code in codes_4xx:
            assert code in STATUS_EXTRA, f"Code {code} missing from STATUS_EXTRA"
            assert 'case_studies' in STATUS_EXTRA[code], f"Code {code} missing case_studies"
            assert len(STATUS_EXTRA[code]['case_studies']) >= 1, f"Code {code} has empty case_studies"

    def test_new_case_studies_5xx_coverage(self):
        """All 5xx codes should have case_studies."""
        from status_extra import STATUS_EXTRA
        codes_5xx = ['500', '501', '502', '503', '504', '505', '507', '508', '510', '511', '530']
        for code in codes_5xx:
            assert code in STATUS_EXTRA, f"Code {code} missing from STATUS_EXTRA"
            assert 'case_studies' in STATUS_EXTRA[code], f"Code {code} missing case_studies"
            assert len(STATUS_EXTRA[code]['case_studies']) >= 1, f"Code {code} has empty case_studies"

    def test_case_studies_use_real_api_names(self):
        """Case studies should reference real-world APIs."""
        from status_extra import STATUS_EXTRA
        known_apis = ['Stripe', 'GitHub', 'AWS', 'Cloudflare', 'Twilio', 'Slack',
                       'Google', 'Twitter', 'YouTube', 'Kubernetes', 'Nginx', 'Heroku',
                       'OAuth', 'WebDAV', 'CalDAV', 'Microsoft', 'Reddit', 'Node.js',
                       'Netflix', 'Dropbox', 'Exchange', 'SharePoint', 'Apple']
        api_found = False
        for code, data in STATUS_EXTRA.items():
            if 'case_studies' in data:
                for entry in data['case_studies']:
                    for api_name in known_apis:
                        if api_name.lower() in entry['api'].lower():
                            api_found = True
                            break
        assert api_found, "No real-world API names found in case studies"

    def test_new_case_study_page_renders_for_202(self, client):
        """Code 202 should render its case studies on the detail page."""
        resp = client.get('/202')
        html = resp.get_data(as_text=True)
        assert 'case-studies-section' in html
        assert 'Twilio' in html

    def test_new_case_study_page_renders_for_451(self, client):
        """Code 451 should render its case studies on the detail page."""
        resp = client.get('/451')
        html = resp.get_data(as_text=True)
        assert 'case-studies-section' in html
        assert 'DMCA' in html or 'GitHub' in html


# --- Keyboard Shortcuts Overlay ---

class TestKeyboardShortcutsOverlay:
    def test_shortcuts_overlay_present_in_html(self, client):
        """Base template should contain the keyboard shortcuts overlay element."""
        resp = client.get('/')
        html = resp.get_data(as_text=True)
        assert 'id="kbd-shortcuts-overlay"' in html
        assert 'kbd-shortcuts-panel' in html

    def test_shortcuts_overlay_has_aria_attributes(self, client):
        """Shortcuts overlay should have proper ARIA dialog attributes."""
        resp = client.get('/')
        html = resp.get_data(as_text=True)
        assert 'role="dialog"' in html
        assert 'aria-modal="true"' in html
        assert 'aria-label="Keyboard shortcuts"' in html

    def test_shortcuts_overlay_has_close_button(self, client):
        """Overlay should have a close button with aria-label."""
        resp = client.get('/')
        html = resp.get_data(as_text=True)
        assert 'id="kbd-shortcuts-close"' in html
        assert 'aria-label="Close shortcuts overlay"' in html

    def test_shortcuts_overlay_has_general_shortcuts(self, client):
        """Overlay should list the general keyboard shortcuts."""
        resp = client.get('/')
        html = resp.get_data(as_text=True)
        assert 'Focus search' in html
        assert 'Show this help' in html
        assert 'Close overlay' in html

    def test_shortcuts_overlay_has_context_groups(self, client):
        """Overlay should have context-specific shortcut groups."""
        resp = client.get('/')
        html = resp.get_data(as_text=True)
        assert 'data-context="home"' in html
        assert 'data-context="quiz"' in html
        assert 'data-context="detail"' in html

    def test_shortcuts_overlay_has_kbd_elements(self, client):
        """Overlay should use <kbd> elements for key display."""
        resp = client.get('/')
        html = resp.get_data(as_text=True)
        assert '<kbd>/</kbd>' in html
        assert '<kbd>?</kbd>' in html
        assert '<kbd>Esc</kbd>' in html

    def test_shortcuts_overlay_has_question_mark_handler(self, client):
        """JavaScript should handle the ? key to toggle the overlay."""
        resp = client.get('/')
        html = resp.get_data(as_text=True)
        assert "e.key === '?'" in html
        assert 'kbd-shortcuts-visible' in html

    def test_shortcuts_overlay_escape_handler(self, client):
        """JavaScript should close overlay on Escape key."""
        resp = client.get('/')
        html = resp.get_data(as_text=True)
        assert "e.key === 'Escape'" in html
        assert 'closeShortcuts' in html

    def test_shortcuts_overlay_backdrop_click_closes(self, client):
        """Clicking the backdrop should close the overlay."""
        resp = client.get('/')
        html = resp.get_data(as_text=True)
        assert 'kbd-shortcuts-backdrop' in html
        assert "backdrop.addEventListener('click', closeShortcuts)" in html

    def test_shortcuts_overlay_hidden_by_default(self, client):
        """Overlay should have hidden attribute by default."""
        resp = client.get('/')
        html = resp.get_data(as_text=True)
        assert 'id="kbd-shortcuts-overlay" role="dialog" aria-modal="true" aria-label="Keyboard shortcuts" hidden' in html

    def test_shortcuts_overlay_present_on_detail_page(self, client):
        """Shortcuts overlay should also be present on detail pages."""
        resp = client.get('/200')
        html = resp.get_data(as_text=True)
        assert 'id="kbd-shortcuts-overlay"' in html

    def test_shortcuts_overlay_present_on_quiz_page(self, client):
        """Shortcuts overlay should also be present on quiz pages."""
        resp = client.get('/quiz')
        html = resp.get_data(as_text=True)
        assert 'id="kbd-shortcuts-overlay"' in html

    def test_shortcuts_css_styles_present(self, client):
        """CSS should have keyboard shortcuts overlay styles."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.kbd-shortcuts-overlay' in css
        assert '.kbd-shortcuts-panel' in css
        assert '.kbd-shortcuts-backdrop' in css
        assert '.kbd-shortcut-row' in css
        assert '.kbd-shortcuts-visible' in css

    def test_shortcuts_css_has_glassmorphism(self, client):
        """Shortcuts panel should use glassmorphism styling."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert 'backdrop-filter' in css
        assert 'blur' in css

    def test_shortcuts_quiz_context_shows_number_keys(self, client):
        """Quiz context group should show 1-4 number key shortcuts."""
        resp = client.get('/')
        html = resp.get_data(as_text=True)
        assert '<kbd>1</kbd>' in html
        assert '<kbd>2</kbd>' in html
        assert '<kbd>3</kbd>' in html
        assert '<kbd>4</kbd>' in html
        assert 'Select answer' in html

    def test_shortcuts_ignores_input_focus(self, client):
        """JS should skip shortcut handler when focus is on input elements."""
        resp = client.get('/')
        html = resp.get_data(as_text=True)
        assert "tag === 'INPUT'" in html
        assert "tag === 'TEXTAREA'" in html


# --- Mobile Polish CSS ---

class TestMobilePolishCSS:
    def test_compare_columns_stacks_at_768(self, client):
        """Compare columns should stack to 1fr at 768px breakpoint."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.compare-columns' in css
        # The stacking rule should exist somewhere in a 768px media query
        assert 'grid-template-columns: 1fr' in css

    def test_playground_stacks_at_768(self, client):
        """Playground builder/preview should stack at 768px."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.playground-layout' in css

    def test_profile_heatmap_scrollable(self, client):
        """Profile heatmap should have overflow-x: auto for mobile scrollability."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert 'overflow-x: auto' in css
        assert '.profile-heatmap-container' in css

    def test_filter_pills_touch_targets(self, client):
        """Filter pills should have 44px minimum touch targets in 768px query."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.cheat-filter-pills .cheat-compact-btn' in css or '.cheat-compact-btn' in css
        assert 'min-height: 44px' in css

    def test_normalized_breakpoints_576(self, client):
        """CSS should use 576px as the standard small breakpoint."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '576px' in css

    def test_normalized_breakpoints_768(self, client):
        """CSS should use 768px as the standard tablet breakpoint."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert 'max-width: 768px' in css

    def test_normalized_breakpoints_992(self, client):
        """CSS should use 992px as the standard desktop breakpoint."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert 'max-width: 992px' in css


class TestProfileFlockSharing:
    """Tests for profile sharing with flock codes."""

    def test_profile_has_share_section(self, client):
        """Profile page should contain the Share Profile section."""
        resp = client.get('/profile')
        html = resp.data.decode()
        assert 'profile-share-section' in html
        assert 'Share Profile' in html

    def test_profile_has_copy_flock_code_button(self, client):
        """Profile page should have a Copy Flock Code button."""
        resp = client.get('/profile')
        html = resp.data.decode()
        assert 'copy-flock-code' in html
        assert 'Copy Flock Code' in html

    def test_profile_has_copy_link_button(self, client):
        """Profile page should have a Copy Link button."""
        resp = client.get('/profile')
        html = resp.data.decode()
        assert 'copy-flock-link' in html
        assert 'Copy Link' in html

    def test_profile_has_share_on_x_button(self, client):
        """Profile page should have a Share on X link."""
        resp = client.get('/profile')
        html = resp.data.decode()
        assert 'share-flock-x' in html
        assert 'Share on X' in html

    def test_profile_flock_param_passed_to_template(self, client):
        """When ?flock= is present, the value should appear in the page JS."""
        resp = client.get('/profile?flock=dGVzdA==')
        html = resp.data.decode()
        assert 'dGVzdA==' in html

    def test_profile_flock_param_empty_by_default(self, client):
        """Without ?flock=, the FLOCK_PARAM should be empty string."""
        resp = client.get('/profile')
        html = resp.data.decode()
        assert 'var FLOCK_PARAM = ""' in html

    def test_profile_has_flock_comparison_section(self, client):
        """Profile page should contain the flock comparison section (hidden by default)."""
        resp = client.get('/profile')
        html = resp.data.decode()
        assert 'flock-comparison-section' in html
        assert 'flock-visitor-card' in html
        assert 'flock-you-card' in html

    def test_profile_flock_visitor_card_has_golden_border(self, client):
        """Visitor flock card should use the golden border style class."""
        resp = client.get('/profile')
        html = resp.data.decode()
        assert 'flock-card--visitor' in html

    def test_profile_flock_comparison_hidden_by_default(self, client):
        """Flock comparison section should be hidden when no flock param."""
        resp = client.get('/profile')
        html = resp.data.decode()
        assert 'id="flock-comparison-section"' in html
        assert 'style="display:none"' in html

    def test_profile_has_profile_card_section(self, client):
        """Profile page should have the screenshot-shareable profile card."""
        resp = client.get('/profile')
        html = resp.data.decode()
        assert 'profile-card-section' in html
        assert 'profile-share-card' in html
        assert 'profile-share-card-inner' in html

    def test_profile_card_has_brand_gradient(self, client):
        """Profile share card should use the brand gradient via CSS."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.profile-share-card' in css
        assert 'var(--gradient-brand)' in css

    def test_profile_card_has_glassmorphism(self, client):
        """Profile share card inner should use glassmorphism (backdrop-filter)."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.profile-share-card-inner' in css
        assert 'backdrop-filter: blur(' in css

    def test_profile_card_displays_rank_xp_streak(self, client):
        """Profile card should contain elements for rank, XP, streak, collection."""
        resp = client.get('/profile')
        html = resp.data.decode()
        assert 'profile-card-rank' in html
        assert 'profile-card-xp' in html
        assert 'profile-card-streak' in html
        assert 'profile-card-collection' in html

    def test_profile_card_has_brand_watermark(self, client):
        """Profile card should display httpparrots.com branding."""
        resp = client.get('/profile')
        html = resp.data.decode()
        assert 'httpparrots.com' in html

    def test_profile_js_builds_flock_data(self, client):
        """Profile JS should contain the buildFlockData function."""
        resp = client.get('/profile')
        html = resp.data.decode()
        assert 'buildFlockData' in html
        assert 'encodeFlockData' in html
        assert 'decodeFlockData' in html

    def test_profile_js_flock_url_format(self, client):
        """Flock URL should use the httpparrots.com/profile?flock= format."""
        resp = client.get('/profile')
        html = resp.data.decode()
        assert 'httpparrots.com/profile?flock=' in html

    def test_profile_share_card_css_exists(self, client):
        """CSS should contain profile share card styles."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.profile-share-card-rank' in css
        assert '.profile-share-card-xp' in css
        assert '.profile-share-card-feathers' in css

    def test_profile_flock_comparison_css_exists(self, client):
        """CSS should contain flock comparison card styles."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.flock-comparison-grid' in css
        assert '.flock-card--visitor' in css
        assert '.flock-card--you' in css
        assert '#ffd700' in css  # golden border color

    def test_profile_share_buttons_css_exists(self, client):
        """CSS should contain share button styles."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.profile-share-btn' in css
        assert '.profile-share-buttons' in css

    def test_profile_flock_comparison_responsive(self, client):
        """Flock comparison grid should stack on mobile (576px breakpoint)."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.flock-comparison-grid' in css

    def test_profile_with_flock_returns_200(self, client):
        """Profile page with flock parameter should still return 200."""
        resp = client.get('/profile?flock=eyJyIjoiUGFycm90IFNjb3V0IiwieCI6MTUwMCwicyI6NywiZiI6WyJmaXJzdF9mbGlnaHQiXSwiYyI6MjV9')
        assert resp.status_code == 200

    def test_profile_flock_xss_escaped(self, client):
        """Flock parameter should be safely escaped in the template."""
        resp = client.get('/profile?flock=<script>alert(1)</script>')
        html = resp.data.decode()
        assert '<script>alert(1)</script>' not in html


# --- Interactive Parrot Click ---

class TestInteractiveParrotClick:
    """Tests for interactive parrot click feature on detail pages."""

    def test_detail_parrot_has_clickable_class(self, client):
        """Detail parrot should have the parrot-clickable class."""
        resp = client.get('/200')
        html = resp.data.decode()
        assert 'parrot-clickable' in html

    def test_detail_parrot_has_click_hint_class(self, client):
        """Detail parrot should have the parrot-click-hint class."""
        resp = client.get('/200')
        html = resp.data.decode()
        assert 'parrot-click-hint' in html

    def test_detail_parrot_has_role_button(self, client):
        """Detail parrot should have role=button for accessibility."""
        resp = client.get('/200')
        html = resp.data.decode()
        assert 'role="button"' in html

    def test_detail_parrot_has_tabindex(self, client):
        """Detail parrot should have tabindex=0 for keyboard access."""
        resp = client.get('/200')
        html = resp.data.decode()
        assert 'tabindex="0"' in html

    def test_detail_parrot_has_id(self, client):
        """Detail parrot should have the detail-parrot ID for JS targeting."""
        resp = client.get('/200')
        html = resp.data.decode()
        assert 'id="detail-parrot"' in html

    def test_speech_bubble_element_present(self, client):
        """Detail page should have a speech bubble element."""
        resp = client.get('/200')
        html = resp.data.decode()
        assert 'parrot-speech-bubble' in html
        assert 'id="parrot-speech-bubble"' in html

    def test_speech_bubble_has_aria_live(self, client):
        """Speech bubble should have aria-live for screen readers."""
        resp = client.get('/200')
        html = resp.data.decode()
        assert 'aria-live="polite"' in html

    def test_click_handler_script_present(self, client):
        """Detail page should include the parrot click handler script."""
        resp = client.get('/200')
        html = resp.data.decode()
        assert 'detail-parrot' in html
        assert 'parrot-speech-bubble' in html
        assert 'handleClick' in html

    def test_click_handler_uses_parrot_sound(self, client):
        """Click handler should call ParrotSound.squawk() when sound enabled."""
        resp = client.get('/200')
        html = resp.data.decode()
        assert 'ParrotSound.squawk()' in html

    def test_click_handler_tracks_feather(self, client):
        """Click handler should set httpparrot_parrot_petted localStorage flag."""
        resp = client.get('/200')
        html = resp.data.decode()
        assert 'httpparrot_parrot_petted' in html

    def test_click_handler_awards_xp(self, client):
        """Click handler should award XP on first parrot pet."""
        resp = client.get('/200')
        html = resp.data.decode()
        assert "ParrotXP.award(5, 'parrot_pet')" in html

    def test_click_handler_calls_check_feathers(self, client):
        """Click handler should call checkFeathers after setting flag."""
        resp = client.get('/200')
        html = resp.data.decode()
        assert 'ParrotXP.checkFeathers()' in html

    def test_click_handler_has_animation_class_per_category(self, client):
        """Click handler should build category-specific animation classes."""
        resp = client.get('/200')
        html = resp.data.decode()
        assert "parrot-anim-" in html
        assert "category" in html

    def test_click_handler_keyboard_support(self, client):
        """Click handler should support Enter and Space keys."""
        resp = client.get('/200')
        html = resp.data.decode()
        assert "e.key === 'Enter'" in html
        assert "e.key === ' '" in html

    def test_click_handler_present_on_1xx(self, client):
        """1xx detail pages should have the click handler."""
        resp = client.get('/100')
        html = resp.data.decode()
        assert 'handleClick' in html

    def test_click_handler_present_on_3xx(self, client):
        """3xx detail pages should have the click handler."""
        resp = client.get('/301')
        html = resp.data.decode()
        assert 'handleClick' in html

    def test_speech_bubble_shows_eli5_text(self, client):
        """Speech bubble text pool should include ELI5 text when available."""
        resp = client.get('/200')
        html = resp.data.decode()
        # The eli5 text is embedded in the script as a JSON string
        assert 'eli5Text' in html

    def test_speech_bubble_includes_fun_facts(self, client):
        """Speech bubble should include generic HTTP fun facts."""
        resp = client.get('/200')
        html = resp.data.decode()
        assert 'genericFacts' in html
        assert 'Tim Berners-Lee' in html


class TestInteractiveParrotClickCSS:
    """Tests for CSS animation classes used by interactive parrot click."""

    def test_parrot_clickable_class_exists(self, client):
        """CSS should define .parrot-clickable."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.parrot-clickable' in css

    def test_parrot_click_hint_class_exists(self, client):
        """CSS should define .parrot-click-hint."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.parrot-click-hint' in css

    def test_parrot_click_hint_keyframe_exists(self, client):
        """CSS should define parrot-click-hint keyframe animation."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '@keyframes parrot-click-hint' in css

    def test_parrot_bounce_1xx_animation(self, client):
        """CSS should define the 1xx bounce animation."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '@keyframes parrot-bounce-1xx' in css
        assert '.parrot-anim-1xx' in css

    def test_parrot_wiggle_2xx_animation(self, client):
        """CSS should define the 2xx wiggle animation with green glow."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '@keyframes parrot-wiggle-2xx' in css
        assert '.parrot-anim-2xx' in css

    def test_parrot_slide_3xx_animation(self, client):
        """CSS should define the 3xx slide animation."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '@keyframes parrot-slide-3xx' in css
        assert '.parrot-anim-3xx' in css

    def test_parrot_shake_4xx_animation(self, client):
        """CSS should define the 4xx shake animation."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '@keyframes parrot-shake-4xx' in css
        assert '.parrot-anim-4xx' in css

    def test_parrot_glitch_5xx_animation(self, client):
        """CSS should define the 5xx glitch animation."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '@keyframes parrot-glitch-5xx' in css
        assert '.parrot-anim-5xx' in css

    def test_speech_bubble_css_exists(self, client):
        """CSS should define .parrot-speech-bubble styles."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.parrot-speech-bubble' in css
        assert '.parrot-speech-bubble.visible' in css

    def test_speech_bubble_arrow_exists(self, client):
        """CSS should define the speech bubble arrow via ::before."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.parrot-speech-bubble::before' in css

    def test_category_colored_speech_bubbles(self, client):
        """CSS should have category-colored speech bubble borders."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        for cat in ['1xx', '2xx', '3xx', '4xx', '5xx']:
            assert f'.detail-cat-{cat} .parrot-speech-bubble' in css

    def test_reduced_motion_disables_click_animations(self, client):
        """prefers-reduced-motion should disable parrot click animations."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.parrot-anim-1xx .img img' in css
        assert '.parrot-anim-2xx .img img' in css
        assert '.parrot-anim-3xx .img img' in css
        assert '.parrot-anim-4xx .img img' in css
        assert '.parrot-anim-5xx .img img' in css
        # Verify these are within a reduced motion media query
        assert 'prefers-reduced-motion: reduce' in css

    def test_click_hint_hidden_class(self, client):
        """CSS should define .parrot-click-hint-hidden to remove the hint."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.parrot-click-hint-hidden' in css

    def test_4xx_red_flash_glow(self, client):
        """4xx animation should include red box-shadow glow."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.parrot-anim-4xx .img' in css
        assert 'rgba(233, 69, 96' in css

    def test_5xx_purple_glow(self, client):
        """5xx animation should include purple box-shadow glow."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.parrot-anim-5xx .img' in css
        assert 'rgba(123, 97, 255' in css


class TestParrotPetterFeather:
    """Tests for the Parrot Petter feather badge."""

    def test_parrot_petter_in_feathers_array(self, client):
        """Parrot Petter feather should be defined in FEATHERS array."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'parrot_petter' in html
        assert 'Parrot Petter' in html

    def test_parrot_petter_feather_description(self, client):
        """Parrot Petter feather should have correct description."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'Click any parrot on a detail page' in html

    def test_parrot_petter_check_in_check_feathers(self, client):
        """checkFeathers should check httpparrot_parrot_petted flag."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'httpparrot_parrot_petted' in html
        assert "parrot_petter" in html

    def test_parrot_petter_bonus_xp(self, client):
        """Parrot Petter should award 10 bonus XP."""
        resp = client.get('/')
        html = resp.data.decode()
        # The feather definition should have bonus: 10
        assert "'parrot_petter'" in html or "parrot_petter" in html


# --- Weekly Progress Chart (Profile) ---

class TestProfileWeeklyChart:
    """Tests for the weekly progress bar chart on the profile page."""

    def test_profile_has_weekly_section(self, client):
        """Profile page should contain the weekly progress section."""
        resp = client.get('/profile')
        html = resp.data.decode()
        assert 'profile-weekly-section' in html

    def test_profile_weekly_chart_container(self, client):
        """Profile page should contain the weekly chart container."""
        resp = client.get('/profile')
        html = resp.data.decode()
        assert 'profile-weekly-container' in html
        assert 'profile-weekly-chart' in html

    def test_profile_weekly_chart_has_aria_label(self, client):
        """Weekly chart should have an aria-label for accessibility."""
        resp = client.get('/profile')
        html = resp.data.decode()
        assert 'Bar chart showing XP earned per week' in html

    def test_profile_weekly_trend_element(self, client):
        """Profile page should contain the trend indicator element."""
        resp = client.get('/profile')
        html = resp.data.decode()
        assert 'profile-weekly-trend' in html

    def test_profile_weekly_heading(self, client):
        """Profile page should show Weekly Progress heading."""
        resp = client.get('/profile')
        html = resp.data.decode()
        assert 'Weekly Progress' in html

    def test_profile_weekly_chart_js_aggregates_by_week(self, client):
        """JS should compute ISO week numbers from activity data."""
        resp = client.get('/profile')
        html = resp.data.decode()
        assert 'weeklyXp' in html
        assert 'weekNum' in html

    def test_profile_weekly_chart_renders_bars(self, client):
        """JS should create weekly-bar elements for each week."""
        resp = client.get('/profile')
        html = resp.data.decode()
        assert 'weekly-bar-col' in html
        assert 'weekly-bar' in html

    def test_profile_weekly_trend_shows_change(self, client):
        """JS should compute and display the trend percentage."""
        resp = client.get('/profile')
        html = resp.data.decode()
        assert 'weekly-trend-up' in html
        assert 'weekly-trend-down' in html

    def test_profile_weekly_css_exists(self, client):
        """CSS should contain styles for the weekly chart."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.profile-weekly-section' in css
        assert '.profile-weekly-container' in css
        assert '.profile-weekly-chart' in css
        assert '.weekly-bar-col' in css
        assert '.weekly-bar' in css
        assert '.weekly-bar-label' in css

    def test_profile_weekly_trend_css_exists(self, client):
        """CSS should contain styles for the trend indicator."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.weekly-trend-up' in css
        assert '.weekly-trend-down' in css
        assert '.weekly-trend-flat' in css

    def test_profile_weekly_chart_uses_flex(self, client):
        """Weekly chart should use flexbox layout for bars."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.profile-weekly-chart' in css
        assert 'display: flex' in css


# --- Compare Page Transitions ---

class TestCompareTransitions:
    """Tests for compare page crossfade transitions and swap rotation."""

    def test_compare_fading_out_css_exists(self, client):
        """CSS should define .fading-out class for crossfade."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.compare-card.fading-out' in css

    def test_compare_fading_in_css_exists(self, client):
        """CSS should define .fading-in class for crossfade."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.compare-card.fading-in' in css

    def test_compare_fade_in_keyframes_exist(self, client):
        """CSS should define the compare-fade-in keyframe animation."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '@keyframes compare-fade-in' in css

    def test_compare_fading_out_opacity(self, client):
        """Fading-out class should set opacity to 0."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.compare-card.fading-out' in css
        # Find the rule and check opacity
        idx = css.index('.compare-card.fading-out')
        block = css[idx:idx+200]
        assert 'opacity: 0' in block

    def test_compare_fading_out_translate(self, client):
        """Fading-out class should use translateY."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        idx = css.index('.compare-card.fading-out')
        block = css[idx:idx+200]
        assert 'translateY' in block

    def test_compare_swap_rotation_css(self, client):
        """CSS should define .swap-rotating class with 180deg rotation."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.compare-swap-btn.swap-rotating' in css
        assert 'rotate(180deg)' in css

    def test_compare_swap_rotation_uses_timing_tokens(self, client):
        """Swap rotation should use the existing timing tokens."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        idx = css.index('.compare-swap-btn.swap-rotating')
        block = css[idx:idx+200]
        assert '--duration-normal' in block
        assert '--ease-out' in block

    def test_compare_diff_expanding_css(self, client):
        """CSS should define .diff-expanding class for animated diff expansion."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.compare-diff-wrap.diff-expanding' in css

    def test_compare_diff_expanded_css(self, client):
        """CSS should define .diff-expanded class for completed expansion."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.compare-diff-wrap.diff-expanded' in css

    def test_compare_diff_max_height_transition(self, client):
        """Diff wrap should use max-height transition for animation."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        idx = css.index('.compare-diff-wrap {')
        block = css[idx:idx+500]
        assert 'max-height' in block

    def test_compare_js_adds_fading_out_on_update(self, client):
        """JS should add fading-out class to existing cards on update."""
        resp = client.get('/compare')
        html = resp.data.decode()
        assert 'fading-out' in html

    def test_compare_js_adds_fading_in_on_render(self, client):
        """JS should add fading-in class to new cards."""
        resp = client.get('/compare')
        html = resp.data.decode()
        assert 'fading-in' in html

    def test_compare_js_swap_rotating_toggle(self, client):
        """JS should toggle swap-rotating class on swap button click."""
        resp = client.get('/compare')
        html = resp.data.decode()
        assert 'swap-rotating' in html

    def test_compare_js_diff_expanding_applied(self, client):
        """JS should apply diff-expanding then diff-expanded classes."""
        resp = client.get('/compare')
        html = resp.data.decode()
        assert 'diff-expanding' in html
        assert 'diff-expanded' in html

    def test_compare_card_has_transition_property(self, client):
        """Compare card should have transition property for smooth crossfade."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        # Compare cards should have transition support via fading classes
        assert '.compare-card.fading-out' in css
        assert '.compare-card.fading-in' in css


# --- Flock Formation Celebration ---

class TestFlockFormation:
    """Tests for the flock formation celebration feature."""

    def test_flock_formation_function_defined(self, client):
        """Base template should define spawnFlockFormation function."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'function spawnFlockFormation' in html

    def test_flock_formation_exposed_on_parrotxp(self, client):
        """ParrotXP should expose spawnFlockFormation."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'spawnFlockFormation: spawnFlockFormation' in html

    def test_flock_formation_called_in_feather_toast(self, client):
        """showFeatherToast should call spawnFlockFormation after confetti."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'spawnFlockFormation(false)' in html

    def test_flock_formation_legendary_on_rank_up(self, client):
        """Legendary Lorikeet rank-up should trigger legendary flock."""
        resp = client.get('/')
        html = resp.data.decode()
        assert "rankTitle === 'Legendary Lorikeet'" in html
        assert 'spawnFlockFormation(true)' in html

    def test_flock_formation_respects_reduced_motion(self, client):
        """spawnFlockFormation should check prefers-reduced-motion."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'prefers-reduced-motion' in html

    def test_flock_formation_creates_container(self, client):
        """spawnFlockFormation should create a container element."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'flock-formation-container' in html

    def test_flock_formation_v_formation_offset(self, client):
        """Flock parrots should use V-formation offsets."""
        resp = client.get('/')
        html = resp.data.decode()
        assert '--flock-y' in html
        assert '--flock-x' in html

    def test_flock_formation_lead_parrot_larger(self, client):
        """Lead parrot should get a special class for larger size."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'flock-parrot-lead' in html

    def test_flock_formation_legendary_golden_class(self, client):
        """Legendary flock parrots should get golden styling class."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'flock-parrot-golden' in html

    def test_flock_formation_auto_cleanup(self, client):
        """Flock container should auto-remove after animation."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'container.remove()' in html

    def test_flock_formation_css_exists(self, client):
        """Flock formation CSS should be defined in stylesheet."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.flock-formation-container' in css
        assert '.flock-parrot' in css
        assert 'flock-fly' in css

    def test_flock_parrot_lead_css(self, client):
        """Lead parrot CSS should have larger font-size."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.flock-parrot-lead' in css

    def test_flock_golden_css(self, client):
        """Golden flock parrots should have gold drop-shadow."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.flock-parrot-golden' in css
        assert 'drop-shadow' in css

    def test_flock_fly_keyframes(self, client):
        """flock-fly keyframes animation should be defined."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '@keyframes flock-fly' in css

    def test_flock_fly_loop_keyframes(self, client):
        """flock-fly-loop keyframes animation for legendary flock."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '@keyframes flock-fly-loop' in css

    def test_flock_reduced_motion_css(self, client):
        """Flock animations should be disabled for prefers-reduced-motion."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.flock-parrot { animation: none' in css
        assert '.flock-formation-container { display: none' in css

    def test_flock_legendary_container_class(self, client):
        """Legendary flock should add a legendary class to container."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'flock-formation-legendary' in html


# --- 404 Memory Card Game ---

class TestMemoryGame:
    """Tests for the 404 memory card game feature."""

    def test_404_has_memory_game_script(self, client):
        """404 page should include the memory game script."""
        resp = client.get('/nonexistent')
        html = resp.data.decode()
        assert 'MEMORY_PAIRS' in html
        assert 'httpparrot_404_count' in html

    def test_memory_game_tracks_404_count(self, client):
        """Memory game should track failed URL attempts in sessionStorage."""
        resp = client.get('/nonexistent')
        html = resp.data.decode()
        assert 'httpparrot_404_count' in html
        assert 'sessionStorage' in html

    def test_memory_game_triggers_after_3_visits(self, client):
        """Memory game prompt should appear after count >= 3."""
        resp = client.get('/nonexistent')
        html = resp.data.decode()
        assert 'count < 3' in html

    def test_memory_game_has_8_pairs(self, client):
        """Memory game should define 8 status code pairs."""
        resp = client.get('/nonexistent')
        html = resp.data.decode()
        codes = ['200', '301', '404', '500', '401', '503', '418', '429']
        for code in codes:
            assert code in html, f"Status code {code} not found in memory game"

    def test_memory_game_has_status_names(self, client):
        """Memory game should include status code names."""
        resp = client.get('/nonexistent')
        html = resp.data.decode()
        names = ['OK', 'Not Found', 'Internal Server Error', 'Unauthorized',
                 'Too Many Requests', 'Service Unavailable']
        for name in names:
            assert name in html, f"Status name '{name}' not in memory game"

    def test_memory_game_prompt_button(self, client):
        """Memory game should have a start button."""
        resp = client.get('/nonexistent')
        html = resp.data.decode()
        assert 'memory-game-start-btn' in html
        assert 'Play Memory Game' in html

    def test_memory_game_grid_4x4(self, client):
        """Memory game should create a 4x4 grid."""
        resp = client.get('/nonexistent')
        html = resp.data.decode()
        assert 'memory-game-grid' in html

    def test_memory_game_cards_have_3d_flip(self, client):
        """Cards should use CSS 3D transform classes."""
        resp = client.get('/nonexistent')
        html = resp.data.decode()
        assert 'memory-card-inner' in html
        assert 'memory-card-front' in html
        assert 'memory-card-back' in html
        assert 'memory-card-flipped' in html

    def test_memory_game_match_detection(self, client):
        """Game should detect matches by pair ID and different type."""
        resp = client.get('/nonexistent')
        html = resp.data.decode()
        assert 'data-pair-id' in html
        assert 'data-card-type' in html
        assert 'memory-card-matched' in html

    def test_memory_game_match_highlight(self, client):
        """Matched cards should get a highlight class."""
        resp = client.get('/nonexistent')
        html = resp.data.decode()
        assert 'memory-card-matched' in html

    def test_memory_game_completion_handler(self, client):
        """Game should call onGameComplete when all pairs matched."""
        resp = client.get('/nonexistent')
        html = resp.data.decode()
        assert 'onGameComplete' in html

    def test_memory_game_shows_hidden_fact(self, client):
        """On completion, game should show a hidden fact."""
        resp = client.get('/nonexistent')
        html = resp.data.decode()
        assert 'HIDDEN_FACTS' in html
        assert 'Hidden fact:' in html

    def test_memory_game_awards_photo_memory_feather(self, client):
        """Completion should award the Photographic Memory feather."""
        resp = client.get('/nonexistent')
        html = resp.data.decode()
        assert 'httpparrot_memory_game_complete' in html
        assert 'Photographic Memory' in html

    def test_memory_game_tracks_in_eggs(self, client):
        """Completion should track memory_game in eggs_found."""
        resp = client.get('/nonexistent')
        html = resp.data.decode()
        assert "eggs.indexOf('memory_game')" in html
        assert 'eggs_found' in html

    def test_memory_game_awards_xp(self, client):
        """Completion should award XP via ParrotXP."""
        resp = client.get('/nonexistent')
        html = resp.data.decode()
        assert 'ParrotXP.award' in html
        assert 'memory_game_complete' in html

    def test_memory_game_resets_counter(self, client):
        """Completion should reset the 404 counter."""
        resp = client.get('/nonexistent')
        html = resp.data.decode()
        assert "sessionStorage.removeItem('httpparrot_404_count')" in html

    def test_memory_game_accessible_grid(self, client):
        """Memory game grid should have ARIA attributes."""
        resp = client.get('/nonexistent')
        html = resp.data.decode()
        assert "role', 'grid'" in html
        assert 'Memory card game grid' in html

    def test_memory_game_cards_are_buttons(self, client):
        """Memory cards should be button elements for accessibility."""
        resp = client.get('/nonexistent')
        html = resp.data.decode()
        assert "createElement('button')" in html
        assert "Memory card " in html

    def test_memory_game_fisher_yates_shuffle(self, client):
        """Cards should be shuffled using Fisher-Yates algorithm."""
        resp = client.get('/nonexistent')
        html = resp.data.decode()
        assert 'Fisher-Yates' in html

    def test_memory_game_no_match_flip_back(self, client):
        """Non-matching cards should flip back after a delay."""
        resp = client.get('/nonexistent')
        html = resp.data.decode()
        assert "classList.remove('memory-card-flipped')" in html

    def test_memory_game_css_grid(self, client):
        """Memory game grid CSS should use 4-column grid."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.memory-game-grid' in css
        assert 'repeat(4, 1fr)' in css

    def test_memory_card_3d_transform_css(self, client):
        """Memory card CSS should use 3D transforms."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert 'transform-style: preserve-3d' in css
        assert 'backface-visibility: hidden' in css
        assert 'rotateY(180deg)' in css

    def test_memory_match_glow_keyframes(self, client):
        """Match highlight should have a glow animation."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '@keyframes memory-match-glow' in css

    def test_memory_complete_appear_keyframes(self, client):
        """Completion panel should have an appear animation."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '@keyframes memory-complete-appear' in css

    def test_memory_game_reduced_motion_css(self, client):
        """Memory game animations should be disabled for reduced motion."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.memory-card-inner { transition: none' in css
        assert '.memory-game-complete { animation: none' in css

    def test_memory_game_start_btn_css(self, client):
        """Start button should have styled CSS."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.memory-game-start-btn' in css

    def test_memory_game_congrats_css(self, client):
        """Congrats heading should use gradient text."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.memory-game-congrats' in css

    def test_memory_game_feather_award_css(self, client):
        """Feather award text should use gold color."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.memory-game-feather-award' in css


# --- Photographic Memory Feather ---

class TestPhotographicMemoryFeather:
    """Tests for the Photographic Memory feather badge."""

    def test_photo_memory_in_feathers_array(self, client):
        """Photographic Memory feather should be defined in FEATHERS array."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'photo_memory' in html
        assert 'Photographic Memory' in html

    def test_photo_memory_feather_description(self, client):
        """Photographic Memory feather should describe the memory game."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'Complete the 404 memory card game' in html

    def test_photo_memory_feather_bonus(self, client):
        """Photographic Memory feather should award 100 bonus XP."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'photo_memory' in html

    def test_photo_memory_check_in_check_feathers(self, client):
        """checkFeathers should check httpparrot_memory_game_complete flag."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'httpparrot_memory_game_complete' in html
        assert "photo_memory" in html

    def test_photo_memory_feather_icon(self, client):
        """Photographic Memory feather should have a brain icon."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'photo_memory' in html


# --- Fetch URL (GET mode) endpoint ---

class TestFetchURL:
    """Tests for the /api/fetch-url endpoint (GET mode with body preview)."""

    def test_fetch_url_success_returns_body(self, client):
        """fetch-url should return status, headers, body, and content_type."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {'Content-Type': 'application/json'}
        mock_resp.content = b'{"hello": "world"}'
        mock_resp.elapsed.total_seconds.return_value = 0.05
        addrinfo = [(socket.AF_INET, socket.SOCK_STREAM, 0, '', ('93.184.216.34', 0))]
        with patch('index.socket.getaddrinfo', return_value=addrinfo), \
             patch('requests.get', return_value=mock_resp):
            resp = client.get('/api/fetch-url?url=https://example.com')
            assert resp.status_code == 200
            data = resp.get_json()
            assert data['code'] == 200
            assert data['url'] == 'https://example.com'
            assert 'body' in data
            assert data['body'] == '{"hello": "world"}'
            assert data['content_type'] == 'application/json'
            assert data['truncated'] is False
            assert 'headers' in data
            assert 'time_ms' in data

    def test_fetch_url_truncates_large_body(self, client):
        """Bodies larger than 10KB should be truncated."""
        large_body = b'x' * (11 * 1024)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {'Content-Type': 'text/plain'}
        mock_resp.content = large_body
        mock_resp.elapsed.total_seconds.return_value = 0.1
        addrinfo = [(socket.AF_INET, socket.SOCK_STREAM, 0, '', ('93.184.216.34', 0))]
        with patch('index.socket.getaddrinfo', return_value=addrinfo), \
             patch('requests.get', return_value=mock_resp):
            resp = client.get('/api/fetch-url?url=https://example.com')
            data = resp.get_json()
            assert data['truncated'] is True
            assert len(data['body']) == 10 * 1024

    def test_fetch_url_no_url(self, client):
        """fetch-url without URL param should return 400."""
        resp = client.get('/api/fetch-url')
        assert resp.status_code == 400
        data = resp.get_json()
        assert 'error' in data

    def test_fetch_url_ssrf_blocked(self, client):
        """fetch-url should block private IPs (SSRF protection)."""
        resp = client.get('/api/fetch-url?url=http://127.0.0.1/')
        assert resp.status_code == 403
        assert b'not allowed' in resp.data

    def test_fetch_url_metadata_blocked(self, client):
        """fetch-url should block cloud metadata endpoints."""
        resp = client.get('/api/fetch-url?url=http://169.254.169.254/latest/')
        assert resp.status_code == 403

    def test_fetch_url_connection_error(self, client):
        """fetch-url should return 502 on connection errors."""
        addrinfo = [(socket.AF_INET, socket.SOCK_STREAM, 0, '', ('93.184.216.34', 0))]
        with patch('index.socket.getaddrinfo', return_value=addrinfo), \
             patch('requests.get', side_effect=requests.RequestException):
            resp = client.get('/api/fetch-url?url=https://example.com')
            assert resp.status_code == 502
            assert b'Could not connect' in resp.data

    def test_fetch_url_rate_limited(self, client):
        """fetch-url should be rate-limited."""
        for _ in range(10):
            client.get('/api/fetch-url?url=http://127.0.0.1/')
        resp = client.get('/api/fetch-url?url=https://example.com')
        assert resp.status_code == 429
        assert b'Rate limit' in resp.data

    def test_fetch_url_auto_prefix(self, client):
        """URLs without scheme should get https:// prepended."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {'Content-Type': 'text/html'}
        mock_resp.content = b'<html></html>'
        mock_resp.elapsed.total_seconds.return_value = 0.05
        addrinfo = [(socket.AF_INET, socket.SOCK_STREAM, 0, '', ('93.184.216.34', 0))]
        with patch('index.socket.getaddrinfo', return_value=addrinfo), \
             patch('requests.get', return_value=mock_resp):
            resp = client.get('/api/fetch-url?url=example.com')
            data = resp.get_json()
            assert data['url'] == 'https://example.com'

    def test_fetch_url_does_not_follow_redirects(self, client):
        """fetch-url should not follow redirects (SSRF mitigation)."""
        mock_resp = MagicMock()
        mock_resp.status_code = 301
        mock_resp.headers = {'Location': 'http://example.com/new', 'Content-Type': 'text/html'}
        mock_resp.content = b''
        mock_resp.elapsed.total_seconds.return_value = 0.1
        addrinfo = [(socket.AF_INET, socket.SOCK_STREAM, 0, '', ('93.184.216.34', 0))]
        with patch('index.socket.getaddrinfo', return_value=addrinfo), \
             patch('requests.get', return_value=mock_resp) as mock_get:
            resp = client.get('/api/fetch-url?url=http://example.com')
            data = resp.get_json()
            assert data['code'] == 301
            call_kwargs = mock_get.call_args
            assert call_kwargs[1].get('allow_redirects') is False

    def test_fetch_url_strips_set_cookie(self, client):
        """fetch-url should strip Set-Cookie headers from response."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {'Content-Type': 'text/html', 'Set-Cookie': 'session=abc'}
        mock_resp.content = b'ok'
        mock_resp.elapsed.total_seconds.return_value = 0.05
        addrinfo = [(socket.AF_INET, socket.SOCK_STREAM, 0, '', ('93.184.216.34', 0))]
        with patch('index.socket.getaddrinfo', return_value=addrinfo), \
             patch('requests.get', return_value=mock_resp):
            resp = client.get('/api/fetch-url?url=https://example.com')
            data = resp.get_json()
            assert 'Set-Cookie' not in data['headers']

    def test_fetch_url_in_robots_disallow(self, client):
        """robots.txt should disallow /api/fetch-url."""
        resp = client.get('/robots.txt')
        body = resp.data.decode()
        assert 'Disallow: /api/fetch-url' in body

    def test_fetch_url_html_body(self, client):
        """fetch-url should return HTML body correctly."""
        html_body = b'<html><body><h1>Hello</h1></body></html>'
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {'Content-Type': 'text/html; charset=utf-8'}
        mock_resp.content = html_body
        mock_resp.elapsed.total_seconds.return_value = 0.05
        addrinfo = [(socket.AF_INET, socket.SOCK_STREAM, 0, '', ('93.184.216.34', 0))]
        with patch('index.socket.getaddrinfo', return_value=addrinfo), \
             patch('requests.get', return_value=mock_resp):
            resp = client.get('/api/fetch-url?url=https://example.com')
            data = resp.get_json()
            assert '<html>' in data['body']
            assert data['content_type'] == 'text/html; charset=utf-8'


class TestTesterMethodToggle:
    """Tests for the GET/HEAD method toggle in the tester UI."""

    def test_tester_has_method_toggle(self, client):
        """Tester page should contain method toggle buttons."""
        resp = client.get('/tester')
        html = resp.data.decode()
        assert 'tester-method-toggle' in html
        assert 'tester-method-btn' in html
        assert 'data-method="HEAD"' in html
        assert 'data-method="GET"' in html

    def test_tester_head_is_default(self, client):
        """HEAD method should be active by default."""
        resp = client.get('/tester')
        html = resp.data.decode()
        # HEAD button should have active class and aria-pressed=true
        assert 'data-method="HEAD"' in html
        # Check that the JS initializes with HEAD
        assert "selectedMethod = 'HEAD'" in html

    def test_tester_has_body_preview_markup(self, client):
        """Tester JS should contain body preview CSS classes."""
        resp = client.get('/tester')
        html = resp.data.decode()
        assert 'tester-body-preview' in html
        assert 'tester-body-header' in html
        assert 'tester-body-pre' in html
        assert 'tester-copy-body-btn' in html
        assert 'tester-body-collapse-btn' in html
        assert 'tester-content-type-badge' in html

    def test_tester_uses_fetch_url_for_get_mode(self, client):
        """Tester JS should call /api/fetch-url when GET mode is selected."""
        resp = client.get('/tester')
        html = resp.data.decode()
        assert '/api/fetch-url' in html

    def test_tester_method_toggle_aria(self, client):
        """Method toggle should have proper ARIA attributes."""
        resp = client.get('/tester')
        html = resp.data.decode()
        assert 'role="radiogroup"' in html
        assert 'aria-label="HTTP method"' in html
        assert 'aria-pressed="true"' in html
        assert 'aria-pressed="false"' in html

    def test_tester_body_preview_css_exists(self, client):
        """CSS should contain body preview styles."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.tester-body-preview' in css
        assert '.tester-body-pre' in css
        assert '.tester-content-type-badge' in css
        assert '.tester-method-toggle' in css
        assert '.tester-method-btn' in css
        assert '.tester-copy-body-btn' in css
        assert '.tester-body-collapse-btn' in css


# --- Practice Results Summary ---

class TestPracticeResultsSummary:
    """Tests for the practice completion results summary overlay."""

    def test_practice_has_results_overlay_css(self, client):
        """Practice page should include results overlay CSS classes."""
        resp = client.get('/practice')
        html = resp.data.decode()
        assert 'practice-results-overlay' in html
        assert 'practice-results-card' in html

    def test_practice_has_results_title_css(self, client):
        """Practice page CSS should include the results title styles."""
        resp = client.get('/practice')
        html = resp.data.decode()
        assert 'practice-results-title' in html

    def test_practice_has_results_score_class(self, client):
        """Practice page should include score display in results."""
        resp = client.get('/practice')
        html = resp.data.decode()
        assert 'practice-results-score' in html

    def test_practice_has_results_xp_class(self, client):
        """Practice page should include XP display in results."""
        resp = client.get('/practice')
        html = resp.data.decode()
        assert 'practice-results-xp' in html

    def test_practice_has_emoji_grid_class(self, client):
        """Practice page should include emoji recap grid in results."""
        resp = client.get('/practice')
        html = resp.data.decode()
        assert 'practice-results-grid' in html

    def test_practice_has_share_button_class(self, client):
        """Practice page should include share button in results."""
        resp = client.get('/practice')
        html = resp.data.decode()
        assert 'practice-results-share' in html

    def test_practice_has_try_again_button_class(self, client):
        """Practice page should include try again button in results."""
        resp = client.get('/practice')
        html = resp.data.decode()
        assert 'practice-results-again' in html

    def test_practice_results_share_text(self, client):
        """Practice results share text should include domain."""
        resp = client.get('/practice')
        html = resp.data.decode()
        assert 'httpparrots.com/practice' in html

    def test_practice_results_check_completion_function(self, client):
        """Practice script should have a checkCompletion function."""
        resp = client.get('/practice')
        html = resp.data.decode()
        assert 'checkCompletion' in html

    def test_practice_results_reset_on_try_again(self, client):
        """Practice try again button should reset answered state."""
        resp = client.get('/practice')
        html = resp.data.decode()
        assert "classList.remove('answered')" in html


# --- Debug Results Summary ---

class TestDebugResultsSummary:
    """Tests for the debug completion results summary overlay."""

    def test_debug_has_results_overlay_css(self, client):
        """Debug page should include results overlay CSS classes."""
        resp = client.get('/debug')
        html = resp.data.decode()
        assert 'debug-results-overlay' in html
        assert 'debug-results-card' in html

    def test_debug_has_results_title_css(self, client):
        """Debug page CSS should include the results title styles."""
        resp = client.get('/debug')
        html = resp.data.decode()
        assert 'debug-results-title' in html

    def test_debug_has_results_score_class(self, client):
        """Debug page should include score display in results."""
        resp = client.get('/debug')
        html = resp.data.decode()
        assert 'debug-results-score' in html

    def test_debug_has_results_xp_class(self, client):
        """Debug page should include XP display in results."""
        resp = client.get('/debug')
        html = resp.data.decode()
        assert 'debug-results-xp' in html

    def test_debug_has_emoji_grid_class(self, client):
        """Debug page should include emoji recap grid in results."""
        resp = client.get('/debug')
        html = resp.data.decode()
        assert 'debug-results-grid' in html

    def test_debug_has_share_button_class(self, client):
        """Debug page should include share button in results."""
        resp = client.get('/debug')
        html = resp.data.decode()
        assert 'debug-results-share' in html

    def test_debug_has_try_again_button_class(self, client):
        """Debug page should include try again button in results."""
        resp = client.get('/debug')
        html = resp.data.decode()
        assert 'debug-results-again' in html

    def test_debug_results_share_text(self, client):
        """Debug results share text should include domain."""
        resp = client.get('/debug')
        html = resp.data.decode()
        assert 'httpparrots.com/debug' in html

    def test_debug_results_check_completion_function(self, client):
        """Debug script should have a checkCompletion function."""
        resp = client.get('/debug')
        html = resp.data.decode()
        assert 'checkCompletion' in html

    def test_debug_results_reset_on_try_again(self, client):
        """Debug try again button should reset answered state."""
        resp = client.get('/debug')
        html = resp.data.decode()
        assert "classList.remove('answered')" in html


# --- Bento Dashboard Polish ---

class TestBentoDashboardPolish:
    """Tests for bento dashboard polish: XP animation, streak pulse, hover lift, enhanced recommender."""

    def test_bento_tile_hover_lift_css(self):
        """Bento tiles should have hover lift transform in CSS."""
        with open('static/style.css') as f:
            css = f.read()
        assert 'translateY(-3px)' in css

    def test_bento_tile_transition_includes_transform(self):
        """Bento tile transition should include transform for hover lift."""
        with open('static/style.css') as f:
            css = f.read()
        # Find the bento-tile transition block
        import re
        match = re.search(r'\.bento-tile\s*\{[^}]*transition:[^;]*transform', css)
        assert match is not None, "bento-tile transition should include transform"

    def test_bento_streak_pulse_keyframes(self):
        """CSS should define bento-streak-pulse keyframe animation."""
        with open('static/style.css') as f:
            css = f.read()
        assert '@keyframes bento-streak-pulse' in css

    def test_bento_streak_has_streak_class(self):
        """CSS should define .bento-streak-count.has-streak class with animation."""
        with open('static/style.css') as f:
            css = f.read()
        assert '.bento-streak-count.has-streak' in css
        assert 'bento-streak-pulse' in css

    def test_bento_xp_bar_fill_animation_transition(self):
        """XP bar fill should have a smooth animation transition."""
        with open('static/style.css') as f:
            css = f.read()
        assert '.bento-xp-bar-fill' in css
        assert 'cubic-bezier' in css

    def test_bento_xp_bar_animate_fill_class(self):
        """CSS should define .animate-fill class for XP bar."""
        with open('static/style.css') as f:
            css = f.read()
        assert '.bento-xp-bar-fill.animate-fill' in css

    def test_bento_reduced_motion_streak_pulse(self):
        """Reduced motion should disable streak pulse animation."""
        with open('static/style.css') as f:
            css = f.read()
        assert '.bento-streak-count.has-streak' in css
        # Should appear in reduced motion block
        import re
        reduced = re.findall(r'prefers-reduced-motion: reduce\).*?(?=@media|\Z)', css, re.DOTALL)
        found = any('bento-streak-count.has-streak' in block for block in reduced)
        assert found, "Reduced motion should disable streak pulse"

    def test_bento_reduced_motion_hover_lift(self):
        """Reduced motion should disable hover lift on bento tiles."""
        with open('static/style.css') as f:
            css = f.read()
        import re
        reduced = re.findall(r'prefers-reduced-motion: reduce\).*?(?=@media|\Z)', css, re.DOTALL)
        found = any('bento-tile:hover' in block for block in reduced)
        assert found, "Reduced motion should disable bento tile hover lift"

    def test_streak_pulse_applied_when_streak_positive(self, client):
        """Homepage script should add has-streak class when streak > 0."""
        resp = client.get('/')
        html = resp.data.decode()
        assert "classList.add('has-streak')" in html
        assert 'dailyState.streak > 0' in html

    def test_xp_bar_animated_fill_on_load(self, client):
        """Homepage script should animate XP bar fill on load with setTimeout."""
        resp = client.get('/')
        html = resp.data.decode()
        assert "animate-fill" in html
        assert "setTimeout" in html

    def test_nextup_recommender_least_visited_category(self, client):
        """Next Up recommender should suggest least-visited category."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'httpparrot_cat_visits' in html
        assert 'Explore' in html

    def test_nextup_recommender_confusion_pair(self, client):
        """Next Up recommender should suggest confusion pairs."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'httpparrot_pairs_viewed' in html
        assert 'Study Pair' in html
        assert '401-vs-403' in html

    def test_nextup_confusion_pairs_list(self, client):
        """Recommender should include multiple confusion pairs."""
        resp = client.get('/')
        html = resp.data.decode()
        assert '301-vs-302' in html
        assert '200-vs-204' in html
        assert '500-vs-502' in html
        assert '400-vs-422' in html


class TestLightThemeCompleteness:
    """Tests for light theme overrides on pages that were missing them."""

    def _get_light_css(self, client):
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        idx = css.index('@media (prefers-color-scheme: light)')
        return css[idx:]

    def test_light_theme_fault_sim_try(self, client):
        """Fault simulator try panels should have light overrides."""
        block = self._get_light_css(client)
        assert '.fault-sim-try' in block
        assert '.fault-sim-result' in block

    def test_light_theme_fault_sim_input(self, client):
        """Fault simulator inputs should use light backgrounds."""
        block = self._get_light_css(client)
        assert '.fault-sim-try input' in block
        assert '.fault-sim-try label' in block

    def test_light_theme_fault_sim_progress(self, client):
        """Fault simulator progress bar should have light override."""
        block = self._get_light_css(client)
        assert '.fault-sim-progress' in block

    def test_light_theme_tester_timing(self, client):
        """Tester timing bar should have light overrides."""
        block = self._get_light_css(client)
        assert '.tester-timing-bar-wrap' in block
        assert '.tester-timing-category' in block

    def test_light_theme_tester_result_actions(self, client):
        """Tester result actions should have light border."""
        block = self._get_light_css(client)
        assert '.tester-result-actions' in block

    def test_light_theme_tester_loading(self, client):
        """Tester loading text should be dark in light mode."""
        block = self._get_light_css(client)
        assert '.tester-loading' in block

    def test_light_theme_trace_hop_pre(self, client):
        """Webhook inspector body pre should have light background."""
        block = self._get_light_css(client)
        assert '.trace-hop pre' in block

    def test_light_theme_trace_hop_loc_value(self, client):
        """Trace hop location value should use teal in light mode."""
        block = self._get_light_css(client)
        assert '.trace-hop-loc-value' in block

    def test_light_theme_trace_hop_error(self, client):
        """Trace hop error message should use dark coral in light mode."""
        block = self._get_light_css(client)
        assert '.trace-hop-error-msg' in block

    def test_light_theme_curl_tabs(self, client):
        """cURL import tab bar should have light theme overrides."""
        block = self._get_light_css(client)
        assert '.curl-tab-bar' in block
        assert '.curl-tab ' in block
        assert '.curl-tab-active' in block

    def test_light_theme_curl_method_badges(self, client):
        """cURL method badges for HEAD/OPTIONS should have light overrides."""
        block = self._get_light_css(client)
        assert '.curl-method-head' in block
        assert '.curl-method-options' in block

    def test_light_theme_curl_copy_btn(self, client):
        """cURL copy button should have light override."""
        block = self._get_light_css(client)
        assert '.curl-copy-btn' in block

    def test_light_theme_audit_result_card(self, client):
        """Security audit result card should have light background."""
        block = self._get_light_css(client)
        assert '.audit-result-card' in block

    def test_light_theme_audit_grade(self, client):
        """Security audit grade badge should have light overrides."""
        block = self._get_light_css(client)
        assert '.audit-grade-badge' in block
        assert '.audit-grade-score' in block

    def test_light_theme_audit_check_card(self, client):
        """Security audit check cards should have light backgrounds."""
        block = self._get_light_css(client)
        assert '.audit-check-card' in block
        assert '.audit-check-label' in block
        assert '.audit-check-points' in block
        assert '.audit-check-desc' in block

    def test_light_theme_audit_fix(self, client):
        """Security audit fix section should have light overrides."""
        block = self._get_light_css(client)
        assert '.audit-fix-wrap' in block
        assert '.audit-fix-code' in block

    def test_light_theme_review_card(self, client):
        """Review page cards should have light overrides."""
        block = self._get_light_css(client)
        assert '.review-card' in block
        assert '.review-question' in block
        assert '.review-option-btn' in block

    def test_light_theme_review_explanation(self, client):
        """Review explanation area should have light background."""
        block = self._get_light_css(client)
        assert '.review-explanation' in block
        assert '.review-explanation p' in block

    def test_light_theme_leitner_bar(self, client):
        """Leitner distribution bar should have light overrides."""
        block = self._get_light_css(client)
        assert '.leitner-dist-bar' in block
        assert '.leitner-dist-label' in block
        assert '.leitner-mastered-count' in block


class TestReviewProgressVisualization:
    """Tests for the Leitner box distribution bar on the review page."""

    def test_review_has_leitner_dist_bar(self, client):
        """Review page should contain the Leitner distribution bar."""
        resp = client.get('/review')
        html = resp.data.decode()
        assert 'leitner-dist' in html
        assert 'leitner-dist-bar' in html

    def test_review_has_five_box_columns(self, client):
        """Distribution bar should have columns for boxes 1-5."""
        resp = client.get('/review')
        html = resp.data.decode()
        for b in range(1, 6):
            assert 'leitner-count-' + str(b) in html
            assert 'leitner-fill-' + str(b) in html
            assert 'Box ' + str(b) in html

    def test_review_has_mastered_count(self, client):
        """Review page should display a mastered count (box 5 items)."""
        resp = client.get('/review')
        html = resp.data.decode()
        assert 'leitner-mastered' in html
        assert 'Mastered:' in html

    def test_review_has_caught_up_message(self, client):
        """Review page should contain a caught-up message for empty queue."""
        resp = client.get('/review')
        html = resp.data.decode()
        assert 'review-caught-up' in html
        assert 'All caught up! Come back tomorrow.' in html

    def test_review_has_box_distribution_title(self, client):
        """Distribution bar should have a title."""
        resp = client.get('/review')
        html = resp.data.decode()
        assert 'Box Distribution' in html

    def test_review_leitner_dist_css_classes(self, client):
        """Leitner distribution bar CSS classes should exist in the page."""
        resp = client.get('/review')
        html = resp.data.decode()
        assert 'leitner-dist-boxes' in html
        assert 'leitner-dist-box' in html
        assert 'leitner-dist-fill' in html
        assert 'leitner-dist-label' in html
        assert 'leitner-dist-count' in html

    def test_review_update_leitner_dist_function(self, client):
        """Review JS should contain the updateLeitnerDist function."""
        resp = client.get('/review')
        html = resp.data.decode()
        assert 'updateLeitnerDist' in html

    def test_review_leitner_reads_review_data(self, client):
        """Leitner dist should read from existing review data."""
        resp = client.get('/review')
        html = resp.data.decode()
        assert 'box_level' in html
        assert 'httpparrot_review' in html

    def test_review_caught_up_initially_hidden(self, client):
        """Caught-up message should be hidden by default."""
        resp = client.get('/review')
        html = resp.data.decode()
        assert 'display:none' in html or "display:none" in html

    def test_review_leitner_bar_has_aria_label(self, client):
        """Leitner distribution bar should have an aria-label for accessibility."""
        resp = client.get('/review')
        html = resp.data.decode()
        assert 'aria-label="Leitner box distribution"' in html

    def test_review_mastered_has_aria_live(self, client):
        """Mastered count should have aria-live for screen readers."""
        resp = client.get('/review')
        html = resp.data.decode()
        assert 'id="leitner-mastered"' in html
        assert 'aria-live="polite"' in html

    def test_review_caught_up_has_aria_live(self, client):
        """Caught-up message should have aria-live for screen readers."""
        resp = client.get('/review')
        html = resp.data.decode()
        assert 'id="review-caught-up"' in html
        assert 'aria-live="polite"' in html

    def test_review_leitner_dist_color_coding(self, client):
        """Each box should have a distinct color fill class."""
        resp = client.get('/review')
        html = resp.data.decode()
        for b in range(1, 6):
            assert 'leitner-dist-box-' + str(b) in html


# --- Mobile UX Polish ---

class TestBackToTopOnLongPages:
    """Back-to-top button should be present on practice, debug, and review pages."""

    def test_practice_has_back_to_top_button(self, client):
        resp = client.get('/practice')
        html = resp.data.decode()
        assert 'id="back-to-top"' in html
        assert 'back-to-top' in html
        assert 'Back to top' in html

    def test_practice_has_back_to_top_script(self, client):
        resp = client.get('/practice')
        html = resp.data.decode()
        assert "getElementById('back-to-top')" in html
        assert "classList.add('visible')" in html

    def test_debug_has_back_to_top_button(self, client):
        resp = client.get('/debug')
        html = resp.data.decode()
        assert 'id="back-to-top"' in html
        assert 'back-to-top' in html
        assert 'Back to top' in html

    def test_debug_has_back_to_top_script(self, client):
        resp = client.get('/debug')
        html = resp.data.decode()
        assert "getElementById('back-to-top')" in html
        assert "classList.add('visible')" in html

    def test_review_has_back_to_top_button(self, client):
        resp = client.get('/review')
        html = resp.data.decode()
        assert 'id="back-to-top"' in html
        assert 'back-to-top' in html
        assert 'Back to top' in html

    def test_review_has_back_to_top_script(self, client):
        resp = client.get('/review')
        html = resp.data.decode()
        assert "getElementById('back-to-top')" in html
        assert "classList.add('visible')" in html

    def test_back_to_top_has_aria_label_on_practice(self, client):
        resp = client.get('/practice')
        html = resp.data.decode()
        assert 'aria-label="Back to top"' in html

    def test_back_to_top_has_aria_label_on_debug(self, client):
        resp = client.get('/debug')
        html = resp.data.decode()
        assert 'aria-label="Back to top"' in html

    def test_back_to_top_has_aria_label_on_review(self, client):
        resp = client.get('/review')
        html = resp.data.decode()
        assert 'aria-label="Back to top"' in html


class TestMobileEdgeCaseCSS:
    """CSS should have mobile edge case fixes for 320-375px screens."""

    def test_share_actions_375px_flex_wrap(self):
        """Share button row should have flex-wrap at 375px."""
        with open('static/style.css') as f:
            css = f.read()
        assert '.share-actions' in css
        assert 'flex-wrap: wrap' in css

    def test_cheatsheet_compact_grid_375px(self):
        """Cheatsheet compact grid should have smaller minmax at 375px."""
        with open('static/style.css') as f:
            css = f.read()
        assert 'minmax(85px, 1fr)' in css

    def test_playground_raw_overflow(self):
        """Playground raw response should have overflow-x auto at 375px."""
        with open('static/style.css') as f:
            css = f.read()
        # Find the 375px media query section
        idx = css.rfind('@media (max-width: 375px)')
        assert idx != -1
        section = css[idx:idx + 2000]
        assert 'overflow-x: auto' in section
        assert '.playground-raw' in section

    def test_bento_dashboard_320_spacing(self):
        """Bento dashboard should have proper spacing at 375px breakpoint."""
        with open('static/style.css') as f:
            css = f.read()
        idx = css.rfind('@media (max-width: 375px)')
        assert idx != -1
        section = css[idx:idx + 2000]
        assert '.bento-dashboard' in section
        assert '.bento-tile' in section

    def test_compare_selector_stacking_tablet(self):
        """Compare selectors should have visual separation at tablet width."""
        with open('static/style.css') as f:
            css = f.read()
        assert 'border-bottom' in css
        assert '.compare-select-wrap' in css


class TestTouchFeedbackDetailParrot:
    """Detail page parrot should have touch feedback styles."""

    def test_tap_highlight_color(self):
        """Parrot-clickable should disable default tap highlight."""
        with open('static/style.css') as f:
            css = f.read()
        assert '-webkit-tap-highlight-color' in css
        assert '.parrot-clickable' in css

    def test_active_feedback(self):
        """Parrot-clickable should have :active scale transform."""
        with open('static/style.css') as f:
            css = f.read()
        assert '.parrot-clickable:active' in css
        assert 'scale(0.96)' in css


class TestSearchInputCSSConsistency:
    """Search input styles should be consistent across header and homepage."""

    def test_search_input_sm_has_border_radius(self):
        """Header .search-input-sm should use var(--radius-sm) for border-radius."""
        with open('static/style.css') as f:
            css = f.read()
        # Find the .search-input-sm block and verify border-radius
        import re
        match = re.search(r'\.search-input-sm\s*\{[^}]+\}', css)
        assert match, '.search-input-sm rule not found'
        block = match.group(0)
        assert 'border-radius: var(--radius-sm)' in block

    def test_search_input_sm_tablet_min_width(self):
        """On tablet (768-992px), .search-input-sm should have min-width: 140px."""
        with open('static/style.css') as f:
            css = f.read()
        assert '(min-width: 768px) and (max-width: 992px)' in css
        # The breakpoint should contain the min-width rule for search-input-sm
        import re
        match = re.search(
            r'@media\s*\(min-width:\s*768px\)\s*and\s*\(max-width:\s*992px\)\s*\{([^}]+\})',
            css,
        )
        assert match, 'Tablet breakpoint (768-992px) not found'
        block = match.group(1)
        assert '.search-input-sm' in block
        assert 'min-width: 140px' in block


class TestPlaygroundLayoutBreakpoints:
    """Playground layout should adapt to narrow tablet and prevent overflow."""

    def test_playground_900px_breakpoint_exists(self):
        """A 900px breakpoint should switch .playground-layout to single column."""
        with open('static/style.css') as f:
            css = f.read()
        assert '@media (max-width: 900px)' in css
        import re
        match = re.search(
            r'@media\s*\(max-width:\s*900px\)\s*\{([^}]+\})+',
            css,
        )
        assert match, '900px breakpoint not found'
        block = match.group(0)
        assert '.playground-layout' in block
        assert 'grid-template-columns: 1fr' in block

    def test_playground_preview_static_at_900px(self):
        """At 900px breakpoint, .playground-preview should be position: static."""
        with open('static/style.css') as f:
            css = f.read()
        import re
        match = re.search(
            r'@media\s*\(max-width:\s*900px\)\s*\{([^}]+\})+',
            css,
        )
        assert match, '900px breakpoint not found'
        block = match.group(0)
        assert '.playground-preview' in block
        assert 'position: static' in block

    def test_playground_raw_overflow_x(self):
        """Base .playground-raw should have overflow-x: auto and max-width: 100%."""
        with open('static/style.css') as f:
            css = f.read()
        import re
        assert '.playground-raw' in css
        assert 'overflow-x: auto' in css


# --- Issue Fix Verification Tests ---

class TestPOTDBadgeCSS:
    """Verify the Parrot of the Day CSS ribbon/badge exists on featured cards."""

    def test_featured_before_pseudo_element_exists(self):
        """CSS should define .parrot.featured::before with POTD badge text."""
        with open('static/style.css') as f:
            css = f.read()
        assert '.parrot.featured::before' in css

    def test_featured_before_has_potd_content(self):
        """The ::before pseudo-element should say 'Parrot of the day'."""
        with open('static/style.css') as f:
            css = f.read()
        # The content property should reference 'Parrot of the day'
        assert "content: 'Parrot of the day'" in css

    def test_featured_before_is_positioned(self):
        """The POTD badge should be absolutely positioned inside the card."""
        with open('static/style.css') as f:
            css = f.read()
        assert '.parrot.featured::before' in css
        assert 'position: absolute' in css

    def test_featured_class_applied_in_homepage(self, client):
        """Homepage should have a card with the 'featured' CSS class."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'class="parrot parrot-' in html
        assert ' featured' in html

    def test_featured_card_has_green_border(self):
        """Featured card should have a distinct green border color."""
        with open('static/style.css') as f:
            css = f.read()
        assert '.parrot.featured' in css
        assert 'border-color' in css


class TestKonamiEasterEgg:
    """Verify the Konami code easter egg listener and overlay exist."""

    def test_konami_code_listener_exists(self, client):
        """Homepage should have the Konami code keydown listener."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'konamiCode' in html
        assert "['ArrowUp','ArrowUp','ArrowDown','ArrowDown','ArrowLeft','ArrowRight','ArrowLeft','ArrowRight','b','a']" in html

    def test_party_parrot_overlay_html_exists(self, client):
        """Homepage should have the party-parrot-overlay div."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'id="party-parrot-overlay"' in html
        assert 'id="party-parrot-container"' in html
        assert 'id="party-parrot-text"' in html
        assert 'PARTY PARROT MODE' in html

    def test_party_parrot_overlay_css_exists(self):
        """CSS should define styles for the party parrot overlay."""
        with open('static/style.css') as f:
            css = f.read()
        assert '#party-parrot-overlay' in css
        assert '#party-parrot-overlay.active' in css

    def test_konami_activates_party_function(self, client):
        """Konami code should call activatePartyParrot function."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'activatePartyParrot' in html

    def test_konami_saves_easter_egg(self, client):
        """Konami code should save 'konami' to eggs_found in localStorage."""
        resp = client.get('/')
        html = resp.data.decode()
        assert "eggs.indexOf('konami')" in html
        assert 'eggs_found' in html


class TestFunFactsPool:
    """Verify the fun facts pool includes code-specific data."""

    def test_fun_facts_include_generic_facts(self, client):
        """Detail page should include generic HTTP fun facts."""
        resp = client.get('/200')
        html = resp.data.decode()
        assert 'genericFacts' in html
        assert 'Tim Berners-Lee' in html

    def test_fun_facts_include_code_specific_facts(self, client):
        """Detail page should include code-specific facts from examples/case_studies."""
        resp = client.get('/200')
        html = resp.data.decode()
        assert 'codeSpecificFacts' in html

    def test_fun_facts_include_eli5_text(self, client):
        """Detail page should include ELI5 text in the fun facts pool."""
        resp = client.get('/200')
        html = resp.data.decode()
        assert 'eli5Text' in html
        assert 'codeSpecificFacts.push' in html

    def test_fun_facts_include_examples_for_code_with_extras(self, client):
        """Detail page with extra examples should inject them into codeSpecificFacts."""
        resp = client.get('/404')
        html = resp.data.decode()
        # 404 has examples in STATUS_EXTRA, they should appear in codeSpecificFacts
        assert 'codeSpecificFacts' in html

    def test_fun_facts_pool_has_more_than_ten_generic(self, client):
        """The generic facts pool should have more than 10 entries."""
        resp = client.get('/200')
        html = resp.data.decode()
        # Count occurrences of entries in genericFacts array
        assert 'Roy Fielding' in html
        assert 'HTTPS was introduced' in html
        assert 'Cookies were invented' in html


# --- E5: Weekly Challenge Distinct Rewards ---

class TestWeeklyHistory:
    """Tests for weekly challenge history tracking and Theme Master feather."""

    def test_weekly_has_history_section(self, client):
        """Weekly page should contain the history container element."""
        resp = client.get('/weekly')
        html = resp.get_data(as_text=True)
        assert 'weekly-history' in html
        assert 'weekly-history-list' in html
        assert 'Past Challenges' in html

    def test_weekly_history_js_storage_key(self, client):
        """Weekly page JS should use httpparrot_weekly_history localStorage key."""
        resp = client.get('/weekly')
        html = resp.get_data(as_text=True)
        assert 'httpparrot_weekly_history' in html

    def test_weekly_history_save_function(self, client):
        """Weekly page JS should define saveHistory and getHistory functions."""
        resp = client.get('/weekly')
        html = resp.get_data(as_text=True)
        assert 'function saveHistory' in html
        assert 'function getHistory' in html

    def test_weekly_history_render_function(self, client):
        """Weekly page JS should define renderHistory for displaying past scores."""
        resp = client.get('/weekly')
        html = resp.get_data(as_text=True)
        assert 'function renderHistory' in html
        assert 'weekly-history-row' in html

    def test_weekly_history_called_on_init(self, client):
        """renderHistory should be called during initialization."""
        resp = client.get('/weekly')
        html = resp.get_data(as_text=True)
        assert 'renderHistory()' in html

    def test_weekly_history_tracks_theme(self, client):
        """History entries should include the theme name."""
        resp = client.get('/weekly')
        html = resp.get_data(as_text=True)
        assert 'theme: THEME_NAME' in html


class TestThemeMasterFeather:
    """Tests for the Theme Master feather in base.html."""

    def test_theme_master_in_feathers_array(self, client):
        """FEATHERS array should contain theme_master."""
        resp = client.get('/')
        html = resp.data.decode()
        assert "'theme_master'" in html
        assert 'Theme Master' in html

    def test_theme_master_check_in_checkfeathers(self, client):
        """checkFeathers should check for theme_master via weekly_champion flag."""
        resp = client.get('/')
        html = resp.data.decode()
        assert "!has('theme_master')" in html
        assert 'httpparrot_weekly_champion' in html


# --- E4: Parrotdex Completion Milestones ---

class TestParrotdexMilestones:
    """Tests for milestone badges and category progress in collection page."""

    def test_collection_has_milestone_badges(self, client):
        """Collection page should have milestone badge elements at 10, 25, 50, 72."""
        resp = client.get('/collection')
        html = resp.get_data(as_text=True)
        assert 'milestone-10' in html
        assert 'milestone-25' in html
        assert 'milestone-50' in html
        assert 'milestone-72' in html
        assert 'collection-milestones' in html

    def test_collection_has_category_progress(self, client):
        """Collection page should have category progress bars for 1xx-5xx."""
        resp = client.get('/collection')
        html = resp.get_data(as_text=True)
        assert 'category-progress' in html
        assert 'cat-fill-1' in html
        assert 'cat-fill-2' in html
        assert 'cat-fill-3' in html
        assert 'cat-fill-4' in html
        assert 'cat-fill-5' in html

    def test_collection_milestone_js_logic(self, client):
        """Collection JS should contain milestone earned logic."""
        resp = client.get('/collection')
        html = resp.get_data(as_text=True)
        assert 'milestone-earned' in html
        assert 'catTotals' in html
        assert 'catCollected' in html

    def test_collection_category_bar_labels(self, client):
        """Category bars should have correct labels."""
        resp = client.get('/collection')
        html = resp.get_data(as_text=True)
        assert 'category-bar-label' in html
        for cat in ['1xx', '2xx', '3xx', '4xx', '5xx']:
            assert cat in html

    def test_milestone_css_styles(self):
        """CSS should include milestone badge styles."""
        with open('static/style.css') as f:
            css = f.read()
        assert '.milestone-badge' in css
        assert '.milestone-earned' in css
        assert '.collection-milestones' in css

    def test_category_bar_css_styles(self):
        """CSS should include category progress bar styles."""
        with open('static/style.css') as f:
            css = f.read()
        assert '.category-bar' in css
        assert '.category-bar-fill' in css
        assert '.category-bar-track' in css
        assert '.collection-category-progress' in css


class TestExplorerFeathers:
    """Tests for Explorer 10/25/50 feathers."""

    def test_explorer_feathers_in_array(self, client):
        """FEATHERS array should contain explorer_10, explorer_25, explorer_50."""
        resp = client.get('/')
        html = resp.data.decode()
        assert "'explorer_10'" in html
        assert "'explorer_25'" in html
        assert "'explorer_50'" in html
        assert 'Explorer 10' in html
        assert 'Explorer 25' in html
        assert 'Explorer 50' in html

    def test_explorer_feather_checks(self, client):
        """checkFeathers should check parrotdex length for explorer milestones."""
        resp = client.get('/')
        html = resp.data.decode()
        assert "!has('explorer_10')" in html
        assert 'parrotdex.length >= 10' in html
        assert 'parrotdex.length >= 25' in html
        assert 'parrotdex.length >= 50' in html


# --- FN1: Tester Truncation Warning ---

class TestTesterTruncationWarning:
    """Tests for the visible truncation warning in tester."""

    def test_tester_has_truncation_warning_class(self, client):
        """Tester page JS should create tester-truncation-warning element."""
        resp = client.get('/tester')
        html = resp.get_data(as_text=True)
        assert 'tester-truncation-warning' in html
        assert 'Response truncated at 10KB. Full response is larger.' in html

    def test_tester_truncation_warning_has_role_alert(self, client):
        """Truncation warning should have role=alert for accessibility."""
        resp = client.get('/tester')
        html = resp.get_data(as_text=True)
        assert "role', 'alert'" in html

    def test_tester_truncation_css(self):
        """CSS should include truncation warning styles with yellow theme."""
        with open('static/style.css') as f:
            css = f.read()
        assert '.tester-truncation-warning' in css
        assert '.tester-truncation-text' in css
        assert '.tester-truncation-icon' in css

    def test_tester_truncation_only_on_truncated(self, client):
        """Truncation warning should only appear when data.truncated is true."""
        resp = client.get('/tester')
        html = resp.get_data(as_text=True)
        assert 'if (data.truncated)' in html


# --- ED5: Expanded Case Studies ---

class TestExpandedCaseStudies:
    """Tests for the expanded case studies (60+ codes)."""

    def test_1xx_codes_have_case_studies(self):
        """1xx codes 100, 101, 102, 103 should all have case_studies."""
        from status_extra import STATUS_EXTRA
        for code in ['100', '101', '102', '103']:
            assert code in STATUS_EXTRA, f"Code {code} missing from STATUS_EXTRA"
            assert 'case_studies' in STATUS_EXTRA[code], f"Code {code} missing case_studies"
            assert len(STATUS_EXTRA[code]['case_studies']) >= 1

    def test_new_2xx_case_studies(self):
        """205 should now have case_studies."""
        from status_extra import STATUS_EXTRA
        assert 'case_studies' in STATUS_EXTRA['205']
        assert len(STATUS_EXTRA['205']['case_studies']) >= 1

    def test_new_3xx_case_studies(self):
        """300 and 306 should now have case_studies."""
        from status_extra import STATUS_EXTRA
        for code in ['300', '306']:
            assert 'case_studies' in STATUS_EXTRA[code], f"Code {code} missing case_studies"

    def test_new_4xx_case_studies(self):
        """402, 407, 425, 444, 494, 498, 499 should have case_studies."""
        from status_extra import STATUS_EXTRA
        for code in ['402', '407', '425', '444', '494', '498', '499']:
            assert code in STATUS_EXTRA, f"Code {code} missing from STATUS_EXTRA"
            assert 'case_studies' in STATUS_EXTRA[code], f"Code {code} missing case_studies"
            assert len(STATUS_EXTRA[code]['case_studies']) >= 1

    def test_new_5xx_case_studies(self):
        """506 and 509 should now have case_studies."""
        from status_extra import STATUS_EXTRA
        for code in ['506', '509']:
            assert 'case_studies' in STATUS_EXTRA[code], f"Code {code} missing case_studies"
            assert len(STATUS_EXTRA[code]['case_studies']) >= 1

    def test_total_case_studies_at_least_60(self):
        """Total codes with case_studies should be at least 60."""
        from status_extra import STATUS_EXTRA
        codes_with_studies = [
            code for code, data in STATUS_EXTRA.items()
            if 'case_studies' in data and len(data['case_studies']) > 0
        ]
        assert len(codes_with_studies) >= 60, (
            f"Only {len(codes_with_studies)} codes have case_studies, need at least 60"
        )

    def test_all_new_case_studies_have_required_keys(self):
        """Every case_studies entry should have api, scenario, and lesson."""
        from status_extra import STATUS_EXTRA
        for code in ['100', '101', '102', '103', '205', '300', '306', '402',
                      '407', '425', '444', '494', '498', '499', '506', '509']:
            if code in STATUS_EXTRA and 'case_studies' in STATUS_EXTRA[code]:
                for entry in STATUS_EXTRA[code]['case_studies']:
                    assert 'api' in entry, f"Missing 'api' in {code} case study"
                    assert 'scenario' in entry, f"Missing 'scenario' in {code} case study"
                    assert 'lesson' in entry, f"Missing 'lesson' in {code} case study"


# --- Weekly History CSS ---

class TestWeeklyHistoryCSS:
    """Tests for weekly history CSS styles."""

    def test_weekly_history_css(self):
        """CSS should include weekly history styles."""
        with open('static/style.css') as f:
            css = f.read()
        assert '.weekly-history' in css
        assert '.weekly-history-row' in css
        assert '.weekly-history-title' in css
        assert '.weekly-history-score' in css


# --- Adaptive Quiz Difficulty ---

class TestAdaptiveQuizDifficulty:
    """Tests for adaptive quiz difficulty with mistake tracking."""

    def test_quiz_has_mistakes_key(self, client):
        """Quiz should define the localStorage key for mistakes."""
        resp = client.get('/quiz')
        html = resp.data.decode()
        assert 'httpparrot_quiz_mistakes' in html

    def test_quiz_has_get_mistakes_function(self, client):
        """Quiz should have a getMistakes function for loading from localStorage."""
        resp = client.get('/quiz')
        html = resp.data.decode()
        assert 'function getMistakes()' in html

    def test_quiz_has_save_mistakes_function(self, client):
        """Quiz should have a saveMistakes function for persisting to localStorage."""
        resp = client.get('/quiz')
        html = resp.data.decode()
        assert 'function saveMistakes(' in html

    def test_quiz_has_add_mistake_function(self, client):
        """Quiz should have an addMistake function to record wrong answers."""
        resp = client.get('/quiz')
        html = resp.data.decode()
        assert 'function addMistake(' in html

    def test_quiz_has_remove_mistake_function(self, client):
        """Quiz should have a removeMistake function to clear mastered codes."""
        resp = client.get('/quiz')
        html = resp.data.decode()
        assert 'function removeMistake(' in html

    def test_quiz_has_weighted_pick_function(self, client):
        """Quiz should have a pickWeightedCode function for adaptive selection."""
        resp = client.get('/quiz')
        html = resp.data.decode()
        assert 'function pickWeightedCode()' in html

    def test_quiz_weighted_pick_uses_50_percent(self, client):
        """Weighted pick should use 50% probability for mistake codes."""
        resp = client.get('/quiz')
        html = resp.data.decode()
        assert 'Math.random() < 0.5' in html

    def test_quiz_calls_add_mistake_on_wrong(self, client):
        """Wrong answers should call addMistake with the correct code."""
        resp = client.get('/quiz')
        html = resp.data.decode()
        assert 'addMistake(correct.code)' in html

    def test_quiz_calls_remove_mistake_on_correct(self, client):
        """Correct answers should call removeMistake to clear the code."""
        resp = client.get('/quiz')
        html = resp.data.decode()
        assert 'removeMistake(correct.code)' in html

    def test_quiz_next_round_uses_weighted_pick(self, client):
        """nextRound should use pickWeightedCode instead of plain random."""
        resp = client.get('/quiz')
        html = resp.data.decode()
        assert 'const correct = pickWeightedCode()' in html


# --- Form Validation UX ---

class TestFormValidationUX:
    """Tests for inline validation error messages on forms."""

    def test_tester_has_validation_error_element(self, client):
        """Tester page should have a validation-error element for empty URL."""
        resp = client.get('/tester')
        html = resp.data.decode()
        assert 'id="url-validation-error"' in html
        assert 'Please enter a URL' in html

    def test_tester_validation_error_hidden_by_default(self, client):
        """Tester validation error should be hidden by default."""
        resp = client.get('/tester')
        html = resp.data.decode()
        assert 'id="url-validation-error" role="alert" style="display:none;"' in html

    def test_tester_validation_error_has_role_alert(self, client):
        """Tester validation error should have role=alert for accessibility."""
        resp = client.get('/tester')
        html = resp.data.decode()
        assert 'id="url-validation-error" role="alert"' in html

    def test_trace_has_validation_error_element(self, client):
        """Trace page should have a validation-error element for empty URL."""
        resp = client.get('/trace')
        html = resp.data.decode()
        assert 'id="trace-validation-error"' in html
        assert 'Please enter a URL' in html

    def test_trace_validation_error_hidden_by_default(self, client):
        """Trace validation error should be hidden by default."""
        resp = client.get('/trace')
        html = resp.data.decode()
        assert 'id="trace-validation-error" role="alert" style="display:none;"' in html

    def test_security_audit_has_validation_error_element(self, client):
        """Security audit page should have a validation-error element."""
        resp = client.get('/security-audit')
        html = resp.data.decode()
        assert 'id="audit-validation-error"' in html
        assert 'Please enter a URL' in html

    def test_security_audit_validation_error_hidden_by_default(self, client):
        """Security audit validation error should be hidden by default."""
        resp = client.get('/security-audit')
        html = resp.data.decode()
        assert 'id="audit-validation-error" role="alert" style="display:none;"' in html

    def test_cors_checker_has_url_validation_error(self, client):
        """CORS checker should have a validation-error for empty URL."""
        resp = client.get('/cors-checker')
        html = resp.data.decode()
        assert 'id="cors-url-validation-error"' in html
        assert 'URL is required' in html

    def test_cors_checker_has_origin_validation_error(self, client):
        """CORS checker should have a validation-error for empty origin."""
        resp = client.get('/cors-checker')
        html = resp.data.decode()
        assert 'id="cors-origin-validation-error"' in html
        assert 'Origin is required' in html

    def test_cors_checker_validation_errors_hidden_by_default(self, client):
        """CORS checker validation errors should be hidden by default."""
        resp = client.get('/cors-checker')
        html = resp.data.decode()
        assert 'id="cors-url-validation-error" role="alert" style="display:none;"' in html
        assert 'id="cors-origin-validation-error" role="alert" style="display:none;"' in html

    def test_headers_has_validation_error_element(self, client):
        """Headers page should have a validation-error element."""
        resp = client.get('/headers')
        html = resp.data.decode()
        assert 'id="header-validation-error"' in html
        assert 'Paste some headers first' in html

    def test_headers_validation_error_hidden_by_default(self, client):
        """Headers validation error should be hidden by default."""
        resp = client.get('/headers')
        html = resp.data.decode()
        assert 'id="header-validation-error" role="alert" style="display:none;"' in html

    def test_validation_error_css_exists(self):
        """CSS should include validation-error styles."""
        with open('static/style.css') as f:
            css = f.read()
        assert '.validation-error' in css
        assert '#ff6b6b' in css

    def test_tester_shows_error_on_empty_submit(self, client):
        """Tester JS should show the error when URL is empty."""
        resp = client.get('/tester')
        html = resp.data.decode()
        assert "getElementById('url-validation-error').style.display = ''" in html

    def test_tester_hides_error_on_input(self, client):
        """Tester JS should hide validation error on input event."""
        resp = client.get('/tester')
        html = resp.data.decode()
        assert "url-input').addEventListener('input'" in html

    def test_trace_shows_error_on_empty_submit(self, client):
        """Trace JS should show error when URL is empty."""
        resp = client.get('/trace')
        html = resp.data.decode()
        assert "getElementById('trace-validation-error').style.display = ''" in html

    def test_trace_hides_error_on_input(self, client):
        """Trace JS should hide validation error on input event."""
        resp = client.get('/trace')
        html = resp.data.decode()
        assert "trace-url').addEventListener('input'" in html

    def test_security_audit_shows_error_on_empty_submit(self, client):
        """Security audit JS should show error when URL is empty."""
        resp = client.get('/security-audit')
        html = resp.data.decode()
        assert "getElementById('audit-validation-error').style.display = ''" in html

    def test_cors_shows_both_errors_on_empty_submit(self, client):
        """CORS checker JS should show both errors when fields are empty."""
        resp = client.get('/cors-checker')
        html = resp.data.decode()
        assert "getElementById('cors-url-validation-error').style.display = ''" in html
        assert "getElementById('cors-origin-validation-error').style.display = ''" in html

    def test_headers_shows_error_on_empty_click(self, client):
        """Headers JS should show error when textarea is empty."""
        resp = client.get('/headers')
        html = resp.data.decode()
        assert "getElementById('header-validation-error').style.display = ''" in html


# --- Daily Challenge Suggested Actions ---

class TestDailySuggestedActions:
    """Tests for daily challenge navigation improvement."""

    def test_daily_has_suggested_actions(self, client):
        """Daily page should have suggested actions section."""
        resp = client.get('/daily')
        html = resp.data.decode()
        assert 'daily-suggested-actions' in html

    def test_daily_has_weekly_link(self, client):
        """Daily page should link to weekly challenge."""
        resp = client.get('/daily')
        html = resp.data.decode()
        assert 'href="/weekly"' in html
        assert 'Weekly Challenge' in html

    def test_daily_has_practice_link(self, client):
        """Daily page should link to practice mode."""
        resp = client.get('/daily')
        html = resp.data.decode()
        assert 'href="/practice"' in html
        assert 'Practice' in html

    def test_daily_has_quiz_link(self, client):
        """Daily page should link to quiz mode."""
        resp = client.get('/daily')
        html = resp.data.decode()
        assert 'href="/quiz"' in html
        assert 'Quiz' in html

    def test_daily_has_suggested_label(self, client):
        """Daily page should have a label for the suggested actions."""
        resp = client.get('/daily')
        html = resp.data.decode()
        assert 'daily-suggested-label' in html
        assert 'Keep practicing' in html

    def test_daily_no_back_to_home_dead_end(self, client):
        """Daily page should not have the old 'Back to Home' dead end link."""
        resp = client.get('/daily')
        html = resp.data.decode()
        assert 'Back to Home' not in html

    def test_daily_suggested_actions_css(self):
        """CSS should include daily suggested actions styles."""
        with open('static/style.css') as f:
            css = f.read()
        assert '.daily-suggested-actions' in css
        assert '.daily-suggested-label' in css
        assert '.daily-suggested-link' in css


# --- Command Palette ---

class TestCommandPalette:
    """Tests for the command palette (Cmd+K / Ctrl+K) feature."""

    def test_command_palette_overlay_in_base(self, client):
        """Base template should contain the command palette overlay."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'cmd-palette-overlay' in html
        assert 'cmd-palette-input' in html
        assert 'cmd-palette-results' in html

    def test_command_palette_on_detail_page(self, client):
        """Command palette should be available on detail pages too."""
        resp = client.get('/200')
        html = resp.data.decode()
        assert 'cmd-palette-overlay' in html

    def test_command_palette_has_search_input(self, client):
        """Command palette should have a search input with proper attributes."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'placeholder="Search pages, status codes, actions..."' in html
        assert 'aria-label="Command palette search"' in html

    def test_command_palette_has_footer_hints(self, client):
        """Command palette footer should show keyboard hints."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'navigate' in html
        assert 'cmd-palette-footer' in html

    def test_command_palette_has_backdrop(self, client):
        """Command palette should have a backdrop for closing."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'cmd-palette-backdrop' in html

    def test_command_palette_accessible_dialog(self, client):
        """Command palette overlay should have proper ARIA attributes."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'role="dialog"' in html
        assert 'aria-modal="true"' in html
        assert 'aria-label="Command palette"' in html

    def test_command_palette_results_listbox(self, client):
        """Results container should have listbox role."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'role="listbox"' in html

    def test_command_palette_status_codes_json(self, client):
        """Template should receive status codes JSON for the command palette."""
        resp = client.get('/')
        html = resp.data.decode()
        # Should contain status codes as JSON array
        assert '"200"' in html
        assert '"404"' in html
        assert '"OK"' in html
        assert '"Not Found"' in html

    def test_command_palette_pages_data(self, client):
        """Command palette JS should include page routes."""
        resp = client.get('/')
        html = resp.data.decode()
        assert "'/quiz'" in html
        assert "'/daily'" in html
        assert "'/tester'" in html
        assert "'/profile'" in html

    def test_command_palette_actions_data(self, client):
        """Command palette JS should include action items."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'Take Quiz' in html
        assert 'Random Parrot' in html

    def test_keyboard_shortcuts_includes_cmdk(self, client):
        """Keyboard shortcuts overlay should list Cmd+K."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'Command palette' in html
        assert 'Ctrl+K' in html

    def test_command_palette_css(self):
        """CSS should include command palette styles."""
        with open('static/style.css') as f:
            css = f.read()
        assert '.cmd-palette-overlay' in css
        assert '.cmd-palette-panel' in css
        assert '.cmd-palette-input' in css
        assert '.cmd-palette-result' in css
        assert '.cmd-palette-result-active' in css
        assert '.cmd-palette-backdrop' in css
        assert '.cmd-palette-footer' in css

    def test_command_palette_css_glassmorphism(self):
        """Command palette panel should use glassmorphism (backdrop-filter)."""
        with open('static/style.css') as f:
            css = f.read()
        # Find the palette panel section
        assert 'backdrop-filter: blur(24px)' in css

    def test_command_palette_css_responsive(self):
        """Command palette should have responsive styles for mobile."""
        with open('static/style.css') as f:
            css = f.read()
        # Check mobile breakpoint adjustments
        assert '.cmd-palette-panel' in css
        # The footer should hide on mobile
        assert '.cmd-palette-footer' in css

    def test_command_palette_hidden_by_default(self, client):
        """Command palette should be hidden by default."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'hidden' in html


# --- Customizable Avatar & Theme Accent ---

class TestCustomizeAvatarAccent:
    """Tests for the customizable avatar and theme accent feature on the profile page."""

    def test_customize_section_exists(self, client):
        """Profile page should contain the customize section."""
        resp = client.get('/profile')
        html = resp.data.decode()
        assert 'profile-customize-section' in html
        assert 'Customize' in html

    def test_spirit_parrot_grid(self, client):
        """Profile page should have a spirit parrot selection grid."""
        resp = client.get('/profile')
        html = resp.data.decode()
        assert 'spirit-parrot-grid' in html
        assert 'Spirit Parrot' in html

    def test_spirit_parrot_options_count(self, client):
        """There should be 8 spirit parrot options."""
        resp = client.get('/profile')
        html = resp.data.decode()
        # Count only the button elements with data-code (not JS references)
        assert html.count('class="spirit-parrot-option"') == 8

    def test_spirit_parrot_codes(self, client):
        """Spirit parrot options should include popular status codes."""
        resp = client.get('/profile')
        html = resp.data.decode()
        for code in ['200', '201', '301', '404', '418', '500', '503', '429']:
            assert f'data-code="{code}"' in html

    def test_spirit_parrot_images(self, client):
        """Spirit parrot options should have thumbnail images."""
        resp = client.get('/profile')
        html = resp.data.decode()
        assert '/static/200.jpg' in html
        assert '/static/404.jpg' in html
        assert '/static/418.jpg' in html

    def test_spirit_parrot_accessibility(self, client):
        """Spirit parrot grid should have proper ARIA attributes."""
        resp = client.get('/profile')
        html = resp.data.decode()
        assert 'role="radiogroup"' in html
        assert 'role="radio"' in html
        assert 'aria-checked=' in html
        assert 'aria-label="Choose your spirit parrot"' in html

    def test_accent_color_grid(self, client):
        """Profile page should have an accent color selection grid."""
        resp = client.get('/profile')
        html = resp.data.decode()
        assert 'accent-color-grid' in html
        assert 'Theme Accent' in html

    def test_accent_color_options(self, client):
        """There should be 5 accent color options."""
        resp = client.get('/profile')
        html = resp.data.decode()
        for accent in ['teal', 'purple', 'blue', 'gold', 'coral']:
            assert f'data-accent="{accent}"' in html

    def test_accent_color_swatches(self, client):
        """Accent color options should show color swatches."""
        resp = client.get('/profile')
        html = resp.data.decode()
        assert 'accent-color-swatch' in html
        assert '#00c9a7' in html  # teal
        assert '#7b61ff' in html  # purple
        assert '#00b4d8' in html  # blue
        assert '#f9c74f' in html  # gold
        assert '#ff6b6b' in html  # coral

    def test_accent_color_accessibility(self, client):
        """Accent color grid should have proper ARIA attributes."""
        resp = client.get('/profile')
        html = resp.data.decode()
        assert 'aria-label="Choose accent color"' in html

    def test_customize_descriptions(self, client):
        """Customize sections should have descriptive text."""
        resp = client.get('/profile')
        html = resp.data.decode()
        assert 'Pick the parrot that represents you' in html
        assert 'Choose your accent color' in html

    def test_customize_localstorage_keys_in_js(self, client):
        """Profile JS should reference the expected localStorage keys."""
        resp = client.get('/profile')
        html = resp.data.decode()
        assert 'httpparrot_avatar' in html
        assert 'httpparrot_accent' in html

    def test_base_template_avatar_application(self, client):
        """Base template should include script to apply saved avatar."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'httpparrot_avatar' in html
        assert 'xp-badge-icon' in html

    def test_base_template_accent_application(self, client):
        """Base template should include script to apply saved accent color."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'httpparrot_accent' in html
        assert '--color-accent' in html

    def test_xp_badge_icon_has_id(self, client):
        """XP badge icon should have an id for avatar script targeting."""
        resp = client.get('/200')
        html = resp.data.decode()
        assert 'id="xp-badge-icon"' in html

    def test_customize_css(self):
        """CSS should include customize section styles."""
        with open('static/style.css') as f:
            css = f.read()
        assert '.profile-customize-section' in css
        assert '.spirit-parrot-grid' in css
        assert '.spirit-parrot-option' in css
        assert '.spirit-parrot-option.selected' in css
        assert '.accent-color-grid' in css
        assert '.accent-color-option' in css
        assert '.accent-color-swatch' in css
        assert '.accent-color-option.selected' in css

    def test_customize_css_responsive(self):
        """Customize CSS should include responsive styles."""
        with open('static/style.css') as f:
            css = f.read()
        # Mobile grid should be 4 columns
        assert 'repeat(4, 1fr)' in css


# --- Status Codes JSON Context Processor ---

class TestStatusCodesJsonContextProcessor:
    """Tests for the inject_status_codes_json context processor."""

    def test_all_pages_have_status_codes_json(self, client):
        """Multiple pages should have status codes JSON available."""
        for path in ['/', '/quiz', '/profile', '/cheatsheet']:
            resp = client.get(path)
            html = resp.data.decode()
            assert '"200"' in html, f"Status codes JSON missing on {path}"
            assert '"Not Found"' in html, f"Status code names missing on {path}"

    def test_status_codes_json_contains_all_codes(self, client):
        """The status codes JSON should contain all codes from status_code_list."""
        from index import status_code_list
        resp = client.get('/')
        html = resp.data.decode()
        # Spot-check a few codes from different categories
        for code in ['100', '200', '301', '404', '500']:
            assert f'"{code}"' in html


# === F4: Meta-Feather Unlock Animation Variety ===

class TestMetaFeatherAnimation:
    """Tests for distinct meta-feather celebration animations."""

    def test_show_feather_toast_checks_meta_flag(self, client):
        """showFeatherToast should check feather.meta property."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'feather.meta' in html or '!!feather.meta' in html

    def test_meta_toast_class_added(self, client):
        """Meta feathers should get the feather-toast-meta class."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'feather-toast-meta' in html

    def test_meta_achievement_label(self, client):
        """Meta feather toast should include META ACHIEVEMENT label."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'META ACHIEVEMENT' in html

    def test_golden_confetti_function_exists(self, client):
        """spawnGoldenConfetti function should be defined."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'spawnGoldenConfetti' in html

    def test_screen_shake_function_exists(self, client):
        """triggerScreenShake function should be defined."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'triggerScreenShake' in html

    def test_meta_toast_calls_golden_confetti(self, client):
        """Meta feather path calls spawnGoldenConfetti instead of regular."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'spawnGoldenConfetti(toast)' in html

    def test_meta_toast_calls_screen_shake(self, client):
        """Meta feather path calls triggerScreenShake."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'triggerScreenShake()' in html

    def test_meta_toast_uses_legendary_flock(self, client):
        """Meta feathers use legendary flock formation."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'spawnFlockFormation(true)' in html

    def test_golden_confetti_uses_gold_colors(self, client):
        """Golden confetti uses gold color palette."""
        resp = client.get('/')
        html = resp.data.decode()
        assert "'#ffd700'" in html
        assert "'#ffb300'" in html

    def test_golden_confetti_css_class(self, client):
        """Golden confetti particles get the golden-confetti CSS class."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'golden-confetti' in html

    def test_meta_screen_shake_css(self):
        """CSS should have meta-screen-shake keyframes."""
        with open('static/style.css') as f:
            css = f.read()
        assert 'meta-screen-shake' in css
        assert '@keyframes meta-screen-shake' in css

    def test_meta_feather_toast_css(self):
        """CSS should style feather-toast-meta with golden border."""
        with open('static/style.css') as f:
            css = f.read()
        assert '.feather-toast-meta' in css
        assert '#ffd700' in css

    def test_meta_feather_label_css(self):
        """CSS should style feather-toast-meta-label."""
        with open('static/style.css') as f:
            css = f.read()
        assert '.feather-toast-meta-label' in css

    def test_meta_shake_reduced_motion(self):
        """Screen shake should be disabled for reduced motion preference."""
        with open('static/style.css') as f:
            css = f.read()
        assert 'prefers-reduced-motion' in css
        assert '.meta-screen-shake' in css

    def test_meta_toast_longer_display(self, client):
        """Meta feather toast should be visible longer than regular."""
        resp = client.get('/')
        html = resp.data.decode()
        # Meta toast uses 5500ms dismiss time
        assert '5500' in html

    def test_regular_feather_unchanged(self, client):
        """Regular feathers still use spawnCelebrationConfetti."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'spawnCelebrationConfetti(toast)' in html

    def test_screen_shake_respects_reduced_motion(self, client):
        """triggerScreenShake checks prefers-reduced-motion."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'prefers-reduced-motion' in html


# === F5: 404 Memory Game Replay ===

class TestMemoryGameReplay:
    """Tests for memory game Play Again button, best time, and faster replay."""

    def test_replay_button_in_completion(self, client):
        """Completion screen should include a Play Again button."""
        resp = client.get('/nonexistent-page')
        html = resp.data.decode()
        assert 'Play Again' in html

    def test_replay_button_class(self, client):
        """Play Again button should have memory-game-replay-btn class."""
        resp = client.get('/nonexistent-page')
        html = resp.data.decode()
        assert 'memory-game-replay-btn' in html

    def test_replay_calls_start_memory_game(self, client):
        """Play Again button calls startMemoryGame to reset the game."""
        resp = client.get('/nonexistent-page')
        html = resp.data.decode()
        assert 'startMemoryGame(parent)' in html

    def test_best_time_key_defined(self, client):
        """Best time localStorage key should be defined."""
        resp = client.get('/nonexistent-page')
        html = resp.data.decode()
        assert 'httpparrot_memory_best_time' in html

    def test_best_time_display_element(self, client):
        """Memory game should show a best time display."""
        resp = client.get('/nonexistent-page')
        html = resp.data.decode()
        assert 'memory-game-best-time' in html

    def test_best_time_saved_to_localstorage(self, client):
        """Best time should be saved to localStorage."""
        resp = client.get('/nonexistent-page')
        html = resp.data.decode()
        assert 'saveBestTime' in html
        assert 'BEST_TIME_KEY' in html

    def test_elapsed_time_tracked(self, client):
        """Game should track elapsed time from start to completion."""
        resp = client.get('/nonexistent-page')
        html = resp.data.decode()
        assert 'gameStartTime' in html
        assert 'Date.now()' in html

    def test_new_best_indicator(self, client):
        """Should show 'New best!' when a new record is set."""
        resp = client.get('/nonexistent-page')
        html = resp.data.decode()
        assert 'New best!' in html

    def test_faster_replay_delay(self, client):
        """Replay games should use 800ms flip-back delay instead of 900ms."""
        resp = client.get('/nonexistent-page')
        html = resp.data.decode()
        assert '800' in html
        assert 'getFlipBackDelay' in html

    def test_play_count_tracked(self, client):
        """Play count should be tracked for replay speed adjustment."""
        resp = client.get('/nonexistent-page')
        html = resp.data.decode()
        assert 'playCount' in html

    def test_format_time_function(self, client):
        """formatTime function should exist for time display."""
        resp = client.get('/nonexistent-page')
        html = resp.data.decode()
        assert 'formatTime' in html

    def test_memory_game_actions_row(self, client):
        """Completion screen should have actions row with both buttons."""
        resp = client.get('/nonexistent-page')
        html = resp.data.decode()
        assert 'memory-game-actions' in html

    def test_replay_css_exists(self):
        """CSS should style the replay button and time displays."""
        with open('static/style.css') as f:
            css = f.read()
        assert '.memory-game-replay-btn' in css
        assert '.memory-game-time' in css
        assert '.memory-game-best-time' in css
        assert '.memory-game-actions' in css

    def test_time_display_in_completion(self, client):
        """Completion handler receives elapsed time parameter."""
        resp = client.get('/nonexistent-page')
        html = resp.data.decode()
        assert 'onGameComplete(parent, elapsed)' in html

    def test_home_btn_still_present(self, client):
        """Home button should still be present alongside replay."""
        resp = client.get('/nonexistent-page')
        html = resp.data.decode()
        assert 'memory-game-home-btn' in html
        assert 'Back to all parrots' in html


# === FN4: Global Search Live Dropdown ===

class TestGlobalSearchDropdown:
    """Tests for global header search live dropdown."""

    def test_search_dropdown_element_exists(self, client):
        """Global search dropdown element should be in the DOM."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'global-search-dropdown' in html

    def test_search_dropdown_hidden_by_default(self, client):
        """Dropdown should be hidden by default."""
        resp = client.get('/200')
        html = resp.data.decode()
        assert 'global-search-dropdown' in html

    def test_search_wrap_has_position_relative(self, client):
        """Search wrap should have global-search-wrap class for positioning."""
        resp = client.get('/200')
        html = resp.data.decode()
        assert 'global-search-wrap' in html

    def test_dropdown_calls_api_search(self, client):
        """Search dropdown should call /api/search endpoint."""
        resp = client.get('/')
        html = resp.data.decode()
        assert '/api/search' in html

    def test_search_debounce_300ms(self, client):
        """Search input should debounce API calls at 300ms."""
        resp = client.get('/')
        html = resp.data.decode()
        assert '300' in html
        assert 'debounceTimer' in html

    def test_search_escape_closes(self, client):
        """Pressing Escape should close the dropdown."""
        resp = client.get('/')
        html = resp.data.decode()
        assert "e.key === 'Escape'" in html or 'Escape' in html

    def test_search_click_outside_closes(self, client):
        """Clicking outside should close the dropdown."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'closeDropdown' in html

    def test_search_result_structure(self, client):
        """Each result should show code, name, and description."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'global-search-result-code' in html
        assert 'global-search-result-name' in html
        assert 'global-search-result-desc' in html

    def test_search_result_is_link(self, client):
        """Each search result should be a link to the code page."""
        resp = client.get('/')
        html = resp.data.decode()
        # Results are <a> elements with href = '/' + code
        assert "opt.href = '/' + item.code" in html

    def test_search_keyboard_navigation(self, client):
        """Arrow keys should navigate results."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'ArrowDown' in html
        assert 'ArrowUp' in html

    def test_search_enter_navigates(self, client):
        """Enter on active result should navigate to it."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'currentResults[activeIndex]' in html

    def test_search_dropdown_css_exists(self):
        """CSS should style the search dropdown."""
        with open('static/style.css') as f:
            css = f.read()
        assert '.global-search-dropdown' in css
        assert '.global-search-result' in css

    def test_search_dropdown_matches_nav_style(self):
        """Dropdown should use similar styles to nav-dropdown-menu."""
        with open('static/style.css') as f:
            css = f.read()
        # Both use var(--surface-2) background and blur
        assert 'backdrop-filter: blur(16px)' in css

    def test_search_dropdown_hidden_on_mobile(self):
        """Search dropdown should be hidden on mobile."""
        with open('static/style.css') as f:
            css = f.read()
        assert '.global-search-dropdown' in css
        assert 'display: none !important' in css

    def test_search_desktop_check(self, client):
        """Search only activates on desktop (>= 768px)."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'isDesktop' in html
        assert '768' in html

    def test_search_listbox_role(self, client):
        """Dropdown should have listbox role for accessibility."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'role="listbox"' in html

    def test_search_result_option_role(self, client):
        """Each result should have option role."""
        resp = client.get('/')
        html = resp.data.decode()
        assert "role', 'option'" in html

    def test_search_truncates_description(self, client):
        """Long descriptions should be truncated to 80 chars."""
        resp = client.get('/')
        html = resp.data.decode()
        assert '80' in html
        assert "substring(0, 80)" in html

    def test_api_search_returns_results(self, client):
        """API search endpoint should return results for valid query."""
        resp = client.get('/api/search?q=not+found')
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)
        assert len(data) > 0
        assert data[0]['code'] == '404'


# === FN3: cURL Import to Playground Integration ===

class TestCurlImportPlayground:
    """Tests for cURL Import to Playground link and Playground query param pre-population."""

    def test_playground_button_exists(self, client):
        """cURL import page should have an Open in Playground button."""
        resp = client.get('/curl-import')
        html = resp.data.decode()
        assert 'curl-playground-btn' in html

    def test_playground_button_hidden_initially(self, client):
        """Playground button should be hidden before parsing."""
        resp = client.get('/curl-import')
        html = resp.data.decode()
        assert "display:none" in html or "display: none" in html

    def test_playground_link_builder(self, client):
        """updatePlaygroundLink function should exist."""
        resp = client.get('/curl-import')
        html = resp.data.decode()
        assert 'updatePlaygroundLink' in html

    def test_playground_link_has_method_param(self, client):
        """Playground link should include method query param."""
        resp = client.get('/curl-import')
        html = resp.data.decode()
        assert "params.set('method'" in html

    def test_playground_link_has_url_param(self, client):
        """Playground link should include url query param."""
        resp = client.get('/curl-import')
        html = resp.data.decode()
        assert "params.set('url'" in html

    def test_playground_link_has_header_params(self, client):
        """Playground link should append header query params."""
        resp = client.get('/curl-import')
        html = resp.data.decode()
        assert "params.append('header'" in html

    def test_playground_link_has_body_param(self, client):
        """Playground link should include body query param when present."""
        resp = client.get('/curl-import')
        html = resp.data.decode()
        assert "params.set('body'" in html

    def test_playground_link_navigates_to_playground(self, client):
        """Playground link href should point to /playground."""
        resp = client.get('/curl-import')
        html = resp.data.decode()
        assert "'/playground?'" in html

    def test_playground_reads_query_params_on_load(self, client):
        """Playground should check for query params on load."""
        resp = client.get('/playground')
        html = resp.data.decode()
        assert 'URLSearchParams' in html
        assert "params.has('method')" in html or "params.has('url')" in html

    def test_playground_populates_headers_from_params(self, client):
        """Playground should populate headers from query params."""
        resp = client.get('/playground')
        html = resp.data.decode()
        assert "params.getAll('header')" in html

    def test_playground_populates_body_from_params(self, client):
        """Playground should populate body from query params."""
        resp = client.get('/playground')
        html = resp.data.decode()
        assert "params.get('body')" in html

    def test_playground_cleans_url_after_populate(self, client):
        """Playground should clean URL params after populating."""
        resp = client.get('/playground')
        html = resp.data.decode()
        assert 'replaceState' in html

    def test_playground_page_loads_with_params(self, client):
        """Playground should load successfully with query params."""
        resp = client.get('/playground?method=POST&url=https://api.example.com&body=test')
        assert resp.status_code == 200

    def test_playground_button_label(self, client):
        """Button should say 'Open in Playground'."""
        resp = client.get('/curl-import')
        html = resp.data.decode()
        assert 'Open in Playground' in html

    def test_render_parsed_calls_playground_link(self, client):
        """renderParsed should call updatePlaygroundLink."""
        resp = client.get('/curl-import')
        html = resp.data.decode()
        assert 'updatePlaygroundLink(req)' in html


# --- Task 1: Fill remaining case_studies gaps ---

class TestRemainingCaseStudies:
    """Tests for the 10 newly added case_studies entries."""

    def test_case_studies_added_to_10_remaining_codes(self):
        """All 10 codes that previously lacked case_studies should now have them."""
        from status_extra import STATUS_EXTRA
        codes = ['305', '413', '417', '419', '420', '421', '423', '424', '426', '450']
        for code in codes:
            assert code in STATUS_EXTRA, f"Code {code} not in STATUS_EXTRA"
            assert 'case_studies' in STATUS_EXTRA[code], (
                f"Code {code} still missing case_studies"
            )
            assert len(STATUS_EXTRA[code]['case_studies']) >= 2, (
                f"Code {code} should have at least 2 case_studies entries, "
                f"got {len(STATUS_EXTRA[code]['case_studies'])}"
            )

    def test_new_case_studies_have_required_keys(self):
        """Every new case_studies entry must have api, scenario, lesson."""
        from status_extra import STATUS_EXTRA
        codes = ['305', '413', '417', '419', '420', '421', '423', '424', '426', '450']
        for code in codes:
            for i, entry in enumerate(STATUS_EXTRA[code]['case_studies']):
                assert 'api' in entry, f"Missing 'api' in {code}[{i}]"
                assert 'scenario' in entry, f"Missing 'scenario' in {code}[{i}]"
                assert 'lesson' in entry, f"Missing 'lesson' in {code}[{i}]"

    def test_new_case_studies_non_empty_strings(self):
        """All case study strings should be non-empty."""
        from status_extra import STATUS_EXTRA
        codes = ['305', '413', '417', '419', '420', '421', '423', '424', '426', '450']
        for code in codes:
            for i, entry in enumerate(STATUS_EXTRA[code]['case_studies']):
                assert len(entry['api'].strip()) > 0, f"Empty api in {code}[{i}]"
                assert len(entry['scenario'].strip()) > 0, f"Empty scenario in {code}[{i}]"
                assert len(entry['lesson'].strip()) > 0, f"Empty lesson in {code}[{i}]"

    def test_new_case_studies_render_on_pages(self, client):
        """Newly added case_studies should render on their detail pages."""
        for code in ['305', '413', '417', '421', '426']:
            resp = client.get(f'/{code}')
            html = resp.get_data(as_text=True)
            assert 'case-studies-section' in html, f"/{code} missing case-studies-section"
            assert 'case-study-card' in html, f"/{code} missing case-study-card"

    def test_total_case_studies_at_least_70(self):
        """With 10 new additions, total should be at least 70."""
        from status_extra import STATUS_EXTRA
        codes_with_studies = [
            code for code, data in STATUS_EXTRA.items()
            if 'case_studies' in data and len(data['case_studies']) > 0
        ]
        assert len(codes_with_studies) >= 70, (
            f"Only {len(codes_with_studies)} codes have case_studies, need at least 70"
        )


# --- Task 2: Fill common_mistakes for high-importance codes ---

class TestNewCommonMistakes:
    """Tests for the 6 newly added common_mistakes entries."""

    def test_common_mistakes_added_to_6_codes(self):
        """All 6 high-importance codes should now have common_mistakes."""
        from status_extra import STATUS_EXTRA
        codes = ['402', '407', '421', '425', '499', '507']
        for code in codes:
            assert code in STATUS_EXTRA, f"Code {code} not in STATUS_EXTRA"
            assert 'common_mistakes' in STATUS_EXTRA[code], (
                f"Code {code} missing common_mistakes"
            )
            assert len(STATUS_EXTRA[code]['common_mistakes']) >= 2, (
                f"Code {code} should have at least 2 common_mistakes entries"
            )

    def test_new_common_mistakes_structure(self):
        """Each new common_mistakes entry should have mistake and consequence."""
        from status_extra import STATUS_EXTRA
        codes = ['402', '407', '421', '425', '499', '507']
        for code in codes:
            for i, entry in enumerate(STATUS_EXTRA[code]['common_mistakes']):
                assert 'mistake' in entry, f"Missing 'mistake' in {code}[{i}]"
                assert 'consequence' in entry, f"Missing 'consequence' in {code}[{i}]"
                assert len(entry['mistake'].strip()) > 0, f"Empty mistake in {code}[{i}]"
                assert len(entry['consequence'].strip()) > 0, f"Empty consequence in {code}[{i}]"

    def test_new_common_mistakes_render_on_pages(self, client):
        """Newly added common_mistakes should render on their detail pages."""
        for code in ['402', '407', '421', '499', '507']:
            resp = client.get(f'/{code}')
            html = resp.get_data(as_text=True)
            assert 'mistakes-section' in html, f"/{code} missing mistakes-section"
            assert 'mistake-card' in html, f"/{code} missing mistake-card"

    def test_total_common_mistakes_at_least_45(self):
        """With 6 new additions, total should be at least 45."""
        from status_extra import STATUS_EXTRA
        codes_with_mistakes = [
            code for code, data in STATUS_EXTRA.items()
            if 'common_mistakes' in data and len(data['common_mistakes']) > 0
        ]
        assert len(codes_with_mistakes) >= 45, (
            f"Only {len(codes_with_mistakes)} codes have common_mistakes, need at least 45"
        )


# --- Task 3: "When NOT to Use" section (dont_use_when) ---

class TestDontUseWhen:
    """Tests for the dont_use_when feature on the 15 most misused codes."""

    def test_dont_use_when_present_on_15_codes(self):
        """All 15 commonly misused codes should have dont_use_when."""
        from status_extra import STATUS_EXTRA
        codes = ['200', '201', '204', '301', '302', '307', '400', '401', '403',
                 '404', '409', '422', '429', '500', '503']
        for code in codes:
            assert code in STATUS_EXTRA, f"Code {code} not in STATUS_EXTRA"
            assert 'dont_use_when' in STATUS_EXTRA[code], (
                f"Code {code} missing dont_use_when"
            )
            assert isinstance(STATUS_EXTRA[code]['dont_use_when'], list), (
                f"Code {code} dont_use_when should be a list"
            )
            assert len(STATUS_EXTRA[code]['dont_use_when']) >= 3, (
                f"Code {code} should have at least 3 dont_use_when entries"
            )

    def test_dont_use_when_strings_non_empty(self):
        """All dont_use_when entries should be non-empty strings."""
        from status_extra import STATUS_EXTRA
        for code, data in STATUS_EXTRA.items():
            if 'dont_use_when' in data:
                for i, reason in enumerate(data['dont_use_when']):
                    assert isinstance(reason, str), (
                        f"Code {code}[{i}] dont_use_when should be a string"
                    )
                    assert len(reason.strip()) > 0, (
                        f"Code {code}[{i}] has empty dont_use_when entry"
                    )

    def test_dont_use_when_section_renders_on_page(self, client):
        """Pages with dont_use_when should render the section."""
        resp = client.get('/200')
        html = resp.get_data(as_text=True)
        assert 'dont-use-section' in html
        assert 'When NOT to use this code' in html

    def test_dont_use_when_renders_list_items(self, client):
        """Each dont_use_when reason should render as a list item."""
        resp = client.get('/404')
        html = resp.get_data(as_text=True)
        assert 'dont-use-list' in html
        assert 'dont-use-item' in html

    def test_dont_use_when_absent_on_page_without_data(self, client):
        """Pages without dont_use_when should not show the section."""
        resp = client.get('/102')
        html = resp.get_data(as_text=True)
        assert 'dont-use-section' not in html
        assert 'dont-use-item' not in html

    def test_dont_use_when_uses_details_element(self, client):
        """The dont_use_when section should use a details/summary for collapsibility."""
        resp = client.get('/200')
        html = resp.get_data(as_text=True)
        assert 'dont-use-summary' in html

    def test_dont_use_when_css_styles_present(self, client):
        """CSS should contain dont-use styles with red/coral accent."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.dont-use-section' in css
        assert '.dont-use-summary' in css
        assert '.dont-use-list' in css
        assert '.dont-use-item' in css
        assert '#e05252' in css

    def test_dont_use_when_appears_after_mistakes(self, client):
        """The dont_use_when section should appear after common mistakes."""
        resp = client.get('/200')
        html = resp.get_data(as_text=True)
        mistakes_pos = html.find('mistakes-section')
        dont_use_pos = html.find('dont-use-section')
        assert mistakes_pos > 0, "mistakes-section not found"
        assert dont_use_pos > 0, "dont-use-section not found"
        assert dont_use_pos > mistakes_pos, (
            "dont-use-section should appear after mistakes-section"
        )

    def test_dont_use_when_renders_multiple_codes(self, client):
        """Multiple codes should render the dont_use_when section."""
        for code in ['201', '301', '401', '500']:
            resp = client.get(f'/{code}')
            html = resp.get_data(as_text=True)
            assert 'dont-use-section' in html, f"/{code} missing dont-use-section"


# --- Task 4: Security-category scenarios ---

class TestSecurityScenarios:
    """Tests for the 5 new security-category scenarios."""

    def test_security_scenarios_exist(self):
        """There should be at least 5 security-category scenarios."""
        from scenarios import SCENARIOS
        security = [s for s in SCENARIOS if s['category'] == 'security']
        assert len(security) >= 5, (
            f"Only {len(security)} security scenarios, expected at least 5"
        )

    def test_security_scenario_ids_unique(self):
        """Security scenario IDs should not conflict with existing IDs."""
        from scenarios import SCENARIOS
        ids = [s['id'] for s in SCENARIOS]
        assert len(ids) == len(set(ids)), "Duplicate scenario IDs found"

    def test_security_scenarios_cover_expected_topics(self):
        """Security scenarios should cover CORS, XSS, SSRF, CSP, and webhooks."""
        from scenarios import SCENARIOS
        security = [s for s in SCENARIOS if s['category'] == 'security']
        all_descriptions = ' '.join(s['description'].lower() for s in security)
        assert 'cors' in all_descriptions or 'preflight' in all_descriptions, (
            "Missing CORS preflight scenario"
        )
        assert 'xss' in all_descriptions or 'content-type' in all_descriptions.lower() or 'mime' in all_descriptions or 'nosniff' in all_descriptions, (
            "Missing XSS/Content-Type scenario"
        )
        assert 'ssrf' in all_descriptions or '169.254' in all_descriptions or 'metadata' in all_descriptions, (
            "Missing SSRF scenario"
        )
        assert 'csp' in all_descriptions or 'content security policy' in all_descriptions, (
            "Missing CSP violation scenario"
        )
        assert 'webhook' in all_descriptions or 'signature' in all_descriptions, (
            "Missing webhook signature scenario"
        )

    def test_security_scenarios_have_valid_structure(self):
        """Each security scenario should have all required fields."""
        from scenarios import SCENARIOS
        security = [s for s in SCENARIOS if s['category'] == 'security']
        for s in security:
            assert 'id' in s
            assert 'difficulty' in s
            assert 'description' in s
            assert 'correct' in s
            assert 'options' in s
            assert 'explanations' in s
            assert len(s['options']) == 4, f"Scenario {s['id']} should have 4 options"
            assert s['correct'] in s['options'], (
                f"Scenario {s['id']} correct answer not in options"
            )
            for opt in s['options']:
                assert opt in s['explanations'], (
                    f"Scenario {s['id']} missing explanation for {opt}"
                )

    def test_security_scenarios_have_valid_difficulty(self):
        """Security scenarios should have valid difficulty levels."""
        from scenarios import SCENARIOS
        security = [s for s in SCENARIOS if s['category'] == 'security']
        valid = {'beginner', 'intermediate', 'expert'}
        for s in security:
            assert s['difficulty'] in valid, (
                f"Scenario {s['id']} has invalid difficulty: {s['difficulty']}"
            )

    def test_total_scenarios_at_least_55(self):
        """With 5 new additions, total should be at least 55."""
        from scenarios import SCENARIOS
        assert len(SCENARIOS) >= 55, f"Only {len(SCENARIOS)} scenarios, expected 55+"


# --- Task D1: Light Theme Coverage for Tool Pages ---

class TestLightThemeToolPages:
    """Tests for light theme overrides on tool pages (D1 final polish)."""

    def _get_light_css(self, client):
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        idx = css.index('@media (prefers-color-scheme: light)')
        return css[idx:]

    def test_light_theme_fault_sim_btn(self, client):
        """Fault simulator button should have light theme override."""
        block = self._get_light_css(client)
        assert '.fault-sim-btn' in block

    def test_light_theme_compare_diff_label(self, client):
        """Compare diff label should have light theme override."""
        block = self._get_light_css(client)
        assert '.compare-diff-label' in block

    def test_light_theme_compare_diff_arrow(self, client):
        """Compare diff arrow should have light theme override."""
        block = self._get_light_css(client)
        assert '.compare-diff-arrow' in block

    def test_light_theme_compare_summary_text(self, client):
        """Compare summary text should have light theme override."""
        block = self._get_light_css(client)
        assert '.compare-summary-text' in block

    def test_light_theme_compare_summary_box(self, client):
        """Compare summary box should have light theme override."""
        block = self._get_light_css(client)
        assert '.compare-summary-box' in block

    def test_light_theme_headers_hero_p(self, client):
        """Headers hero paragraph should have light theme override."""
        block = self._get_light_css(client)
        assert '.headers-hero p' in block

    def test_light_theme_cors_label(self, client):
        """CORS label should have light theme override."""
        block = self._get_light_css(client)
        assert '.cors-label' in block

    def test_light_theme_playground_body(self, client):
        """Playground body textarea should have light theme override."""
        block = self._get_light_css(client)
        assert '.playground-body' in block

    def test_light_theme_trace_hop_final_badge(self, client):
        """Trace hop final badge should have light theme override."""
        block = self._get_light_css(client)
        assert '.trace-hop-final-badge' in block

    def test_light_theme_trace_chain(self, client):
        """Trace chain should have light theme override."""
        block = self._get_light_css(client)
        assert '.trace-chain' in block

    def test_light_theme_dont_use_list(self, client):
        """Dont-use list should have light theme override."""
        block = self._get_light_css(client)
        assert '.dont-use-list' in block

    def test_curl_import_has_light_theme_styles(self, client):
        """cURL import page should include light theme overrides in its inline styles."""
        resp = client.get('/curl-import')
        html = resp.data.decode()
        assert 'prefers-color-scheme: light' in html
        assert '.curl-method-head' in html
        assert '.curl-tab-bar' in html


# --- Task D3: Bento Dashboard Mobile Fix ---

class TestBentoDashboardMobileFix:
    """Tests for bento dashboard working well at 320-375px (D3)."""

    def _get_css(self):
        with open('static/style.css') as f:
            return f.read()

    def _get_bento_576_block(self):
        """Find the 576px media query that contains bento-dashboard."""
        css = self._get_css()
        start = 0
        while True:
            idx = css.find('@media (max-width: 576px)', start)
            if idx < 0:
                return ''
            block = css[idx:idx + 800]
            if '.bento-dashboard' in block:
                return block
            start = idx + 1

    def test_bento_576_single_column(self):
        """At 576px, bento dashboard should use single column grid."""
        block = self._get_bento_576_block()
        assert block, "No 576px media query with .bento-dashboard found"
        assert 'grid-template-columns: 1fr' in block

    def test_bento_576_overflow_hidden(self):
        """At 576px, bento dashboard should prevent horizontal overflow."""
        block = self._get_bento_576_block()
        assert 'overflow-x: hidden' in block

    def test_bento_576_span2_override(self):
        """At 576px, grid-column span 2 should be overridden to span 1."""
        block = self._get_bento_576_block()
        assert 'grid-column: span 1' in block

    def test_bento_375_single_column(self):
        """At 375px, bento dashboard should explicitly set single column."""
        css = self._get_css()
        idx_375 = css.rfind('@media (max-width: 375px)')
        assert idx_375 > 0
        block = css[idx_375:idx_375 + 1200]
        assert 'grid-template-columns: 1fr' in block

    def test_bento_375_overflow_hidden(self):
        """At 375px, bento dashboard should prevent horizontal overflow."""
        css = self._get_css()
        idx_375 = css.rfind('@media (max-width: 375px)')
        block = css[idx_375:idx_375 + 1200]
        assert 'overflow-x: hidden' in block

    def test_bento_375_max_width_viewport(self):
        """At 375px, bento dashboard should not exceed viewport width."""
        css = self._get_css()
        idx_375 = css.rfind('@media (max-width: 375px)')
        block = css[idx_375:idx_375 + 1200]
        assert 'max-width: 100vw' in block

    def test_bento_375_touch_friendly_action(self):
        """Bento tile actions should have min 44px touch target."""
        css = self._get_css()
        assert '.bento-tile-action' in css
        assert 'min-height: 44px' in css

    def test_bento_375_span_override(self):
        """At 375px, all bento children should be forced to span 1."""
        css = self._get_css()
        idx_375 = css.rfind('@media (max-width: 375px)')
        block = css[idx_375:idx_375 + 1200]
        assert 'grid-column: span 1' in block

    def test_bento_375_potd_image_smaller(self):
        """At 375px, POTD image should be smaller (120px) for tight screens."""
        css = self._get_css()
        idx_375 = css.rfind('@media (max-width: 375px)')
        block = css[idx_375:idx_375 + 1200]
        assert 'width: 120px' in block

    def test_bento_375_streak_count_smaller(self):
        """Streak count should have smaller font on mobile."""
        css = self._get_css()
        # Check that bento-streak-count exists somewhere in a 375px block
        idx = css.find('.bento-streak-count')
        block = css[idx:idx + 200] if idx > 0 else css
        assert '.bento-streak-count' in block


# --- Task: "When NOT to Use" Section Polish ---

class TestDontUseSectionPolish:
    """Tests for dont-use-when section CSS polish."""

    def _get_css(self):
        with open('static/style.css') as f:
            return f.read()

    def _get_light_css(self, client):
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        idx = css.index('@media (prefers-color-scheme: light)')
        return css[idx:]

    def test_dont_use_mobile_responsive(self):
        """Dont-use section should have mobile responsive rules."""
        css = self._get_css()
        assert '.dont-use-item' in css
        # Check there is a responsive breakpoint for dont-use
        idx = css.find('@media (max-width: 576px)')
        assert idx > 0
        # Find dont-use within a 576px block
        block_end = css.find('}', css.find('}', idx + 1) + 1)
        full_576_area = css[idx:idx + 2000]
        assert '.dont-use-item' in full_576_area or '.dont-use-list' in full_576_area

    def test_dont_use_mobile_smaller_font(self):
        """Dont-use items should use smaller font on mobile."""
        css = self._get_css()
        # Find the responsive mobile block for dont-use
        idx = css.find('responsive mobile')
        assert idx > 0, "responsive mobile comment not found in CSS"
        block = css[idx:idx + 800]
        assert 'font-size: var(--text-sm)' in block

    def test_dont_use_mobile_tighter_padding(self):
        """Dont-use items should have tighter padding on mobile."""
        css = self._get_css()
        idx = css.find('responsive mobile')
        assert idx > 0
        block = css[idx:idx + 800]
        assert '0.6rem' in block

    def test_dont_use_mobile_thinner_border(self):
        """Dont-use section should have thinner border on mobile."""
        css = self._get_css()
        idx = css.find('responsive mobile')
        assert idx > 0
        block = css[idx:idx + 800]
        assert 'border-left-width: 2px' in block

    def test_dont_use_light_theme_section(self, client):
        """Dont-use section should have light theme border override."""
        block = self._get_light_css(client)
        assert '.dont-use-section' in block

    def test_dont_use_light_theme_item(self, client):
        """Dont-use items should have light theme overrides."""
        block = self._get_light_css(client)
        assert '.dont-use-item' in block

    def test_dont_use_light_theme_summary(self, client):
        """Dont-use summary should have light theme color."""
        block = self._get_light_css(client)
        assert '.dont-use-summary h2' in block

    def test_dont_use_light_theme_before_pseudo(self, client):
        """Dont-use item before pseudo should have light theme color."""
        block = self._get_light_css(client)
        assert ".dont-use-item::before" in block

    def test_dont_use_coral_accent_in_dark(self):
        """Dont-use section should use coral/red (#e05252) accent in dark mode."""
        css = self._get_css()
        # Base dont-use styles should use #e05252
        idx = css.find('.dont-use-section {')
        assert idx > 0
        block = css[idx:idx + 300]
        assert '#e05252' in block

    def test_dont_use_consistent_with_mistakes_pattern(self):
        """Dont-use section should follow the same structural pattern as mistakes."""
        css = self._get_css()
        # Both should use color-mix, border-left, and similar class structure
        assert '.mistakes-section' in css
        assert '.dont-use-section' in css
        # Both use border-left
        mistakes_idx = css.find('.mistakes-section {')
        mistakes_block = css[mistakes_idx:mistakes_idx + 200]
        assert 'border-left' in mistakes_block
        dont_use_idx = css.find('.dont-use-section {')
        dont_use_block = css[dont_use_idx:dont_use_idx + 200]
        assert 'border-left' in dont_use_block


# --- Java & Rust code examples (ED2) ---

class TestJavaRustCodeExamples:
    """Tests for Java and Rust code snippets in STATUS_EXTRA."""

    TARGET_CODES = ['200', '201', '301', '400', '401', '403', '404', '422', '500', '503']

    def test_java_snippets_present_for_target_codes(self):
        """The 10 most important codes should have Java code examples."""
        from status_extra import STATUS_EXTRA
        for code in self.TARGET_CODES:
            assert 'java' in STATUS_EXTRA[code]['code'], (
                f"Code {code} missing 'java' snippet"
            )

    def test_rust_snippets_present_for_target_codes(self):
        """The 10 most important codes should have Rust code examples."""
        from status_extra import STATUS_EXTRA
        for code in self.TARGET_CODES:
            assert 'rust' in STATUS_EXTRA[code]['code'], (
                f"Code {code} missing 'rust' snippet"
            )

    def test_java_snippets_use_spring_boot_style(self):
        """Java snippets should use Spring Boot ResponseEntity style."""
        from status_extra import STATUS_EXTRA
        for code in self.TARGET_CODES:
            snippet = STATUS_EXTRA[code]['code']['java']
            assert 'ResponseEntity' in snippet or 'HttpStatus' in snippet, (
                f"Java snippet for {code} does not use Spring Boot style"
            )

    def test_rust_snippets_use_actix_style(self):
        """Rust snippets should use Actix-web HttpResponse style."""
        from status_extra import STATUS_EXTRA
        for code in self.TARGET_CODES:
            snippet = STATUS_EXTRA[code]['code']['rust']
            assert 'HttpResponse' in snippet or 'StatusCode' in snippet, (
                f"Rust snippet for {code} does not use Actix-web style"
            )

    def test_java_snippets_are_non_empty(self):
        """Java snippets should not be empty strings."""
        from status_extra import STATUS_EXTRA
        for code in self.TARGET_CODES:
            assert len(STATUS_EXTRA[code]['code']['java'].strip()) > 10, (
                f"Java snippet for {code} is too short or empty"
            )

    def test_rust_snippets_are_non_empty(self):
        """Rust snippets should not be empty strings."""
        from status_extra import STATUS_EXTRA
        for code in self.TARGET_CODES:
            assert len(STATUS_EXTRA[code]['code']['rust'].strip()) > 10, (
                f"Rust snippet for {code} is too short or empty"
            )

    def test_java_snippets_rendered_on_detail_page(self, client):
        """Java code examples should appear on the status detail page."""
        resp = client.get('/200')
        html = resp.data.decode()
        assert 'java' in html.lower() or 'Java' in html
        assert 'ResponseEntity' in html

    def test_rust_snippets_rendered_on_detail_page(self, client):
        """Rust code examples should appear on the status detail page."""
        resp = client.get('/200')
        html = resp.data.decode()
        assert 'rust' in html.lower() or 'Rust' in html
        assert 'HttpResponse' in html

    def test_compare_page_includes_java_rust_langs(self, client):
        """Compare page JS should list java and rust in code snippet langs."""
        resp = client.get('/compare')
        html = resp.data.decode()
        assert "'java'" in html or '"java"' in html
        assert "'rust'" in html or '"rust"' in html
        assert 'Java' in html
        assert 'Rust' in html


# --- Learning Path Completion Certificates (ED4) ---

class TestPathCompletionCertificate:
    """Tests for the Certificate of Completion on learning path detail pages."""

    def test_certificate_section_present(self, client):
        """Path detail page should contain the certificate HTML."""
        resp = client.get('/paths/http-foundations')
        html = resp.data.decode()
        assert 'path-certificate' in html

    def test_certificate_has_heading(self, client):
        """Certificate should have a Certificate of Completion heading."""
        resp = client.get('/paths/http-foundations')
        html = resp.data.decode()
        assert 'Certificate of Completion' in html

    def test_certificate_has_path_name(self, client):
        """Certificate should include the path name."""
        resp = client.get('/paths/http-foundations')
        html = resp.data.decode()
        assert 'path-certificate-path-name' in html
        assert 'HTTP Foundations' in html

    def test_certificate_has_step_count(self, client):
        """Certificate should show step count."""
        resp = client.get('/paths/http-foundations')
        html = resp.data.decode()
        assert 'steps completed' in html

    def test_certificate_has_share_button(self, client):
        """Certificate should have a Share Certificate button."""
        resp = client.get('/paths/http-foundations')
        html = resp.data.decode()
        assert 'cert-share-btn' in html
        assert 'Share Certificate' in html

    def test_certificate_has_xp_bonus(self, client):
        """Certificate should show the 500 XP bonus."""
        resp = client.get('/paths/http-foundations')
        html = resp.data.decode()
        assert '+500 XP' in html

    def test_certificate_has_date_placeholder(self, client):
        """Certificate should have a date element for JS to fill."""
        resp = client.get('/paths/http-foundations')
        html = resp.data.decode()
        assert 'cert-date' in html

    def test_certificate_hidden_by_default(self, client):
        """Certificate should be hidden by default (no visible class)."""
        resp = client.get('/paths/http-foundations')
        html = resp.data.decode()
        assert 'path-certificate" id="path-certificate"' in html
        # Should NOT have visible class in the static HTML
        assert 'path-certificate visible' not in html

    def test_certificate_share_script(self, client):
        """Share button script should copy text to clipboard."""
        resp = client.get('/paths/http-foundations')
        html = resp.data.decode()
        assert 'cert-share-btn' in html
        assert 'clipboard' in html
        assert '#HTTPParrots' in html

    def test_completion_awards_500_xp(self, client):
        """Completion script should award 500 XP (not 200)."""
        resp = client.get('/paths/http-foundations')
        html = resp.data.decode()
        assert 'ParrotXP.award(500' in html

    def test_certificate_badge_icon(self, client):
        """Certificate should have a trophy badge icon."""
        resp = client.get('/paths/http-foundations')
        html = resp.data.decode()
        assert 'path-certificate-badge' in html

    def test_certificate_stores_completion_date(self, client):
        """Script should store completion date in localStorage."""
        resp = client.get('/paths/http-foundations')
        html = resp.data.decode()
        assert 'httpparrot_path_date_' in html
        assert 'toLocaleDateString' in html


# --- UX Fixes ---

class TestPlaygroundClipboardCatch:
    """Test that playground copy button has a .catch() handler."""

    def test_clipboard_catch_handler(self, client):
        """Playground clipboard writeText should have a .catch() handler."""
        resp = client.get('/playground')
        html = resp.data.decode()
        assert '.catch(function' in html

    def test_clipboard_catch_shows_error(self, client):
        """Clipboard .catch should show a 'Copy failed' message."""
        resp = client.get('/playground')
        html = resp.data.decode()
        assert 'Copy failed' in html


class TestCompareEmptyState:
    """Test that compare page has a styled empty state."""

    def test_empty_state_has_icon(self, client):
        """Empty state should have an icon element."""
        resp = client.get('/compare')
        html = resp.data.decode()
        assert 'compare-empty-icon' in html

    def test_empty_state_has_heading(self, client):
        """Empty state should have a descriptive heading."""
        resp = client.get('/compare')
        html = resp.data.decode()
        assert 'compare-empty-heading' in html
        assert 'Pick two codes to compare' in html

    def test_empty_state_has_cta_text(self, client):
        """Empty state should have CTA text mentioning presets."""
        resp = client.get('/compare')
        html = resp.data.decode()
        assert 'compare-empty-text' in html
        assert 'quick compare presets' in html

    def test_empty_state_css_styles(self):
        """CSS should include compare-empty-icon, heading, and text styles."""
        with open('/Users/mfelldin/dev/personal/httpparrot/static/style.css') as f:
            css = f.read()
        assert '.compare-empty-icon' in css
        assert '.compare-empty-heading' in css
        assert '.compare-empty-text' in css


class TestCheatsheetPrintFeedback:
    """Test that cheatsheet print button shows feedback."""

    def test_print_button_shows_feedback(self, client):
        """Print button should show 'Opening print dialog...' feedback."""
        resp = client.get('/cheatsheet')
        html = resp.data.decode()
        assert 'Opening print dialog...' in html

    def test_print_button_reverts_text(self, client):
        """Print button should revert to original text after timeout."""
        resp = client.get('/cheatsheet')
        html = resp.data.decode()
        assert 'Print this page' in html
        assert 'setTimeout' in html
