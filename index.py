import ipaddress
import json
import logging
import os
import random
import re
import secrets
import socket
import time
from collections import namedtuple
from datetime import date, datetime, timezone
from urllib.parse import urlparse
from xml.sax.saxutils import escape as xml_escape

import requests as req
from flask import (Flask, abort, g, jsonify, redirect, render_template,
                   request, send_from_directory, url_for)
from flask_compress import Compress
from markupsafe import Markup, escape
from werkzeug.middleware.proxy_fix import ProxyFix

from status_descriptions import STATUS_INFO
from status_extra import STATUS_EXTRA
from http_examples import HTTP_EXAMPLES
from scenarios import SCENARIOS
from debug_exercises import DEBUG_EXERCISES
from confusion_pairs import CONFUSION_PAIRS, CONFUSION_PAIRS_BY_SLUG, CONFUSION_PAIRS_BY_CODE
from learning_paths import LEARNING_PATHS, LEARNING_PATHS_BY_ID

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


_HTTP_METHOD_RE = re.compile(
    r'^(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS|PROPFIND|PROPPATCH|MKCOL'
    r'|COPY|MOVE|LOCK|UNLOCK|TRACE|CONNECT)\b',
    re.MULTILINE,
)
_HTTP_STATUS_LINE_RE = re.compile(r'^(HTTP/\d\.\d\s+\d{3}[^\n]*)', re.MULTILINE)
_HTTP_HEADER_RE = re.compile(r'^([A-Za-z][A-Za-z0-9\-]*)(:)', re.MULTILINE)


@app.template_filter('highlight_http')
def highlight_http(text, panel_type='request'):
    """Add syntax-highlighting spans to HTTP request/response text.

    Wraps HTTP methods, status lines, and header names in styled spans
    so CSS can colorize them without JavaScript.  Each line is wrapped in
    a ``<span class="http-line">`` so CSS can animate lines sequentially.
    """
    text = str(escape(text))
    # Highlight status lines first (response)
    text = _HTTP_STATUS_LINE_RE.sub(
        r'<span class="http-hl-status">\1</span>', text)
    # Highlight HTTP methods (request)
    text = _HTTP_METHOD_RE.sub(
        r'<span class="http-hl-method">\1</span>', text)
    # Highlight header names
    text = _HTTP_HEADER_RE.sub(
        r'<span class="http-hl-header">\1</span>\2', text)
    # Wrap each line in a span for sequential animation
    lines = text.split('\n')
    text = '\n'.join(
        f'<span class="http-line">{line}</span>' for line in lines
    )
    return Markup(text)


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


def _is_blocked_ip(ip):
    """Return True if the IP address falls within any blocked network."""
    # Normalize IPv6-mapped IPv4 addresses (e.g. ::ffff:127.0.0.1)
    # to their IPv4 equivalent so they match the IPv4 blocked networks.
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return any(ip in net for net in BLOCKED_NETWORKS)


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
    _FAIL = (None, None)
    parsed = urlparse(url)
    if parsed.scheme not in ('http', 'https'):
        return _FAIL
    hostname = parsed.hostname
    if not hostname:
        return _FAIL
    if parsed.username or parsed.password:
        return _FAIL
    # Only allow standard HTTP(S) ports to prevent SSRF to internal services
    if parsed.port is not None and parsed.port not in (80, 443):
        return _FAIL
    try:
        addr_infos = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC,
                                        socket.SOCK_STREAM)
    except (socket.gaierror, OSError):
        return _FAIL
    if not addr_infos:
        return _FAIL
    for _family, _type, _proto, _canonname, sockaddr in addr_infos:
        try:
            ip = ipaddress.ip_address(sockaddr[0])
        except ValueError:
            return _FAIL
        if _is_blocked_ip(ip):
            return _FAIL
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
    # Clean old entries for this IP and check the limit
    timestamps = [t for t in _rate_limit.get(client_ip, []) if now - t < RATE_LIMIT_WINDOW]
    if len(timestamps) >= RATE_LIMIT_MAX:
        _rate_limit[client_ip] = timestamps
        return True
    timestamps.append(now)
    _rate_limit[client_ip] = timestamps
    return False


def _ensure_scheme(url):
    """Prepend https:// if the URL has no scheme."""
    if not url.startswith(('http://', 'https://')):
        return 'https://' + url
    return url


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
        f"style-src 'self' 'nonce-{nonce}' https://fonts.googleapis.com; "
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

# O(1) name lookup dict — eliminates repeated linear scans of status_code_list
_name_cache = {sc.code: sc.name for sc in status_code_list}


def pruned_status_codes():
    return _pruned_cache


def find_image(code):
    return _image_cache.get(code)


def status_name(code):
    """Look up the human name for a status code in O(1)."""
    return _name_cache.get(code, '')


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


# --- FAQ generation helper ---

