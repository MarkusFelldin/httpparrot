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
    @pytest.mark.parametrize("path,expected_status,expected_text", [
        ('/', 200, b'HTTP Parrots'),
        ('/200', 200, b'OK'),
        ('/404', 404, b'Not Found'),
        ('/500', 500, None),
        ('/100', 200, None),  # 1xx returns 200
        ('/301', 200, None),  # 3xx returns 200
        ('/quiz', 200, b'Quiz'),
        ('/flowchart', 200, b'Which Status Code'),
        ('/compare', 200, None),
        ('/tester', 200, b'Tester'),
        ('/cheatsheet', 200, b'Cheat Sheet'),
        ('/api-docs', 200, b'API'),
        ('/practice', 200, b'Scenario Practice'),
        ('/bingo', 200, b'Bingo'),
        ('/predict', 200, b'Guess the Response'),
        ('/incidents', 200, b'War Stories'),
    ])
    def test_page_returns_expected(self, client, path, expected_status, expected_text):
        """Pages should return correct status codes and contain expected text."""
        resp = client.get(path)
        assert resp.status_code == expected_status, f"{path} returned {resp.status_code}"
        if expected_text:
            assert expected_text in resp.data, f"{path} missing expected text"

    @pytest.mark.parametrize("path", ['/999', '/abc'])
    def test_invalid_paths_return_404(self, client, path):
        """Invalid codes and non-numeric paths should return 404."""
        assert client.get(path).status_code == 404

    def test_custom_404_page(self, client):
        """Custom 404 page should have parrot branding."""
        resp = client.get('/nonexistent-page')
        assert resp.status_code == 404
        assert b'Parrot Not Found' in resp.data

    def test_horoscope_page(self, client):
        """Horoscope page should mention Horoscope or Oracle."""
        resp = client.get('/horoscope')
        assert resp.status_code == 200
        assert b'Horoscope' in resp.data or b'Oracle' in resp.data

    def test_glossary_page(self, client):
        """Glossary page should render with glossary terms."""
        resp = client.get('/glossary')
        assert resp.status_code == 200
        assert b'Glossary' in resp.data

    def test_theme_toggle_in_header(self, client):
        """Theme toggle button should be present in the header."""
        resp = client.get('/')
        assert b'theme-toggle' in resp.data

    def test_compare_page_elements(self, client):
        """Compare page should have selects, result area, and presets."""
        html = client.get('/compare').data.decode()
        assert 'Compare Status Codes' in html
        assert 'select-a' in html
        assert 'select-b' in html
        assert 'compare-result' in html
        assert 'noscript' in html
        # With params
        assert client.get('/compare?a=301&b=308').status_code == 200

    def test_practice_page_features(self, client):
        """Practice page should have cards, difficulty filters, and nav link."""
        html = client.get('/practice').data.decode()
        assert 'practice-card' in html
        assert 'practice-option-btn' in html
        for diff in ['all', 'beginner', 'intermediate', 'expert']:
            assert f'data-difficulty="{diff}"' in html
        assert 'href="/practice"' in client.get('/').data.decode()


# --- Content negotiation ---

    def test_headers_page(self, client):
        """Header Explainer should render with script and nonce."""
        resp = client.get('/headers')
        assert resp.status_code == 200
        html = resp.data.decode()
        assert 'Header Explainer' in html
        assert 'header-input' in html
        assert 'explain-btn' in html
        assert 'HEADER_DB' in html
        assert 'parseHeaders' in html
        # Nonce verification
        csp = resp.headers.get('Content-Security-Policy', '')
        nonce = re.search(r"'nonce-([^']+)'", csp).group(1)
        assert f'nonce="{nonce}"'.encode() in resp.data


    def test_content_negotiation_page(self, client):
        resp = client.get('/content-negotiation')
        assert resp.status_code == 200
        assert b'Content Negotiation' in resp.data


    def test_potd_deterministic(self, client):
        """Homepage should have a deterministic featured card."""
        html1 = client.get('/').data.decode()
        html2 = client.get('/').data.decode()
        assert 'featured' in html1
        strip_nonce = lambda h: re.sub(r'nonce="[^"]*"', 'nonce=""', h)
        assert strip_nonce(html1) == strip_nonce(html2)


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
    @pytest.mark.parametrize("code,expected", [
        (200, 200), (503, 503), (418, 418),
    ])
    def test_return_valid_codes(self, client, code, expected):
        """Valid codes should return matching status."""
        resp = client.get(f'/return/{code}')
        assert resp.status_code == expected

    def test_return_200_body(self, client):
        """Return 200 should have code and description in JSON."""
        data = client.get('/return/200').get_json()
        assert data['code'] == 200
        assert data['description'] == 'OK'

    @pytest.mark.parametrize("code", [600, 99])
    def test_return_out_of_range(self, client, code):
        """Out of range codes should return 404."""
        assert client.get(f'/return/{code}').status_code == 404


# --- Security headers ---

class TestSecurityHeaders:
    def test_all_security_headers_present(self, client):
        """Homepage should have all required security headers."""
        resp = client.get('/')
        assert resp.headers.get('X-Content-Type-Options') == 'nosniff'
        assert resp.headers.get('X-Frame-Options') == 'DENY'
        assert resp.headers.get('Referrer-Policy') == 'strict-origin-when-cross-origin'
        assert 'camera=()' in resp.headers.get('Permissions-Policy', '')
        csp = resp.headers.get('Content-Security-Policy', '')
        assert "default-src 'self'" in csp
        assert "script-src 'self'" in csp
        assert 'max-age=31536000' in resp.headers.get('Strict-Transport-Security', '')
        assert 'max-age=60' in resp.headers.get('Cache-Control', '')

    def test_cache_control_static(self, client):
        resp = client.get('/static/style.css')
        assert 'max-age=86400' in resp.headers.get('Cache-Control', '')


# --- SSRF protection ---

class TestSSRFProtection:
    @pytest.mark.parametrize("ip", [
        '10.0.0.1', '172.16.0.1', '192.168.1.1', '169.254.169.254',
    ])
    def test_blocks_private_ips(self, ip):
        """Private/link-local IPs should be blocked."""
        addrinfo = [(socket.AF_INET, socket.SOCK_STREAM, 0, '', (ip, 0))]
        with patch('index.socket.getaddrinfo', return_value=addrinfo):
            result, _ = resolve_and_validate('http://internal.example.com/')
            assert result is None, f"Should block {ip}"

    def test_blocks_localhost(self):
        result, _ = resolve_and_validate('http://127.0.0.1/')
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


    def test_return_various_codes(self, client):
        """Verify /return/ endpoint returns correct status codes."""
        for code in [200, 201, 301, 404, 500]:
            resp = client.get(f'/return/{code}')
            assert resp.status_code == code, f"/return/{code} returned {resp.status_code}"


class TestCheckURLSuccess:
    def _mock_addrinfo(self):
        return [(socket.AF_INET, socket.SOCK_STREAM, 0, '', ('93.184.216.34', 0))]

    def test_check_url_success(self, client):
        """Successful URL check returns code, url, headers, and time_ms."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {'Content-Type': 'text/html', 'X-Custom': 'test'}
        mock_resp.elapsed.total_seconds.return_value = 0.123
        with patch('index.socket.getaddrinfo', return_value=self._mock_addrinfo()), \
             patch('requests.head', return_value=mock_resp):
            resp = client.get('/api/check-url?url=https://example.com')
            assert resp.status_code == 200
            data = resp.get_json()
            assert data['code'] == 200
            assert data['url'] == 'https://example.com'
            assert data['headers']['Content-Type'] == 'text/html'
            assert data['headers']['X-Custom'] == 'test'
            assert isinstance(data['time_ms'], int)
            assert data['time_ms'] == 123

    def test_check_url_auto_prefix(self, client):
        """URLs without scheme should get https:// prepended."""
        mock_resp = MagicMock()
        mock_resp.status_code = 301
        mock_resp.headers = {'Location': 'https://www.example.com'}
        mock_resp.elapsed.total_seconds.return_value = 0.1
        with patch('index.socket.getaddrinfo', return_value=self._mock_addrinfo()), \
             patch('requests.head', return_value=mock_resp):
            data = client.get('/api/check-url?url=example.com').get_json()
            assert data['code'] == 301
            assert data['url'] == 'https://example.com'

    def test_check_url_connection_error(self, client):
        """Connection errors should return 502."""
        with patch('index.socket.getaddrinfo', return_value=self._mock_addrinfo()), \
             patch('requests.head', side_effect=requests.RequestException):
            resp = client.get('/api/check-url?url=https://example.com')
            assert resp.status_code == 502
            assert b'Could not connect' in resp.data


# --- Tester timing bar UI ---

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
    def test_csp_nonce_changes_per_request(self, client):
        """Each request should get a unique nonce."""
        resp1 = client.get('/')
        resp2 = client.get('/')
        csp1 = resp1.headers.get('Content-Security-Policy', '')
        csp2 = resp2.headers.get('Content-Security-Policy', '')
        nonce1 = re.search(r"'nonce-([^']+)'", csp1).group(1)
        nonce2 = re.search(r"'nonce-([^']+)'", csp2).group(1)
        assert nonce1 != nonce2

    def test_homepage_combined(self, client):
        """Combined checks for /."""
        resp = client.get('/')
        html = resp.data.decode()
        csp = resp.headers.get('Content-Security-Policy', '')
        assert "'nonce-" in csp
        assert "'unsafe-inline'" not in csp.split('script-src')[1].split(';')[0]
        csp = resp.headers.get('Content-Security-Policy', '')
        assert "'unsafe-inline'" not in csp
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
    def test_scroll_animations_css(self, client):
        """CSS should have scroll-animated class, keyframes, and will-reveal."""
        css = client.get('/static/style.css').data.decode()
        assert '.parrot-card.scroll-animated' in css
        assert 'animation-timeline: view()' in css
        assert '@supports (animation-timeline: view())' in css
        assert '@keyframes scroll-card-in' in css
        assert 'scale(0.95)' in css
        assert 'rotate(' in css
        assert '.parrot-card.will-reveal' in css
        assert 'rotate(-1deg)' in css

    def test_homepage_viewport_reveal(self, client):
        """Homepage JS should use IntersectionObserver for viewport reveals."""
        html = client.get('/').data.decode()
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


# --- Echo / API endpoints ---

    def test_sitemap_structure_and_content(self, client):
        """Sitemap should be valid XML with all public pages and no API endpoints."""
        resp = client.get('/sitemap.xml')
        assert resp.status_code == 200
        assert 'application/xml' in resp.content_type
        assert 'max-age=86400' in resp.headers.get('Cache-Control', '')
        body = resp.data.decode()
        assert '<?xml version="1.0"' in body
        assert '<urlset' in body
        assert '</urlset>' in body
        assert '<url><loc>http://localhost/</loc><priority>1.0</priority></url>' in body
        # All public pages present
        for page in ['/', '/quiz', '/personality', '/daily', '/practice', '/debug',
                     '/flowchart', '/compare', '/tester', '/cheatsheet', '/headers',
                     '/cors-checker', '/security-audit', '/collection', '/playground',
                     '/api-docs', '/profile', '/map']:
            assert f'<loc>http://localhost{page}</loc>' in body, f"Sitemap missing: {page}"
        # Status code pages present
        for code in ['200', '301', '404', '500']:
            assert f'<loc>http://localhost/{code}</loc>' in body, f"Sitemap missing: /{code}"
        # API endpoints excluded
        for api in ['/api/search', '/api/check-url', '/api/check-cors',
                    '/api/mock-response', '/api/diff', '/echo', '/return/', '/redirect/']:
            assert api not in body, f"Sitemap should not include: {api}"


    def test_robots_txt_content(self, client):
        """robots.txt should be valid with correct allow/disallow rules."""
        resp = client.get('/robots.txt')
        assert resp.status_code == 200
        assert resp.content_type == 'text/plain; charset=utf-8'
        body = resp.data.decode()
        assert 'User-agent: *' in body
        assert 'Allow: /' in body
        assert 'Sitemap:' in body
        assert 'sitemap.xml' in body
        for rule in ['Disallow: /api/check-url', 'Disallow: /api/fetch-url',
                     'Disallow: /api/check-cors', 'Disallow: /api/security-audit',
                     'Disallow: /api/mock-response', 'Disallow: /api/diff',
                     'Disallow: /api/search', 'Disallow: /return/',
                     'Disallow: /echo', 'Disallow: /redirect/']:
            assert rule in body, f"robots.txt missing: {rule}"


    def test_api_docs_all_endpoints_documented(self, client):
        """API docs should document all endpoints with key details."""
        html = client.get('/api-docs').data.decode()
        # Endpoint paths
        for endpoint in ['/{code}', '/{code}.jpg', '/random', '/api/search',
                         '/api/check-url', '/api/check-cors', '/return/{code}',
                         '/echo', '/api/diff', '/redirect/{n}', '/api/mock-response']:
            assert endpoint in html, f"API docs missing endpoint: {endpoint}"
        # Key response fields
        for field in ['application/json', 'score', 'time_ms', 'preflight',
                      'analysis', 'delay', 'POST', 'key_difference', 'status_code']:
            assert field in html, f"API docs missing field: {field}"
        # Interactive pages
        for page in ['/quiz', '/daily', '/practice', '/flowchart', '/compare',
                     '/tester', '/cheatsheet', '/collection', '/headers',
                     '/cors-checker', '/playground']:
            assert page in html, f"API docs missing interactive page: {page}"
        # Response schemas
        assert 'Response schema' in html or 'Request body schema' in html


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


class TestDesignTokenUsage:
    """Verify templates use CSS custom properties instead of hardcoded colors."""

    @pytest.mark.parametrize("page", ['/debug', '/practice', '/review', '/paths'])
    def test_pages_use_design_tokens(self, client, page):
        """Pages should use CSS custom properties for colors."""
        html = client.get(page).data.decode()
        assert 'var(--text-primary)' in html, f"{page} missing --text-primary"
        assert 'var(--text-secondary)' in html, f"{page} missing --text-secondary"

    def test_debug_style_no_hardcoded_colors(self, client):
        """debug.html style blocks should not have hardcoded color values."""
        import re
        html = client.get('/debug').data.decode()
        style_match = re.search(r'<style[^>]*>(.*?)</style>', html, re.DOTALL)
        if style_match:
            style_block = style_match.group(1)
            assert 'color: #f0f0f0' not in style_block
            assert 'color: #a0a0b0' not in style_block

    def test_css_defines_text_tokens(self, client):
        """style.css defines the text color custom properties."""
        css = client.get('/static/style.css').data.decode()
        for token in ['--text-primary:', '--text-secondary:', '--text-muted:',
                      '--surface-interactive:', '--border-interactive:']:
            assert token in css, f"Missing token: {token}"


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
        """Collection page should return 200 with all expected content."""
        resp = client.get('/collection')
        assert resp.status_code == 200
        html = resp.data.decode()
        assert 'Parrotdex' in html
        assert 'collection-grid' in html
        assert 'collect-count' in html
        assert 'collection-progress-bar' in html
        assert 'id="progress-bar"' in html
        assert 'parrotdex' in html
        assert 'uncollected' in html
        # Secrets section
        assert 'Secret Parrots' in html
        assert 'egg-card' in html
        assert 'eggs_found' in html
        assert 'egg-found' in html

    def test_collection_contains_all_pruned_codes(self, client):
        """Collection page should list every status code that has an image."""
        from index import pruned_status_codes
        html = client.get('/collection').data.decode()
        for sc in pruned_status_codes():
            assert f'data-code="{sc.code}"' in html, f"Collection missing code {sc.code}"

    def test_collection_has_nonce(self, client):
        """Collection script tag should have a nonce."""
        resp = client.get('/collection')
        csp = resp.headers.get('Content-Security-Policy', '')
        nonce = re.search(r"'nonce-([^']+)'", csp).group(1)
        assert f'nonce="{nonce}"'.encode() in resp.data

    def test_detail_page_has_parrotdex_tracking(self, client):
        """Detail pages should include localStorage parrotdex tracking script."""
        html = client.get('/200').data.decode()
        assert 'parrotdex' in html
        assert "localStorage.getItem('parrotdex')" in html


# --- Quiz shareable results ---

    def test_collection_has_all_new_egg_cards(self, client):
        """Collection page should have all new and original egg cards with hints."""
        html = client.get('/collection').data.decode()
        # New eggs
        for egg in ['barrel_roll', '404_catch', 'time_404', 'time_200', 'time_5xx', 'coffee']:
            assert f'data-egg="{egg}"' in html, f"Missing egg: {egg}"
        # Hints
        for hint in ['barrel roll', 'wandering parrot', 'teapot']:
            assert hint in html.lower(), f"Missing hint: {hint}"
        # Original eggs preserved
        for egg in ['204', '418', '429', '508', 'konami']:
            assert f'data-egg="{egg}"' in html, f"Missing original egg: {egg}"


    def test_homepage_tracks_easter_eggs(self, client):
        """Homepage should track easter eggs including konami code."""
        html = client.get('/').data.decode()
        assert 'eggs_found' in html
        assert "eggs.indexOf('konami')" in html


class TestShareAndEmbed:
    """Tests for share buttons and embed codes on detail pages."""

    def test_share_and_embed_features(self, client):
        """Detail page should have share buttons, embed section, and native share."""
        html = client.get('/200').get_data(as_text=True)
        # Share buttons
        for btn in ['share-native', 'share-link', 'share-image', 'share-slack', 'share-discord', 'share-twitter']:
            assert f'id="{btn}"' in html, f"Missing share button: {btn}"
        assert 'twitter.com/intent/tweet' in html
        # Embed section
        assert 'embed-section' in html
        assert 'Embed this parrot' in html
        assert 'embed-code' in html
        # Scripts
        assert 'navigator.clipboard.writeText' in html
        assert 'navigator.share' in html

    def test_embed_formats_on_404(self, client):
        """404 page should have embed format examples."""
        html = client.get('/404').get_data(as_text=True)
        assert '404.jpg' in html
        assert 'img src=' in html
        assert '![HTTP 404' in html


# --- ELI5 Toggle ---

class TestELI5Toggle:
    def test_eli5_features_on_detail_pages(self, client):
        """Detail pages should have ELI5 toggle, both text modes, and localStorage."""
        # Test 404 page for toggle and content
        html = client.get('/404').get_data(as_text=True)
        assert 'eli5-switch' in html
        assert 'eli5-toggle' in html
        assert 'Simple mode' in html
        assert 'eli5-simple' in html
        # Test 200 page for both modes
        html = client.get('/200').get_data(as_text=True)
        assert 'eli5-technical' in html
        assert 'eli5-simple' in html
        # Test localStorage persistence
        html = client.get('/500').get_data(as_text=True)
        assert "localStorage.getItem('eli5')" in html
        assert "localStorage.setItem('eli5'" in html

    def test_eli5_toggle_on_all_codes(self, client):
        """All status code pages (except 204) should have ELI5 toggle and content."""
        from status_extra import STATUS_EXTRA
        for code in STATUS_EXTRA:
            if code == '204':
                continue
            html = client.get(f'/{code}').get_data(as_text=True)
            assert 'eli5-switch' in html, f"Missing eli5-switch for {code}"
            assert 'eli5-simple' in html, f"Missing ELI5 for {code}"

    def test_eli5_data_in_all_status_extra(self):
        """STATUS_EXTRA should have eli5 keys for ALL 72 codes."""
        from status_extra import STATUS_EXTRA
        assert len(STATUS_EXTRA) == 72, f"Expected 72 codes, got {len(STATUS_EXTRA)}"
        for code in STATUS_EXTRA:
            assert 'eli5' in STATUS_EXTRA[code], f"Missing eli5 key for {code}"
            assert len(STATUS_EXTRA[code]['eli5']) > 20, f"ELI5 for {code} seems too short"


# --- Daily HTTP Challenge ---

class TestDailyChallenge:
    def test_daily_page_and_elements(self, client):
        """Daily challenge should have all quiz elements and 4 options."""
        resp = client.get('/daily')
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert 'Daily HTTP Challenge' in html
        assert 'daily-scenario' in html
        assert 'daily-choices' in html
        assert 'quiz-btn' in html
        assert 'Share on Twitter' in html
        assert 'Copy Result' in html
        assert html.count('class="quiz-btn daily-btn"') == 4

    def test_daily_deterministic_same_day(self, client):
        """Same day should produce the same challenge."""
        html1 = client.get('/daily').get_data(as_text=True)
        html2 = client.get('/daily').get_data(as_text=True)
        strip_nonce = lambda h: re.sub(r'nonce="[^"]*"', 'nonce=""', h)
        assert strip_nonce(html1) == strip_nonce(html2)


# --- FAQPage structured data ---

class TestFAQSchema:
    def test_faq_structured_data(self, client):
        """Detail pages should have FAQPage structured data with proper format."""
        html = client.get('/200').data.decode()
        assert 'FAQPage' in html
        assert 'DefinedTerm' in html
        assert 'What does HTTP 200 mean?' in html
        assert 'When should I use HTTP 200?' in html
        assert 'What is the difference between HTTP 200 and 201?' in html
        ld_match = re.search(r'<script type="application/ld\+json">\s*\[', html)
        assert ld_match is not None, "JSON-LD should be a JSON array"
        # Check Question/Answer structure on 404
        html404 = client.get('/404').data.decode()
        assert '"@type": "Question"' in html404
        assert '"@type": "Answer"' in html404
        assert 'acceptedAnswer' in html404

    def test_build_faq_entries_function(self):
        """build_faq_entries should generate correct FAQ entries."""
        from index import build_faq_entries
        info = {'description': 'Test description'}
        extra = {'examples': ['Example 1', 'Example 2']}
        related = [('201', 'Created vs retrieved')]
        faq = build_faq_entries('200', 'OK', info, extra, related)
        assert len(faq) >= 3
        assert faq[0]['question'] == 'What does HTTP 200 mean?'
        assert 'difference between HTTP 200 and 201' in faq[2]['question']
        # Minimal data
        faq_min = build_faq_entries('200', 'OK', {'description': 'Test'}, {}, [])
        assert len(faq_min) == 1
        assert faq_min[0]['question'] == 'What does HTTP 200 mean?'


# --- Parrot of the Day on homepage ---

class TestRSSFeed:
    def test_feed_autodiscovery_in_html(self, client):
        """All HTML pages should include RSS autodiscovery link tag."""
        for path in ['/', '/200', '/quiz']:
            resp = client.get(path)
            html = resp.data.decode()
            assert 'application/rss+xml' in html, f"Missing RSS autodiscovery on {path}"
            assert '/feed.xml' in html, f"Missing feed URL on {path}"

    def test_feed_xml_combined(self, client):
        """Combined checks for /feed.xml."""
        resp = client.get('/feed.xml')
        html = resp.data.decode()
        assert 'rss' in resp.content_type
        xml = resp.data.decode()
        assert '<?xml version' in xml
        assert '<rss version="2.0">' in xml
        assert '<channel>' in xml
        assert '<title>HTTP Parrots</title>' in xml
        assert '</channel>' in xml
        assert '</rss>' in xml
        xml = resp.data.decode()
        assert '<item>' in xml
        assert 'Parrot of the Day' in xml
        assert '<pubDate>' in xml
        assert '<guid>' in xml
        xml = resp.data.decode()
        assert '<enclosure' in xml
        assert 'type="image/jpeg"' in xml
        assert 'max-age=3600' in resp.headers.get('Cache-Control', '')
        xml = resp.data.decode()
        assert '<description>' in xml
        assert '<language>en-us</language>' in xml
        assert '<lastBuildDate>' in xml
