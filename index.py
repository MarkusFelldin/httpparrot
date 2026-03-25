import ipaddress
import logging
import os
import random
import secrets
import socket
import time
from collections import namedtuple
from datetime import date
from urllib.parse import urlparse, urlunparse

import requests as req
from flask import (Flask, abort, g, jsonify, redirect, render_template,
                   request, send_from_directory, url_for)
from flask_compress import Compress

from status_descriptions import STATUS_INFO
from status_extra import STATUS_EXTRA
from http_examples import HTTP_EXAMPLES

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', os.urandom(32).hex())
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 86400  # 24h cache for static files
app.config['MAX_CONTENT_LENGTH'] = 1 * 1024 * 1024  # 1MB request body limit
app.config['DEBUG'] = False
Compress(app)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# --- Security ---

BLOCKED_NETWORKS = [
    ipaddress.ip_network('10.0.0.0/8'),
    ipaddress.ip_network('172.16.0.0/12'),
    ipaddress.ip_network('192.168.0.0/16'),
    ipaddress.ip_network('127.0.0.0/8'),
    ipaddress.ip_network('169.254.0.0/16'),
    ipaddress.ip_network('0.0.0.0/8'),
    ipaddress.ip_network('::1/128'),
    ipaddress.ip_network('fc00::/7'),
    ipaddress.ip_network('fe80::/10'),
]


def resolve_and_validate(url):
    """Resolve hostname to IP, validate it's not private, return IP-based URL.

    Returns (safe_url, resolved_ip) or (None, None) if blocked.
    Resolves once and rewrites the URL to use the IP directly,
    preventing DNS rebinding attacks.
    """
    parsed = urlparse(url)
    hostname = parsed.hostname
    if not hostname:
        return None, None
    try:
        resolved_ip = socket.gethostbyname(hostname)
        ip = ipaddress.ip_address(resolved_ip)
    except (socket.gaierror, ValueError):
        return None, None
    if any(ip in net for net in BLOCKED_NETWORKS):
        return None, None
    # Rewrite URL to use resolved IP, preventing DNS rebinding
    safe_parsed = parsed._replace(netloc=f"{resolved_ip}:{parsed.port}" if parsed.port else resolved_ip)
    return urlunparse(safe_parsed), hostname


# Simple in-memory rate limiter
_rate_limit = {}
_rate_limit_last_prune = 0
RATE_LIMIT_MAX = 10  # requests per window
RATE_LIMIT_WINDOW = 60  # seconds
_PRUNE_INTERVAL = 300  # prune stale entries every 5 minutes


def is_rate_limited(client_ip):
    global _rate_limit_last_prune
    now = time.time()
    # Periodically prune stale entries to prevent unbounded memory growth
    if now - _rate_limit_last_prune > _PRUNE_INTERVAL:
        _rate_limit_last_prune = now
        stale = [ip for ip, ts in _rate_limit.items()
                 if not ts or now - ts[-1] > RATE_LIMIT_WINDOW]
        for ip in stale:
            del _rate_limit[ip]
    if client_ip not in _rate_limit:
        _rate_limit[client_ip] = []
    # Clean old entries for this IP
    _rate_limit[client_ip] = [t for t in _rate_limit[client_ip] if now - t < RATE_LIMIT_WINDOW]
    if len(_rate_limit[client_ip]) >= RATE_LIMIT_MAX:
        return True
    _rate_limit[client_ip].append(now)
    return False


@app.context_processor
def inject_csp_nonce():
    nonce = secrets.token_urlsafe(32)
    g.csp_nonce = nonce
    return {'csp_nonce': nonce}


@app.after_request
def set_security_headers(response):
    nonce = getattr(g, 'csp_nonce', '')
    response.headers.pop('Server', None)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        f"script-src 'self' 'nonce-{nonce}'; "
        "style-src 'self' https://fonts.googleapis.com; "
        "font-src https://fonts.gstatic.com; "
        "img-src 'self'; "
        "connect-src 'self'"
    )
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    if request.path.startswith('/static/'):
        response.headers['Cache-Control'] = 'public, max-age=86400'
    else:
        response.headers['Cache-Control'] = 'public, max-age=60'
    return response


# --- Data ---

StatusCode = namedtuple('StatusCode', ['code', 'name'])
StatusCodeWithImage = namedtuple('StatusCodeWithImage', ['code', 'name', 'image'])