def build_faq_entries(status_code, description, info, extra, related):
    """Build FAQ entries for structured data on detail pages.

    Generates questions and answers from status descriptions, examples,
    and related codes to produce FAQPage schema entries.
    """
    faq = []
    if info.get('description'):
        faq.append({
            "question": f"What does HTTP {status_code} mean?",
            "answer": info['description'],
        })
    if extra.get('examples'):
        examples_text = " ".join(f"- {ex}" for ex in extra['examples'])
        faq.append({
            "question": f"When should I use HTTP {status_code}?",
            "answer": f"Common scenarios for HTTP {status_code} {description}: {examples_text}",
        })
    for rel_code, diff in related[:3]:
        rel_name = status_name(rel_code) or rel_code
        faq.append({
            "question": f"What is the difference between HTTP {status_code} and {rel_code}?",
            "answer": f"HTTP {status_code} ({description}) vs HTTP {rel_code} ({rel_name}): {diff}",
        })
    return faq


# --- Featured parrot of the day ---

def get_featured_parrot():
    """Return the featured 'parrot of the day' based on today's date."""
    codes = pruned_status_codes()
    day_index = date.today().toordinal() % len(codes)
    return codes[day_index]


# --- Routes ---

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404


@app.route('/')
def http_parrots():
    """Render the homepage gallery of all HTTP status code parrots."""
    codes = pruned_status_codes()
    featured_parrot = get_featured_parrot()
    featured = featured_parrot.code
    # Get a fun fact for the featured parrot
    featured_info = STATUS_INFO.get(featured, {})
    featured_extra = STATUS_EXTRA.get(featured, {})
    featured_description = status_name(featured)
    featured_fun_fact = None
    if featured_extra and featured_extra.get('examples'):
        featured_fun_fact = featured_extra['examples'][0]
    elif featured_info and featured_info.get('description'):
        featured_fun_fact = featured_info['description']
    return render_template('http_parrots.html', status_code_list=codes, featured=featured,
                           status_info=STATUS_INFO, featured_description=featured_description,
                           featured_image=featured_parrot.image,
                           featured_fun_fact=featured_fun_fact)


@app.route('/quiz')
def quiz():
    """Render the quiz page where users guess status codes from parrot images."""
    codes = pruned_status_codes()
    quiz_data = [{"code": c.code, "name": c.name, "image": c.image} for c in codes]
    return render_template('quiz.html', quiz_data=quiz_data)


@app.route('/daily')
def daily():
    """Render the daily HTTP challenge — one scenario question per day."""
    today = date.today()
    day_number = today.toordinal()
    rng = random.Random(day_number)

    # Build candidates: codes that have examples in STATUS_EXTRA
    codes = pruned_status_codes()
    candidates = [c for c in codes if c.code in STATUS_EXTRA
                  and STATUS_EXTRA[c.code].get('examples')]
    if len(candidates) < 4:
        candidates = codes  # fallback

    # Pick the correct answer deterministically
    correct = rng.choice(candidates)
    example_list = STATUS_EXTRA.get(correct.code, {}).get('examples', [])
    scenario = rng.choice(example_list) if example_list else f"A server responds with {correct.code} {correct.name}"

    # Pick 3 wrong answers from the same category (same first digit) if possible
    same_category = [c for c in candidates if c.code != correct.code
                     and c.code[0] == correct.code[0]]
    others = [c for c in candidates if c.code != correct.code
              and c.code[0] != correct.code[0]]
    pool = same_category + others
    rng.shuffle(pool)
    distractors = pool[:3]

    options = [correct] + distractors
    rng.shuffle(options)

    correct_index = options.index(correct)

    info = STATUS_INFO.get(correct.code, {})
    explanation = info.get('meaning', f'{correct.code} {correct.name}')
    image = correct.image

    return render_template('daily.html',
                           scenario=scenario,
                           options=[{"code": o.code, "name": o.name} for o in options],
                           correct_index=correct_index,
                           correct_code=correct.code,
                           correct_name=correct.name,
                           explanation=explanation,
                           image=image,
                           day_number=day_number,
                           date_str=today.isoformat())


@app.route('/practice')
def practice():
    """Render the scenario-based practice page for HTTP status code training."""
    return render_template('practice.html', scenarios=SCENARIOS)


@app.route('/debug')
def debug_page():
    """Render the Debug This Response exercise page."""
    return render_template('debug.html', exercises=DEBUG_EXERCISES)


@app.route('/api-docs')
def api_docs():
    return render_template('api_docs.html')


@app.route('/cheatsheet')
def cheatsheet():
    """Render the printable cheat sheet of all status codes by category."""
    codes = pruned_status_codes()
    categories = [
        (prefix, name, [c for c in codes if c.code.startswith(digit)])
        for digit, (prefix, name) in sorted(_CATEGORY_LABELS.items())
    ]
    return render_template('cheatsheet.html', categories=categories)


@app.route('/flowchart')
def flowchart():
    return render_template('flowchart.html')


def _build_symmetric_summaries(pairs):
    """Build a dict with both orderings (a,b and b,a) from single-direction pairs."""
    result = {}
    for (a, b), text in pairs.items():
        result[f"{a},{b}"] = text
        result[f"{b},{a}"] = text
    return result


