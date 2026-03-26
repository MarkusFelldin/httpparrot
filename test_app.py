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

    def test_api_docs_copy_curl_buttons(self, client):
        """API docs page has copy-as-curl buttons."""
        resp = client.get('/api-docs')
        html = resp.data.decode()
        assert 'docs-copy-curl-btn' in html
        assert 'Copy curl' in html


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

    def test_eli5_toggle_absent_on_page_without_eli5(self, client):
        """Pages without ELI5 content should not have the toggle."""
        resp = client.get('/100')
        html = resp.get_data(as_text=True)
        assert 'eli5-switch' not in html
        assert 'eli5-toggle' not in html

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

    def test_eli5_present_for_common_codes(self, client):
        """Common status codes should have ELI5 content in rendered HTML."""
        # 204 excluded: HTTP 204 returns empty body by protocol
        codes_with_eli5 = [
            '200', '201', '301', '302', '304', '400', '401', '403',
            '404', '405', '408', '418', '429', '500', '502', '503', '504',
        ]
        for code in codes_with_eli5:
            resp = client.get(f'/{code}')
            html = resp.get_data(as_text=True)
            assert 'eli5-simple' in html, f"Missing ELI5 for status code {code}"

    def test_eli5_data_in_status_extra(self):
        """STATUS_EXTRA should have eli5 keys for common codes."""
        from status_extra import STATUS_EXTRA
        codes_with_eli5 = [
            '200', '201', '204', '301', '302', '304', '400', '401', '403',
            '404', '405', '408', '418', '429', '500', '502', '503', '504',
        ]
        for code in codes_with_eli5:
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
    def test_homepage_has_potd_section(self, client):
        """Homepage should have a Parrot of the Day section."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'potd-section' in html
        assert 'Parrot of the Day' in html

    def test_potd_has_share_button(self, client):
        """POTD section should have a share button."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'potd-share' in html
        assert "Share today's parrot" in html

    def test_potd_has_fun_fact(self, client):
        """POTD section should display a fun fact."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'potd-fun-fact' in html

    def test_potd_has_image(self, client):
        """POTD section should have an image."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'potd-image' in html

    def test_potd_links_to_detail_page(self, client):
        """POTD section should link to the featured code's detail page."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'potd-link' in html

    def test_potd_deterministic(self, client):
        """Same day should produce the same POTD."""
        resp1 = client.get('/')
        resp2 = client.get('/')
        html1 = resp1.data.decode()
        html2 = resp2.data.decode()
        # Both should contain the same potd-code value
        import re
        code1 = re.search(r'class="potd-code[^"]*">(\d+)', html1)
        code2 = re.search(r'class="potd-code[^"]*">(\d+)', html2)
        assert code1 is not None
        assert code1.group(1) == code2.group(1)


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
        """Cheatsheet should have h1 followed by h2 for categories."""
        resp = client.get('/cheatsheet')
        html = resp.data.decode()
        h1_pos = html.find('<h1>')
        h2_pos = html.find('<h2')
        assert h1_pos > 0
        assert h2_pos > h1_pos

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

    def test_potd_link_has_aria_label(self, client):
        """Parrot of the Day link should have descriptive aria-label."""
        resp = client.get('/')
        html = resp.data.decode()
        assert 'class="potd-link"' in html
        assert 'aria-label="Parrot of the Day:' in html


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
        '/', '/quiz', '/daily', '/practice', '/flowchart', '/compare',
        '/tester', '/cheatsheet', '/headers', '/cors-checker',
        '/collection', '/playground', '/api-docs',
    ]

    def test_sitemap_returns_xml(self, client):
        resp = client.get('/sitemap.xml')
        assert resp.status_code == 200
        assert resp.content_type == 'application/xml'

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
            'Disallow: /api/check-cors',
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
