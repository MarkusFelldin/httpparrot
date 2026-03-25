"""Tests for HTTP Parrots application."""
import time
from unittest.mock import patch

import pytest

from index import app, _rate_limit, is_rate_limited, resolve_and_validate


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

    def test_rewrites_url_to_ip(self):
        with patch('socket.gethostbyname', return_value='93.184.216.34'):
            result, _ = resolve_and_validate('http://example.com/path')
            assert '93.184.216.34' in result

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