COMPARISON_SUMMARIES = _build_symmetric_summaries({
    ("401", "403"): "401 means \"who are you?\" (not authenticated) while 403 means \"I know who you are but you can't do that\" (not authorized).",
    ("301", "302"): "301 is a permanent redirect (update your bookmarks) while 302 is temporary (the original URL is still the right one).",
    ("500", "502"): "500 means the server itself crashed while 502 means the server is fine but an upstream service it depends on sent a bad response.",
    ("200", "204"): "Both mean success, but 200 returns a response body while 204 intentionally returns nothing.",
    ("301", "308"): "Both are permanent redirects, but 301 may change POST to GET while 308 preserves the original HTTP method.",
    ("302", "307"): "Both are temporary redirects, but 302 may change POST to GET while 307 preserves the original HTTP method.",
    ("404", "410"): "404 means the resource was not found (might appear later) while 410 means it existed but was permanently removed.",
    ("502", "504"): "502 means the upstream sent a bad response while 504 means the upstream did not respond at all (timed out).",
    ("400", "422"): "400 means the request is malformed (bad syntax) while 422 means the syntax is fine but the content is semantically invalid.",
    ("503", "500"): "500 is an unexpected server error while 503 means the server is temporarily unavailable (overloaded or in maintenance).",
})


@app.route('/compare')
def compare():
    """Render the side-by-side status code comparison tool."""
    codes = pruned_status_codes()
    code_list = [{"code": c.code, "name": c.name} for c in codes]
    return render_template('compare.html', code_list=code_list,
                           status_info=STATUS_INFO, status_extra=STATUS_EXTRA,
                           comparison_summaries=COMPARISON_SUMMARIES)


_LEARN_CAT_COLORS = {
    '1': '#48cae4', '2': '#2dd4a8', '3': '#f9c74f',
    '4': '#ff6b6b', '5': '#a78bfa',
}
_LEARN_CAT_BGS = {
    '1': 'rgba(72,202,228,0.10)', '2': 'rgba(45,212,168,0.10)',
    '3': 'rgba(249,199,79,0.10)', '4': 'rgba(255,107,107,0.10)',
    '5': 'rgba(167,139,250,0.10)',
}


@app.route('/learn')
def learn_index():
    """List all confusion pair lessons."""
    return render_template('learn_index.html', pairs=CONFUSION_PAIRS)


@app.route('/learn/<slug>')
def learn_pair(slug):
    """Render a confusion pair lesson page."""
    pair = CONFUSION_PAIRS_BY_SLUG.get(slug)
    if not pair:
        abort(404)
    code_names = {c: status_name(c) for c in pair['codes']}
    code_images = {c: find_image(c) for c in pair['codes']}
    code_info = {c: STATUS_INFO.get(c, {}) for c in pair['codes']}
    return render_template('learn_pair.html', pair=pair,
                           code_names=code_names, code_images=code_images,
                           code_info=code_info, cat_colors=_LEARN_CAT_COLORS,
                           cat_bgs=_LEARN_CAT_BGS)


@app.route('/paths')
def paths_index():
    """List all guided learning paths with progress summaries."""
    return render_template('paths_index.html', paths=LEARNING_PATHS)


@app.route('/paths/<path_id>')
def path_detail(path_id):
    """Show a single learning path with step checklist and progress."""
    path = LEARNING_PATHS_BY_ID.get(path_id)
    if not path:
        abort(404)
    return render_template('path_detail.html', path=path)


@app.route('/tester')
def tester():
    return render_template('tester.html')


@app.route('/collection')
def collection():
    """Parrotdex — track which status code parrots you've collected."""
    return render_template('collection.html', all_codes=pruned_status_codes())


@app.route('/headers')
def header_explainer():
    """Render the Header Explainer page for annotating HTTP headers."""
    return render_template('headers.html')


@app.route('/profile')
def profile():
    """Render the XP profile page — all state stored client-side in localStorage."""
    return render_template('profile.html')


@app.route('/cors-checker')
def cors_checker():
    """Render the CORS Checker page for testing cross-origin policies."""
    return render_template('cors_checker.html')


@app.route('/api/check-cors')
def check_cors():
    """Check CORS headers for a given URL and origin."""
    if is_rate_limited(request.remote_addr):
        return jsonify({"error": "Rate limit exceeded. Try again later."}), 429
    url = request.args.get('url', '')
    origin = request.args.get('origin', '')
    if not url or not origin:
        return jsonify({"error": "Both url and origin are required"}), 400
    url = _ensure_scheme(url)
    safe_url, hostname = resolve_and_validate(url)
    if not safe_url:
        return jsonify({"error": "URL not allowed"}), 403
    results = {}
    try:
        # Preflight (OPTIONS)
        preflight = req.options(safe_url, headers={
            'Origin': origin,
            'Access-Control-Request-Method': 'GET',
        }, allow_redirects=False, timeout=10)
        results['preflight'] = {
            'status': preflight.status_code,
            'headers': {k: v for k, v in preflight.headers.items()
                       if k.lower().startswith('access-control')},
        }
    except req.RequestException:
        results['preflight'] = {'error': 'Could not connect'}
    try:
        # Actual request
        actual = req.get(safe_url, headers={'Origin': origin},
                        allow_redirects=False, timeout=10, stream=True)
        actual.close()
        results['actual'] = {
            'status': actual.status_code,
            'headers': {k: v for k, v in actual.headers.items()
                       if k.lower().startswith('access-control')},
        }
    except req.RequestException:
        results['actual'] = {'error': 'Could not connect'}
    # Analysis — extract CORS headers from whichever response returned them
    def _cors_header(section, name):
        return results.get(section, {}).get('headers', {}).get(name, '')

    acao = _cors_header('actual', 'Access-Control-Allow-Origin') or _cors_header('preflight', 'Access-Control-Allow-Origin')
    actual_creds = _cors_header('actual', 'Access-Control-Allow-Credentials')
    results['analysis'] = {
        'cors_enabled': bool(acao),
        'allows_origin': acao in ('*', origin),
        'allows_credentials': isinstance(actual_creds, str) and actual_creds.lower() == 'true',
    }
    return jsonify(results)


