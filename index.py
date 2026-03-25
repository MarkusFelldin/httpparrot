import ipaddress
import logging
import os
import random
import re
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
from markupsafe import Markup, escape
from werkzeug.middleware.proxy_fix import ProxyFix

from status_descriptions import STATUS_INFO
from status_extra import STATUS_EXTRA
from http_examples import HTTP_EXAMPLES

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', os.urandom(32).hex())
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 86400  # 24h cache for static files
app.config['MAX_CONTENT_LENGTH'] = 1 * 1024 * 1024  # 1MB request body limit
app.config['DEBUG'] = False
Compress(app)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

_RFC_RE = re.compile(r'(RFC\s+(\d+))')


@app.template_filter('linkify_rfcs')
def linkify_rfcs(text):
    """Convert 'RFC XXXX' references to clickable IETF links."""
    parts = []
    last = 0
    for m in _RFC_RE.finditer(text):
        parts.append(escape(text[last:m.start()]))
        rfc_num = m.group(2)
        parts.append(Markup(
            f'<a href="https://datatracker.ietf.org/doc/html/rfc{rfc_num}" '
            f'class="rfc-link" target="_blank" rel="noopener">{escape(m.group(1))}</a>'
        ))
        last = m.end()
    parts.append(escape(text[last:]))
    return Markup(''.join(parts))


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

if not os.environ.get('SECRET_KEY'):
    logger.warning('SECRET_KEY not set — using random key. '
                   'Sessions will not persist across restarts.')

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
    """Resolve hostname to IP and validate it's not private.

    Returns (validated_url, original_hostname) or (None, None) if blocked.
    Uses getaddrinfo to resolve ALL addresses (IPv4 and IPv6) and validates
    every one against BLOCKED_NETWORKS. Returns the original URL (not
    IP-rewritten) so HTTPS certificate validation works correctly.

    Note: There is an inherent TOCTOU window between DNS resolution here and
    the subsequent HTTP request. We mitigate this by disabling redirect
    following in the caller, which prevents redirect-based SSRF bypass.
    Full elimination would require a custom transport adapter that pins the
    resolved IP, which is beyond scope for this application.
    """
    parsed = urlparse(url)
    hostname = parsed.hostname
    if not hostname:
        return None, None
    if parsed.username or parsed.password:
        return None, None
    try:
        addr_infos = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC,
                                        socket.SOCK_STREAM)
    except (socket.gaierror, OSError):
        return None, None
    if not addr_infos:
        return None, None
    for family, _type, _proto, _canonname, sockaddr in addr_infos:
        try:
            ip = ipaddress.ip_address(sockaddr[0])
        except ValueError:
            return None, None
        if any(ip in net for net in BLOCKED_NETWORKS):
            return None, None
    return url, hostname


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
    if 'Cache-Control' not in response.headers:
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


# --- Related codes ---