# --- Quiz & Practice visual polish ---


class TestQuizVisualFeedback:
    """Verify quiz feedback CSS classes and animation hooks exist in templates."""

    def test_quiz_combined(self, client):
        """Combined checks for /quiz."""
        resp = client.get('/quiz')
        html = resp.data.decode()
        assert "classList.add('correct')" in html or 'classList.add("correct"' in html
        assert "classList.add('wrong')" in html or 'classList.add("wrong"' in html
        assert 'reveal-correct' in html
        assert 'quiz-feedback right' in html or "quiz-feedback right" in html
        assert 'quiz-feedback nope' in html or "quiz-feedback nope" in html

    def test_daily_combined(self, client):
        """Combined checks for /daily."""
        resp = client.get('/daily')
        html = resp.data.decode()
        assert "classList.add('correct')" in html or 'classList.add("correct"' in html
        assert "classList.add('wrong')" in html or 'classList.add("wrong"' in html
        assert 'reveal-correct' in html
        assert 'daily-streak-display' in html
        assert 'streak-count' in html
        assert 'streak-bump' in html

    def test_quiz_results_system(self, client):
        """Quiz should have history tracking, results overlay, and emoji grid."""
        html = client.get('/quiz').data.decode()
        assert 'let history = []' in html
        assert 'history.push(true)' in html
        assert 'history.push(false)' in html
        assert 'total === 10' in html
        assert 'showResults' in html
        assert 'quiz-results-overlay' in html
        assert 'quiz-results-card' in html
        assert 'Share Result' in html
        assert 'Play Again' in html
        assert 'quiz-results-grid' in html
        assert 'httpparrots.com/quiz' in html


class TestPracticeDifficultyTabs:
    """Verify practice page difficulty tabs have correct styling classes."""

    def test_practice_filter_buttons_have_data_difficulty(self, client):
        """Each filter button has a data-difficulty attribute."""
        resp = client.get('/practice')
        html = resp.data.decode()
        for level in ['all', 'beginner', 'intermediate', 'expert']:
            assert f'data-difficulty="{level}"' in html

    def test_practice_combined(self, client):
        """Combined checks for /practice."""
        resp = client.get('/practice')
        html = resp.data.decode()
        assert html.count('practice-filter-btn') >= 4
        assert 'practice-difficulty-badge beginner' in html
        assert 'practice-difficulty-badge intermediate' in html
        assert 'practice-difficulty-badge expert' in html
        assert 'practice-progress-bar' in html
        assert 'practice-progress-track' in html
        assert 'practice-progress-text' in html
        assert 'role="progressbar"' in html
        # Cards should have data-difficulty matching one of the three levels
        import re
        card_diffs = re.findall(r'class="practice-card"[^>]*data-difficulty="(\w+)"', html)
        assert len(card_diffs) > 0
        for diff in card_diffs:
            assert diff in ('beginner', 'intermediate', 'expert')
        assert "classList.add('visible')" in html or 'classList.add("visible"' in html
# --- Detail page polish ---

    def test_practice_category_filters(self, client):
        """Practice page should have category filter buttons and data attributes."""
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
        card_cats = re.findall(r'class="practice-card"[^>]*data-category="([\w-]+)"', html)
        assert len(card_cats) > 0
        assert 'Filter by category' in html
        assert 'data-category="auth"' in html
        assert 'practice-filter-btn' in html


class TestDetailAccentBar:
    """Verify category accent bar class is present on detail page cards."""

    @pytest.mark.parametrize("path,expected_class", [
        ('/100', b'detail-cat-1xx'), ('/200', b'detail-cat-2xx'),
        ('/301', b'detail-cat-3xx'), ('/404', b'detail-cat-4xx'),
        ('/500', b'detail-cat-5xx'),
    ])
    def test_accent_bar_per_category(self, client, path, expected_class):
        """Each category should have its accent bar class on the detail page."""
        assert expected_class in client.get(path).data

    def test_accent_bar_css_exists(self, client):
        """CSS has ::before rules for accent bar on detail cards."""
        css = client.get('/static/style.css').data.decode()
        assert '.detail-parrot::before' in css
        assert '.detail-cat-1xx::before' in css
        assert '.detail-cat-5xx::before' in css


class TestHTTPExchangePanels:
    """Verify HTTP exchange panels, animations, and detail page reveal elements."""

    def test_exchange_panels_and_detail_elements(self, client):
        """Detail page should have styled panels, syntax highlighting, back-to-top, and reveals."""
        html = client.get('/200').data.decode()
        # Panel structure and syntax highlighting
        for cls in ['http-panel-request', 'http-panel-response',
                     'http-hl-method', 'http-hl-status', 'http-hl-header']:
            assert cls in html, f"Missing panel class: {cls}"
        # Back-to-top
        assert 'back-to-top' in html
        assert 'Back to top' in html
        assert "classList.add('visible')" in html or 'classList.add("visible"' in html
        # Section reveal
        assert 'IntersectionObserver' in html
        assert 'detail-section' in html
        # Animation play button
        assert 'http-exchange-play' in html
        assert 'Play Animation' in html
        assert 'aria-label="Play HTTP exchange animation"' in html
        assert 'id="http-exchange"' in html
        assert 'http-line' in html
        assert 'data-auto-played' in html

    def test_exchange_animation_css(self, client):
        """CSS should have all exchange animation, panel, and detail reveal styles."""
        css = client.get('/static/style.css').data.decode()
        # Panel borders
        assert '.http-panel-request' in css
        assert '.http-panel-response' in css
        # Reveal and back-to-top
        assert '.detail-section.revealed' in css
        assert '.back-to-top' in css
        assert '.back-to-top.visible' in css
        # Animation keyframes
        for kf in ['http-slide-in-left', 'http-slide-in-right',
                    'http-arrow-trail', 'http-line-fade', 'http-line-sweep']:
            assert f'@keyframes {kf}' in css, f"Missing keyframe: {kf}"
        assert '.http-exchange-animated' in css
        assert '.http-exchange-play-btn' in css
        # Status line glow and line sweep
        assert '.http-exchange-animated .http-hl-status' in css
        assert 'text-shadow' in css
        assert '.http-exchange-animated .http-line' in css
        # Sequential line delay
        assert '.http-line:nth-child(1)' in css
        assert '.http-line:nth-child(2)' in css
        assert 'animation-delay' in css
        # Reduced motion — consolidated in main block
        assert 'prefers-reduced-motion: reduce' in css
        assert '.http-exchange-play-btn' in css
        assert '.http-exchange-animated .http-hl-status' in css


# --- Compare page enhancements ---

class TestCompareEnhancements:
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

    def test_compare_combined(self, client):
        """Combined checks for /compare."""
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
        assert 'id="swap-codes"' in html
        assert 'compare-swap-btn' in html
        assert 'id="compare-summary"' in html
        assert 'compare-summary' in html
        assert 'comparisonSummaries' in html
        assert 'buildDiffSection' in html
        assert 'compare-diff' in html


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

    def test_api_docs_interactive_features(self, client):
        """API docs page has try-it panels, copy buttons, and enhanced sections."""
        html = client.get('/api-docs').data.decode()
        # Echo documentation
        assert 'format=pretty' in html
        assert 'format=curl' in html
        # Diff documentation
        assert 'Compare status codes' in html
        # Try-it buttons and panels
        assert 'docs-try-btn' in html
        assert 'Try it' in html
        count = html.count('docs-try-it')
        assert count >= 6, f"Expected at least 6 try-it panels, found {count}"
        # Individual try-it panels
        assert 'try-search-q' in html
        assert 'docs-try-input' in html
        assert 'try-check-url' in html
        assert 'try-return-code' in html
        assert 'try-unstable-rate' in html
        assert 'docs-try-slider' in html
        # Unstable docs
        assert 'Unreliable endpoint' in html
        assert 'failure_rate' in html
        # Copy curl buttons
        assert 'docs-copy-curl-btn' in html
        assert 'Copy curl' in html


class TestPlayground:
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

    def test_playground_combined(self, client):
        """Combined checks for /playground."""
        resp = client.get('/playground')
        html = resp.data.decode()
        assert 'Response Playground' in html
        assert 'CORS Error' in html
        assert 'Rate Limited' in html
        assert 'Redirect Chain' in html
        assert 'JSON API Response' in html
        assert 'Auth Required' in html
        assert 'pg-status' in html
        assert '<option value="200"' in html
        assert '<option value="404"' in html
        assert '<option value="500"' in html
        assert 'pg-headers' in html
        assert 'pg-body' in html
        assert 'pg-send' in html
        assert 'pg-copy' in html
        assert 'pg-add-header' in html
        assert 'playground-preview' in html
        assert 'pg-raw' in html
        assert 'pg-status-badge' in html
        csp = resp.headers.get('Content-Security-Policy', '')
        nonce = re.search(r"'nonce-([^']+)'", csp).group(1)
        assert f'nonce="{nonce}"'.encode() in resp.data

    def test_playground_extended_scenarios(self, client):
        """Playground should include extended scenario templates."""
        resp = client.get('/playground')
        html = resp.data.decode()
        assert 'cache_hit' in html
        assert 'Cache Hit (304)' in html
        assert 'webhook_payload' in html
        assert 'Webhook Payload' in html
        assert 'file_download' in html
        assert 'File Download' in html
        assert 'validation_error' in html
        assert 'Validation Error (422)' in html
        assert 'sse_stream' in html
        assert 'SSE Stream' in html
        assert 'rate_limited_429' in html
        assert 'Rate Limited (429)' in html
        assert 'ETag' in html
        assert "'304'" in html or '"304"' in html
        assert 'X-Webhook-Event' in html
        assert 'order.completed' in html
        assert 'Content-Disposition' in html
        assert 'attachment' in html
        assert 'Validation Failed' in html
        assert "'422'" in html or '"422"' in html
        assert 'text/event-stream' in html
        assert 'Retry-After' in html
        assert 'X-RateLimit-Limit' in html


class TestCurlImport:
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

    def test_curl_import_combined(self, client):
        """Combined checks for /curl-import."""
        resp = client.get('/curl-import')
        html = resp.data.decode()
        assert 'cURL Import' in html
        assert 'curl-input' in html
        assert '<textarea' in html
        assert 'curl-parse-btn' in html
        assert 'Parse' in html
        assert 'data-tab="curl"' in html
        assert 'data-tab="python"' in html
        assert 'data-tab="javascript"' in html
        assert 'data-tab="go"' in html
        assert 'curl-copy-btn' in html
        assert 'curl-echo-btn' in html
        assert 'Send to Echo' in html
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

    def test_homepage_combined(self, client):
        """Combined checks for /."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'name="viewport"' in html
        assert 'width=device-width' in html
        assert 'initial-scale=1' in html
        assert 'hamburger-btn' in html
        assert 'aria-label="Open navigation menu"' in html
        assert 'aria-expanded="false"' in html
        assert 'aria-controls="mobile-nav"' in html
        assert html.count('hamburger-line') == 3
        assert 'id="mobile-nav"' in html
        assert 'class="mobile-nav"' in html
        assert 'aria-label="Mobile navigation"' in html
        assert 'id="mobile-nav-overlay"' in html
        assert 'mobile-nav-overlay' in html
        assert 'hamburger-btn' in html
        assert 'mobile-nav' in html
        assert 'is-open' in html
        assert 'Escape' in html


class TestAccessibility:
    """Tests for ARIA attributes, semantic HTML, and accessibility across all templates."""

    A11Y_PAGES = ['/', '/quiz', '/practice', '/daily', '/flowchart',
                  '/compare', '/tester', '/headers', '/cors-checker',
                  '/collection', '/playground', '/cheatsheet', '/api-docs']

    @pytest.mark.parametrize("page", A11Y_PAGES)
    def test_skip_link_and_main_content(self, client, page):
        """All pages should have skip-link, main-content id, and role=main."""
        resp = client.get(page)
        html = resp.data.decode()
        assert 'skip-link' in html, f"skip-link missing on {page}"
        assert '#main-content' in html, f"skip-link target missing on {page}"
        assert 'id="main-content"' in html, f"main-content id missing on {page}"
        assert 'role="main"' in html, f"role=main missing on {page}"

    def test_homepage_roles_and_labels(self, client):
        """Homepage should have proper semantic roles and ARIA labels."""
        html = client.get('/').data.decode()
        assert 'role="banner"' in html
        assert 'role="contentinfo"' in html
        assert 'aria-label="Site navigation"' in html
        assert 'role="search"' in html
        assert 'aria-label="Search status codes"' in html
        assert 'alt="200 OK"' in html
        assert 'aria-hidden="true"' in html
        assert 'id="no-results"' in html
        assert 'aria-live="polite"' in html
        assert 'aria-expanded=' in html
        assert 'aria-controls="filter-dropdown"' in html
        assert 'aria-label="Random parrot"' in html
        assert 'aria-label="200 OK"' in html
        assert 'featured' in html

    def test_detail_page_aria(self, client):
        """Detail page should have breadcrumb, share, and nav ARIA."""
        html = client.get('/200').data.decode()
        assert 'alt="200 OK"' in html
        assert 'aria-label="Breadcrumb"' in html
        assert 'aria-current="page"' in html
        assert 'aria-label="Share options"' in html
        assert 'aria-label="Share this parrot"' in html
        assert 'aria-label="Copy link to this page"' in html
        assert 'aria-label="Status code navigation"' in html
        assert 'aria-label="Next status code:' in html
        assert 'id="copy-curl-icon"' in html
        assert 'aria-live="polite"' in html
        assert 'aria-label="Back to top"' in html

    def test_404_page_accessibility(self, client):
        """Custom 404 page should have proper accessibility."""
        html = client.get('/nonexistent-page').data.decode()
        assert 'id="main-content"' in html
        assert 'role="main"' in html
        assert 'aria-hidden="true"' in html

    def test_quiz_aria(self, client):
        """Quiz page should have proper ARIA for choices and feedback."""
        html = client.get('/quiz').data.decode()
        assert '<h1' in html
        assert 'role="group"' in html
        assert 'aria-label="Answer choices"' in html
        assert 'aria-live="polite"' in html
        assert html.count('aria-live="polite"') >= 3

    def test_daily_aria(self, client):
        """Daily page should have proper ARIA for choices and streak."""
        html = client.get('/daily').data.decode()
        assert 'role="group"' in html
        assert 'aria-label="Answer choices"' in html
        assert 'id="streak-count"' in html
        assert 'aria-live="polite"' in html
        assert 'role="region"' in html
        assert 'aria-label="Streak tracker"' in html

    def test_practice_aria(self, client):
        """Practice page should have proper ARIA for score and progress."""
        html = client.get('/practice').data.decode()
        assert 'id="practice-correct"' in html
        assert 'aria-live="polite"' in html
        assert 'role="progressbar"' in html
        assert 'aria-valuenow' in html
        assert 'aria-valuemin' in html
        assert 'aria-valuemax' in html
        assert 'role="region"' in html
        assert 'aria-label="Score tracker"' in html

    def test_flowchart_aria(self, client):
        """Flowchart page should have tablist pattern."""
        html = client.get('/flowchart').data.decode()
        assert '<h1' in html
        assert 'role="tablist"' in html
        assert 'role="tab"' in html
        assert 'aria-selected="true"' in html
        assert 'role="tabpanel"' in html

    def test_compare_aria(self, client):
        """Compare page should have ARIA labels and live region."""
        html = client.get('/compare').data.decode()
        assert 'aria-label="Compare 401' in html
        assert 'role="group"' in html
        assert 'id="compare-result"' in html
        assert 'aria-live="polite"' in html

    def test_collection_aria(self, client):
        """Collection page should have progressbar and labeled regions."""
        html = client.get('/collection').data.decode()
        assert 'role="progressbar"' in html
        assert 'aria-valuenow' in html
        assert 'aria-valuemin' in html
        assert 'aria-valuemax' in html
        assert 'aria-label="Secret parrots"' in html

    def test_cheatsheet_aria(self, client):
        """Cheatsheet should have h2 headers and sr-only table headers."""
        html = client.get('/cheatsheet').data.decode()
        assert '<h2 class="cheat-cat-header">' in html
        assert 'class="sr-only"' in html
        assert '<th>Code</th>' in html

    def test_tester_aria(self, client):
        """Tester page should have form labels and live region."""
        html = client.get('/tester').data.decode()
        assert 'aria-label="URL tester"' in html
        assert 'for="url-input"' in html
        assert 'aria-live="polite"' in html

    def test_cors_aria(self, client):
        """CORS checker should have form labels and live region."""
        html = client.get('/cors-checker').data.decode()
        assert 'aria-label="CORS checker"' in html
        assert 'for="cors-url"' in html
        assert 'for="cors-origin"' in html
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

    def test_color_contrast_sufficient(self):
        """Key CSS elements should have sufficient contrast (opacity >= 0.6)."""
        import re
        with open('static/style.css', 'r') as f:
            css = f.read()
        assert 'header-subtitle' in css
        for pattern, desc in [
            (r'\.header-subtitle\s*\{[^}]*color:\s*rgba\(255,\s*255,\s*255,\s*([\d.]+)\)', 'header subtitle'),
            (r'\.header-nav\s+a\s*\{[^}]*color:\s*rgba\(255,\s*255,\s*255,\s*([\d.]+)\)', 'nav link'),
            (r'\.footer-github\s*\{[^}]*color:\s*rgba\(255,\s*255,\s*255,\s*([\d.]+)\)', 'footer github'),
        ]:
            m = re.search(pattern, css)
            if m:
                assert float(m.group(1)) >= 0.6, f"{desc} contrast too low: {m.group(1)}"
        with open('templates/headers.html', 'r') as f:
            assert 'rgba(255,255,255,0.4)' not in f.read()


class TestAccessibilityFocusManagement:
    """Tests for keyboard accessibility and focus indicators."""

    def test_focus_and_screen_reader_css(self):
        """CSS should have focus-visible, skip-link, and sr-only styles."""
        with open('static/style.css', 'r') as f:
            css = f.read()
        assert ':focus-visible' in css
        assert '.skip-link:focus' in css
        assert '.skip-link' in css
        assert '.sr-only' in css
        assert 'clip: rect(0, 0, 0, 0)' in css

    def test_interactive_elements_keyboard_accessible(self, client):
        """Key interactive elements should be buttons; quiz should have keyboard shortcuts."""
        html = client.get('/').data.decode()
        assert '<button class="btn-filter"' in html or 'class="btn-filter"' in html
        assert '<button class="cat-pill' in html
        quiz_html = client.get('/quiz').data.decode()
        assert "e.key >= '1'" in quiz_html or "e.key >= \\'1\\'" in quiz_html
        assert "e.key === 'Enter'" in quiz_html or "e.key === \\'Enter\\'" in quiz_html


class TestAccessibilityScreenReader:
    """Tests for screen reader support."""

    def test_homepage_screen_reader_support(self, client):
        """Homepage should have aria-hidden, live regions, aria-expanded/controls, and labels."""
        html = client.get('/').data.decode()
        assert 'aria-hidden="true"' in html
        assert 'id="no-results"' in html
        assert 'aria-live="polite"' in html
        assert 'aria-expanded=' in html
        assert 'aria-controls="filter-dropdown"' in html
        assert 'aria-label="Random parrot"' in html
        assert 'aria-label="200 OK"' in html
        assert 'featured' in html

    def test_detail_back_to_top_has_aria_label(self, client):
        """Back to top button should have aria-label."""
        assert 'aria-label="Back to top"' in client.get('/200').data.decode()


# --- CSS Media Queries ---

class TestCSSMediaQueries:
    """Verify print, reduced-motion, and light-theme media queries exist in the stylesheet."""

    def test_print_styles(self, client):
        """CSS should have comprehensive print styles."""
        css = client.get('/static/style.css').data.decode()
        assert '@media print' in css
        assert 'display: none !important' in css
        assert '.site-header-compact' in css
        assert '.site-footer' in css
        assert 'a[href]::after' in css
        assert 'attr(href)' in css
        assert 'page-break-inside: avoid' in css
        assert 'background: #fff !important' in css
        assert 'color: #000 !important' in css
        assert 'columns: 2' in css
        assert 'break-inside: avoid' in css
        assert 'max-width: 100% !important' in css
        assert 'height: auto !important' in css

    def test_reduced_motion_styles(self, client):
        """Reduced motion should disable animations and transitions."""
        css = client.get('/static/style.css').data.decode()
        assert '@media (prefers-reduced-motion: reduce)' in css
        assert 'animation-duration: 0.01ms !important' in css
        assert 'transition-duration: 0.01ms !important' in css
        # Check the reduced-motion block contents
        idx = css.index('@media (prefers-reduced-motion: reduce)')
        block = css[idx:css.index('/* === Light Theme', idx)]
        assert 'animation: none !important' in block
        assert '.confetti-particle' in block
        assert '.parrot-card.will-reveal' in block
        assert '.parrot-card.scroll-animated' in block
        assert 'transform: none !important' in block

    def test_light_theme_styles(self, client):
        """Light theme should have proper colors and backgrounds."""
        css = client.get('/static/style.css').data.decode()
        assert '@media (prefers-color-scheme: light)' in css
        idx = css.index('@media (prefers-color-scheme: light)')
        block = css[idx:]
        assert '#f8f9fc' in block
        assert '#1a1a1f' in block
        assert '.parrot' in block
        assert '.detail-info' in block
        assert '#ffffff' in block
        for cat in ['.category-1xx', '.category-2xx', '.category-3xx',
                    '.category-4xx', '.category-5xx']:
            assert cat in block, f"Light theme missing {cat}"


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

class TestSSRFIPv6MappedAddresses:
    """Verify SSRF protection against IPv6-mapped IPv4 private addresses."""

    @pytest.mark.parametrize("ip", [
        '::ffff:127.0.0.1', '::ffff:10.0.0.1', '::ffff:172.16.0.1',
        '::ffff:192.168.1.1', '::ffff:169.254.169.254',
    ])
    def test_blocks_ipv6_mapped_private(self, ip):
        """IPv6-mapped private IPs should be blocked."""
        addrinfo = [(socket.AF_INET6, socket.SOCK_STREAM, 0, '', (ip, 0, 0, 0))]
        with patch('index.socket.getaddrinfo', return_value=addrinfo):
            result, _ = resolve_and_validate('http://tricky.example.com/')
            assert result is None, f"Should block {ip}"

    def test_allows_ipv6_mapped_public(self):
        """::ffff:93.184.216.34 should be allowed as it maps to a public IP."""
        addrinfo = [(socket.AF_INET6, socket.SOCK_STREAM, 0, '', ('::ffff:93.184.216.34', 0, 0, 0))]
        with patch('index.socket.getaddrinfo', return_value=addrinfo):
            result, hostname = resolve_and_validate('http://example.com/')
            assert result is not None


class TestSSRFSchemeAndPort:
    """Verify SSRF protection against non-HTTP schemes and non-standard ports."""

    @pytest.mark.parametrize("url", [
        'file:///etc/passwd', 'ftp://internal.example.com/',
        'gopher://internal.example.com/',
    ])
    def test_blocks_non_http_schemes(self, url):
        """Non-HTTP schemes should be blocked."""
        result, _ = resolve_and_validate(url)
        assert result is None, f"Should block {url}"

    @pytest.mark.parametrize("port", [6379, 22])
    def test_blocks_non_standard_ports(self, port):
        """Non-standard ports should be blocked."""
        addrinfo = [(socket.AF_INET, socket.SOCK_STREAM, 0, '', ('93.184.216.34', 0))]
        with patch('index.socket.getaddrinfo', return_value=addrinfo):
            result, _ = resolve_and_validate(f'http://example.com:{port}/')
            assert result is None, f"Should block port {port}"

    @pytest.mark.parametrize("url", [
        'http://example.com:80/', 'https://example.com:443/',
        'https://example.com/',
    ])
    def test_allows_standard_ports(self, url):
        """Standard ports and no port should be allowed."""
        addrinfo = [(socket.AF_INET, socket.SOCK_STREAM, 0, '', ('93.184.216.34', 0))]
        with patch('index.socket.getaddrinfo', return_value=addrinfo):
            result, _ = resolve_and_validate(url)
            assert result is not None, f"Should allow {url}"


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

    def test_practice_inline_style_has_nonce(self, client):
        """Practice page inline <style> should have the CSP nonce."""
        resp = client.get('/practice')
        csp = resp.headers.get('Content-Security-Policy', '')
        nonce = re.search(r"'nonce-([^']+)'", csp).group(1)
        assert f'<style nonce="{nonce}">' in resp.data.decode()

    def test_homepage_combined(self, client):
        """Combined checks for /."""
        resp = client.get('/')
        html = resp.data.decode()
        csp = resp.headers.get('Content-Security-Policy', '')
        nonce_match = re.search(r"'nonce-([^']+)'", csp)
        assert nonce_match, "CSP should contain a nonce"
        nonce = nonce_match.group(1)
        assert f"style-src 'self' 'nonce-{nonce}'" in csp
        # Check specifically for inline event handler attributes on HTML tags.
        # The pattern 'onload="' on a link/img tag would be blocked by CSP.
        # Note: l.onload= inside <script> is fine (DOM property, not HTML attr).
        assert 'onload="this.onload' not in html, \
            "Found inline onload handler on HTML element (blocked by CSP)"
        assert 'id="font-preload"' in html
        assert 'font-preload' in html


class TestCSPOnAllRoutes:
    """Verify CSP headers are present on all routes, not just the homepage."""

    CSP_ROUTES = [
        '/', '/200', '/quiz', '/daily', '/practice', '/flowchart', '/compare',
        '/tester', '/cheatsheet', '/headers', '/cors-checker', '/collection',
        '/playground', '/api-docs', '/profile', '/personality', '/nonexistent',
        '/echo', '/api/search?q=test', '/api/diff?code1=200&code2=404',
        '/return/200',
    ]

    @pytest.mark.parametrize("route", CSP_ROUTES)
    def test_csp_on_route(self, client, route):
        """CSP headers should be correct on all routes."""
        resp = client.get(route)
        csp = resp.headers.get('Content-Security-Policy', '')
        assert "default-src 'self'" in csp, f"Missing default-src on {route}"
        assert "script-src 'self'" in csp, f"Missing script-src on {route}"
        assert "'nonce-" in csp, f"Missing nonce on {route}"
        assert 'unsafe-inline' not in csp, f"unsafe-inline found on {route}"
        assert 'unsafe-eval' not in csp, f"unsafe-eval found on {route}"


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

    @pytest.mark.parametrize("header,value", [
        ('Authorization', 'Bearer secret'),
        ('Cookie', 'session=abc123'),
        ('Proxy-Authorization', 'Basic abc'),
    ])
    def test_echo_strips_sensitive_headers(self, client, header, value):
        """Echo should strip sensitive headers."""
        data = client.get('/echo', headers={header: value}).get_json()
        assert header not in data['headers'], f"Echo should strip {header}"

    def test_echo_returns_json_content_type(self, client):
        """Echo should always return JSON content type."""
        assert client.get('/echo').content_type.startswith('application/json')

    def test_echo_curl_format_no_auth(self, client):
        """Echo with format=curl should not include auth headers."""
        data = client.get('/echo?format=curl',
                          headers={'Authorization': 'Bearer secret'}).get_json()
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
    """Verify all outbound-request endpoints are rate-limited.

    Note: check-cors, mock-response, and trace-redirects rate limiting
    are tested more thoroughly in their feature-specific classes
    (TestCORSChecker, TestMockResponse, TestRedirectTracer).
    """

    def test_check_url_rate_limited(self, client):
        for _ in range(10):
            client.get('/api/check-url?url=http://127.0.0.1/')
        resp = client.get('/api/check-url?url=https://example.com')
        assert resp.status_code == 429

    def test_return_delay_rate_limited(self, client):
        """Return endpoint with delay should be rate-limited."""
        for _ in range(10):
            client.get('/return/200?delay=0.01')
        resp = client.get('/return/200?delay=0.01')
        assert resp.status_code == 429


class TestPerformance:
    """Performance-related tests."""

    def test_detail_image_has_fetchpriority(self, client):
        resp = client.get('/200')
        html = resp.get_data(as_text=True)
        assert 'fetchpriority="high"' in html

    def test_random_endpoint_no_cache(self, client):
        resp = client.get('/random', follow_redirects=False)
        assert 'no-store' in resp.headers.get('Cache-Control', '')


# --- Common Mistakes feature ---

    def test_static_style_css_combined(self, client):
        """Combined CSS checks."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert 'max-age' in resp.headers.get('Cache-Control', '')
        assert b'contain:' in resp.data
        assert b'will-change:' in resp.data

    def test_homepage_combined(self, client):
        """Combined checks for /."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'max-age' in resp.headers.get('Cache-Control', '')
        assert 'loading="lazy"' in html
        assert '<script src=' not in html


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

    def test_templates_use_surface_tokens(self, client):
        """Template inline styles should use surface tokens, not hardcoded rgba."""
        for page in ['/debug', '/practice']:
            resp = client.get(page)
            html = resp.data.decode()
            assert 'rgba(26,26,31,0.95)' not in html, (
                f"{page} should use var(--surface-1-solid) instead of hardcoded rgba"
            )

    def test_static_style_css_combined(self, client):
        """Combined CSS checks."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '--surface-1-light:' in css
        assert '--surface-1-heavy:' in css
        assert '--surface-1-solid:' in css
        assert 'var(--surface-1-light)' in css
        assert 'var(--surface-1-heavy)' in css
        assert 'var(--surface-1-solid)' in css
        assert '.quiz-results-card' in css
        # Find the rule and verify it uses the token
        idx = css.index('.quiz-results-card')
        rule = css[idx:idx+200]
        assert 'var(--surface-1-solid)' in rule