@app.route('/security-audit')
def security_audit():
    """Render the Response Header Security Audit page."""
    return render_template('security_audit.html')


# Security header scoring rubric
_SECURITY_CHECKS = [
    {
        'id': 'hsts',
        'header': 'Strict-Transport-Security',
        'points': 10,
        'label': 'Strict-Transport-Security',
        'desc': 'Ensures browsers only connect via HTTPS, preventing protocol downgrade attacks.',
        'fix': 'Strict-Transport-Security: max-age=31536000; includeSubDomains',
    },
    {
        'id': 'csp',
        'header': 'Content-Security-Policy',
        'points': 15,
        'label': 'Content-Security-Policy',
        'desc': 'Controls which resources the browser can load, mitigating XSS and injection attacks.',
        'fix': "Content-Security-Policy: default-src 'self'; script-src 'self'",
    },
    {
        'id': 'xcto',
        'header': 'X-Content-Type-Options',
        'points': 5,
        'label': 'X-Content-Type-Options: nosniff',
        'desc': 'Prevents browsers from MIME-sniffing the response, enforcing the declared content type.',
        'fix': 'X-Content-Type-Options: nosniff',
    },
    {
        'id': 'xfo',
        'header': 'X-Frame-Options',
        'points': 5,
        'label': 'X-Frame-Options',
        'desc': 'Prevents the page from being embedded in iframes, defending against clickjacking.',
        'fix': 'X-Frame-Options: DENY',
    },
    {
        'id': 'referrer',
        'header': 'Referrer-Policy',
        'points': 5,
        'label': 'Referrer-Policy',
        'desc': 'Controls how much referrer information is sent with outgoing requests.',
        'fix': 'Referrer-Policy: strict-origin-when-cross-origin',
    },
    {
        'id': 'permissions',
        'header': 'Permissions-Policy',
        'points': 5,
        'label': 'Permissions-Policy',
        'desc': 'Restricts which browser features (camera, mic, geolocation) the page can access.',
        'fix': 'Permissions-Policy: camera=(), microphone=(), geolocation=()',
    },
    {
        'id': 'server',
        'header': 'Server',
        'points': 5,
        'label': 'No Server header leaking info',
        'desc': 'The Server header can reveal software and version, aiding attackers in targeting known vulnerabilities.',
        'fix': 'Remove or genericize the Server header in your web server config.',
    },
    {
        'id': 'powered',
        'header': 'X-Powered-By',
        'points': 5,
        'label': 'No X-Powered-By leaking info',
        'desc': 'X-Powered-By reveals backend technology (e.g., Express, PHP), making targeted attacks easier.',
        'fix': 'Remove the X-Powered-By header (e.g., app.disable("x-powered-by") in Express).',
    },
    {
        'id': 'cookie',
        'header': 'Set-Cookie',
        'points': 10,
        'label': 'Set-Cookie security attributes',
        'desc': 'Cookies should use Secure (HTTPS only), HttpOnly (no JS access), and SameSite to prevent CSRF.',
        'fix': 'Set-Cookie: session=abc; Secure; HttpOnly; SameSite=Lax',
    },
    {
        'id': 'cors_wildcard',
        'header': 'Access-Control-Allow-Origin',
        'points': 5,
        'label': 'CORS not wildcard *',
        'desc': 'Using * for Access-Control-Allow-Origin allows any origin to read responses, which may leak data.',
        'fix': 'Access-Control-Allow-Origin: https://your-trusted-domain.com',
    },
]


def _run_security_checks(headers):
    """Run all security header checks against the provided headers dict.

    Returns (score, max_score, checks_list).
    """
    checks = []
    score = 0
    max_score = 0
    lower_headers = {k.lower(): v for k, v in headers.items()}

    for check in _SECURITY_CHECKS:
        hdr = check['header'].lower()
        val = lower_headers.get(hdr, '')
        result = {'id': check['id'], 'header': check['label'],
                  'points': check['points'], 'desc': check['desc'],
                  'fix': check['fix']}
        max_score += check['points']

        if check['id'] == 'xcto':
            passed = val.lower() == 'nosniff' if val else False
        elif check['id'] == 'server':
            passed = not val or val.strip().lower() in ('', 'server')
        elif check['id'] == 'powered':
            passed = not val
        elif check['id'] == 'cookie':
            set_cookies = [v for k, v in headers.items() if k.lower() == 'set-cookie']
            if not set_cookies:
                passed = True
            else:
                all_good = True
                for cookie in set_cookies:
                    cl = cookie.lower()
                    if 'secure' not in cl or 'httponly' not in cl or 'samesite' not in cl:
                        all_good = False
                        break
                passed = all_good
        elif check['id'] == 'cors_wildcard':
            passed = val != '*'
        else:
            passed = bool(val)

        if passed:
            score += check['points']
            result['status'] = 'pass'
        else:
            result['status'] = 'fail'

        checks.append(result)

    return score, max_score, checks