RELATED_CODES = {
    "100": [
        ("102", "Server is actively processing, not just acknowledging the request"),
        ("417", "Server rejected the Expect header that would have triggered 100"),
    ],
    "101": [
        ("426", "Server demands an upgrade — 101 means it accepted one"),
    ],
    "102": [
        ("100", "Simple acknowledgement vs. still actively processing"),
    ],
    "103": [
        ("200", "Final response with the actual content — 103 just sends early headers"),
    ],
    "200": [
        ("201", "Resource was created, not just retrieved"),
        ("204", "Success but intentionally no body"),
        ("304", "Resource hasn't changed — use your cached copy"),
    ],
    "201": [
        ("200", "Success but nothing new was created"),
        ("202", "Request accepted but creation hasn't happened yet"),
    ],
    "202": [
        ("201", "Already created vs. still pending"),
        ("200", "Completed successfully vs. just queued"),
    ],
    "203": [
        ("200", "Response came directly from the origin server, unmodified"),
    ],
    "204": [
        ("200", "Success with a body vs. intentionally empty"),
        ("205", "Also no body, but tells the client to reset its form/view"),
    ],
    "205": [
        ("204", "No content either, but doesn't ask the client to reset anything"),
    ],
    "206": [
        ("200", "Full resource vs. only the requested byte range"),
        ("416", "The requested range was invalid or unsatisfiable"),
    ],
    "207": [
        ("200", "Single status for the whole request vs. per-item statuses in the body"),
        ("208", "Sub-resource already enumerated in a previous 207 response"),
    ],
    "208": [
        ("207", "Multi-status container — 208 avoids repeating members already listed"),
    ],
    "226": [
        ("200", "Full representation vs. result of applying instance-manipulations"),
    ],
    "300": [
        ("301", "Server chose for you (permanent) vs. offering multiple options"),
        ("302", "Server chose for you (temporary) vs. offering multiple options"),
    ],
    "301": [
        ("302", "Temporary, not permanent — browsers may change POST to GET"),
        ("307", "Temporary and preserves the HTTP method"),
        ("308", "Permanent like 301, but preserves the HTTP method"),
    ],
    "302": [
        ("301", "Permanent, not temporary"),
        ("303", "Always redirects as GET — the standard Post/Redirect/Get pattern"),
        ("307", "Temporary like 302, but guarantees the method is preserved"),
    ],
    "303": [
        ("302", "Similar but method preservation is ambiguous"),
        ("307", "Temporary redirect that preserves the method instead of forcing GET"),
    ],
    "304": [
        ("200", "Full response — 304 means your cached version is still valid"),
        ("412", "Precondition failed vs. precondition confirmed (cache is fresh)"),
    ],
    "305": [
        ("407", "Proxy auth required vs. must use a specific proxy"),
    ],
    "306": [
        ("305", "Closely related deprecated proxy directive — 306 is reserved/unused"),
    ],
    "307": [
        ("302", "Similar but doesn't guarantee method preservation"),
        ("301", "Permanent redirect — browsers may change POST to GET"),
        ("308", "Permanent version of 307"),
    ],
    "308": [
        ("301", "Also permanent, but may change POST to GET"),
        ("307", "Temporary version of 308"),
    ],
    "400": [
        ("422", "Request is well-formed but semantically invalid (e.g. validation errors)"),
        ("405", "The URL is right but the HTTP method is wrong"),
    ],
    "401": [
        ("403", "Authenticated but not authorized — re-authenticating won't help"),
        ("407", "Same concept but for proxy authentication"),
    ],
    "402": [
        ("401", "Missing credentials vs. missing payment"),
        ("403", "Forbidden for authorization reasons, not payment"),
    ],
    "403": [
        ("401", "Not authenticated at all — credentials are missing or invalid"),
        ("404", "Sometimes used instead of 403 to hide that the resource exists"),
    ],
    "404": [
        ("410", "Resource existed but was intentionally and permanently removed"),
        ("403", "Resource exists but you're not allowed to see it"),
    ],
    "405": [
        ("400", "The method is fine but the request data is malformed"),
        ("501", "The server doesn't support this method at all, not just this endpoint"),
    ],
    "406": [
        ("415", "Client sent the wrong content type vs. can't get an acceptable one back"),
    ],
    "407": [
        ("401", "Origin server auth vs. proxy auth"),
        ("403", "Proxy refuses the request outright, not asking for credentials"),
    ],
    "408": [
        ("504", "Upstream server timed out vs. the client was too slow"),
        ("429", "Client sent too many requests vs. took too long on one"),
    ],
    "409": [
        ("412", "Precondition check failed vs. general state conflict"),
        ("422", "Semantically invalid vs. conflicts with current resource state"),
    ],
    "410": [
        ("404", "Resource might exist later — 410 means it's gone for good"),
    ],
    "411": [
        ("413", "Content-Length header is missing vs. the body is too large"),
    ],
    "412": [
        ("304", "Cache is still valid vs. precondition failed on a write"),
        ("409", "Resource state conflict vs. explicit precondition mismatch"),
    ],
    "413": [
        ("411", "Content-Length missing vs. body confirmed too large"),
        ("431", "Headers too large vs. body too large"),
    ],
    "414": [
        ("431", "Request headers too large vs. URI specifically too long"),
    ],
    "415": [
        ("406", "Server can't return an acceptable format vs. client sent the wrong format"),
    ],
    "416": [
        ("206", "Successful partial content vs. the range was unsatisfiable"),
    ],
    "417": [
        ("100", "Server would have sent Continue but rejects the expectation instead"),
    ],
    "418": [
        ("406", "Not Acceptable is the serious version of refusing a request"),
    ],
    "421": [
        ("400", "Bad request in general vs. request was routed to the wrong server"),
    ],
    "422": [
        ("400", "Request itself is malformed (bad JSON, missing fields)"),
    ],
    "423": [
        ("409", "Resource conflict vs. resource explicitly locked"),
        ("424", "This resource is locked vs. a dependency is the problem"),
    ],
    "424": [
        ("423", "This resource is locked vs. failed because a prerequisite request failed"),
    ],
    "425": [
        ("421", "Misdirected vs. too early — both reject seemingly valid requests"),
        ("428", "Missing precondition vs. replay risk from early data"),
    ],
    "426": [
        ("101", "Client accepted the upgrade vs. server demands one"),
        ("505", "HTTP version not supported vs. protocol upgrade required"),
    ],
    "428": [
        ("412", "Precondition was present but failed vs. precondition is missing entirely"),
    ],
    "429": [
        ("503", "Server is overloaded in general, not specifically rate-limiting you"),
    ],
    "431": [
        ("413", "Body too large vs. headers too large"),
        ("414", "URI too long — a specific case of oversized request metadata"),
    ],
    "444": [
        ("204", "Intentionally no content vs. connection dropped with no response at all"),
    ],
    "451": [
        ("403", "Forbidden for access-control reasons vs. censored for legal reasons"),
    ],
    "498": [
        ("401", "Standard missing/invalid credentials vs. specifically an invalid token"),
    ],
    "499": [
        ("498", "Token is invalid vs. token is missing entirely"),
        ("401", "Standard missing credentials vs. specifically a missing token"),
    ],
    "500": [
        ("502", "The upstream server sent a bad response, not this server's bug"),
        ("503", "Temporary overload or maintenance — it'll be back"),
    ],
    "501": [
        ("405", "This endpoint doesn't allow that method vs. the server never implements it"),
        ("505", "HTTP version not supported vs. method/feature not implemented"),
    ],
    "502": [
        ("500", "This server's own bug, not an upstream problem"),
        ("504", "Upstream didn't respond at all (timeout) vs. responded badly"),
    ],
    "503": [
        ("500", "Unexpected bug vs. expected downtime"),
        ("429", "Client is being rate-limited vs. server is overwhelmed"),
    ],
    "504": [
        ("502", "Upstream responded with garbage vs. didn't respond at all"),
        ("408", "Client was too slow, not the upstream server"),
    ],
    "505": [
        ("426", "Upgrade to a different protocol vs. HTTP version not supported"),
        ("501", "Feature not implemented vs. HTTP version not supported"),
    ],
    "506": [
        ("500", "Server bug vs. broken content negotiation creating a circular reference"),
    ],
    "507": [
        ("413", "Client payload too large vs. server has no storage left"),
        ("508", "Storage loop vs. simply out of space"),
    ],
    "508": [
        ("507", "Out of storage vs. infinite loop detected in the resource"),
    ],
    "510": [
        ("501", "Not implemented vs. request needs an extension the server lacks"),
    ],
    "511": [
        ("401", "Origin server auth vs. network-level auth (e.g. captive portal)"),
        ("407", "Proxy auth vs. network-level auth"),
    ],
}

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
    return render_template('http_parrots.html', status_code_list=codes, featured=featured,
                           status_info=STATUS_INFO)


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