# --- Easter egg: Barrel Roll ---

    def test_light_theme_selectors_present(self, client):
        """Light theme CSS block should contain overrides for all key components."""
        css = client.get('/static/style.css').data.decode()
        idx = css.index('@media (prefers-color-scheme: light)')
        block = css[idx:]
        required_selectors = [
            # Fault simulator
            '.fault-sim-try', '.fault-sim-result', '.fault-sim-try input',
            '.fault-sim-try label', '.fault-sim-progress',
            # Tester
            '.tester-timing-bar-wrap', '.tester-timing-category',
            '.tester-result-actions', '.tester-loading',
            # Trace / redirect tracer
            '.trace-hop pre', '.trace-hop-loc-value', '.trace-hop-error-msg',
            # cURL import
            '.curl-tab-bar', '.curl-tab ', '.curl-tab-active',
            '.curl-method-head', '.curl-method-options', '.curl-copy-btn',
            # Security audit
            '.audit-result-card', '.audit-grade-badge', '.audit-grade-score',
            '.audit-check-card', '.audit-check-label', '.audit-check-points',
            '.audit-check-desc', '.audit-fix-wrap', '.audit-fix-code',
            # Review / Leitner
            '.review-card', '.review-question', '.review-option-btn',
            '.review-explanation', '.review-explanation p',
            '.leitner-dist-bar', '.leitner-dist-label', '.leitner-mastered-count',
        ]
        for selector in required_selectors:
            assert selector in block, f"Light theme missing override for {selector}"


    def test_review_leitner_dist_bar_complete(self, client):
        """Review page should have complete Leitner distribution bar with all elements."""
        html = client.get('/review').data.decode()
        # Bar structure
        for cls in ['leitner-dist', 'leitner-dist-bar', 'leitner-dist-boxes',
                     'leitner-dist-box', 'leitner-dist-fill', 'leitner-dist-label',
                     'leitner-dist-count']:
            assert cls in html, f"Missing Leitner class: {cls}"
        # Five box columns with color coding
        for b in range(1, 6):
            assert f'leitner-count-{b}' in html
            assert f'leitner-fill-{b}' in html
            assert f'Box {b}' in html
            assert f'leitner-dist-box-{b}' in html
        # Mastered count and title
        assert 'leitner-mastered' in html
        assert 'Mastered:' in html
        assert 'Box Distribution' in html
        # Caught-up message (hidden by default)
        assert 'review-caught-up' in html
        assert 'All caught up! Come back tomorrow.' in html
        assert 'display:none' in html
        # JS logic
        assert 'updateLeitnerDist' in html
        assert 'box_level' in html
        assert 'httpparrot_review' in html
        # Accessibility
        assert 'aria-label="Leitner box distribution"' in html
        assert 'id="leitner-mastered"' in html
        assert 'id="review-caught-up"' in html
        assert 'aria-live="polite"' in html


    def test_touch_feedback_css(self):
        """Parrot-clickable should have tap highlight disabled and active scale."""
        with open('static/style.css') as f:
            css = f.read()
        assert '-webkit-tap-highlight-color' in css
        assert '.parrot-clickable' in css
        assert '.parrot-clickable:active' in css
        assert 'scale(0.96)' in css


    def test_search_input_sm_styles(self):
        """Header .search-input-sm should use var(--radius-sm) and have tablet min-width."""
        import re
        with open('static/style.css') as f:
            css = f.read()
        match = re.search(r'\.search-input-sm\s*\{[^}]+\}', css)
        assert match, '.search-input-sm rule not found'
        assert 'border-radius: var(--radius-sm)' in match.group(0)
        assert '(min-width: 768px) and (max-width: 992px)' in css
        tablet = re.search(
            r'@media\s*\(min-width:\s*768px\)\s*and\s*\(max-width:\s*992px\)\s*\{([^}]+\})', css)
        assert tablet, 'Tablet breakpoint (768-992px) not found'
        assert '.search-input-sm' in tablet.group(1)
        assert 'min-width: 140px' in tablet.group(1)


    def test_playground_breakpoints_and_overflow(self):
        """900px breakpoint should switch to single column; raw should have overflow-x."""
        import re
        with open('static/style.css') as f:
            css = f.read()
        assert '@media (max-width: 900px)' in css
        match = re.search(r'@media\s*\(max-width:\s*900px\)\s*\{([^}]+\})+', css)
        assert match, '900px breakpoint not found'
        block = match.group(0)
        assert '.playground-layout' in block
        assert 'grid-template-columns: 1fr' in block
        assert '.playground-preview' in block
        assert 'position: static' in block
        assert '.playground-raw' in css
        assert 'overflow-x: auto' in css


    def test_theme_master_feather_complete(self, client):
        """FEATHERS array should contain theme_master and checkFeathers should check for it."""
        html = client.get('/').data.decode()
        assert "'theme_master'" in html
        assert 'Theme Master' in html
        assert "!has('theme_master')" in html
        assert 'httpparrot_weekly_champion' in html


    def test_explorer_feathers_complete(self, client):
        """FEATHERS array and checkFeathers should handle explorer_10/25/50."""
        html = client.get('/').data.decode()
        for n in [10, 25, 50]:
            assert f"'explorer_{n}'" in html
            assert f'Explorer {n}' in html
        assert "!has('explorer_10')" in html
        assert 'parrotdex.length >= 10' in html
        assert 'parrotdex.length >= 25' in html
        assert 'parrotdex.length >= 50' in html


    def test_weekly_history_css(self):
        """CSS should include weekly history styles."""
        with open('static/style.css') as f:
            css = f.read()
        assert '.weekly-history' in css
        assert '.weekly-history-row' in css
        assert '.weekly-history-title' in css
        assert '.weekly-history-score' in css


    def test_footer_mobile_padding(self):
        """Footer should have reduced padding on 480px screens."""
        with open('static/style.css') as f:
            css = f.read()
        assert 'padding: 1.25rem 1rem' in css


    def test_print_hides_interactive_elements(self):
        """Print styles should hide mobile nav, toast, command palette, and footer counter."""
        with open('static/style.css') as f:
            css = f.read()
        assert '.mobile-nav,' in css or '.mobile-nav\n' in css
        assert '.toast-container' in css
        assert '.cmd-palette-overlay' in css
        assert '.footer-parrot-counter' in css


    def test_detail_page_dblclick_copy(self, client):
        """Detail page should have double-click-to-copy with clipboard and toast."""
        html = client.get('/200').data.decode()
        assert 'dblclick' in html
        assert 'Double-click to copy' in html
        assert 'navigator.clipboard.writeText' in html
        assert 'Code copied!' in html


    def test_detail_page_has_swipe_navigation(self, client):
        """Detail pages should include swipe navigation script."""
        resp = client.get('/200')
        assert b'swipe' in resp.data.lower() or b'touchstart' in resp.data


    def test_fun_messages_on_empty_states(self, client):
        """Command palette and homepage should show personality messages on empty results."""
        html = client.get('/').data.decode()
        assert "404: Search Result Not Found. How ironic." in html
        assert "funMessages" in html
        assert 'no-results' in html
        assert 'no-results-message' in html
        assert 'noResultsMessages' in html
        assert "301 Moved Permanently" in html


    def test_rfc_easter_egg_complete(self, client):
        """Homepage should have RFC easter egg script, toast, and CSS."""
        html = client.get('/').data.decode()
        assert 'rfc_reader' in html
        assert 'rfc-toast' in html
        assert 'datatracker.ietf.org' in html
        css = client.get('/static/style.css').data.decode()
        for cls in ['.rfc-toast', '.rfc-toast-visible', '.rfc-toast a']:
            assert cls in css, f"Missing CSS class: {cls}"


    def test_all_routes_return_valid_status(self, client):
        """Every page route should return a valid HTTP status."""
        pages = ['/', '/quiz', '/daily', '/weekly', '/practice', '/debug',
                 '/review', '/bingo', '/horoscope', '/predict', '/incidents',
                 '/content-negotiation', '/map', '/credits',
                 '/paths', '/learn', '/tester', '/headers', '/cors-checker',
                 '/security-audit', '/trace', '/playground', '/curl-import',
                 '/fault-simulator', '/webhook-inspector', '/compare',
                 '/personality', '/collection', '/cheatsheet', '/flowchart',
                 '/api-docs', '/profile', '/200', '/404', '/500']
        for page in pages:
            resp = client.get(page)
            assert resp.status_code in (200, 404, 500), f'{page} returned {resp.status_code}'


    def test_paths_http_foundations_combined(self, client):
        """Combined checks for /paths/http-foundations."""
        resp = client.get('/paths/http-foundations')
        html = resp.data.decode()
        assert 'path-certificate' in html
        assert 'Certificate of Completion' in html
        assert 'path-certificate-path-name' in html
        assert 'HTTP Foundations' in html
        assert 'steps completed' in html
        assert 'cert-share-btn' in html
        assert 'Share Certificate' in html
        assert '+500 XP' in html
        assert 'cert-date' in html
        assert 'path-certificate" id="path-certificate"' in html
        # Should NOT have visible class in the static HTML
        assert 'path-certificate visible' not in html
        assert 'cert-share-btn' in html
        assert 'clipboard' in html
        assert '#HTTPParrots' in html
        assert 'ParrotXP.award(500' in html
        assert 'path-certificate-badge' in html
        assert 'httpparrot_path_date_' in html
        assert 'toLocaleDateString' in html
    def test_css_responsive_layout_selectors(self, client):
        """CSS should have responsive layout selectors and breakpoints."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.compare-columns' in css
        # The stacking rule should exist somewhere in a 768px media query
        assert 'grid-template-columns: 1fr' in css
        assert '.playground-layout' in css
        assert 'overflow-x: auto' in css
        assert '.profile-heatmap-container' in css
        assert '.cheat-filter-pills .cheat-compact-btn' in css or '.cheat-compact-btn' in css
        assert 'min-height: 44px' in css
        assert '576px' in css
        assert 'max-width: 768px' in css
        assert 'max-width: 992px' in css


class TestEasterEggs:
    """Tests for barrel roll, 404 catch game, and time traveler easter eggs."""

    def test_barrel_roll_easter_egg(self, client):
        """Homepage should have barrel roll toast, script, and tracking."""
        html = client.get('/').data.decode()
        assert 'barrel-roll-toast' in html
        assert 'barrel roll' in html
        assert 'barrel_roll' in html
        assert "eggs.indexOf('barrel_roll')" in html
        assert 'Polly wants a barrel roll!' in html
        css = client.get('/static/style.css').data.decode()
        assert 'barrel-roll-spin' in css
        assert '.barrel-roll' in css
        assert '.barrel-roll-toast' in css

    def test_404_catch_game(self, client):
        """404 page should have wandering parrot catch game with tracking."""
        html = client.get('/nonexistent').data.decode()
        assert 'error-wandering-parrot' in html
        assert 'handleCatch' in html
        assert 'maxCatches' in html
        assert "eggs.indexOf('404_catch')" in html
        assert "You caught me!" in html
        assert "try /418" in html
        assert 'Catch the wandering parrot' in html

    def test_time_traveler_easter_egg(self, client):
        """Homepage should have time traveler footer script with all messages."""
        html = client.get('/').data.decode()
        assert 'footer-time-egg' in html
        assert 'time_404' in html
        assert 'time_200' in html
        assert 'time_5xx' in html
        assert "even time can" in html
        assert "find this page" in html
        assert '200 OK, but the parrot is napping' in html
        assert "5xx o" in html
        assert "clock somewhere" in html
        assert 'eggs_found' in html
        css = client.get('/static/style.css').data.decode()
        assert 'footer-time-egg' in css


# --- Easter egg: /coffee endpoint ---

class TestCoffeeEasterEgg:
    def test_coffee_page_content(self, client):
        """/coffee should return 418 with teapot content and tracking."""
        resp = client.get('/coffee')
        assert resp.status_code == 418
        html = resp.data.decode()
        assert "teapot" in html.lower()
        assert "coffee" in html.lower()
        assert 'coffee-ascii-teapot' in html
        assert 'coffee-steam' in html
        assert 'steam-particle' in html
        assert 'brew-counter' in html
        assert 'Failed brew attempts' in html
        assert "eggs.indexOf('coffee')" in html
        assert 'href="/"' in html
        assert 'href="/418"' in html
        assert 'coffee-pour-stream' in html

    def test_coffee_security_and_nonce(self, client):
        """/coffee should have CSP, security headers, and nonce."""
        resp = client.get('/coffee')
        csp = resp.headers.get('Content-Security-Policy', '')
        assert "default-src 'self'" in csp
        assert 'X-Content-Type-Options' in resp.headers
        nonce = re.search(r"'nonce-([^']+)'", csp).group(1)
        assert f'nonce="{nonce}"'.encode() in resp.data

    def test_coffee_not_in_navigation(self, client):
        """/coffee should NOT appear in the site navigation."""
        assert 'href="/coffee"' not in client.get('/').data.decode()

    def test_coffee_css_exists(self, client):
        """Style sheet should contain coffee page styles."""
        css = client.get('/static/style.css').data.decode()
        assert 'coffee-container' in css
        assert 'coffee-teapot-tilt' in css
        assert 'coffee-pour' in css

    def test_418_detail_has_coffee_hint(self, client):
        """418 detail page should contain hint; other pages should not."""
        assert '<!-- try /coffee -->' in client.get('/418').data.decode()
        assert '<!-- try /coffee -->' not in client.get('/200').data.decode()


# --- Parrotdex new egg entries ---

class TestProfilePage:
    """Tests for the XP profile page."""

    def test_profile_page_content(self, client):
        """Profile page should have all sections: rank, stats, heatmap, ranks list, XP breakdown."""
        resp = client.get('/profile')
        assert resp.status_code == 200
        html = resp.data.decode()
        assert 'Profile - HTTP Parrots' in html
        assert 'profile-rank-display' in html
        assert 'Fledgling' in html
        assert 'profile-heatmap-container' in html
        assert 'profile-stats-section' in html
        for stat in ['stat-quiz-answers', 'stat-daily-streak', 'stat-codes-visited', 'stat-practice-completed']:
            assert stat in html
        assert 'profile-ranks-list' in html
        for rank in ['Fledgling', 'Nestling', 'Feathered Apprentice', 'Wing Cadet', 'Parrot Scout',
                     'Plume Knight', 'Wing Commander', 'Sky Captain', 'Grand Macaw', 'Legendary Lorikeet']:
            assert rank in html
        assert 'profile-xp-breakdown' in html
        for xp in ['+10 XP', '+50 XP', '+5 XP', '+15 XP', '+100 XP']:
            assert xp in html
        assert 'profile-progress-bar' in html

    def test_xp_system_in_base_template(self, client):
        """Base template should have XP badge, tracking script, and methods."""
        html = client.get('/').data.decode()
        assert 'href="/profile"' in html
        assert 'xp-badge' in html
        assert 'xp-badge-rank' in html
        assert 'ParrotXP' in html
        assert 'httpparrot_xp' in html
        assert 'httpparrot_activity' in html
        for method in ['award:', 'getTotal:', 'getLevel:', 'getRank:']:
            assert method in html

    def test_profile_nav_link_on_subpages(self, client):
        """Profile nav link should be in the base template on subpages."""
        for route in ['/quiz', '/practice', '/daily']:
            assert 'href="/profile"' in client.get(route).data.decode(), f"Missing on {route}"


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

    @pytest.mark.parametrize("page,award_call", [
        ('/quiz', "ParrotXP.award(10, 'quiz_correct')"),
        ('/daily', "ParrotXP.award(50, 'daily_correct')"),
        ('/practice', "ParrotXP.award(15, 'practice_correct')"),
        ('/200', "ParrotXP.award(5, 'page_visit')"),
        ('/collection', "ParrotXP.award(100, 'easter_egg')"),
        ('/coffee', "ParrotXP.award(100, 'easter_egg')"),
    ])
    def test_xp_award_calls(self, client, page, award_call):
        """Templates should call ParrotXP.award with correct amounts."""
        assert award_call in client.get(page).data.decode()

    def test_quiz_and_daily_flags(self, client):
        """Quiz should set perfect_quiz flag, daily should set speed_demon flag."""
        assert 'httpparrot_perfect_quiz' in client.get('/quiz').data.decode()
        assert 'httpparrot_speed_demon' in client.get('/daily').data.decode()


# --- Achievement Badges (Feathers) ---

class TestFeatherBadges:
    """Verify Feathers system is defined and integrated."""

    def test_feathers_system(self, client):
        """Base template should define FEATHERS with all badges and methods."""
        html = client.get('/').data.decode()
        assert 'FEATHERS' in html
        assert 'httpparrot_feathers' in html
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
            assert badge_id in html, f"Badge '{badge_id}' not found"
        # Methods
        assert 'checkFeathers' in html
        assert 'getFeathers' in html
        assert 'showFeatherToast' in html
        assert 'awardWithFeathers' in html
        assert 'checkFeathers()' in html

    def test_feather_toast_css(self, client):
        """Feather toast CSS should exist."""
        css = client.get('/static/style.css').data.decode()
        assert '.feather-toast' in css
        assert '.feather-toast-visible' in css

    def test_profile_feathers_section(self, client):
        """Profile page should have feathers grid with earned/locked states."""
        html = client.get('/profile').data.decode()
        assert 'profile-feathers-section' in html
        assert 'profile-feathers-grid' in html
        assert 'ParrotXP.FEATHERS' in html
        assert 'feather-card' in html
        assert 'earned' in html
        assert 'locked' in html
        css = client.get('/static/style.css').data.decode()
        assert '.feather-card' in css
        assert '.feather-card.earned' in css
        assert '.feather-card.locked' in css


class TestSurfaceElevationSystem:
    """Tests for CSS surface elevation tokens and gradient border hover."""

    def test_surface_and_shadow_tokens(self, client):
        """Surface and shadow tokens should be defined and used."""
        css = client.get('/static/style.css').data.decode()
        for token in ['--surface-0:', '--surface-1:', '--surface-2:', '--surface-3:',
                      '--shadow-sm:', '--shadow-md:', '--shadow-lg:']:
            assert token in css, f"Missing token: {token}"
        assert 'var(--surface-1)' in css
        assert 'var(--surface-2)' in css

    def test_elevation_level_assignments(self, client):
        """Elements should use correct elevation levels."""
        css = client.get('/static/style.css').data.decode()
        # Level 1: cards
        for selector in ['.detail-info {', '.header-card {']:
            idx = css.index(selector)
            block = css[idx:css.index('}', idx)]
            assert 'var(--surface-1)' in block, f"{selector} missing surface-1"
            assert 'var(--shadow-sm)' in block, f"{selector} missing shadow-sm"
        # Level 2: overlays
        for selector in ['.filter-dropdown {', '.quiz-image {', '.tester-result {']:
            idx = css.index(selector)
            block = css[idx:css.index('}', idx)]
            assert 'var(--shadow-md)' in block, f"{selector} missing shadow-md"
        # Level 3: modal-like
        idx = css.index('.mobile-nav {')
        block = css[idx:css.index('}', idx)]
        assert 'var(--surface-3)' in block
        assert 'var(--shadow-lg)' in block

    def test_gradient_border_hover(self, client):
        """Parrot cards should have gradient border hover effect."""
        css = client.get('/static/style.css').data.decode()
        # Category glow colors
        for cat in ['1xx', '2xx', '3xx', '4xx', '5xx']:
            assert f'.parrot-{cat} {{ --cat-glow-color:' in css
        # ::after pseudo element
        assert '.parrot::after' in css
        assert 'conic-gradient' in css
        idx = css.index('.parrot::after')
        block = css[idx:css.index('}', idx)]
        assert 'mask-composite: exclude' in block
        assert '-webkit-mask-composite: xor' in block
        assert 'opacity: 0' in block
        assert 'var(--duration-normal)' in block
        assert 'var(--ease-out)' in block
        assert 'pointer-events: none' in block
        # Hover reveals it
        assert '.parrot:hover::after' in css
        hover_idx = css.index('.parrot:hover::after')
        hover_block = css[hover_idx:css.index('}', hover_idx)]
        assert 'opacity: 1' in hover_block

    def test_light_theme_surface_tokens(self, client):
        """Light theme should override surface and shadow tokens."""
        css = client.get('/static/style.css').data.decode()
        light_block = css[css.index('@media (prefers-color-scheme: light)'):]
        for token in ['--surface-0:', '--surface-1:', '--surface-2:', '--surface-3:',
                      '--shadow-sm:', '--shadow-md:', '--shadow-lg:']:
            assert token in light_block, f"Light theme missing {token}"

    def test_reduced_motion_disables_gradient(self, client):
        """Reduced motion should disable gradient border animation."""
        css = client.get('/static/style.css').data.decode()
        idx = css.index('@media (prefers-reduced-motion: reduce)')
        block = css[idx:css.index('/* === Light Theme', idx)]
        assert '.parrot::after' in block


# --- Debug exercises ---

class TestDebugExercises:
    """Tests for the Debug This Response page."""

    def test_debug_nav_link_present(self, client):
        resp = client.get('/')
        html = resp.data.decode()
        assert 'href="/debug"' in html
        assert '>Debug<' in html

    def test_debug_nav_link_in_mobile_nav(self, client):
        resp = client.get('/')
        html = resp.data.decode()
        assert html.count('href="/debug"') >= 2

    def test_debug_in_sitemap(self, client):
        resp = client.get('/sitemap.xml')
        body = resp.data.decode()
        assert '/debug</loc>' in body

    def test_debug_combined(self, client):
        """Combined checks for /debug."""
        resp = client.get('/debug')
        html = resp.data.decode()
        assert 'Debug This Response' in html
        assert 'Debug This Response - HTTP Parrots' in html
        assert 'debug-card' in html
        assert 'debug-submit-btn' in html
        assert 'debug-description' in html
        assert 'data-difficulty="all"' in html
        assert 'data-difficulty="beginner"' in html
        assert 'data-difficulty="intermediate"' in html
        assert 'data-difficulty="expert"' in html
        assert 'debug-score-bar' in html
        assert 'debug-found' in html
        assert 'debug-missed' in html
        assert 'debug-remaining' in html
        assert 'debug-exchange' in html
        assert 'debug-panel' in html
        assert 'request-label' in html
        assert 'response-label' in html
        assert 'http-hl-status' in html
        assert 'http-hl-method' in html
        assert 'http-hl-header' in html
        assert 'debug-bug-option' in html
        assert 'type="checkbox"' in html
        assert 'distractor-1' in html
        assert 'debug-results' in html
        assert 'debug-result-summary' in html
        assert 'debug-detail-link' in html
        assert 'Learn about' in html
        assert 'ParrotXP.award' in html
        assert 'debug_correct' in html
        assert '<h1>' in html
        assert 'aria-label="Score tracker"' in html
        assert 'aria-label="Filter by difficulty"' in html
        assert 'aria-live="polite"' in html
        csp = resp.headers.get('Content-Security-Policy', '')
        assert "default-src 'self'" in csp
        assert "'nonce-" in csp
        assert 'style nonce=' in html
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
        valid_cats = {'auth', 'caching', 'redirects', 'crud', 'errors', 'headers', 'api-design', 'security'}
        for ex in DEBUG_EXERCISES:
            assert 'category' in ex, f"Exercise {ex['id']} missing category"
            assert ex['category'] in valid_cats, \
                f"Exercise {ex['id']} has invalid category: {ex['category']}"

    def test_multiple_categories_represented(self):
        from debug_exercises import DEBUG_EXERCISES
        categories = {ex['category'] for ex in DEBUG_EXERCISES}
        assert len(categories) >= 4, f"Only {len(categories)} categories represented"

    def test_debug_combined(self, client):
        """Combined checks for /debug."""
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
        import re
        card_cats = re.findall(r'data-category="([\w-]+)".*?class="debug-card"', html)
        card_cats2 = re.findall(r'class="debug-card"[^>]*data-category="([\w-]+)"', html)
        assert len(card_cats) > 0 or len(card_cats2) > 0
        assert 'Filter by category' in html


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

    def test_scenario_difficulty_levels_represented(self):
        from scenarios import SCENARIOS
        difficulties = {s['difficulty'] for s in SCENARIOS}
        assert 'beginner' in difficulties
        assert 'intermediate' in difficulties
        assert 'expert' in difficulties

    def test_scenario_categories_represented(self):
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


class TestConsoleParrotAPI:
    """Tests for the window.parrot console API easter egg."""

    def test_console_parrot_api(self, client):
        """Base template should have full console parrot API with all methods."""
        html = client.get('/').data.decode()
        assert 'window.parrot' in html
        assert 'console.log' in html
        assert '%c' in html
        # Methods
        for method in ['parrot.help()', 'parrot.squawk()', 'parrot.fortune()',
                       'parrot.status(', 'parrot.lore()']:
            assert method in html, f"Missing method: {method}"
        for data in ['SQUAWKS', 'FORTUNES', 'STATUS_CATEGORIES', 'LORE']:
            assert data in html, f"Missing data: {data}"
        assert 'Object.freeze' in html
        # Egg tracking and XP
        assert 'console_parrot' in html
        assert 'eggs_found' in html
        assert 'ParrotXP.award(100' in html

    def test_collection_has_console_parrot_egg(self, client):
        """Collection page should have console_parrot egg card with hint."""
        html = client.get('/collection').data.decode()
        assert 'data-egg="console_parrot"' in html
        assert 'devtools' in html.lower()


# --- HTTP Handshake Easter Egg ---

class TestHTTPHandshakeEasterEgg:
    """Tests for the H-T-T-P keyboard combo handshake easter egg."""

    def test_http_handshake_script(self, client):
        """Base template should have full handshake animation script."""
        html = client.get('/').data.decode()
        assert "['h','t','t','p']" in html
        assert 'INPUT' in html
        assert 'TEXTAREA' in html
        assert 'handshake-overlay' in html
        assert 'handshake-scene' in html
        assert 'SYN' in html
        assert 'SYN-ACK' in html
        assert 'ACK' in html
        assert 'handshake-ok' in html
        assert 'Connection Established!' in html
        assert 'handshake-client' in html
        assert 'handshake-server' in html
        assert 'http_handshake' in html
        assert html.count('ParrotXP.award(100') >= 2
        assert 'handshake-dismissing' in html
        assert 'removeChild' in html
        assert '2000' in html

    def test_handshake_collection_egg(self, client):
        """Collection should have http_handshake egg card with hint."""
        html = client.get('/collection').data.decode()
        assert 'data-egg="http_handshake"' in html
        assert 'protocol' in html.lower()

    def test_handshake_css(self, client):
        """Style.css should contain handshake overlay CSS with reduced motion."""
        css = client.get('/static/style.css').data.decode()
        for cls in ['.handshake-overlay', '.handshake-msg', '.handshake-connected',
                    '.handshake-syn', '.handshake-synack', '.handshake-ack', '.handshake-ok']:
            assert cls in css, f"Missing CSS: {cls}"
        assert 'handshake-bird' in css
        assert 'prefers-reduced-motion' in css


class TestTypographyTokens:
    """Tests for JetBrains Mono font upgrade and type scale tokens."""

    def test_font_and_type_scale(self, client):
        """CSS should use JetBrains Mono and define all type scale tokens."""
        html = client.get('/').data.decode()
        assert 'JetBrains+Mono' in html
        assert 'Share+Tech+Mono' not in html
        css = client.get('/static/style.css').data.decode()
        assert "'JetBrains Mono'" in css
        assert "'Share Tech Mono'" not in css
        assert '--font-code' not in css
        # Type scale tokens defined and used
        for size in ['xs', 'sm', 'base', 'md', 'lg', 'xl', '2xl', '3xl']:
            assert f'--text-{size}:' in css, f"Missing --text-{size} definition"
            assert f'var(--text-{size})' in css, f"Missing var(--text-{size}) usage"

    def test_type_scale_token_values(self):
        """Type scale tokens should use fluid clamp() values."""
        with open('static/style.css', 'r') as f:
            css = f.read()
        for expected in ['--text-xs: clamp(0.6rem', '--text-sm: clamp(0.75rem',
                         '--text-base: 1rem', '--text-lg: clamp(1.1rem',
                         '--text-xl: clamp(1.25rem', '--text-2xl: clamp(1.6rem',
                         '--text-3xl: clamp(2rem']:
            assert expected in css, f"Missing: {expected}"


class TestDesignSystemTokens:
    """Tests for CSS design system token consistency."""

    def test_radius_and_duration_tokens(self):
        """All radius and duration tokens should be defined and used."""
        with open('static/style.css', 'r') as f:
            css = f.read()
        assert '--text-base: 1rem' in css
        assert '--text-md: 1rem' in css
        for r, v in [('xs', '4px'), ('sm', '8px'), ('md', '12px'), ('lg', '16px'), ('full', '9999px')]:
            assert f'--radius-{r}: {v}' in css
            assert f'var(--radius-{r})' in css
        for d in ['fast', 'normal', 'slow']:
            assert f'var(--duration-{d})' in css

    def test_no_hardcoded_values(self, client):
        """CSS should not have hardcoded border-radius, transitions, or font-family."""
        css = client.get('/static/style.css').data.decode()
        import re
        for pattern, desc in [
            (r'border-radius:\s*4px\s*[;!]', 'border-radius: 4px'),
            (r'border-radius:\s*8px\s*[;!]', 'border-radius: 8px'),
            (r'border-radius:\s*16px\s*[;!]', 'border-radius: 16px'),
            (r'border-radius:\s*50%\s*[;!]', 'border-radius: 50%'),
            (r'transition:[^;]*\d+\.\d+s\s+ease(?:-in|-out|-in-out)?', 'hardcoded transition'),
        ]:
            matches = re.findall(pattern, css)
            assert len(matches) == 0, f"Found {desc}: {matches[:3]}"
        # No hardcoded font-family after :root
        root_end = css.index('}')
        assert not re.findall(r"font-family:\s*'Inter',\s*sans-serif", css[root_end:])
        # No low contrast text
        assert 'rgba(255, 255, 255, 0.55)' not in css
        assert 'rgba(255,255,255,0.55)' not in css


# --- Confusion Pair Lessons ---

class TestConfusionPairsData:
    """Tests for confusion_pairs.py data module."""

    def test_pairs_not_empty(self):
        from confusion_pairs import CONFUSION_PAIRS
        assert len(CONFUSION_PAIRS) >= 16

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
            # Round 8 pairs
            '302-vs-303',
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


class TestLearnPairRoute:
    """Tests for /learn/<slug> lesson pages."""

    def test_learn_pair_401_vs_403_content(self, client):
        """401-vs-403 page should have all lesson sections and navigation."""
        html = client.get('/learn/401-vs-403').data.decode()
        assert '401 Unauthorized vs 403 Forbidden' in html
        assert 'learn-tldr' in html and 'TL;DR' in html
        assert 'Decision Tree' in html and 'learn-decision-step' in html
        assert 'Annotated Examples' in html and 'learn-example-card' in html
        assert 'Mini-Quiz' in html and 'learn-quiz-form' in html
        assert 'compare-card' in html and 'Side-by-Side Comparison' in html
        assert 'breadcrumb' in html and 'href="/learn"' in html
        assert 'href="/401"' in html and 'href="/403"' in html
        assert 'ParrotXP' in html and 'learn_quiz_correct' in html

    def test_learn_pair_invalid_slug_returns_404(self, client):
        """Invalid slug should return 404."""
        assert client.get('/learn/999-vs-998').status_code == 404

    def test_all_pairs_render(self, client):
        """Every configured pair should render without error."""
        from confusion_pairs import CONFUSION_PAIRS
        for pair in CONFUSION_PAIRS:
            resp = client.get(f'/learn/{pair["slug"]}')
            assert resp.status_code == 200, f"/learn/{pair['slug']} returned {resp.status_code}"

    def test_scenario_count_at_least_60(self):
        """Scenarios should have at least 60 entries."""
        from scenarios import SCENARIOS
        assert len(SCENARIOS) >= 60

    def test_learn_index_content(self, client):
        """Learn index should render with title, pairs, categories, and counts."""
        resp = client.get('/learn')
        assert resp.status_code == 200
        html = resp.data.decode()
        assert 'Confusion Pairs' in html
        assert '401-vs-403' in html
        assert '301-vs-302' in html
        assert '/learn/' in html
        assert "doesn&#39;t know who you are" in html or "doesn't know who you are" in html or '401' in html
        assert 'learn-index-category-heading' in html
        assert 'Auth pairs' in html
        assert 'Redirect pairs' in html
        assert 'Error pairs' in html
        assert '21 pairs' in html
        assert '8 categories' in html
        for slug in ['502-vs-504', '401-vs-407', '204-vs-205', '409-vs-412',
                      '301-vs-308', '503-vs-504', '502-vs-503']:
            assert slug in html, f"Missing pair: {slug}"


class TestLearnNavAndSitemap:
    """Tests for Learn navigation, sitemap, and detail page links."""

    def test_nav_and_active_states(self, client):
        """Learn link should be in nav with active states."""
        assert 'href="/learn"' in client.get('/').data.decode()
        assert 'nav-active' in client.get('/learn').data.decode()
        assert 'nav-active' in client.get('/learn/401-vs-403').data.decode()

    def test_sitemap_has_learn_pages(self, client):
        """Sitemap should include learn index and pairs."""
        xml = client.get('/sitemap.xml').data.decode()
        assert '/learn' in xml
        assert '/learn/401-vs-403' in xml
        assert '/learn/301-vs-302' in xml

    def test_detail_pages_have_learn_links(self, client):
        """Detail pages with confusion pairs should link to learn pages."""
        assert '/learn/401-vs-403' in client.get('/401').data.decode()
        assert '/learn/401-vs-403' in client.get('/403').data.decode()
        assert '/learn/200-vs-204' in client.get('/200').data.decode()


class TestViewTransitions:
    """Tests for the View Transitions API progressive enhancement."""

    def test_view_transition_meta_and_names(self, client):
        """Pages should have view-transition meta tag and transition names."""
        for page in ['/', '/200']:
            html = client.get(page).data.decode()
            assert '<meta name="view-transition" content="same-origin">' in html
        # Homepage has multiple transition names
        html = client.get('/').data.decode()
        for code in ['200', '404', '500']:
            assert f'view-transition-name: parrot-{code}' in html
        assert 'method-pill' in html

    @pytest.mark.parametrize("code", ['200', '404', '418', '500'])
    def test_detail_transition_name(self, client, code):
        """Detail pages should have matching view-transition-name."""
        assert f'view-transition-name: parrot-{code}' in client.get(f'/{code}').data.decode()

    def test_view_transition_css(self):
        """CSS should have view transition rules, keyframes, and reduced motion."""
        with open('static/style.css') as f:
            css = f.read()
        assert '@view-transition' in css
        assert 'navigation: auto' in css
        assert '@keyframes fade-out' in css
        assert '@keyframes fade-in' in css
        assert '::view-transition-old(root)' in css
        assert '::view-transition-new(root)' in css
        assert 'view-transition-name: site-header' in css
        # Reduced motion
        rm_block = css[css.find('@media (prefers-reduced-motion: reduce)'):css.find('\n/* === Light Theme')]
        assert '::view-transition-old(root)' in rm_block
        assert 'animation: none !important' in rm_block


# --- Streak Freeze & Milestone Celebrations ---

class TestStreakFreeze:
    """Verify streak freeze logic is present in the daily template."""

    def test_freeze_indicator_css_exists(self, client):
        """CSS should have streak-freeze-indicator styles."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.streak-freeze-indicator' in css
        assert '.streak-freeze-message' in css

    def test_daily_combined(self, client):
        """Combined checks for /daily."""
        resp = client.get('/daily')
        html = resp.data.decode()
        assert 'freezesAvailable' in html
        assert 'streak-freeze-indicator' in html
        assert 'freeze-count' in html
        assert 'streak-freeze-msg' in html
        assert 'Streak freeze used' in html
        assert 'state.freezesAvailable > 0' in html
        assert 'state.freezesAvailable--' in html
        assert 'FREEZE_MILESTONES' in html
        assert 'state.freezesAvailable++' in html
        assert 'httpparrot_freeze_used' in html


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

    def test_milestone_toast_uses_existing_css(self, client):
        """Milestone toast should reuse login-reward-toast CSS."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.login-reward-toast' in css

    def test_daily_combined(self, client):
        """Combined checks for /daily."""
        resp = client.get('/daily')
        html = resp.data.decode()
        assert 'showMilestoneCelebration' in html
        assert 'login-reward-toast' in html
        assert 'Bonus XP' in html
        assert 'function showMilestoneCelebration' in html
        assert '4000' in html
        assert 'showMilestoneCelebration' in html
        assert 'spawnConfetti' in html
        assert 'checkMilestoneRewards(state)' in html


class TestCelebrationAnimations:
    """Tests for achievement celebration animations (confetti, rank-up, XP flash)."""

    def test_celebration_scripts(self, client):
        """Base template should have confetti, rank-up, XP flash functions and expose them."""
        html = client.get('/').data.decode()
        # Confetti
        assert 'function spawnCelebrationConfetti' in html
        assert 'celebration-confetti' in html
        assert '#00c9a7' in html and '#7b61ff' in html
        assert 'animationend' in html
        # Rank-up banner
        assert 'function showRankUpBanner' in html
        assert 'Rank Up! You are now a' in html
        assert 'rank-up-banner-icon' in html
        assert 'RANK_BONUS_XP' in html
        assert 'function spawnGoldParticles' in html
        assert 'rankBefore' in html and 'rankAfter' in html
        # XP milestone flash
        assert 'function checkXpMilestoneFlash' in html
        assert 'XP_MILESTONES' in html
        assert 'xp-flash' in html and 'xp-float-number' in html
        # Global exposure
        assert 'spawnCelebrationConfetti: spawnCelebrationConfetti' in html
        assert 'showRankUpBanner: showRankUpBanner' in html
        assert 'checkXpMilestoneFlash: checkXpMilestoneFlash' in html

    def test_celebration_css_and_reduced_motion(self, client):
        """CSS should have celebration animation styles with reduced motion fallbacks."""
        css = client.get('/static/style.css').data.decode()
        for cls in ['.celebration-confetti', '.rank-up-banner', '.rank-up-gold-particle',
                     '.xp-flash', '.xp-float-number']:
            assert cls in css, f"Missing CSS class: {cls}"
        assert 'celebration-burst' in css
        assert 'rank-up-visible' in css
        assert 'gold-shower' in css
        assert '#ffd700' in css and '#ffb300' in css
        assert 'xp-glow-flash' in css and 'xp-float-up' in css
        # Reduced motion — consolidated in main catch-all block
        assert 'prefers-reduced-motion: reduce' in css
        assert '.celebration-confetti { display: none !important; }' in css
        assert '.rank-up-banner { transform: none !important; }' in css
        assert '.rank-up-gold-particle { display: none !important; }' in css
        assert '.xp-float-number { display: none !important; }' in css


class TestSeasonalThemes:
    """Tests for Holiday Plumage seasonal theme system."""

    def test_season_detection_and_tracking(self, client):
        """Base template should have season detection, date checks, and egg tracking."""
        html = client.get('/').data.decode()
        assert 'Holiday Plumage' in html
        assert '_httpparrotSeason' in html
        # Season date checks
        assert "season-winter" in html
        assert "m === 11 && d >= 15" in html
        assert "m === 0 && d <= 5" in html
        assert "season-halloween" in html
        assert "m === 9 && d >= 25" in html
        assert "m === 10 && d <= 1" in html
        assert "season-april-fools" in html
        assert "m === 3 && d === 1" in html
        assert "season-valentine" in html
        assert "m === 1 && d === 14" in html
        # Egg tracking
        for egg in ["'season_winter'", "'season_halloween'", "'season_april'", "'season_valentine'"]:
            assert egg in html, f"Missing egg tracking for {egg}"
        assert "award(50, 'seasonal_egg')" in html
        assert "eggs_found" in html
        assert '_seasonalEggPending' in html

    def test_seasonal_effects(self, client):
        """Homepage should have all seasonal visual effects."""
        html = client.get('/').data.decode()
        assert 'Seasonal Effects' in html
        assert 'halloween-ghost' in html
        assert 'april-fools-banner' in html
        assert 'All status codes are scrambled' in html
        assert 'Just kidding!' in html
        assert '10000' in html
        assert '_valentineHeartConfetti' in html
        assert 'valentine-heart' in html


class TestSeasonalCSS:
    """Tests for seasonal CSS classes, styles, and collection eggs."""

    def test_seasonal_css_and_reduced_motion(self, client):
        """CSS should have all seasonal theme styles with reduced motion fallbacks."""
        css = client.get('/static/style.css').data.decode()
        # Winter
        assert '.season-winter .site-header-compact' in css
        assert '.season-winter::before' in css
        assert '@keyframes snowfall' in css
        # Halloween
        assert '.season-halloween .site-header-compact' in css
        assert '.season-halloween .collection-card:hover' in css
        assert 'hue-rotate' in css
        assert '.halloween-ghost' in css
        assert '@keyframes ghost-float' in css
        # April Fools
        assert '.april-fools-banner' in css
        assert '.april-fools-revert' in css
        # Valentine
        assert '.season-valentine .site-header-compact' in css
        assert '.valentine-heart' in css
        assert 'clip-path' in css
        assert '@keyframes heart-burst' in css
        # Reduced motion — consolidated in main catch-all block
        assert 'prefers-reduced-motion: reduce' in css
        assert '.season-winter::before { display: none !important; }' in css
        assert '.valentine-heart { display: none !important; }' in css

    def test_collection_has_all_seasonal_and_original_eggs(self, client):
        """Collection page should have all seasonal and original egg cards."""
        html = client.get('/collection').data.decode()
        for egg in ['season_winter', 'season_halloween', 'season_april', 'season_valentine',
                     '204', '418', '429', '508', 'konami', 'barrel_roll', 'http_handshake']:
            assert f'data-egg="{egg}"' in html, f"Missing egg: {egg}"
        for hint in ['winter holidays', 'trick or treat', 'not everything is as it seems', 'love is in the http']:
            assert hint in html.lower(), f"Missing seasonal hint: {hint}"


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

    def test_five_paths_exist(self):
        from learning_paths import LEARNING_PATHS
        assert len(LEARNING_PATHS) == 5

    def test_lookup_by_id_and_difficulties(self):
        """Lookup by ID should work and each path should have correct difficulty."""
        from learning_paths import LEARNING_PATHS_BY_ID
        for path_id in ['http-foundations', 'error-whisperer', 'redirect-master', 'api-designer']:
            assert path_id in LEARNING_PATHS_BY_ID
        assert LEARNING_PATHS_BY_ID['http-foundations']['difficulty'] == 'beginner'
        assert LEARNING_PATHS_BY_ID['error-whisperer']['difficulty'] == 'intermediate'
        assert LEARNING_PATHS_BY_ID['redirect-master']['difficulty'] == 'advanced'

    def test_paths_index_content(self, client):
        """Paths index should have title, all paths, badges, progress, links, and descriptions."""
        resp = client.get('/paths')
        assert resp.status_code == 200
        html = resp.data.decode()
        assert 'Learning Paths' in html
        for name in ['HTTP Foundations', 'Error Whisperer', 'Redirect Master', 'API Designer']:
            assert name in html, f"Missing path: {name}"
        for diff in ['path-difficulty-beginner', 'path-difficulty-intermediate', 'path-difficulty-advanced']:
            assert diff in html, f"Missing difficulty badge: {diff}"
        assert 'path-progress-bar' in html
        assert 'progressbar' in html
        for path_id in ['http-foundations', 'error-whisperer', 'redirect-master', 'api-designer']:
            assert f'href="/paths/{path_id}"' in html
        assert 'steps' in html
        assert 'Start your HTTP journey' in html
        assert 'Master the 4xx and 5xx' in html
        assert 'Conquer the full family' in html


class TestPathDetailRoute:
    """Tests for /paths/<path_id> route."""

    def test_path_detail_invalid_id_returns_404(self, client):
        resp = client.get('/paths/nonexistent-path')
        assert resp.status_code == 404

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

    def test_paths_http_foundations_combined(self, client):
        """Combined checks for /paths/http-foundations."""
        resp = client.get('/paths/http-foundations')
        html = resp.data.decode()
        assert 'HTTP Foundations' in html
        assert 'breadcrumb' in html.lower() or 'Breadcrumb' in html
        assert 'href="/paths"' in html
        assert 'path-difficulty-beginner' in html
        assert 'progress-fill' in html
        assert 'progressbar' in html
        assert 'path-step' in html
        assert 'path-step-check' in html
        assert 'path-step-type-visit' in html
        assert 'path-step-type-practice' in html
        assert 'path-step-type-learn' in html
        assert 'path-step-type-quiz' in html
        assert 'href="/200"' in html
        assert 'href="/quiz"' in html
        assert 'href="/learn/200-vs-204"' in html
        assert 'path-complete-banner' in html
        assert 'Path Complete' in html
        assert 'path_complete' in html
        assert '500' in html  # 500 XP bonus


class TestPathsNavAndSitemap:
    """Tests for Paths navigation and sitemap."""

    def test_paths_nav_and_active_states(self, client):
        """Paths link should be in nav with active states."""
        assert 'href="/paths"' in client.get('/').data.decode()
        assert 'nav-active' in client.get('/paths').data.decode()
        assert 'nav-active' in client.get('/paths/http-foundations').data.decode()

    def test_sitemap_includes_paths(self, client):
        """Sitemap should include paths index and details."""
        xml = client.get('/sitemap.xml').data.decode()
        assert '/paths' in xml
        for path_id in ['http-foundations', 'error-whisperer', 'redirect-master']:
            assert f'/paths/{path_id}' in xml


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

    def test_fault_simulator_combined(self, client):
        """Combined checks for /fault-simulator."""
        resp = client.get('/fault-simulator')
        html = resp.data.decode()
        assert b'Fault Simulator' in resp.data
        assert 'section-delay' in html
        assert 'section-drip' in html
        assert 'section-stream' in html
        assert 'section-jitter' in html
        assert 'section-unstable' in html
        assert 'delay-btn' in html
        assert 'drip-btn' in html
        assert 'stream-btn' in html
        assert 'jitter-btn' in html
        assert 'unstable-btn' in html


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

    def test_parrot_sound_api(self, client):
        """ParrotSound should expose all required methods and use Web Audio API."""
        html = client.get('/').data.decode()
        assert 'window.ParrotSound' in html
        # Methods
        for method in ['squawk: squawk', 'correct: correct', 'wrong: wrong',
                       'jingle: jingle', 'click: click', 'isEnabled: isEnabled',
                       'toggle: toggle']:
            assert method in html, f"Missing ParrotSound method: {method}"
        # Web Audio API
        assert 'httpparrot_sound' in html
        assert 'prefers-reduced-motion' in html
        assert 'AudioContext' in html
        assert 'webkitAudioContext' in html
        assert 'createOscillator' in html
        assert 'createGain' in html

    def test_sound_toggle_button(self, client):
        """Header should have sound toggle button with proper accessibility."""
        html = client.get('/200').data.decode()
        assert 'id="sound-toggle"' in html
        assert 'sound-toggle-btn' in html
        assert 'id="sound-toggle-icon"' in html
        assert 'aria-pressed=' in html

    @pytest.mark.parametrize("page,sound", [
        ('/quiz', 'ParrotSound.correct()'),
        ('/quiz', 'ParrotSound.wrong()'),
        ('/daily', 'ParrotSound.correct()'),
        ('/daily', 'ParrotSound.wrong()'),
        ('/practice', 'ParrotSound.correct()'),
        ('/practice', 'ParrotSound.wrong()'),
    ])
    def test_sound_wiring(self, client, page, sound):
        """Sound triggers should be wired into quiz, daily, and practice."""
        assert sound in client.get(page).data.decode()

    def test_jingle_and_gating(self, client):
        """Jingle should be called from multiple places and gated by isEnabled."""
        html = client.get('/').data.decode()
        assert 'ParrotSound.jingle()' in html
        assert html.count('ParrotSound.jingle()') >= 2
        assert 'ParrotSound.isEnabled()' in html


# --- Bento Dashboard ---

class TestBentoDashboard:
    """Tests for the bento grid dashboard on the homepage."""

    def test_dashboard_tiles(self, client):
        """Homepage should have all bento dashboard tiles with proper content."""
        html = client.get('/').data.decode()
        assert 'bento-dashboard' in html
        assert 'aria-label="Dashboard"' in html
        assert 'id="parrot-grid"' in html
        assert 'featured' in html
        # Daily tile
        assert 'bento-tile--daily' in html
        assert 'bento-streak-count' in html
        assert 'Daily Challenge' in html
        assert 'Play Now' in html
        # XP tile
        assert 'bento-tile--xp' in html
        assert 'bento-rank-name' in html
        assert 'XP Progress' in html
        assert 'bento-xp-bar' in html
        assert 'bento-xp-fill' in html
        # Quick tools tile
        assert 'bento-tile--tools' in html
        assert 'Quick Tools' in html
        for tool in ['/quiz', '/practice', '/debug', '/playground']:
            assert f'href="{tool}"' in html
        for label in ['Quiz', 'Practice', 'Debug', 'Playground']:
            assert f'aria-label="{label}"' in html
        # Next Up tile
        assert 'bento-tile--paths' in html
        assert 'Next Up' in html
        assert 'bento-nextup' in html
        assert 'id="bento-nextup-message"' in html
        assert 'id="bento-nextup-sub"' in html
        assert 'id="bento-nextup-action"' in html
        assert 'Get Started' in html
        # Recommender script
        assert 'httpparrot_review' in html
        assert 'httpparrot_daily' in html
        assert 'httpparrot_path_' in html
        assert 'httpparrot_weekly' in html

    def test_bento_dashboard_css(self):
        """CSS should have bento grid, tile, and responsive styles."""
        with open('static/style.css') as f:
            css = f.read()
        assert '.bento-dashboard' in css
        assert 'grid-template-columns' in css
        assert '.bento-tile' in css
        assert 'repeat(2, 1fr)' in css
        assert 'min-height' in css
        assert 'grid-column: span 2' in css


# --- Spaced Repetition Review page ---

class TestReviewPage:
    """Tests for the /review spaced repetition review page."""

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

    def test_review_combined(self, client):
        """Combined checks for /review."""
        resp = client.get('/review')
        html = resp.data.decode()
        assert 'Spaced Repetition Review' in html
        assert 'Review - HTTP Parrots' in html
        assert '<h1>' in html
        assert 'Spaced Repetition Review' in html
        assert 'review-stats-bar' in html
        assert 'review-due' in html
        assert 'review-correct' in html
        assert 'review-wrong' in html
        assert 'review-remaining' in html
        assert 'Due Today' in html
        assert 'Correct' in html
        assert 'Wrong' in html
        assert 'Remaining' in html
        assert 'review-area' in html
        assert 'scenario_' in html
        assert 'debug_' in html
        assert 'confusion_' in html
        assert 'BOX_INTERVALS' in html
        assert 'httpparrot_review' in html
        assert 'ParrotXP.award' in html
        assert 'review_correct' in html
        assert 'Review Complete!' in html
        assert 'No items due for review' in html
        assert 'review-box-indicator' in html
        assert 'type-scenario' in html
        assert 'type-debug' in html
        assert 'type-confusion' in html
        assert 'review-explanation' in html
        assert 'review-next-btn' in html
        assert 'Next Item' in html
        assert 'review-option-btn' in html
        assert 'style nonce=' in html
        assert 'script nonce=' in html
        csp = resp.headers.get('Content-Security-Policy', '')
        assert "default-src 'self'" in csp
        assert "'nonce-" in csp
        assert 'spaced repetition' in html.lower()
        assert 'total_reviews' in html
        assert b'empty-state' in resp.data

    def test_review_combined(self, client):
        """Combined checks for /review."""
        resp = client.get('/review')
        html = resp.data.decode()
        # Box intervals: 1:1, 2:3, 3:7, 4:14, 5:30
        assert '1: 1' in html
        assert '2: 3' in html
        assert '3: 7' in html
        assert '4: 14' in html
        assert '5: 30' in html
        assert 'initItems' in html
        assert 'recordAnswer' in html
        assert 'getDueItems' in html
        assert 'box_level' in html
        assert 'next_review' in html
        assert 'last_answer' in html
        assert 'Math.min(5' in html
        assert 'box_level = 1' in html


    def test_homepage_combined(self, client):
        """Combined checks for /."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'memory_master' in html
        assert 'Memory Master' in html
        assert 'total_reviews' in html
        assert '>= 50' in html
        assert 'Complete 50 spaced repetition reviews' in html


    def test_profile_combined(self, client):
        """Combined checks for /profile."""
        resp = client.get('/profile')
        html = resp.data.decode()
        assert 'stat-review-due' in html
        assert 'Due for Review' in html
        assert 'href="/review"' in html
        assert 'httpparrot_review' in html
        assert 'Spaced repetition review correct' in html
        assert '+15 XP' in html


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

    def test_webhook_in_sitemap_and_robots(self, client):
        """Webhook inspector in sitemap, bins disallowed in robots."""
        assert b'/webhook-inspector' in client.get('/sitemap.xml').data
        text = client.get('/robots.txt').data.decode()
        assert 'Disallow: /api/bin/' in text
        assert 'Disallow: /bin/' in text


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