def _score_to_grade(score, max_score):
    """Convert a numeric score to a letter grade."""
    if max_score == 0:
        return 'F'
    pct = score / max_score * 100
    if pct >= 95:
        return 'A+'
    elif pct >= 85:
        return 'A'
    elif pct >= 70:
        return 'B'
    elif pct >= 50:
        return 'C'
    elif pct >= 30:
        return 'D'
    return 'F'


@app.route('/api/security-audit')
def api_security_audit():
    """Audit response headers of a URL against security best practices."""
    if is_rate_limited(request.remote_addr):
        return jsonify({"error": "Rate limit exceeded. Try again later."}), 429
    url = request.args.get('url', '').strip()
    if not url:
        return jsonify({"error": "Missing required parameter: url"}), 400
    url = _ensure_scheme(url)
    safe_url, hostname = resolve_and_validate(url)
    if not safe_url:
        return jsonify({"error": "URL not allowed"}), 403
    try:
        resp = req.get(safe_url, allow_redirects=False, timeout=10, stream=True)
        raw_headers = dict(resp.headers)
        resp.close()
    except req.RequestException:
        return jsonify({"error": "Could not connect to the URL"}), 502
    score, max_score, checks = _run_security_checks(raw_headers)
    grade = _score_to_grade(score, max_score)
    return jsonify({
        "url": safe_url,
        "grade": grade,
        "score": score,
        "max_score": max_score,
        "checks": checks,
    })


@app.route('/api/search')
def api_search():
    """Search status codes by code number, name, description, or keywords.

    Returns a JSON array of matching status codes with relevance scores.
    Query parameter: q (required).
    """
    query = request.args.get('q', '').strip().lower()
    if not query:
        return jsonify({"error": "Missing required query parameter: q"}), 400
    if len(query) > 200:
        return jsonify({"error": "Query too long (max 200 characters)"}), 400

    results = []
    for sc in status_code_list:
        score = 0
        code = sc.code
        name = sc.name.lower()
        info = STATUS_INFO.get(code, {})
        description = info.get('description', '').lower()

        # Exact code match (highest relevance)
        if query == code:
            score = 100
        # Code starts with query (e.g. "40" matches 400, 401, etc.)
        elif code.startswith(query) and query.isdigit():
            score = 80
        # Code contains query digits
        elif query.isdigit() and query in code:
            score = 60

        # Name matching
        if query in name:
            name_bonus = 70 if query == name else 50
            score = max(score, name_bonus)

        # Description matching
        if query in description:
            score = max(score, 30)

        # Keyword matching in name words
        query_words = query.split()
        if len(query_words) > 1:
            matched_words = sum(1 for w in query_words if w in name or w in description)
            if matched_words > 0:
                word_score = int(20 + (matched_words / len(query_words)) * 40)
                score = max(score, word_score)

        if score > 0:
            results.append({
                "code": code,
                "name": sc.name,
                "description": info.get('description', ''),
                "score": score,
            })

    results.sort(key=lambda r: (-r['score'], r['code']))
    return jsonify(results)


@app.route('/api/check-url')
def check_url():
    """Make a HEAD request to a user-provided URL and return its status code."""
    if is_rate_limited(request.remote_addr):
        logger.warning('Rate limit exceeded for %s', request.remote_addr)
        return jsonify({"error": "Rate limit exceeded. Try again later."}), 429
    url = request.args.get('url', '')
    if not url:
        return jsonify({"error": "No URL provided"}), 400
    url = _ensure_scheme(url)
    safe_url, hostname = resolve_and_validate(url)
    if not safe_url:
        logger.warning('SSRF blocked: %s from %s', url, request.remote_addr)
        return jsonify({"error": "URL not allowed"}), 403
    try:
        resp = req.head(safe_url, allow_redirects=False, timeout=10)
        headers = {k: v for k, v in resp.headers.items()
                   if k.lower() not in ('set-cookie',)}
        return jsonify({
            "code": resp.status_code,
            "url": url,
            "headers": headers,
            "time_ms": round(resp.elapsed.total_seconds() * 1000),
        })
    except req.RequestException:
        return jsonify({"error": "Could not connect to the provided URL"}), 502


@app.route('/trace')
def trace_page():
    """Render the Redirect Tracer page for visualizing redirect chains."""
    return render_template('trace.html')