status_code_list = [
    StatusCode("100", "Continue"), StatusCode("101", "Switching Protocols"),
    StatusCode("102", "Processing"), StatusCode("103", "Early Hints"),
    StatusCode("200", "OK"), StatusCode("201", "Created"),
    StatusCode("202", "Accepted"), StatusCode("203", "Non-Authoritative Information"),
    StatusCode("204", "No Content"), StatusCode("205", "Reset Content"),
    StatusCode("206", "Partial Content"), StatusCode("207", "Multi-Status"),
    StatusCode("208", "Already Reported"), StatusCode("226", "IM Used"),
    StatusCode("300", "Multiple Choices"), StatusCode("301", "Moved Permanently"),
    StatusCode("302", "Found"), StatusCode("303", "See Other"),
    StatusCode("304", "Not Modified"), StatusCode("305", "Use Proxy"),
    StatusCode("306", "Switch Proxy"), StatusCode("307", "Temporary Redirect"),
    StatusCode("308", "Permanent Redirect"),
    StatusCode("400", "Bad Request"), StatusCode("401", "Unauthorized"),
    StatusCode("402", "Payment Required"), StatusCode("403", "Forbidden"),
    StatusCode("404", "Not Found"), StatusCode("405", "Method Not Allowed"),
    StatusCode("406", "Not Acceptable"), StatusCode("407", "Proxy Authentication Required"),
    StatusCode("408", "Request Time-out"), StatusCode("409", "Conflict"),
    StatusCode("410", "Gone"), StatusCode("411", "Length Required"),
    StatusCode("412", "Precondition Failed"), StatusCode("413", "Payload Too Large"),
    StatusCode("414", "URI Too Long"), StatusCode("415", "Unsupported Media Type"),
    StatusCode("416", "Range Not Satisfiable"), StatusCode("417", "Expectation Failed"),
    StatusCode("418", "I'm a teapot"), StatusCode("419", "I'm a Fox"),
    StatusCode("420", "Enhance Your Calm"), StatusCode("421", "Misdirected Request"),
    StatusCode("422", "Unprocessable Entity"), StatusCode("423", "Locked"),
    StatusCode("424", "Failed Dependency"), StatusCode("425", "Too Early"),
    StatusCode("426", "Upgrade Required"), StatusCode("428", "Precondition Required"),
    StatusCode("429", "Too Many Requests"), StatusCode("431", "Request Header Fields Too Large"),
    StatusCode("444", "No Response"), StatusCode("450", "Blocked by Windows Parental Controls"),
    StatusCode("451", "Unavailable For Legal Reasons"),
    StatusCode("494", "Request Header Too Large"),
    StatusCode("498", "Invalid Token"), StatusCode("499", "Token Required"),
    StatusCode("500", "Internal Server Error"), StatusCode("501", "Not Implemented"),
    StatusCode("502", "Bad Gateway"), StatusCode("503", "Service Unavailable"),
    StatusCode("504", "Gateway Time-out"), StatusCode("505", "HTTP Version Not Supported"),
    StatusCode("506", "Variant Also Negotiates"), StatusCode("507", "Insufficient Storage"),
    StatusCode("508", "Loop Detected"), StatusCode("509", "Bandwidth Limit Exceeded"),
    StatusCode("510", "Not Extended"), StatusCode("511", "Network Authentication Required"),
    StatusCode("530", "Site is Frozen"),
]

IMAGE_EXTENSIONS = ['.jpg', '.jpeg', '.JPG', '.png', '.gif']


def _find_image(code):
    for ext in IMAGE_EXTENSIONS:
        path = os.path.join('static', code + ext)
        if os.path.exists(path):
            return code + ext
    return None


# Build caches at startup
def _build_caches():
    pruned = []
    image_map = {}
    for sc in status_code_list:
        image = _find_image(sc.code)
        if image:
            pruned.append(StatusCodeWithImage(sc.code, sc.name, image))
            image_map[sc.code] = image
    pruned.sort(key=lambda s: int(s.code))
    return pruned, image_map


_pruned_cache, _image_cache = _build_caches()


def pruned_status_codes():
    return _pruned_cache


def find_image(code):
    return _image_cache.get(code)


# --- Routes ---

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404


@app.route('/')
def http_parrots():
    """Render the homepage gallery of all HTTP status code parrots."""
    codes = pruned_status_codes()
    day_index = date.today().toordinal() % len(codes)
    featured = codes[day_index].code
    return render_template('http_parrots.html', status_code_list=codes, featured=featured)