@app.route('/compare')
def compare():
    """Render the side-by-side status code comparison tool."""
    codes = pruned_status_codes()
    code_list = [{"code": c.code, "name": c.name} for c in codes]
    return render_template('compare.html', code_list=code_list,
                           status_info=STATUS_INFO, status_extra=STATUS_EXTRA)


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
        resp = req.head(safe_url, allow_redirects=False, timeout=10)
        return jsonify({"code": resp.status_code, "url": url})
    except req.RequestException:
        return jsonify({"error": "Could not connect to the provided URL"}), 502


@app.route('/return/<int:code>')
def return_status(code):
    """Return a JSON response with the given HTTP status code.

    Intentionally returns the actual status code (including 1xx informational
    codes) so developers can use this endpoint for testing HTTP clients.
    """
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
    response = redirect(url_for('http_parrot', status_code=choice.code))
    response.headers['Cache-Control'] = 'no-store'
    return response


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
    related = RELATED_CODES.get(status_code, [])
    curl_cmd = f"curl -i {request.host_url}return/{status_code}"
    return render_template('http_parrot.html', status_code=status_code,
                           description=description, image=image, info=info,
                           extra=extra, http_example=http_example,
                           prev_code=prev_code, next_code=next_code,
                           related=related, curl_cmd=curl_cmd), code


@app.route('/<status_code>.jpg')
def http_parrot_image(status_code):
    image = find_image(status_code)
    if not image:
        abort(404)
    return send_from_directory('static', image)


if __name__ == '__main__':
    app.run()