@app.route('/api/trace-redirects')
def trace_redirects():
    """Follow redirects manually and return a JSON array of hops.

    Each hop contains: url, status_code, location, time_ms, and key
    response headers (Strict-Transport-Security, Set-Cookie presence,
    Cache-Control).  SSRF protection is applied at every hop.
    Max 10 hops to prevent infinite loops.
    """
    if is_rate_limited(request.remote_addr):
        return jsonify({"error": "Rate limit exceeded. Try again later."}), 429
    url = request.args.get('url', '')
    if not url:
        return jsonify({"error": "No URL provided"}), 400
    url = _ensure_scheme(url)

    hops = []
    current_url = url
    max_hops = 10

    for _ in range(max_hops):
        safe_url, hostname = resolve_and_validate(current_url)
        if not safe_url:
            hops.append({"url": current_url, "error": "URL not allowed (SSRF protection)"})
            break
        try:
            resp = req.head(safe_url, allow_redirects=False, timeout=10)
        except req.Timeout:
            hops.append({"url": current_url, "error": "Request timed out"})
            break
        except req.ConnectionError:
            hops.append({"url": current_url, "error": "Could not connect"})
            break
        except req.RequestException:
            hops.append({"url": current_url, "error": "Request failed"})
            break

        hop = {
            "url": current_url,
            "status_code": resp.status_code,
            "time_ms": round(resp.elapsed.total_seconds() * 1000),
            "headers": {},
        }
        # Collect key security/caching headers
        for hdr in ('Strict-Transport-Security', 'Cache-Control',
                     'Content-Type', 'Server'):
            if hdr in resp.headers:
                hop["headers"][hdr] = resp.headers[hdr]
        if 'Set-Cookie' in resp.headers:
            hop["headers"]["Set-Cookie"] = "(present)"

        location = resp.headers.get('Location')
        if location:
            hop["location"] = location

        hops.append(hop)

        # If not a redirect status, we've reached the final destination
        if resp.status_code not in (301, 302, 303, 307, 308):
            break

        if not location:
            break
        current_url = location
    else:
        # Loop completed without break — max hops exceeded
        hops.append({"url": current_url, "error": "Too many redirects (max 10)"})

    return jsonify(hops)


@app.route('/playground')
def playground():
    """Render the Interactive Response Playground page."""
    codes = [{"code": c.code, "name": c.name} for c in status_code_list]
    return render_template('playground.html', all_codes=codes)


@app.route('/curl-import')
def curl_import():
    """Render the cURL Import/Parse Tool page."""
    return render_template('curl_import.html')


# Security-sensitive headers that mock-response users must not override
_BLOCKED_MOCK_HEADERS = frozenset({
    'set-cookie', 'content-security-policy', 'x-frame-options',
    'x-content-type-options', 'strict-transport-security',
    'referrer-policy', 'permissions-policy', 'server',
    'transfer-encoding',
})


def _is_safe_header_value(s):
    """Return True if the string contains no newline/carriage-return characters."""
    return '\n' not in s and '\r' not in s


@app.route('/api/mock-response', methods=['POST'])
def mock_response():
    """Return an HTTP response with user-specified status, headers, and body.

    Accepts JSON: {status_code: int, headers: dict, body: string}.
    Rate-limited to prevent abuse.
    """
    if is_rate_limited(request.remote_addr):
        return jsonify({"error": "Rate limit exceeded. Try again later."}), 429
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid JSON body"}), 400
    status = data.get('status_code', 200)
    if not isinstance(status, int) or status < 100 or status > 599:
        return jsonify({"error": "status_code must be an integer between 100 and 599"}), 400
    headers = data.get('headers', {})
    if not isinstance(headers, dict):
        return jsonify({"error": "headers must be a dict"}), 400
    body = data.get('body', '')
    if not isinstance(body, str):
        return jsonify({"error": "body must be a string"}), 400
    if len(body) > 10000:
        return jsonify({"error": "body must be 10000 characters or fewer"}), 400
    if len(headers) > 50:
        return jsonify({"error": "Too many headers (max 50)"}), 400
    resp = app.response_class(body, status=status)
    for key, value in headers.items():
        key_clean = str(key).strip()
        value_clean = str(value).strip()
        if (key_clean
                and _is_safe_header_value(key_clean)
                and _is_safe_header_value(value_clean)
                and key_clean.lower() not in _BLOCKED_MOCK_HEADERS):
            resp.headers[key_clean] = value_clean
    return resp