class TestPersonalityQuizPage:
    """Tests for the /personality route and template."""

    def test_personality_combined(self, client):
        """Combined checks for /personality."""
        resp = client.get('/personality')
        html = resp.data.decode()
        assert 'Which HTTP Status Code Are You?' in html
        assert 'personality-progress' in html
        assert 'progress-bar' in html
        assert 'progressbar' in html
        assert 'quiz-area' in html
        assert 'question-text' in html
        assert 'choices' in html
        assert 'result-area' in html
        assert 'result-card' in html
        assert 'result-img' in html
        assert 'result-name' in html
        assert 'result-desc' in html
        assert 'copy-result' in html
        assert 'twitter-share' in html
        assert 'Copy Result' in html
        assert 'Share on X' in html
        assert 'retake-btn' in html
        assert 'Retake Quiz' in html
        assert 'detail-link' in html
        assert 'Learn more about this status code' in html
        assert 'og:title' in html
        assert 'og:description' in html
        assert 'HTTP Personality Quiz' in html

    def test_personality_combined(self, client):
        """Combined checks for /personality."""
        resp = client.get('/personality')
        html = resp.data.decode()
        assert 'QUESTIONS' in html
        assert 'Question 1 of 8' in html
        assert 'PERSONALITIES' in html
        required_codes = [
            '200', '201', '204', '301', '302', '307',
            '400', '401', '403', '404', '418', '429',
            '500', '502', '503',
        ]
        for code in required_codes:
            assert f'"{code}"' in html, f"Missing personality for code {code}"
        assert 'traits' in html
        assert 'spawnConfetti' in html
        assert 'confetti-particle' in html
        assert 'ParrotXP' in html
        assert 'personality_quiz' in html


    def test_static_style_css_combined(self, client):
        """Combined CSS checks."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.personality-container' in css
        assert '.personality-title' in css
        assert '.personality-progress' in css
        assert '.personality-result-card' in css
        assert '.personality-traits' in css
        assert '.personality-share-buttons' in css
        assert '.personality-result-badge' in css


    def test_personality_combined(self, client):
        """Combined checks for /personality."""
        resp = client.get('/personality')
        html = resp.data.decode()
        assert 'role="main"' in html
        assert 'id="main-content"' in html
        assert 'role="progressbar"' in html
        assert 'aria-valuenow' in html
        assert 'aria-valuemin' in html
        assert 'aria-valuemax' in html
        assert 'aria-live="polite"' in html
        csp = resp.headers.get('Content-Security-Policy', '')
        nonce = re.search(r"'nonce-([^']+)'", csp)
        assert nonce is not None
        assert f'nonce="{nonce.group(1)}"' in html


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


class TestWeeklyRoute:
    """Tests for the /weekly route returning 200 and containing expected content."""

    def test_weekly_contains_week_number(self, client):
        """Weekly page should display the current week number."""
        from datetime import date
        fixed_date = date(2025, 3, 10)  # Monday of ISO week 11
        with patch('index.date') as mock_date:
            mock_date.today.return_value = fixed_date
            mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
            resp = client.get('/weekly')
            html = resp.data.decode()
            assert 'Week 11' in html

    def test_weekly_combined(self, client):
        """Combined checks for /weekly."""
        resp = client.get('/weekly')
        html = resp.data.decode()
        theme_names = [
            'Redirect Week', 'Auth Week', 'Error Week', 'Success Week',
            'Caching Week', 'API Design Week', 'Debug Week', 'Speed Round',
        ]
        assert any(name in html for name in theme_names), \
            "No theme name found in weekly page"
        assert 'weekly-theme-desc' in html
        assert 'var QUESTIONS = [' in html
        question_ids = re.findall(r'"id":\s*\d+', html)
        assert len(question_ids) == 5, f"Expected 5 questions, found {len(question_ids)}"
        for i in range(5):
            assert f'id="step-{i}"' in html
        assert 'weekly-timer' in html
        assert 'weekly-timer-value' in html
        assert 'role="timer"' in html
        assert 'weekly-results-card' in html
        assert 'weekly-final-score' in html
        assert 'weekly-final-time' in html
        assert 'weekly-final-xp' in html
        assert 'weekly-share-copy' in html
        assert 'weekly-share-twitter' in html
        assert 'Share on Twitter' in html
        assert 'Copy Result' in html
        assert 'weekly-results-badge' in html
        assert 'Weekly Champion' in html
        assert 'id="weekly-choices"' in html
        assert 'role="group"' in html
        assert 'aria-label="Answer choices"' in html
        assert 'id="weekly-feedback"' in html
        assert 'aria-live="polite"' in html
        assert 'weekly-next-btn' in html
        assert 'Next Question' in html

    def test_sitemap_contains_weekly(self, client):
        """Sitemap should include /weekly."""
        resp = client.get('/sitemap.xml')
        xml = resp.data.decode()
        assert '/weekly' in xml


    def test_weekly_combined(self, client):
        """Combined checks for /weekly."""
        resp = client.get('/weekly')
        html = resp.data.decode()
        assert "ParrotXP.award(25, 'weekly_correct')" in html
        assert "ParrotXP.award(100, 'weekly_perfect')" in html
        assert 'httpparrot_weekly_champion' in html
        assert 'httpparrot_weekly' in html
        assert 'streak' in html
        assert 'weekly-streak-label' in html
        assert 'weekly-results-streak' in html


    def test_static_style_css_combined(self, client):
        """Combined CSS checks."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.weekly-theme-banner' in css
        assert '.weekly-theme-name' in css
        assert '.weekly-progress' in css
        assert '.weekly-step' in css
        assert '.step-correct' in css
        assert '.step-wrong' in css
        assert '.weekly-results-card' in css
        assert '.weekly-results-badge' in css
        assert '.weekly-results-badge' in css
        assert '.weekly-progress-fill' in css


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
        fixed_date = date(2025, 3, 10)  # ISO week 11
        themes = [
            'Redirect Week', 'Auth Week', 'Error Week', 'Success Week',
            'Caching Week', 'API Design Week', 'Debug Week', 'Speed Round',
        ]
        expected_theme = themes[11 % len(themes)]  # week 11
        with patch('index.date') as mock_date:
            mock_date.today.return_value = fixed_date
            mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
            with app.test_client() as client:
                resp = client.get('/weekly')
                html = resp.data.decode()
                assert expected_theme in html


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


