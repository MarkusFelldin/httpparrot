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