@app.route('/return/<int:code>')
def return_status(code):
    """Return a JSON response with the given HTTP status code.

    Intentionally returns the actual status code (including 1xx informational
    codes) so developers can use this endpoint for testing HTTP clients.
    """
    if code < 100 or code > 599:
        abort(404)
    delay = request.args.get('delay', type=float)
    if delay and 0 < delay <= 10:
        if is_rate_limited(request.remote_addr):
            return jsonify({"error": "Rate limit exceeded. Try again later."}), 429
        time.sleep(delay)
    description = status_name(str(code)) or 'Unknown'
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
    description = status_name(status_code)
    if not description:
        abort(404)
    # Only return the actual status code for 2xx/4xx/5xx.
    # 1xx and 3xx codes have special HTTP semantics that break the response.
    if code < 200 or 300 <= code < 400:
        code = 200
    image = find_image(status_code)
    best = request.accept_mimetypes.best_match(['text/html', 'image/*', 'application/json'])
    if image and best == 'image/*':
        return send_from_directory('static', image), code
    info = STATUS_INFO.get(status_code, {})
    extra = STATUS_EXTRA.get(status_code, {})
    if best == 'application/json':
        return jsonify({
            "code": status_code,
            "description": description,
            "image": f"/{image}" if image else None,
            "meaning": info.get("description", ""),
            "history": info.get("history", ""),
        }), code
    http_example = HTTP_EXAMPLES.get(status_code, {})
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
    faq_entries = build_faq_entries(status_code, description, info, extra, related)
    eli5 = extra.get('eli5', '')
    # Build lesson links for related codes
    learn_links = {}
    for rel_code, _diff in related:
        pair_key = tuple(sorted([status_code, rel_code]))
        slug = f"{pair_key[0]}-vs-{pair_key[1]}"
        if slug in CONFUSION_PAIRS_BY_SLUG:
            learn_links[rel_code] = slug
    return render_template('http_parrot.html', status_code=status_code,
                           description=description, image=image, info=info,
                           extra=extra, http_example=http_example,
                           prev_code=prev_code, next_code=next_code,
                           related=related, curl_cmd=curl_cmd,
                           faq_entries=faq_entries, eli5=eli5,
                           learn_links=learn_links), code


@app.route('/<status_code>.jpg')
def http_parrot_image(status_code):
    image = find_image(status_code)
    if not image:
        abort(404)
    return send_from_directory('static', image)


_ECHO_STRIP_HEADERS = {'authorization', 'cookie', 'proxy-authorization',
                       'set-cookie', 'x-api-key'}


@app.route('/echo', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'HEAD', 'OPTIONS'])
def echo():
    """Echo the request details back as JSON (httpbin-style).

    Supports all HTTP methods. For POST/PUT/PATCH the request body and
    parsed JSON are included.  Query parameters are always echoed in
    ``args``.

    Special query params:
      ?format=pretty  -- return indented JSON
      ?format=curl    -- return a curl command that reproduces the request
    """
    safe_headers = {k: v for k, v in request.headers
                    if k.lower() not in _ECHO_STRIP_HEADERS}
    args = {k: v for k, v in request.args.items() if k != 'format'}

    fmt = request.args.get('format', '').lower()

    if fmt == 'curl':
        # Build a curl command that reproduces this request
        parts = ['curl']
        if request.method != 'GET':
            parts.append(f'-X {request.method}')
        # Rebuild URL without the format param
        base_url = request.base_url
        if args:
            qs = '&'.join(f'{k}={v}' for k, v in args.items())
            base_url = f'{base_url}?{qs}'
        parts.append(f"'{base_url}'")
        for k, v in safe_headers.items():
            parts.append(f"-H '{k}: {v}'")
        if request.method in ('POST', 'PUT', 'PATCH'):
            body = request.get_data(as_text=True)
            if body:
                escaped = body.replace("'", "'\\''")
                parts.append(f"-d '{escaped}'")
        return jsonify({'curl': ' \\\n  '.join(parts)})

    data = {
        'method': request.method,
        'url': request.url,
        'headers': safe_headers,
        'args': args,
    }
    if request.method in ('POST', 'PUT', 'PATCH'):
        data['body'] = request.get_data(as_text=True)
        if request.is_json:
            data['json'] = request.get_json(silent=True)

    if fmt == 'pretty':
        resp = app.response_class(
            json.dumps(data, indent=2, sort_keys=True) + '\n',
            mimetype='application/json',
        )
        return resp

    return jsonify(data)


_CATEGORY_LABELS = {
    '1': ('1xx', 'Informational'),
    '2': ('2xx', 'Success'),
    '3': ('3xx', 'Redirection'),
    '4': ('4xx', 'Client Error'),
    '5': ('5xx', 'Server Error'),
}


def _code_category(code_str):
    """Return the category label for a status code string, e.g. '404' -> '4xx Client Error'."""
    first = code_str[0] if code_str else '?'
    prefix, name = _CATEGORY_LABELS.get(first, (None, None))
    return f'{prefix} {name}' if prefix else 'Unknown'


@app.route('/api/diff')
def api_diff():
    """Compare two HTTP status codes and return their differences as JSON.

    Query params:
      code1 -- first status code  (required)
      code2 -- second status code (required)

    Returns descriptions, categories, real-world examples, related codes,
    and a human-readable key_difference summary.
    """
    code1 = request.args.get('code1', '').strip()
    code2 = request.args.get('code2', '').strip()
    if not code1 or not code2:
        return jsonify({'error': 'Both code1 and code2 query params are required.'}), 400

    name1 = status_name(code1)
    name2 = status_name(code2)
    if not name1 or not name2:
        missing = [c for c, n in [(code1, name1), (code2, name2)] if not n]
        return jsonify({'error': f"Unknown status code(s): {', '.join(missing)}"}), 404

    related1 = RELATED_CODES.get(code1, [])
    related2 = RELATED_CODES.get(code2, [])

    # Try to find a direct key_difference from RELATED_CODES
    key_diff = (
        next((exp for rc, exp in related1 if rc == code2), None)
        or next((exp for rc, exp in related2 if rc == code1), None)
        or (f"{code1} ({name1}) is a {_code_category(code1).split(' ', 1)[1].lower()} response; "
            f"{code2} ({name2}) is a {_code_category(code2).split(' ', 1)[1].lower()} response.")
    )

    def _code_detail(code, name, related):
        info = STATUS_INFO.get(code, {})
        extra = STATUS_EXTRA.get(code, {})
        return {
            'code': code,
            'name': name,
            'category': _code_category(code),
            'description': info.get('description', ''),
            'examples': extra.get('examples', []),
            'related_codes': [{'code': c, 'why': w} for c, w in related],
        }

    return jsonify({
        'code1': _code_detail(code1, name1, related1),
        'code2': _code_detail(code2, name2, related2),
        'key_difference': key_diff,
    })