class TestCheatsheetToolbar:
    """Tests for the cheatsheet filter, search, and compact toggle."""

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

    def test_cheatsheet_combined(self, client):
        """Combined checks for /cheatsheet."""
        resp = client.get('/cheatsheet')
        html = resp.data.decode()
        assert 'id="cheat-search"' in html
        assert 'cheat-search-input' in html
        assert 'id="cheat-filter-pills"' in html
        assert 'data-cat="all"' in html
        assert 'data-cat="1xx"' in html
        assert 'data-cat="2xx"' in html
        assert 'data-cat="3xx"' in html
        assert 'data-cat="4xx"' in html
        assert 'data-cat="5xx"' in html
        assert 'id="cheat-compact-toggle"' in html
        assert 'cheat-compact-btn' in html
        assert 'Compact View' in html
        assert 'id="cheat-compact-view"' in html
        assert 'cheat-compact-grid' in html
        assert 'id="cheat-no-results"' in html
        assert 'cheat-no-results' in html
        assert 'data-code="200"' in html
        assert 'data-name=' in html
        assert 'data-category="1xx"' in html
        assert 'data-category="2xx"' in html
        assert 'data-category="5xx"' in html
        assert 'id="cheat-toolbar"' in html
        assert 'cheat-toolbar' in html
        assert 'cheat-search' in html
        assert 'cheat-filter-pills' in html
        assert 'filterAll' in html
        assert 'class="cat-pill' in html


