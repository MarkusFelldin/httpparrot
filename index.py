import ipaddress
import os
import random
import socket
import time
from datetime import date
from urllib.parse import urlparse, urlunparse

import requests as req
from flask import (Flask, abort, jsonify, redirect, render_template, request,
                   send_from_directory, url_for)

from status_descriptions import STATUS_INFO
from status_extra import STATUS_EXTRA
from http_examples import HTTP_EXAMPLES

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', os.urandom(32).hex())
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 86400  # 24h cache for static files


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
RATE_LIMIT_MAX = 10  # requests per window
RATE_LIMIT_WINDOW = 60  # seconds


def is_rate_limited(client_ip):
    now = time.time()
    if client_ip not in _rate_limit:
        _rate_limit[client_ip] = []
    # Clean old entries
    _rate_limit[client_ip] = [t for t in _rate_limit[client_ip] if now - t < RATE_LIMIT_WINDOW]
    if len(_rate_limit[client_ip]) >= RATE_LIMIT_MAX:
        return True
    _rate_limit[client_ip].append(now)
    return False


@app.after_request
def set_security_headers(response):
    response.headers.pop('Server', None)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
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

status_code_list = [
    ["100", "Continue"], ["101", "Switching Protocols"], ["102", "Processing"],
    ["103", "Early Hints"],
    ["200", "OK"], ["201", "Created"], ["202", "Accepted"],
    ["203", "Non-Authoritative Information"], ["204", "No Content"],
    ["205", "Reset Content"], ["206", "Partial Content"],
    ["207", "Multi-Status"], ["208", "Already Reported"], ["226", "IM Used"],
    ["300", "Multiple Choices"], ["301", "Moved Permanently"], ["302", "Found"],
    ["303", "See Other"], ["304", "Not Modified"], ["305", "Use Proxy"],
    ["306", "Switch Proxy"], ["307", "Temporary Redirect"],
    ["308", "Permanent Redirect"],
    ["400", "Bad Request"], ["401", "Unauthorized"], ["402", "Payment Required"],
    ["403", "Forbidden"], ["404", "Not Found"], ["405", "Method Not Allowed"],
    ["406", "Not Acceptable"], ["407", "Proxy Authentication Required"],
    ["408", "Request Time-out"], ["409", "Conflict"], ["410", "Gone"],
    ["411", "Length Required"], ["412", "Precondition Failed"],
    ["413", "Payload Too Large"], ["414", "URI Too Long"],
    ["415", "Unsupported Media Type"], ["416", "Range Not Satisfiable"],
    ["417", "Expectation Failed"], ["418", "I'm a teapot"],
    ["419", "I'm a Fox"], ["420", "Enhance Your Calm"],
    ["421", "Misdirected Request"], ["422", "Unprocessable Entity"],
    ["423", "Locked"], ["424", "Failed Dependency"], ["425", "Too Early"],
    ["426", "Upgrade Required"], ["428", "Precondition Required"],
    ["429", "Too Many Requests"], ["431", "Request Header Fields Too Large"],
    ["444", "No Response"], ["450", "Blocked by Windows Parental Controls"],
    ["451", "Unavailable For Legal Reasons"],
    ["494", "Request Header Too Large"],
    ["498", "Invalid Token"], ["499", "Token Required"],
    ["500", "Internal Server Error"], ["501", "Not Implemented"],
    ["502", "Bad Gateway"], ["503", "Service Unavailable"],
    ["504", "Gateway Time-out"], ["505", "HTTP Version Not Supported"],
    ["506", "Variant Also Negotiates"], ["507", "Insufficient Storage"],
    ["508", "Loop Detected"], ["509", "Bandwidth Limit Exceeded"],
    ["510", "Not Extended"], ["511", "Network Authentication Required"],
    ["530", "Site is Frozen"],
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
    for status_code in status_code_list:
        image = _find_image(status_code[0])
        if image:
            pruned.append(status_code + [image])
            image_map[status_code[0]] = image
    pruned.sort(key=lambda s: int(s[0]))
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
    codes = pruned_status_codes()
    day_index = date.today().toordinal() % len(codes)
    featured = codes[day_index][0]
    return render_template('http_parrots.html', status_code_list=codes, featured=featured)


@app.route('/quiz')
def quiz():
    codes = pruned_status_codes()
    quiz_data = [{"code": c[0], "name": c[1], "image": c[2]} for c in codes]
    return render_template('quiz.html', quiz_data=quiz_data)


@app.route('/api-docs')
def api_docs():
    return render_template('api_docs.html')


@app.route('/cheatsheet')
def cheatsheet():
    codes = pruned_status_codes()
    categories = [
        ("1xx", "Informational", [c for c in codes if c[0].startswith('1')]),
        ("2xx", "Success", [c for c in codes if c[0].startswith('2')]),
        ("3xx", "Redirection", [c for c in codes if c[0].startswith('3')]),
        ("4xx", "Client Error", [c for c in codes if c[0].startswith('4')]),
        ("5xx", "Server Error", [c for c in codes if c[0].startswith('5')]),
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
    if is_rate_limited(request.remote_addr):
        return jsonify({"error": "Rate limit exceeded. Try again later."}), 429
    url = request.args.get('url', '')
    if not url:
        return jsonify({"error": "No URL provided"}), 400
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    safe_url, hostname = resolve_and_validate(url)
    if not safe_url:
        return jsonify({"error": "URL not allowed"}), 403
    try:
        resp = req.head(safe_url, headers={"Host": hostname},
                        allow_redirects=False, timeout=10)
        return jsonify({"code": resp.status_code, "url": url})
    except req.RequestException:
        return jsonify({"error": "Could not connect to the provided URL"}), 502


@app.route('/random')
def random_parrot():
    codes = pruned_status_codes()
    choice = random.choice(codes)
    return redirect(url_for('http_parrot', status_code=choice[0]))


@app.route('/<status_code>')
def http_parrot(status_code):
    try:
        code = int(status_code)
    except ValueError:
        abort(404)
    if not any(s[0] == status_code for s in status_code_list):
        abort(404)
    # Only return the actual status code for 2xx/4xx/5xx.
    # 1xx and 3xx codes have special HTTP semantics that break the response.
    if code < 200 or 300 <= code < 400:
        code = 200
    image = find_image(status_code)
    best = request.accept_mimetypes.best_match(['text/html', 'image/*', 'application/json'])
    if image and best == 'image/*':
        return send_from_directory('static', image), code
    description = next((s[1] for s in status_code_list if s[0] == status_code), '')
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
    code_list = [c[0] for c in codes]
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