@app.route('/quiz')
def quiz():
    """Render the quiz page where users guess status codes from parrot images."""
    codes = pruned_status_codes()
    quiz_data = [{"code": c.code, "name": c.name, "image": c.image} for c in codes]
    return render_template('quiz.html', quiz_data=quiz_data)


@app.route('/api-docs')
def api_docs():
    return render_template('api_docs.html')


@app.route('/cheatsheet')
def cheatsheet():
    """Render the printable cheat sheet of all status codes by category."""
    codes = pruned_status_codes()
    categories = [
        ("1xx", "Informational", [c for c in codes if c.code.startswith('1')]),
        ("2xx", "Success", [c for c in codes if c.code.startswith('2')]),
        ("3xx", "Redirection", [c for c in codes if c.code.startswith('3')]),
        ("4xx", "Client Error", [c for c in codes if c.code.startswith('4')]),
        ("5xx", "Server Error", [c for c in codes if c.code.startswith('5')]),
    ]
    return render_template('cheatsheet.html', categories=categories)


@app.route('/flowchart')
def flowchart():
    return render_template('flowchart.html')


@app.route('/tester')
def tester():
    return render_template('tester.html')


@app.route('/api/check-url')
def check_url():
    """Make a HEAD request to a user-provided URL and return its status code."""
    if is_rate_limited(request.remote_addr):
        logger.warning('Rate limit exceeded for %s', request.remote_addr)
        return jsonify({"error": "Rate limit exceeded. Try again later."}), 429
    url = request.args.get('url', '')
    if not url:
        return jsonify({"error": "No URL provided"}), 400
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    safe_url, hostname = resolve_and_validate(url)
    if not safe_url:
        logger.warning('SSRF blocked: %s from %s', url, request.remote_addr)
        return jsonify({"error": "URL not allowed"}), 403
    try:
        resp = req.head(safe_url, headers={"Host": hostname},
                        allow_redirects=False, timeout=10)
        return jsonify({"code": resp.status_code, "url": url})
    except req.RequestException:
        return jsonify({"error": "Could not connect to the provided URL"}), 502


@app.route('/return/<int:code>')
def return_status(code):
    """Return a JSON response with the given HTTP status code."""
    if code < 100 or code > 599:
        abort(404)
    description = next((s.name for s in status_code_list if s.code == str(code)), 'Unknown')
    response = jsonify({
        "code": code,
        "description": description,
        "message": f"This response was returned with HTTP status {code}.",
    })
    response.status_code = code
    return response


@app.route('/random')
def random_parrot():
    """Redirect to a random status code detail page."""
    codes = pruned_status_codes()
    choice = random.choice(codes)
    return redirect(url_for('http_parrot', status_code=choice.code))


@app.route('/<status_code>')
def http_parrot(status_code):
    """Serve a status code detail page, image, or JSON via content negotiation."""
    try:
        code = int(status_code)
    except ValueError:
        abort(404)
    if not any(s.code == status_code for s in status_code_list):
        abort(404)
    # Only return the actual status code for 2xx/4xx/5xx.
    # 1xx and 3xx codes have special HTTP semantics that break the response.
    if code < 200 or 300 <= code < 400:
        code = 200
    image = find_image(status_code)
    best = request.accept_mimetypes.best_match(['text/html', 'image/*', 'application/json'])
    if image and best == 'image/*':
        return send_from_directory('static', image), code
    description = next((s.name for s in status_code_list if s.code == status_code), '')
    info = STATUS_INFO.get(status_code, {})
    extra = STATUS_EXTRA.get(status_code, {})
    http_example = HTTP_EXAMPLES.get(status_code, {})
    if best == 'application/json':
        return jsonify({
            "code": status_code,
            "description": description,
            "image": f"/{image}" if image else None,
            "meaning": info.get("description", ""),
            "history": info.get("history", ""),
        }), code
    codes = pruned_status_codes()
    code_list = [c.code for c in codes]
    try:
        idx = code_list.index(status_code)
    except ValueError:
        idx = -1
    prev_code = code_list[idx - 1] if idx > 0 else None
    next_code = code_list[idx + 1] if 0 <= idx < len(code_list) - 1 else None
    return render_template('http_parrot.html', status_code=status_code,
                           description=description, image=image, info=info,
                           extra=extra, http_example=http_example,
                           prev_code=prev_code, next_code=next_code), code


@app.route('/<status_code>.jpg')
def http_parrot_image(status_code):
    image = find_image(status_code)
    if not image:
        abort(404)
    return send_from_directory('static', image)


if __name__ == '__main__':
    app.run()