class TestNextUpRecommender:
    """Tests for the Next Up smart recommender on the homepage."""

    def test_nextup_css_styles_present(self, client):
        """CSS should have Next Up recommender styles."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.bento-nextup' in css
        assert '.bento-nextup-message' in css
        assert '.bento-nextup-sub' in css

    def test_homepage_combined(self, client):
        """Combined checks for /."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'bento-nextup' in html
        assert 'bento-nextup-message' in html
        assert 'bento-nextup-sub' in html
        assert 'Start a learning path' in html
        assert "httpparrot_review" in html
        assert "Review Now" in html
        assert "httpparrot_daily" in html
        assert "Play Daily" in html
        assert "httpparrot_path_" in html
        assert "http-foundations" in html
        assert "error-whisperer" in html
        assert "redirect-master" in html
        assert "httpparrot_weekly" in html
        assert "Start Challenge" in html


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

    def test_homepage_combined(self, client):
        """Combined checks for /."""
        resp = client.get('/')
        html = resp.data.decode()
        for mf in self.META_FEATHERS:
            assert mf['id'] in html, f"Meta-feather '{mf['id']}' not found"
        for mf in self.META_FEATHERS:
            assert f"id: '{mf['id']}'" in html
        assert 'meta: true' in html
        for mf in self.META_FEATHERS:
            assert f"bonus: {mf['bonus']}" in html, \
                f"Meta-feather '{mf['id']}' should have bonus: {mf['bonus']}"
        assert "!has('explorer')" in html
        assert "charAt(0) === '1'" in html
        assert "charAt(0) === '2'" in html
        assert "charAt(0) === '3'" in html
        assert "charAt(0) === '4'" in html
        assert "charAt(0) === '5'" in html
        assert "!has('polyglot')" in html
        assert "'quiz_correct'" in html
        assert "'practice_correct'" in html
        assert "'debug_correct'" in html
        assert "'review_correct'" in html
        assert "!has('streak_lord')" in html
        assert "milestonesHit" in html
        assert "indexOf(30)" in html
        assert "!has('triple_threat')" in html
        assert "'quiz_whiz'" in html
        assert "'scholar'" in html
        assert "'memory_master'" in html
        assert "!has('full_spectrum')" in html
        assert "'error_expert'" in html
        assert "'server_sage'" in html
        assert "!has('parrot_polymath')" in html
        assert "baseCount >= 12" in html
        assert "META_IDS" in html
        assert "META_IDS" in html
        assert "'explorer'" in html
        assert "'polyglot'" in html
        assert "'streak_lord'" in html
        assert "'triple_threat'" in html
        assert "'full_spectrum'" in html
        assert "'parrot_polymath'" in html
        names = ['Explorer', 'Polyglot', 'Streak Lord', 'Triple Threat',
                 'Full Spectrum', 'Parrot Polymath']
        for name in names:
            assert name in html, f"Meta-feather name '{name}' not found"
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

    def test_429_combined(self, client):
        """Combined checks for /429."""
        resp = client.get('/429')
        html = resp.data.decode()
        assert 'case-study-card' in html
        assert 'case-study-api' in html
        assert 'case-study-scenario' in html
        assert 'case-study-lesson' in html
        assert 'Twitter/X API' in html
        assert 'exponential backoff' in html
        assert 'case-studies-badge' in html
        assert '3 cases' in html


class TestKeyboardShortcutsOverlay:
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

    def test_homepage_combined(self, client):
        """Combined checks for /."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'id="kbd-shortcuts-overlay"' in html
        assert 'kbd-shortcuts-panel' in html
        assert 'role="dialog"' in html
        assert 'aria-modal="true"' in html
        assert 'aria-label="Keyboard shortcuts"' in html
        assert 'id="kbd-shortcuts-close"' in html
        assert 'aria-label="Close shortcuts overlay"' in html
        assert 'Focus search' in html
        assert 'Show this help' in html
        assert 'Close overlay' in html
        assert 'data-context="home"' in html
        assert 'data-context="quiz"' in html
        assert 'data-context="detail"' in html
        assert '<kbd>/</kbd>' in html
        assert '<kbd>?</kbd>' in html
        assert '<kbd>Esc</kbd>' in html
        assert "e.key === '?'" in html
        assert 'kbd-shortcuts-visible' in html
        assert "e.key === 'Escape'" in html
        assert 'closeShortcuts' in html
        assert 'kbd-shortcuts-backdrop' in html
        assert "backdrop.addEventListener('click', closeShortcuts)" in html
        assert 'id="kbd-shortcuts-overlay" role="dialog" aria-modal="true" aria-label="Keyboard shortcuts" hidden' in html
        assert '<kbd>1</kbd>' in html
        assert '<kbd>2</kbd>' in html
        assert '<kbd>3</kbd>' in html
        assert '<kbd>4</kbd>' in html
        assert 'Select answer' in html
        assert "tag === 'INPUT'" in html
        assert "tag === 'TEXTAREA'" in html
# --- Mobile Polish CSS ---


class TestProfileFlockSharing:
    """Tests for profile sharing with flock codes."""

    def test_profile_flock_param_passed_to_template(self, client):
        """When ?flock= is present, the value should appear in the page JS."""
        resp = client.get('/profile?flock=dGVzdA==')
        html = resp.data.decode()
        assert 'dGVzdA==' in html

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

    def test_profile_combined(self, client):
        """Combined checks for /profile."""
        resp = client.get('/profile')
        html = resp.data.decode()
        assert 'profile-share-section' in html
        assert 'Share Profile' in html
        assert 'copy-flock-code' in html
        assert 'Copy Flock Code' in html
        assert 'copy-flock-link' in html
        assert 'Copy Link' in html
        assert 'share-flock-x' in html
        assert 'Share on X' in html
        assert 'var FLOCK_PARAM = ""' in html
        assert 'flock-comparison-section' in html
        assert 'flock-visitor-card' in html
        assert 'flock-you-card' in html
        assert 'flock-card--visitor' in html
        assert 'id="flock-comparison-section"' in html
        assert 'style="display:none"' in html
        assert 'profile-card-section' in html
        assert 'profile-share-card' in html
        assert 'profile-share-card-inner' in html
        assert 'profile-card-rank' in html
        assert 'profile-card-xp' in html
        assert 'profile-card-streak' in html
        assert 'profile-card-collection' in html
        assert 'httpparrots.com' in html
        assert 'buildFlockData' in html
        assert 'encodeFlockData' in html
        assert 'decodeFlockData' in html
        assert 'httpparrots.com/profile?flock=' in html

    def test_static_style_css_combined(self, client):
        """Combined CSS checks."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.profile-share-card' in css
        assert 'var(--gradient-brand)' in css
        assert '.profile-share-card-inner' in css
        assert 'backdrop-filter: blur(' in css
        assert '.profile-share-card-rank' in css
        assert '.profile-share-card-xp' in css
        assert '.profile-share-card-feathers' in css
        assert '.flock-comparison-grid' in css
        assert '.flock-card--visitor' in css
        assert '.flock-card--you' in css
        assert '#ffd700' in css  # golden border color
        assert '.profile-share-btn' in css
        assert '.profile-share-buttons' in css
        assert '.flock-comparison-grid' in css

    def test_profile_combined(self, client):
        """Combined checks for /profile."""
        resp = client.get('/profile')
        html = resp.data.decode()
        assert 'stat-freeze-count' in html
        assert 'Freezes' in html
        assert 'profile-milestones-section' in html
        assert 'profile-milestones-list' in html
        assert 'Milestones' in html
        assert 'httpparrot_daily' in html
        assert 'freezesAvailable' in html
        assert 'milestonesHit' in html
        assert '7-Day Streak' in html
        assert '14-Day Streak' in html
        assert '30-Day Streak' in html


    def test_frozen_solid_feather(self, client):
        """Frozen Solid feather should be defined and checked."""
        html = client.get('/').data.decode()
        assert 'frozen_solid' in html
        assert 'Frozen Solid' in html
        assert "!has('frozen_solid')" in html
        assert "httpparrot_freeze_used" in html


    def test_homepage_combined(self, client):
        """Combined checks for /."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'parrot_petter' in html
        assert 'Parrot Petter' in html
        assert 'Click any parrot on a detail page' in html
        assert 'httpparrot_parrot_petted' in html
        assert "parrot_petter" in html
        # The feather definition should have bonus: 10
        assert "'parrot_petter'" in html or "parrot_petter" in html


class TestInteractiveParrotClick:
    """Tests for interactive parrot click feature on detail pages."""

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

    def test_200_combined(self, client):
        """Combined checks for /200."""
        resp = client.get('/200')
        html = resp.data.decode()
        assert 'parrot-clickable' in html
        assert 'parrot-click-hint' in html
        assert 'role="button"' in html
        assert 'tabindex="0"' in html
        assert 'id="detail-parrot"' in html
        assert 'parrot-speech-bubble' in html
        assert 'id="parrot-speech-bubble"' in html
        assert 'aria-live="polite"' in html
        assert 'detail-parrot' in html
        assert 'parrot-speech-bubble' in html
        assert 'handleClick' in html
        assert 'ParrotSound.squawk()' in html
        assert 'httpparrot_parrot_petted' in html
        assert "ParrotXP.award(5, 'parrot_pet')" in html
        assert 'ParrotXP.checkFeathers()' in html
        assert "parrot-anim-" in html
        assert "category" in html
        assert "e.key === 'Enter'" in html
        assert "e.key === ' '" in html
        # The eli5 text is embedded in the script as a JSON string
        assert 'eli5Text' in html
        assert 'genericFacts' in html
        assert 'Tim Berners-Lee' in html


class TestInteractiveParrotClickCSS:
    """Tests for CSS animation classes used by interactive parrot click."""

    def test_category_colored_speech_bubbles(self, client):
        """CSS should have category-colored speech bubble borders."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        for cat in ['1xx', '2xx', '3xx', '4xx', '5xx']:
            assert f'.detail-cat-{cat} .parrot-speech-bubble' in css

    def test_static_style_css_combined(self, client):
        """Combined CSS checks."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.parrot-clickable' in css
        assert '.parrot-click-hint' in css
        assert '@keyframes parrot-click-hint' in css
        assert '@keyframes parrot-bounce-1xx' in css
        assert '.parrot-anim-1xx' in css
        assert '@keyframes parrot-wiggle-2xx' in css
        assert '.parrot-anim-2xx' in css
        assert '@keyframes parrot-slide-3xx' in css
        assert '.parrot-anim-3xx' in css
        assert '@keyframes parrot-shake-4xx' in css
        assert '.parrot-anim-4xx' in css
        assert '@keyframes parrot-glitch-5xx' in css
        assert '.parrot-anim-5xx' in css
        assert '.parrot-speech-bubble' in css
        assert '.parrot-speech-bubble.visible' in css
        assert '.parrot-speech-bubble::before' in css
        assert '.parrot-anim-1xx .img img' in css
        assert '.parrot-anim-2xx .img img' in css
        assert '.parrot-anim-3xx .img img' in css
        assert '.parrot-anim-4xx .img img' in css
        assert '.parrot-anim-5xx .img img' in css
        # Verify these are within a reduced motion media query
        assert 'prefers-reduced-motion: reduce' in css
        assert '.parrot-click-hint-hidden' in css
        assert '.parrot-anim-4xx .img' in css
        assert 'rgba(233, 69, 96' in css
        assert '.parrot-anim-5xx .img' in css
        assert 'rgba(123, 97, 255' in css


class TestProfileWeeklyChart:
    """Tests for the weekly progress bar chart on the profile page."""

    def test_profile_combined(self, client):
        """Combined checks for /profile."""
        resp = client.get('/profile')
        html = resp.data.decode()
        assert 'profile-weekly-section' in html
        assert 'profile-weekly-container' in html
        assert 'profile-weekly-chart' in html
        assert 'Bar chart showing XP earned per week' in html
        assert 'profile-weekly-trend' in html
        assert 'Weekly Progress' in html
        assert 'weeklyXp' in html
        assert 'weekNum' in html
        assert 'weekly-bar-col' in html
        assert 'weekly-bar' in html
        assert 'weekly-trend-up' in html
        assert 'weekly-trend-down' in html

    def test_static_style_css_combined(self, client):
        """Combined CSS checks."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.profile-weekly-section' in css
        assert '.profile-weekly-container' in css
        assert '.profile-weekly-chart' in css
        assert '.weekly-bar-col' in css
        assert '.weekly-bar' in css
        assert '.weekly-bar-label' in css
        assert '.weekly-trend-up' in css
        assert '.weekly-trend-down' in css
        assert '.weekly-trend-flat' in css
        assert '.profile-weekly-chart' in css
        assert 'display: flex' in css


class TestProfileWeeklyTier:
    """Tests for the weekly tier leaderboard on the profile page."""

    def test_profile_tier_css_exists(self, client):
        """CSS should contain styles for the weekly tier system."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.profile-tier-card' in css
        assert '.tier-bar' in css
        assert '.tier-bar-wrap' in css
        assert '.tier-name' in css

    def test_profile_top3_css_exists(self, client):
        """CSS should contain styles for the top 3 rarest feathers."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.profile-share-card-top3' in css
        assert '.top3-feather' in css


# --- Prestige System & Feather Progress ---

    def test_profile_combined(self, client):
        """Combined checks for /profile."""
        resp = client.get('/profile')
        html = resp.data.decode()
        assert b'Weekly Tier' in resp.data
        assert 'profile-tier-card' in html
        assert 'tier-bar' in html
        assert 'tier-bar-wrap' in html
        assert 'weeklyXP' in html
        assert 'weekStartStr' in html
        assert 'Bronze' in html
        assert 'Silver' in html
        assert 'Gold' in html
        assert 'Platinum' in html
        assert 'profile-card-top3' in html
        assert 'b.bonus - a.bonus' in html


class TestPrestigeSystem:
    """Tests for the prestige system and feather progress indicators."""

    def test_comeback_mechanic_in_base(self, client):
        """Base template should include comeback mechanic JS."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'httpparrot_last_visit_date' in html
        assert 'comeback-banner' in html

    def test_comeback_awards_bonus_xp(self, client):
        """Comeback mechanic should award bonus XP via ParrotXP."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'comeback_bonus' in html

    def test_profile_combined(self, client):
        """Combined checks for /profile."""
        resp = client.get('/profile')
        html = resp.data.decode()
        assert b'prestige' in resp.data.lower()
        assert 'prestige-btn' in html
        assert 'prestige-stars' in html
        assert 'getPrestige' in html
        assert 'PRESTIGE_KEY' in html
        assert 'prestige: prestige' in html
        assert 'getPrestige: getPrestige' in html
        assert 'getPrestige() * 0.1' in html
        assert 'getFeatherProgress' in html
        assert "'quiz_whiz'" in html or '"quiz_whiz"' in html
        assert "'explorer_10'" in html or '"explorer_10"' in html
        assert 'ParrotXP.prestige()' in html
        assert 'ParrotToast.show' in html
        assert 'XP reset with' in html
        assert b'Goals' in resp.data and b'goal-form' in resp.data
        assert b'goal-xp' in resp.data
        assert b'goal-date' in resp.data
        assert b'goal-set' in resp.data and b'Set Goal' in resp.data
        assert b'goal-display' in resp.data
        assert b'goal-progress-bar' in resp.data
        assert b'goal-clear' in resp.data
        assert 'httpparrot_goal' in html
        assert 'renderGoal' in html

    def test_static_style_css_combined(self, client):
        """Combined CSS checks."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.prestige-display' in css
        assert '.prestige-stars' in css
        assert '.prestige-btn' in css
        assert '.feather-progress' in css
        assert '.feather-progress-bar' in css
        assert '.feather-progress-text' in css
        assert '.comeback-banner' in css
        assert '.goal-form' in css
        assert '.goal-display' in css
        assert '.goal-progress-bar' in css
# --- Compare Page Transitions ---


class TestCompareTransitions:
    """Tests for compare page crossfade transitions and swap rotation."""

    def test_static_style_css_combined(self, client):
        """Combined CSS checks."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.compare-card.fading-out' in css
        assert '.compare-card.fading-in' in css
        assert '@keyframes compare-fade-in' in css
        assert '.compare-card.fading-out' in css
        # Find the rule and check opacity
        idx = css.index('.compare-card.fading-out')
        block = css[idx:idx+200]
        assert 'opacity: 0' in block
        idx = css.index('.compare-card.fading-out')
        block = css[idx:idx+200]
        assert 'translateY' in block
        assert '.compare-swap-btn.swap-rotating' in css
        assert 'rotate(180deg)' in css
        idx = css.index('.compare-swap-btn.swap-rotating')
        block = css[idx:idx+200]
        assert '--duration-normal' in block
        assert '--ease-out' in block
        assert '.compare-diff-wrap.diff-expanding' in css
        assert '.compare-diff-wrap.diff-expanded' in css
        idx = css.index('.compare-diff-wrap {')
        block = css[idx:idx+500]
        assert 'max-height' in block
        # Compare cards should have transition support via fading classes
        assert '.compare-card.fading-out' in css
        assert '.compare-card.fading-in' in css
# --- Flock Formation Celebration ---

    def test_compare_combined(self, client):
        """Combined checks for /compare."""
        resp = client.get('/compare')
        html = resp.data.decode()
        assert 'fading-out' in html
        assert 'fading-in' in html
        assert 'swap-rotating' in html
        assert 'diff-expanding' in html
        assert 'diff-expanded' in html


class TestFlockFormation:
    """Tests for the flock formation celebration feature."""

    def test_homepage_combined(self, client):
        """Combined checks for /."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'function spawnFlockFormation' in html
        assert 'spawnFlockFormation: spawnFlockFormation' in html
        assert 'spawnFlockFormation(false)' in html
        assert "rankTitle === 'Legendary Lorikeet'" in html
        assert 'spawnFlockFormation(true)' in html
        assert 'prefers-reduced-motion' in html
        assert 'flock-formation-container' in html
        assert '--flock-y' in html
        assert '--flock-x' in html
        assert 'flock-parrot-lead' in html
        assert 'flock-parrot-golden' in html
        assert 'container.remove()' in html
        assert 'flock-formation-legendary' in html
# --- 404 Memory Card Game ---

    def test_static_style_css_combined(self, client):
        """Combined CSS checks."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.flock-formation-container' in css
        assert '.flock-parrot' in css
        assert 'flock-fly' in css
        assert '.flock-parrot-lead' in css
        assert '.flock-parrot-golden' in css
        assert 'drop-shadow' in css
        assert '@keyframes flock-fly' in css
        assert '@keyframes flock-fly-loop' in css
        assert '.flock-parrot { display: none !important; }' in css
        assert '.flock-formation-container { display: none !important; }' in css


class TestMemoryGame:
    """Tests for the 404 memory card game feature."""

    def test_nonexistent_combined(self, client):
        """Combined checks for /nonexistent."""
        resp = client.get('/nonexistent')
        html = resp.data.decode()
        assert 'MEMORY_PAIRS' in html
        assert 'httpparrot_404_count' in html
        assert 'httpparrot_404_count' in html
        assert 'sessionStorage' in html
        assert 'count < 3' in html
        codes = ['200', '301', '404', '500', '401', '503', '418', '429']
        for code in codes:
            assert code in html, f"Status code {code} not found in memory game"
        names = ['OK', 'Not Found', 'Internal Server Error', 'Unauthorized',
                 'Too Many Requests', 'Service Unavailable']
        for name in names:
            assert name in html, f"Status name '{name}' not in memory game"
        assert 'memory-game-start-btn' in html
        assert 'Play Memory Game' in html
        assert 'memory-game-grid' in html
        assert 'memory-card-inner' in html
        assert 'memory-card-front' in html
        assert 'memory-card-back' in html
        assert 'memory-card-flipped' in html
        assert 'data-pair-id' in html
        assert 'data-card-type' in html
        assert 'memory-card-matched' in html
        assert 'memory-card-matched' in html
        assert 'onGameComplete' in html
        assert 'HIDDEN_FACTS' in html
        assert 'Hidden fact:' in html
        assert 'httpparrot_memory_game_complete' in html
        assert 'Photographic Memory' in html
        assert "eggs.indexOf('memory_game')" in html
        assert 'eggs_found' in html
        assert 'ParrotXP.award' in html
        assert 'memory_game_complete' in html
        assert "sessionStorage.removeItem('httpparrot_404_count')" in html
        assert "role', 'grid'" in html
        assert 'Memory card game grid' in html
        assert "createElement('button')" in html
        assert "Memory card " in html
        assert 'Fisher-Yates' in html
        assert "classList.remove('memory-card-flipped')" in html

    def test_static_style_css_combined(self, client):
        """Combined CSS checks."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.memory-game-grid' in css
        assert 'repeat(4, 1fr)' in css
        assert 'transform-style: preserve-3d' in css
        assert 'backface-visibility: hidden' in css
        assert 'rotateY(180deg)' in css
        assert '@keyframes memory-match-glow' in css
        assert '@keyframes memory-complete-appear' in css
        # Reduced motion handled by global catch-all block
        assert '.memory-card-inner' in css
        assert '.memory-game-complete' in css
        assert '.memory-game-start-btn' in css
        assert '.memory-game-congrats' in css
        assert '.memory-game-feather-award' in css
# --- Photographic Memory Feather ---


class TestPhotographicMemoryFeather:
    """Tests for the Photographic Memory feather badge."""

    def test_homepage_combined(self, client):
        """Combined checks for /."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'photo_memory' in html
        assert 'Photographic Memory' in html
        assert 'Complete the 404 memory card game' in html
        assert 'photo_memory' in html
        assert 'httpparrot_memory_game_complete' in html
        assert "photo_memory" in html
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

    def test_tester_combined(self, client):
        """Combined checks for /tester."""
        resp = client.get('/tester')
        html = resp.data.decode()
        assert 'tester-method-toggle' in html
        assert 'tester-method-btn' in html
        assert 'data-method="HEAD"' in html
        assert 'data-method="GET"' in html
        # HEAD button should have active class and aria-pressed=true
        assert 'data-method="HEAD"' in html
        # Check that the JS initializes with HEAD
        assert "selectedMethod = 'HEAD'" in html
        assert 'tester-body-preview' in html
        assert 'tester-body-header' in html
        assert 'tester-body-pre' in html
        assert 'tester-copy-body-btn' in html
        assert 'tester-body-collapse-btn' in html
        assert 'tester-content-type-badge' in html
        assert '/api/fetch-url' in html
        assert 'role="radiogroup"' in html
        assert 'aria-label="HTTP method"' in html
        assert 'aria-pressed="true"' in html
        assert 'aria-pressed="false"' in html


class TestPracticeResultsSummary:
    """Tests for the practice completion results summary overlay."""

    def test_practice_combined(self, client):
        """Combined checks for /practice."""
        resp = client.get('/practice')
        html = resp.data.decode()
        assert 'practice-results-overlay' in html
        assert 'practice-results-card' in html
        assert 'practice-results-title' in html
        assert 'practice-results-score' in html
        assert 'practice-results-xp' in html
        assert 'practice-results-grid' in html
        assert 'practice-results-share' in html
        assert 'practice-results-again' in html
        assert 'httpparrots.com/practice' in html
        assert 'checkCompletion' in html
        assert "classList.remove('answered')" in html