@app.route('/redirect/<int:n>')
def redirect_chain(n):
    """Chain of n redirects ending at 200. Max 10 hops."""
    if n < 0:
        abort(404)
    if n == 0:
        return jsonify({"message": "End of redirect chain", "code": 200})
    if n > 10:
        abort(404)
    return redirect(url_for('redirect_chain', n=n - 1), code=302)


@app.route('/feed.xml')
def rss_feed():
    """Generate an RSS 2.0 feed with the daily parrot as the latest item."""
    base = request.url_root.rstrip('/')
    featured = get_featured_parrot()
    info = STATUS_INFO.get(featured.code, {})
    description = info.get('description', f'HTTP {featured.code} {featured.name}')
    pub_date = datetime.now(timezone.utc).strftime('%a, %d %b %Y %H:%M:%S +0000')

    items_xml = []
    # Daily parrot as the latest item
    items_xml.append(
        f'    <item>\n'
        f'      <title>Parrot of the Day: HTTP {xml_escape(featured.code)} {xml_escape(featured.name)}</title>\n'
        f'      <link>{xml_escape(base)}/{xml_escape(featured.code)}</link>\n'
        f'      <description>{xml_escape(description)}</description>\n'
        f'      <enclosure url="{xml_escape(base)}/static/{xml_escape(featured.image)}" type="image/jpeg" />\n'
        f'      <pubDate>{pub_date}</pubDate>\n'
        f'      <guid>{xml_escape(base)}/{xml_escape(featured.code)}#{date.today().isoformat()}</guid>\n'
        f'    </item>'
    )

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0">\n'
        '  <channel>\n'
        f'    <title>HTTP Parrots</title>\n'
        f'    <link>{xml_escape(base)}/</link>\n'
        f'    <description>Every HTTP status code, explained by parrots. A fun visual reference for developers.</description>\n'
        f'    <language>en-us</language>\n'
        f'    <lastBuildDate>{pub_date}</lastBuildDate>\n'
        + '\n'.join(items_xml) + '\n'
        '  </channel>\n'
        '</rss>'
    )
    resp = app.response_class(xml, mimetype='application/rss+xml')
    resp.headers['Cache-Control'] = 'public, max-age=3600'
    return resp


@app.route('/sitemap.xml')
def sitemap():
    """Generate a dynamic XML sitemap."""
    base = request.url_root.rstrip('/')
    pages = []
    for rule in ['/', '/quiz', '/daily', '/practice', '/debug',
                 '/flowchart', '/compare', '/learn', '/paths', '/tester',
                 '/cheatsheet', '/headers', '/cors-checker', '/security-audit',
                 '/trace', '/collection', '/playground', '/curl-import', '/api-docs',
                 '/profile']:
        pages.append({'loc': base + rule, 'priority': '1.0' if rule == '/' else '0.7'})
    for sc in pruned_status_codes():
        pages.append({'loc': base + '/' + sc.code, 'priority': '0.8'})
    for pair in CONFUSION_PAIRS:
        pages.append({'loc': base + '/learn/' + pair['slug'], 'priority': '0.6'})
    for lp in LEARNING_PATHS:
        pages.append({'loc': base + '/paths/' + lp['id'], 'priority': '0.6'})
    xml = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for p in pages:
        xml.append(f'  <url><loc>{p["loc"]}</loc><priority>{p["priority"]}</priority></url>')
    xml.append('</urlset>')
    resp = app.response_class('\n'.join(xml), mimetype='application/xml')
    resp.headers['Cache-Control'] = 'public, max-age=86400'
    return resp


@app.route('/coffee')
def coffee():
    """Hidden easter egg: a teapot that can't brew coffee. Returns 418."""
    # Fake "failed brew attempts" counter seeded from Unix timestamp
    brew_attempts = int(time.time()) % 9000 + 1000
    return render_template('coffee.html', brew_attempts=brew_attempts), 418


@app.route('/robots.txt')
def robots():
    """Serve robots.txt."""
    content = (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /api/check-url\n"
        "Disallow: /api/check-cors\n"
        "Disallow: /api/security-audit\n"
        "Disallow: /api/trace-redirects\n"
        "Disallow: /api/mock-response\n"
        "Disallow: /api/diff\n"
        "Disallow: /api/search\n"
        "Disallow: /return/\n"
        "Disallow: /echo\n"
        "Disallow: /redirect/\n"
        f"\nSitemap: {request.url_root}sitemap.xml\n"
    )
    return app.response_class(content, mimetype='text/plain')


if __name__ == '__main__':
    app.run()