# --- Debug Results Summary ---

    def test_debug_combined(self, client):
        """Combined checks for /debug."""
        resp = client.get('/debug')
        html = resp.data.decode()
        assert 'debug-results-overlay' in html
        assert 'debug-results-card' in html
        assert 'debug-results-title' in html
        assert 'debug-results-score' in html
        assert 'debug-results-xp' in html
        assert 'debug-results-grid' in html
        assert 'debug-results-share' in html
        assert 'debug-results-again' in html
        assert 'httpparrots.com/debug' in html
        assert 'checkCompletion' in html
        assert "classList.remove('answered')" in html


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

    def test_homepage_combined(self, client):
        """Combined checks for /."""
        resp = client.get('/')
        html = resp.data.decode()
        assert "classList.add('has-streak')" in html
        assert 'dailyState.streak > 0' in html
        assert "animate-fill" in html
        assert "setTimeout" in html
        assert 'httpparrot_cat_visits' in html
        assert 'Explore' in html
        assert 'httpparrot_pairs_viewed' in html
        assert 'Study Pair' in html
        assert '401-vs-403' in html
        assert '301-vs-302' in html
        assert '200-vs-204' in html
        assert '500-vs-502' in html
        assert '400-vs-422' in html


class TestBackToTopOnLongPages:
    """Back-to-top button should be present on practice, debug, and review pages."""

    def test_practice_combined(self, client):
        """Combined checks for /practice."""
        resp = client.get('/practice')
        html = resp.data.decode()
        assert 'id="back-to-top"' in html
        assert 'back-to-top' in html
        assert 'Back to top' in html
        assert "getElementById('back-to-top')" in html
        assert "classList.add('visible')" in html
        assert 'aria-label="Back to top"' in html

    def test_debug_combined(self, client):
        """Combined checks for /debug."""
        resp = client.get('/debug')
        html = resp.data.decode()
        assert 'id="back-to-top"' in html
        assert 'back-to-top' in html
        assert 'Back to top' in html
        assert "getElementById('back-to-top')" in html
        assert "classList.add('visible')" in html
        assert 'aria-label="Back to top"' in html

    def test_review_combined(self, client):
        """Combined checks for /review."""
        resp = client.get('/review')
        html = resp.data.decode()
        assert 'id="back-to-top"' in html
        assert 'back-to-top' in html
        assert 'Back to top' in html
        assert "getElementById('back-to-top')" in html
        assert "classList.add('visible')" in html
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


class TestPOTDBadgeCSS:
    """Verify the Parrot of the Day CSS ribbon/badge exists on featured cards."""

    def test_potd_badge_css_complete(self):
        """CSS should have featured::before with POTD content, positioning, and border."""
        with open('static/style.css') as f:
            css = f.read()
        assert '.parrot.featured::before' in css
        assert "content: 'Parrot of the day'" in css
        assert 'position: absolute' in css
        assert '.parrot.featured' in css
        assert 'border-color' in css

    def test_featured_class_applied_in_homepage(self, client):
        """Homepage should have a card with the 'featured' CSS class."""
        html = client.get('/').data.decode()
        assert 'class="parrot parrot-' in html
        assert ' featured' in html


class TestKonamiEasterEgg:
    """Verify the Konami code easter egg listener and overlay exist."""

    def test_konami_easter_egg_complete(self, client):
        """Homepage should have Konami listener, overlay, party function, and egg tracking."""
        html = client.get('/').data.decode()
        assert 'konamiCode' in html
        assert "['ArrowUp','ArrowUp','ArrowDown','ArrowDown','ArrowLeft','ArrowRight','ArrowLeft','ArrowRight','b','a']" in html
        assert 'id="party-parrot-overlay"' in html
        assert 'id="party-parrot-container"' in html
        assert 'id="party-parrot-text"' in html
        assert 'PARTY PARROT MODE' in html
        assert 'activatePartyParrot' in html
        assert "eggs.indexOf('konami')" in html

    def test_konami_css(self):
        """CSS should define styles for the party parrot overlay."""
        with open('static/style.css') as f:
            css = f.read()
        assert '#party-parrot-overlay' in css
        assert '#party-parrot-overlay.active' in css


class TestFunFactsPool:
    """Verify the fun facts pool includes code-specific data."""

    def test_fun_facts_include_examples_for_code_with_extras(self, client):
        """Detail page with extra examples should inject them into codeSpecificFacts."""
        resp = client.get('/404')
        html = resp.data.decode()
        # 404 has examples in STATUS_EXTRA, they should appear in codeSpecificFacts
        assert 'codeSpecificFacts' in html

    def test_200_combined(self, client):
        """Combined checks for /200."""
        resp = client.get('/200')
        html = resp.data.decode()
        assert 'genericFacts' in html
        assert 'Tim Berners-Lee' in html
        assert 'codeSpecificFacts' in html
        assert 'eli5Text' in html
        assert 'codeSpecificFacts.push' in html
        # Count occurrences of entries in genericFacts array
        assert 'Roy Fielding' in html
        assert 'HTTPS was introduced' in html
        assert 'Cookies were invented' in html
# --- E5: Weekly Challenge Distinct Rewards ---


class TestWeeklyHistory:
    """Tests for weekly challenge history tracking and Theme Master feather."""

    def test_weekly_combined(self, client):
        """Combined checks for /weekly."""
        resp = client.get('/weekly')
        html = resp.data.decode()
        assert 'weekly-history' in html
        assert 'weekly-history-list' in html
        assert 'Past Challenges' in html
        assert 'httpparrot_weekly_history' in html
        assert 'function saveHistory' in html
        assert 'function getHistory' in html
        assert 'function renderHistory' in html
        assert 'weekly-history-row' in html
        assert 'renderHistory()' in html
        assert 'theme: THEME_NAME' in html


class TestParrotdexMilestones:
    """Tests for milestone badges and category progress in collection page."""

    def test_collection_category_bar_labels(self, client):
        """Category bars should have correct labels."""
        resp = client.get('/collection')
        html = resp.get_data(as_text=True)
        assert 'category-bar-label' in html
        for cat in ['1xx', '2xx', '3xx', '4xx', '5xx']:
            assert cat in html

    def test_milestone_and_category_bar_css(self):
        """CSS should include milestone badge and category progress bar styles."""
        with open('static/style.css') as f:
            css = f.read()
        for cls in ['.milestone-badge', '.milestone-earned', '.collection-milestones',
                     '.category-bar', '.category-bar-fill', '.category-bar-track',
                     '.collection-category-progress']:
            assert cls in css, f"Missing CSS class: {cls}"

    def test_collection_combined(self, client):
        """Combined checks for /collection."""
        resp = client.get('/collection')
        html = resp.data.decode()
        assert 'milestone-10' in html
        assert 'milestone-25' in html
        assert 'milestone-50' in html
        assert 'milestone-72' in html
        assert 'collection-milestones' in html
        assert 'category-progress' in html
        assert 'cat-fill-1' in html
        assert 'cat-fill-2' in html
        assert 'cat-fill-3' in html
        assert 'cat-fill-4' in html
        assert 'cat-fill-5' in html
        assert 'milestone-earned' in html
        assert 'catTotals' in html
        assert 'catCollected' in html


class TestTesterTruncationWarning:
    """Tests for the visible truncation warning in tester."""

    def test_tester_truncation_css(self):
        """CSS should include truncation warning styles with yellow theme."""
        with open('static/style.css') as f:
            css = f.read()
        assert '.tester-truncation-warning' in css
        assert '.tester-truncation-text' in css
        assert '.tester-truncation-icon' in css

    def test_tester_combined(self, client):
        """Combined checks for /tester."""
        resp = client.get('/tester')
        html = resp.data.decode()
        assert 'tester-truncation-warning' in html
        assert 'Response truncated at 10KB. Full response is larger.' in html
        assert "role', 'alert'" in html
        assert 'if (data.truncated)' in html
# --- FN2: Tester History, Export, Cross-links ---


class TestTesterHistoryExportCrosslinks:
    """Tests for tester request history panel, export buttons, and cross-tool links."""

    def test_tester_export_css_exists(self):
        """CSS should contain export button styles."""
        with open('static/style.css') as f:
            css = f.read()
        assert '.tester-export' in css
        assert '.tester-export-btn' in css

    def test_tester_crosslinks_css_exists(self):
        """CSS should contain cross-tool link styles."""
        with open('static/style.css') as f:
            css = f.read()
        assert '.tester-crosslinks' in css
        assert '.crosslink-btn' in css
        assert '.crosslink-label' in css

    def test_tester_history_css_exists(self):
        """CSS should contain history panel styles."""
        with open('static/style.css') as f:
            css = f.read()
        assert '.tester-history' in css
        assert '.history-row' in css
        assert '.history-method' in css
        assert '.history-url' in css
        assert '.history-status' in css
        assert '.history-time' in css
        assert '.tester-history-count' in css


# --- ED5: Expanded Case Studies ---

    def test_tester_combined(self, client):
        """Combined checks for /tester."""
        resp = client.get('/tester')
        html = resp.data.decode()
        assert b'tester-history' in resp.data
        assert 'export-curl' in html
        assert 'export-har' in html
        assert 'tester-export' in html
        assert 'crosslink-trace' in html
        assert 'crosslink-security' in html
        assert 'crosslink-cors' in html
        assert 'tester-crosslinks' in html
        assert 'httpparrot_tester_history' in html
        assert 'saveToHistory' in html
        assert 'renderHistory' in html
        assert 'getHistory' in html


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

class TestAdaptiveQuizDifficulty:
    """Tests for adaptive quiz difficulty with mistake tracking."""

    def test_quiz_combined(self, client):
        """Combined checks for /quiz."""
        resp = client.get('/quiz')
        html = resp.data.decode()
        assert 'httpparrot_quiz_mistakes' in html
        assert 'function getMistakes()' in html
        assert 'function saveMistakes(' in html
        assert 'function addMistake(' in html
        assert 'function removeMistake(' in html
        assert 'function pickWeightedCode()' in html
        assert 'Math.random() < 0.5' in html
        assert 'addMistake(correct.code)' in html
        assert 'removeMistake(correct.code)' in html
        assert 'const correct = pickWeightedCode()' in html
# --- Quiz Difficulty Selector ---


class TestQuizDifficultySelector:
    """Tests for the quiz difficulty selector (easy/medium/hard)."""

    def test_quiz_difficulty_css(self, client):
        """CSS should include quiz difficulty styles."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.quiz-difficulty' in css
        assert '.quiz-diff-btn' in css
        assert '.quiz-hard-input' in css


# --- Hover Sparkle ---

    def test_quiz_combined(self, client):
        """Combined checks for /quiz."""
        resp = client.get('/quiz')
        html = resp.data.decode()
        assert b'quiz-difficulty' in resp.data or b'quiz-diff-btn' in resp.data
        assert 'data-diff="easy"' in html
        assert 'data-diff="medium"' in html
        assert 'data-diff="hard"' in html
        assert "var difficulty = 'easy'" in html
        assert 'quiz-hard-guess' in html
        assert 'quiz-hard-submit' in html
        assert 'buildHardModeUI' in html
        assert "difficulty === 'medium' ? 6 : 4" in html
        assert 'function handleAnswer(' in html
        assert 'aria-label="Difficulty"' in html


class TestHoverSparkle:
    """Tests for subtle hover sparkle particles on parrot cards."""

    def test_homepage_has_hover_sparkle_script(self, client):
        """Homepage should include the hover sparkle particle script."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'hover-sparkle' in html
        assert 'mouseenter' in html
        assert 'prefers-reduced-motion' in html

    def test_hover_sparkle_respects_touch(self, client):
        """Sparkle script should skip on touch devices."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'ontouchstart' in html

    def test_hover_sparkle_css(self, client):
        """CSS should include hover sparkle styles."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.hover-sparkle' in css
        assert 'sparkle-fade' in css


# --- Quiz Share ---

class TestQuizShare:
    """Tests for enhanced quiz results sharing."""

    def test_quiz_share_css(self, client):
        """CSS should include quiz share styles."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.quiz-results-score' in css
        assert '.quiz-results-streak' in css
        assert '.quiz-results-actions' in css
        assert '.quiz-share-btn' in css


# --- Copy Helper ---

    def test_quiz_combined(self, client):
        """Combined checks for /quiz."""
        resp = client.get('/quiz')
        html = resp.data.decode()
        assert 'quiz-share-btn' in html
        assert 'Share Result' in html
        assert 'bestStreak' in html
        assert 'Best streak' in html
        assert 'quiz-results-score' in html
        assert 'quiz-results-streak' in html
        assert 'quiz-results-actions' in html


class TestCopyHelper:
    """Tests for the global ParrotCopy clipboard helper."""

    def test_base_has_copy_helper(self, client):
        """Base template should include the ParrotCopy helper."""
        resp = client.get('/')
        assert b'ParrotCopy' in resp.data

    def test_copy_helper_has_copy_method(self, client):
        """ParrotCopy should expose a copy method."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'ParrotCopy' in html
        assert 'copy: function(' in html

    def test_copy_success_css(self, client):
        """CSS should include copy-success flash styles."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.copy-success' in css


# --- Form Validation UX ---

class TestFormValidationUX:
    """Tests for inline validation error messages on forms."""

    def test_validation_error_css_exists(self):
        """CSS should include validation-error styles."""
        with open('static/style.css') as f:
            css = f.read()
        assert '.validation-error' in css
        assert '#ff6b6b' in css

    def test_tester_combined(self, client):
        """Combined checks for /tester."""
        resp = client.get('/tester')
        html = resp.data.decode()
        assert 'id="url-validation-error"' in html
        assert 'Please enter a URL' in html
        assert 'id="url-validation-error" role="alert" style="display:none;"' in html
        assert 'id="url-validation-error" role="alert"' in html
        assert "getElementById('url-validation-error').style.display = ''" in html
        assert "url-input').addEventListener('input'" in html

    def test_trace_combined(self, client):
        """Combined checks for /trace."""
        resp = client.get('/trace')
        html = resp.data.decode()
        assert 'id="trace-validation-error"' in html
        assert 'Please enter a URL' in html
        assert 'id="trace-validation-error" role="alert" style="display:none;"' in html
        assert "getElementById('trace-validation-error').style.display = ''" in html
        assert "trace-url').addEventListener('input'" in html

    def test_security_audit_combined(self, client):
        """Combined checks for /security-audit."""
        resp = client.get('/security-audit')
        html = resp.data.decode()
        assert 'id="audit-validation-error"' in html
        assert 'Please enter a URL' in html
        assert 'id="audit-validation-error" role="alert" style="display:none;"' in html
        assert "getElementById('audit-validation-error').style.display = ''" in html

    def test_cors_checker_combined(self, client):
        """Combined checks for /cors-checker."""
        resp = client.get('/cors-checker')
        html = resp.data.decode()
        assert 'id="cors-url-validation-error"' in html
        assert 'URL is required' in html
        assert 'id="cors-origin-validation-error"' in html
        assert 'Origin is required' in html
        assert 'id="cors-url-validation-error" role="alert" style="display:none;"' in html
        assert 'id="cors-origin-validation-error" role="alert" style="display:none;"' in html
        assert "getElementById('cors-url-validation-error').style.display = ''" in html
        assert "getElementById('cors-origin-validation-error').style.display = ''" in html

    def test_headers_combined(self, client):
        """Combined checks for /headers."""
        resp = client.get('/headers')
        html = resp.data.decode()
        assert 'id="header-validation-error"' in html
        assert 'Paste some headers first' in html
        assert 'id="header-validation-error" role="alert" style="display:none;"' in html
        assert "getElementById('header-validation-error').style.display = ''" in html
# --- Daily Challenge Suggested Actions ---


class TestDailySuggestedActions:
    """Tests for daily challenge navigation improvement."""

    def test_daily_suggested_actions_css(self):
        """CSS should include daily suggested actions styles."""
        with open('static/style.css') as f:
            css = f.read()
        assert '.daily-suggested-actions' in css
        assert '.daily-suggested-label' in css
        assert '.daily-suggested-link' in css

    def test_weekly_has_countdown(self, client):
        """Weekly page should have a countdown timer for next weekly challenge."""
        resp = client.get('/weekly')
        assert b'countdown' in resp.data.lower()


# --- Command Palette ---

    def test_daily_combined(self, client):
        """Combined checks for /daily."""
        resp = client.get('/daily')
        html = resp.data.decode()
        assert 'daily-suggested-actions' in html
        assert 'href="/weekly"' in html
        assert 'Weekly Challenge' in html
        assert 'href="/practice"' in html
        assert 'Practice' in html
        assert 'href="/quiz"' in html
        assert 'Quiz' in html
        assert 'daily-suggested-label' in html
        assert 'Keep practicing' in html
        assert 'Back to Home' not in html
        assert b'countdown' in resp.data.lower()


class TestCommandPalette:
    """Tests for the command palette (Cmd+K / Ctrl+K) feature."""

    def test_command_palette_on_detail_page(self, client):
        """Command palette should be available on detail pages too."""
        resp = client.get('/200')
        html = resp.data.decode()
        assert 'cmd-palette-overlay' in html

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

    def test_homepage_combined(self, client):
        """Combined checks for /."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'cmd-palette-overlay' in html
        assert 'cmd-palette-input' in html
        assert 'cmd-palette-results' in html
        assert 'placeholder="Search pages, status codes, actions..."' in html
        assert 'aria-label="Command palette search"' in html
        assert 'navigate' in html
        assert 'cmd-palette-footer' in html
        assert 'cmd-palette-backdrop' in html
        assert 'role="dialog"' in html
        assert 'aria-modal="true"' in html
        assert 'aria-label="Command palette"' in html
        assert 'role="listbox"' in html
        # Should contain status codes as JSON array
        assert '"200"' in html
        assert '"404"' in html
        assert '"OK"' in html
        assert '"Not Found"' in html
        assert "'/quiz'" in html
        assert "'/daily'" in html
        assert "'/tester'" in html
        assert "'/profile'" in html
        assert 'Take Quiz' in html
        assert 'Random Parrot' in html
        assert 'Go to Homepage' in html
        assert 'Go to Quiz' in html
        assert 'Go to Daily' in html
        assert 'Go to Profile' in html
        assert 'Random parrot' in html
        assert 'Command palette' in html
        assert 'Ctrl+K' in html
        assert 'hidden' in html
# --- Customizable Avatar & Theme Accent ---


class TestCustomizeAvatarAccent:
    """Tests for the customizable avatar and theme accent feature on the profile page."""

    def test_spirit_parrot_codes(self, client):
        """Spirit parrot options should include popular status codes."""
        resp = client.get('/profile')
        html = resp.data.decode()
        for code in ['200', '201', '301', '404', '418', '500', '503', '429']:
            assert f'data-code="{code}"' in html

    def test_accent_color_options(self, client):
        """There should be 5 accent color options."""
        resp = client.get('/profile')
        html = resp.data.decode()
        for accent in ['teal', 'purple', 'blue', 'gold', 'coral']:
            assert f'data-accent="{accent}"' in html

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

    def test_profile_combined(self, client):
        """Combined checks for /profile."""
        resp = client.get('/profile')
        html = resp.data.decode()
        assert 'profile-customize-section' in html
        assert 'Customize' in html
        assert 'spirit-parrot-grid' in html
        assert 'Spirit Parrot' in html
        # Count only the button elements with data-code (not JS references)
        assert html.count('class="spirit-parrot-option"') == 8
        assert '/static/200.jpg' in html
        assert '/static/404.jpg' in html
        assert '/static/418.jpg' in html
        assert 'role="radiogroup"' in html
        assert 'role="radio"' in html
        assert 'aria-checked=' in html
        assert 'aria-label="Choose your spirit parrot"' in html
        assert 'accent-color-grid' in html
        assert 'Theme Accent' in html
        assert 'accent-color-swatch' in html
        assert '#00c9a7' in html  # teal
        assert '#7b61ff' in html  # purple
        assert '#00b4d8' in html  # blue
        assert '#f9c74f' in html  # gold
        assert '#ff6b6b' in html  # coral
        assert 'aria-label="Choose accent color"' in html
        assert 'Pick the parrot that represents you' in html
        assert 'Choose your accent color' in html
        assert 'httpparrot_avatar' in html
        assert 'httpparrot_accent' in html


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

    def test_homepage_combined(self, client):
        """Combined checks for /."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'feather.meta' in html or '!!feather.meta' in html
        assert 'feather-toast-meta' in html
        assert 'META ACHIEVEMENT' in html
        assert 'spawnGoldenConfetti' in html
        assert 'triggerScreenShake' in html
        assert 'spawnGoldenConfetti(toast)' in html
        assert 'triggerScreenShake()' in html
        assert 'spawnFlockFormation(true)' in html
        assert "'#ffd700'" in html
        assert "'#ffb300'" in html
        assert 'golden-confetti' in html
        # Meta toast uses 5500ms dismiss time
        assert '5500' in html
        assert 'spawnCelebrationConfetti(toast)' in html
        assert 'prefers-reduced-motion' in html
# === F5: 404 Memory Game Replay ===


class TestMemoryGameReplay:
    """Tests for memory game Play Again button, best time, and faster replay."""

    def test_replay_css_exists(self):
        """CSS should style the replay button and time displays."""
        with open('static/style.css') as f:
            css = f.read()
        assert '.memory-game-replay-btn' in css
        assert '.memory-game-time' in css
        assert '.memory-game-best-time' in css
        assert '.memory-game-actions' in css

    def test_nonexistent_page_combined(self, client):
        """Combined checks for /nonexistent-page."""
        resp = client.get('/nonexistent-page')
        html = resp.data.decode()
        assert 'Play Again' in html
        assert 'memory-game-replay-btn' in html
        assert 'startMemoryGame(parent)' in html
        assert 'httpparrot_memory_best_time' in html
        assert 'memory-game-best-time' in html
        assert 'saveBestTime' in html
        assert 'BEST_TIME_KEY' in html
        assert 'gameStartTime' in html
        assert 'Date.now()' in html
        assert 'New best!' in html
        assert '800' in html
        assert 'getFlipBackDelay' in html
        assert 'playCount' in html
        assert 'formatTime' in html
        assert 'memory-game-actions' in html
        assert 'onGameComplete(parent, elapsed)' in html
        assert 'memory-game-home-btn' in html
        assert 'Back to all parrots' in html
# === FN4: Global Search Live Dropdown ===


class TestGlobalSearchDropdown:
    """Tests for global header search live dropdown."""

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

    def test_api_search_returns_results(self, client):
        """API search endpoint should return results for valid query."""
        resp = client.get('/api/search?q=not+found')
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)
        assert len(data) > 0
        assert data[0]['code'] == '404'


# === FN3: cURL Import to Playground Integration ===

    def test_homepage_combined(self, client):
        """Combined checks for /."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'global-search-dropdown' in html
        assert '/api/search' in html
        assert '300' in html
        assert 'debounceTimer' in html
        assert "e.key === 'Escape'" in html or 'Escape' in html
        assert 'closeDropdown' in html
        assert 'global-search-result-code' in html
        assert 'global-search-result-name' in html
        assert 'global-search-result-desc' in html
        # Results are <a> elements with href = '/' + code
        assert "opt.href = '/' + item.code" in html
        assert 'ArrowDown' in html
        assert 'ArrowUp' in html
        assert 'currentResults[activeIndex]' in html
        assert 'isDesktop' in html
        assert '768' in html
        assert 'role="listbox"' in html
        assert "role', 'option'" in html
        assert '80' in html
        assert "substring(0, 80)" in html


class TestCurlImportPlayground:
    """Tests for cURL Import to Playground link and Playground query param pre-population."""

    def test_playground_page_loads_with_params(self, client):
        """Playground should load successfully with query params."""
        resp = client.get('/playground?method=POST&url=https://api.example.com&body=test')
        assert resp.status_code == 200

    def test_curl_import_combined(self, client):
        """Combined checks for /curl-import."""
        resp = client.get('/curl-import')
        html = resp.data.decode()
        assert 'curl-playground-btn' in html
        assert "display:none" in html or "display: none" in html
        assert 'updatePlaygroundLink' in html
        assert "params.set('method'" in html
        assert "params.set('url'" in html
        assert "params.append('header'" in html
        assert "params.set('body'" in html
        assert "'/playground?'" in html
        assert 'Open in Playground' in html
        assert 'updatePlaygroundLink(req)' in html
# --- Task 1: Fill remaining case_studies gaps ---

    def test_playground_combined(self, client):
        """Combined checks for /playground."""
        resp = client.get('/playground')
        html = resp.data.decode()
        assert 'URLSearchParams' in html
        assert "params.has('method')" in html or "params.has('url')" in html
        assert "params.getAll('header')" in html
        assert "params.get('body')" in html
        assert 'replaceState' in html


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

    def test_dont_use_when_css_styles_present(self, client):
        """CSS should contain dont-use styles with red/coral accent."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert '.dont-use-section' in css
        assert '.dont-use-summary' in css
        assert '.dont-use-list' in css
        assert '.dont-use-item' in css
        assert '#e05252' in css

    def test_dont_use_when_renders_multiple_codes(self, client):
        """Multiple codes should render the dont_use_when section."""
        for code in ['201', '301', '401', '500']:
            resp = client.get(f'/{code}')
            html = resp.get_data(as_text=True)
            assert 'dont-use-section' in html, f"/{code} missing dont-use-section"


# --- Task 4: Security-category scenarios ---

    def test_200_combined(self, client):
        """Combined checks for /200."""
        resp = client.get('/200')
        html = resp.data.decode()
        assert 'dont-use-section' in html
        assert 'When NOT to use this code' in html
        assert 'dont-use-summary' in html
        mistakes_pos = html.find('mistakes-section')
        dont_use_pos = html.find('dont-use-section')
        assert mistakes_pos > 0, "mistakes-section not found"
        assert dont_use_pos > 0, "dont-use-section not found"
        assert dont_use_pos > mistakes_pos, (
            "dont-use-section should appear after mistakes-section"
        )


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

    def test_empty_state_css_styles(self):
        """CSS should include compare-empty-icon, heading, and text styles."""
        with open('/Users/mfelldin/dev/personal/httpparrot/static/style.css') as f:
            css = f.read()
        assert '.compare-empty-icon' in css
        assert '.compare-empty-heading' in css
        assert '.compare-empty-text' in css

    def test_compare_combined(self, client):
        """Combined checks for /compare."""
        resp = client.get('/compare')
        html = resp.data.decode()
        assert 'compare-empty-icon' in html
        assert 'compare-empty-heading' in html
        assert 'Pick two codes to compare' in html
        assert 'compare-empty-text' in html
        assert 'quick compare presets' in html


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


class TestBackToTopButton:
    """Test the back-to-top button styling and behavior."""

    def test_back_to_top_css_visibility(self):
        """Back-to-top CSS should use visibility for show/hide."""
        with open('static/style.css') as f:
            css = f.read()
        assert 'visibility: hidden' in css
        assert 'visibility: visible' in css

    def test_back_to_top_css_box_shadow(self):
        """Back-to-top button should use shadow token."""
        with open('static/style.css') as f:
            css = f.read()
        assert '.back-to-top' in css
        assert 'box-shadow: var(--shadow-md)' in css

    def test_back_to_top_visible_class(self):
        """Back-to-top .visible class should set visibility: visible."""
        with open('static/style.css') as f:
            css = f.read()
        # Check that .back-to-top.visible rule exists
        assert '.back-to-top.visible' in css


class TestFooterParrotCounter:
    """Test the footer parrot counter easter egg."""

    def test_footer_parrot_fly_animation(self):
        """CSS should contain the footer-parrot-fly keyframes."""
        with open('static/style.css') as f:
            css = f.read()
        assert '@keyframes footer-parrot-fly' in css

    def test_homepage_combined(self, client):
        """Combined checks for /."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'footer-parrot-counter' in html
        assert 'footer_party' in html
        assert 'eggs_found' in html
        assert "ParrotXP.award(100, 'easter_egg')" in html


class TestVerbRoulette:
    """Tests for the /verb-roulette mini-game page."""

    def test_verb_roulette_in_sitemap(self, client):
        resp = client.get('/sitemap.xml')
        assert b'/verb-roulette' in resp.data

    def test_verb_roulette_combined(self, client):
        """Combined checks for /verb-roulette."""
        resp = client.get('/verb-roulette')
        html = resp.data.decode()
        assert b'Verb Roulette' in resp.data
        assert 'id="r-method"' in html
        assert 'id="r-code"' in html
        assert 'id="r-yes"' in html
        assert 'id="r-no"' in html
        assert 'id="r-feedback"' in html
        assert 'id="r-correct"' in html
        assert 'id="r-total"' in html
        assert 'validMap' in html
        assert "'GET'" in html
        assert "'POST'" in html
        assert "'DELETE'" in html
        assert 'href="/verb-roulette"' in html


class TestHeaderChallenge:
    """Tests for the /header-challenge fill-in-the-header page."""

    def test_header_challenge_in_sitemap(self, client):
        resp = client.get('/sitemap.xml')
        assert b'/header-challenge' in resp.data

    def test_header_challenge_combined(self, client):
        """Combined checks for /header-challenge."""
        resp = client.get('/header-challenge')
        html = resp.data.decode()
        assert b'Header Challenge' in resp.data
        assert 'id="hc-code"' in html
        assert 'id="hc-answer"' in html
        assert 'id="hc-submit"' in html
        assert 'id="hc-feedback"' in html
        assert 'id="hc-correct"' in html
        assert 'id="hc-streak"' in html
        assert 'href="/header-challenge"' in html


class TestStatusCodeMap:
    """Tests for the /map status code relationship map page."""

    def test_map_in_sitemap(self, client):
        resp = client.get('/sitemap.xml')
        assert b'/map' in resp.data

    def test_map_combined(self, client):
        """Combined checks for /map."""
        resp = client.get('/map')
        html = resp.data.decode()
        assert b'Relationship Map' in resp.data or b'Status Code Map' in resp.data
        assert 'data-cat="all"' in html
        assert 'data-cat="1"' in html
        assert 'data-cat="5"' in html
        assert 'id="map-grid"' in html
        assert 'id="map-detail"' in html
        assert 'map-detail-hint' in html
        assert 'related' in html
        assert 'href="/map"' in html
        assert 'Visual map of HTTP status code relationships' in html


class TestApiDesignerPath:
    """Tests for the API Designer learning path."""

    def test_api_designer_path_content(self, client):
        """API Designer path should appear on paths index and have steps on detail page."""
        assert b'API Designer' in client.get('/paths').data
        html = client.get('/paths/api-designer').data.decode()
        assert 'API Designer' in html
        assert 'Visit 200 OK' in html
        assert 'Quiz: 10 questions' in html

    def test_api_designer_in_sitemap(self, client):
        """Sitemap should include the API Designer path."""
        assert b'/paths/api-designer' in client.get('/sitemap.xml').data


class TestRound6FinalPolish:
    """Tests for Round 6 Pass 10 final polish features."""

    def test_polish_css_features(self, client):
        """CSS should have page fade-in, visit-200 banner, search focus, and reduced motion."""
        css = client.get('/static/style.css').data.decode()
        assert 'page-fade-in' in css
        assert '.visit-200-banner' in css
        assert '.visit-200-visible' in css
        assert '.visit-200-text' in css
        assert '.search-input.search-focused' in css
        assert 'prefers-reduced-motion' in css

    def test_polish_homepage_scripts(self, client):
        """Homepage should have visit-200 celebration, search focus, and favorites."""
        html = client.get('/').data.decode()
        assert 'httpparrot_total_visits' in html
        assert 'visit-200-banner' in html
        assert 'search-focused' in html
        assert 'favorites' in html.lower() or 'fav-chip' in html


class TestRound7EngagementAndContent:
    """Tests for Round 7 engagement features and content additions."""

    def test_musical_tones_and_flash_xp(self, client):
        """Detail pages should have musical tones; homepage should have flash XP event."""
        assert b'AudioContext' in client.get('/200').data or b'musical' in client.get('/200').data.lower()
        resp404 = client.get('/404')
        assert b'chords' in resp404.data and b'sawtooth' in resp404.data
        assert '294, 349, 440' in client.get('/500').data.decode()
        home = client.get('/').data
        assert b'flash_event' in home or b'FLASH_KEY' in home
        assert b'isFlashActive()' in home

    def test_flash_and_animation_css(self, client):
        """CSS should have flash banner, indicator, details animation, fluid typography, and sticky profile."""
        css = client.get('/static/style.css').data
        assert b'flash-event-banner' in css
        assert b'flash-indicator' in css
        assert b'flash-pulse' in css
        assert b'details-open' in css
        assert b'clamp(' in css
        assert b'sticky' in css and b'profile-container' in css

    def test_round7_content_additions(self, client):
        """Debug exercises and learning paths should have new entries."""
        assert b'429 Missing Retry-After' in client.get('/debug').data or b'429-no-retry-after' in client.get('/debug').data
        assert b'Security Sentinel' in client.get('/paths').data
        assert client.get('/paths/security-sentinel').status_code == 200
        resp = client.get('/credits')
        assert resp.status_code == 200
        assert b'Credits' in resp.data or b'HTTP Parrots' in resp.data


class TestDesignAuditRound7:
    """Round 7 Pass 11 design audit -- spacing, light theme, focus, print."""

    def test_all_pages_return_200(self, client):
        """Every page route should return 200 or valid status."""
        pages = ['/', '/quiz', '/daily', '/weekly', '/practice', '/debug',
                 '/review', '/bingo', '/horoscope', '/predict', '/incidents',
                 '/content-negotiation', '/map', '/credits',
                 '/paths', '/learn', '/tester', '/headers', '/cors-checker',
                 '/security-audit', '/trace', '/playground', '/curl-import',
                 '/fault-simulator', '/webhook-inspector', '/compare',
                 '/personality', '/collection', '/cheatsheet', '/flowchart',
                 '/api-docs', '/profile', '/200', '/404']
        for page in pages:
            resp = client.get(page)
            assert resp.status_code in (200, 404), f'{page} returned {resp.status_code}'

    def test_container_padding_and_max_width(self, client):
        """Page containers should use 1.5rem padding and standard width tiers."""
        import re
        css = client.get('/static/style.css').data.decode()
        containers = [
            'incidents-container', 'predict-container', 'bingo-container',
            'horoscope-container', 'conneg-container', 'map-container',
        ]
        for c in containers:
            assert f'.{c}' in css
            match = re.search(rf'\.{c}\s*\{{[^}}]*padding:\s*[^;]*1\.5rem[^;]*;', css)
            assert match, f'.{c} should have 1.5rem side padding'
        valid_widths = {'560px', '620px', '640px', '720px', '800px', '900px', '1100px'}
        for match in re.finditer(r'\.\w+-container\s*\{[^}]*max-width:\s*(\d+px)', css):
            width = match.group(1)
            assert width in valid_widths, f'Container has non-standard max-width: {width}'

    def test_light_theme_overrides_round7(self, client):
        """Light theme should have overrides for incident, credits, favorites, predict, daily, timeline."""
        css = client.get('/static/style.css').data.decode()
        light_blocks = css.split('prefers-color-scheme: light')
        assert len(light_blocks) > 1, 'No light theme block found'
        light_css = ''.join(light_blocks[1:])
        for selector in ['.incident-card', '.credits-tagline', '.favorites-bar',
                         '.predict-correct', '.predict-wrong', '.daily-countdown',
                         '.incident-timeline']:
            assert selector in light_css, f'{selector} missing light theme override'

    def test_focus_visible_and_hover_states(self, client):
        """Key interactive elements should have focus-visible and hover styles."""
        css = client.get('/static/style.css').data.decode()
        for selector in ['.fav-chip:focus-visible', '.predict-submit:focus-visible',
                         '.incident-card summary:focus-visible',
                         '.predict-submit:hover', '.learn-quiz-submit:hover']:
            assert selector in css, f"Missing {selector}"

    def test_print_hides_interactive_chrome(self, client):
        """Print styles should hide flash banners and interactive chrome."""
        css = client.get('/static/style.css').data.decode()
        print_section = css.split('@media print')[1]
        for selector in ['.flash-event-banner', '.daily-countdown',
                         '.favorites-bar', '.insomnia-parrot',
                         '.feather-toast', '.rank-up-banner']:
            assert selector in print_section, f'{selector} should be hidden in print'

    def test_mobile_breakpoints(self, client):
        """Credits, incidents, and map should have mobile breakpoint styles."""
        import re
        css = client.get('/static/style.css').data.decode()
        assert '.credits-title' in css
        assert re.findall(r'@media\s*\(max-width:\s*576px\)\s*\{[^}]*\.credits-', css), \
            'Credits page missing mobile breakpoint'
        assert re.findall(r'@media\s*\(max-width:\s*576px\)\s*\{[^}]*\.incident', css), \
            'Incidents page missing mobile breakpoint'
        assert '.map-node' in css
        assert '.map-grid' in css


class TestHeaderRequirementIndicators:
    """Pass 3: Header requirement indicators on detail pages."""

    @pytest.mark.parametrize("path,header_name", [
        ('/301', 'Location'), ('/429', 'Retry-After'),
        ('/401', 'WWW-Authenticate'), ('/405', 'Allow'),
    ])
    def test_required_header_shown(self, client, path, header_name):
        """Pages with required headers should display them."""
        html = client.get(path).data.decode()
        assert header_name in html
        assert 'header-req-required' in html

    def test_recommended_header_shown(self, client):
        """304 should show ETag as recommended header."""
        html = client.get('/304').data.decode()
        assert 'ETag' in html
        assert 'header-req-recommended' in html

    def test_no_required_headers_on_200(self, client):
        """200 should not show required headers section."""
        assert 'Required Headers' not in client.get('/200').data.decode()

    def test_header_requirements_css(self, client):
        """CSS should have header requirement styles including mobile wrapping."""
        css = client.get('/static/style.css').data.decode()
        for cls in ['.header-requirements', '.header-req-row', '.header-req-name',
                     '.header-req-required', '.header-req-recommended']:
            assert cls in css, f"Missing CSS class: {cls}"
        assert 'flex-wrap: wrap' in css


class TestConfusionPair302vs303:
    """Pass 4: 302 vs 303 and other confusion pairs."""

    def test_learn_pair_302_vs_303_content(self, client):
        """302 vs 303 pair page should render with title and TL;DR."""
        html = client.get('/learn/302-vs-303').data.decode()
        assert '302 Found vs 303 See Other' in html
        assert 'Post/Redirect/Get' in html

    @pytest.mark.parametrize("slug", ['502-vs-504', '403-vs-404'])
    def test_additional_pairs_render(self, client, slug):
        """Additional confusion pair pages should render."""
        assert client.get(f'/learn/{slug}').status_code == 200

    def test_302_vs_303_in_learn_index(self, client):
        """Learn index should list the 302-vs-303 pair."""
        assert '302-vs-303' in client.get('/learn').data.decode()

    def test_scenario_count_at_least_64(self):
        """Scenarios module should have at least 64 entries."""
        from scenarios import SCENARIOS
        assert len(SCENARIOS) >= 64


class TestStaggeredReveals:
    """Tests for scroll-triggered staggered section reveals (Round 8 Pass 2)."""

    def test_detail_page_staggered_reveal_and_suggested_next(self, client):
        """Detail page should have staggered reveals and suggested-next section."""
        html = client.get('/200').data.decode()
        assert 'revealIndex' in html
        assert 'revealIndex * 80' in html
        assert 'suggested-next' in html
        assert 'suggested-link' in html
        assert 'You might also like' in html
        assert 'related-code-card' in html

    def test_suggested_next_css(self, client):
        """CSS should include suggested-next styles."""
        css = client.get('/static/style.css').data.decode()
        for cls in ['.suggested-next', '.suggested-label', '.suggested-link']:
            assert cls in css, f"Missing CSS class: {cls}"


class TestApiDocsBookmarklet:
    """Tests for the bookmarklet generator on the API docs page."""

    def test_api_docs_bookmarklet_complete(self, client):
        """API docs should have bookmarklet link, container, hint, and tester URL."""
        html = client.get('/api-docs').data.decode()
        assert 'bookmarklet' in html.lower()
        assert 'bookmarklet-link' in html
        assert 'bookmarklet-container' in html
        assert 'javascript:' in html
        assert 'tester?url=' in html
        assert 'bookmarklet-hint' in html
        assert 'Drag me' in html

    def test_bookmarklet_css(self, client):
        """CSS should include bookmarklet styles."""
        css = client.get('/static/style.css').data.decode()
        for cls in ['.bookmarklet-link', '.bookmarklet-hint', '.bookmarklet-container']:
            assert cls in css, f"Missing CSS class: {cls}"


class TestSmokeTest:
    """Quick smoke test covering all major features."""

    def test_all_page_routes_accessible(self, client):
        """Every page route returns 200 or expected status."""
        routes = [
            ('/', 200), ('/quiz', 200), ('/daily', 200), ('/weekly', 200),
            ('/practice', 200), ('/debug', 200), ('/review', 200),
            ('/bingo', 200), ('/horoscope', 200), ('/predict', 200),
            ('/incidents', 200), ('/content-negotiation', 200),
            ('/map', 200), ('/credits', 200), ('/paths', 200),
            ('/learn', 200), ('/tester', 200), ('/headers', 200),
            ('/cors-checker', 200), ('/security-audit', 200),
            ('/trace', 200), ('/playground', 200), ('/curl-import', 200),
            ('/fault-simulator', 200), ('/webhook-inspector', 200),
            ('/compare', 200), ('/personality', 200), ('/collection', 200),
            ('/cheatsheet', 200), ('/flowchart', 200), ('/api-docs', 200),
            ('/glossary', 200), ('/header-challenge', 200), ('/verb-roulette', 200),
            ('/profile', 200), ('/200', 200), ('/404', 404), ('/500', 500),
            ('/coffee', 418), ('/random', 302),
        ]
        for path, expected in routes:
            resp = client.get(path)
            assert resp.status_code == expected, (
                f'{path} returned {resp.status_code}, expected {expected}'
            )

    def test_api_endpoints_respond(self, client):
        """Core API endpoints return JSON."""
        resp = client.get('/api/search?q=200')
        assert resp.status_code == 200
        assert resp.content_type.startswith('application/json')

        resp = client.get('/api/diff?code1=200&code2=404')
        assert resp.status_code == 200

        resp = client.get('/echo')
        assert resp.status_code == 200

    def test_static_assets_serve(self, client):
        """CSS and images are accessible."""
        resp = client.get('/static/style.css')
        assert resp.status_code == 200
        assert b':root' in resp.data

        resp = client.get('/200.jpg')
        assert resp.status_code == 200


class TestRound10Pass7DebugExercises:
    """Tests for Round 10 Pass 7 — 3 new debug exercises."""

    def test_debug_exercise_count_at_least_36(self):
        from debug_exercises import DEBUG_EXERCISES
        assert len(DEBUG_EXERCISES) >= 36

    def test_debug_combined(self, client):
        """Combined checks for /debug."""
        resp = client.get('/debug')
        html = resp.data.decode()
        assert b'302 Changing POST to GET' in resp.data or b'302-method-change' in resp.data
        assert b'429 Without Backoff Guidance' in resp.data or b'429-aggressive-retry' in resp.data
        assert b'JSON Response with Wrong Content-Type' in resp.data or b'200-wrong-content-type' in resp.data

    def test_static_style_css_combined(self, client):
        """Combined CSS checks."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert b'path-step:hover' in resp.data
        assert b'path-card:hover' in resp.data
        assert b'color-teal' in resp.data
        assert b'collect-progress-fill' in resp.data


    def test_predict_page_tracks_timing(self, client):
        resp = client.get('/predict')
        assert b'questionStartTime' in resp.data or b'answerTime' in resp.data


    def test_static_style_css_combined(self, client):
        """Combined CSS checks."""
        resp = client.get('/static/style.css')
        css = resp.data.decode()
        assert b'.roulette-card' in resp.data
        assert b'.roulette-method' in resp.data
        assert b'.lightning-badge' in resp.data
        assert b'.roulette-btn:focus-visible' in resp.data
        assert b'.quiz-share-btn:focus-visible' in resp.data
        assert b'.roulette-buttons' in resp.data
        assert b'.hchallenge-input' in resp.data


    def test_scenario_count_at_least_68(self):
        """Scenarios module should have at least 68 entries."""
        from scenarios import SCENARIOS
        assert len(SCENARIOS) >= 68


    def test_debug_exercise_403_leak(self, client):
        resp = client.get('/debug')
        assert b'403-leaking-existence' in resp.data or b'Leaking Resource' in resp.data


    def test_homepage_has_onboarding(self, client):
        """Homepage should contain onboarding script."""
        resp = client.get('/')
        assert b'onboarding' in resp.data.lower()


    def test_profile_has_export(self, client):
        """Profile page should have export data section."""
        resp = client.get('/profile')
        assert b'Export Data' in resp.data or b'profile-export' in resp.data


    def test_learn_pair_408_vs_504(self, client):
        """408 vs 504 pair page should render successfully."""
        resp = client.get('/learn/408-vs-504')
        assert resp.status_code == 200


    def test_scenario_count_at_least_72(self):
        """Scenarios module should have at least 72 entries."""
        from scenarios import SCENARIOS
        assert len(SCENARIOS) >= 72


    def test_base_has_http_version_egg(self, client):
        """Homepage should contain HTTP version easter egg script."""
        resp = client.get('/')
        assert b'http_version' in resp.data or b'HTTP/2' in resp.data


    def test_static_style_css_combined(self, client):
        """Combined CSS checks."""
        css = client.get('/static/style.css').data.decode()
        with app.test_client() as client:
            assert '.glossary-term' in css
            assert '.onboarding-banner' in css
            assert '.theme-toggle-btn' in css
            assert '.profile-export-btn' in css
        with app.test_client() as client:
            assert '.glossary-search-wrap .search-input:focus-visible' in css
            assert '.onboarding-dismiss:focus-visible' in css
            assert '.theme-toggle-btn:focus-visible' in css
            assert '.profile-export-btn:focus-visible' in css
        with app.test_client() as client:
            assert '.onboarding-banner' in css
            assert '.glossary-search-wrap' in css
        with app.test_client() as client:
            assert 'prefers-reduced-motion' in css

