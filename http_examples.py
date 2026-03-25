"""Example HTTP request/response pairs for status codes."""

HTTP_EXAMPLES = {
    "100": {
        "request": "POST /api/upload HTTP/1.1\nHost: api.example.com\nContent-Type: video/mp4\nContent-Length: 104857600\nExpect: 100-continue",
        "response": "HTTP/1.1 100 Continue",
    },
    "101": {
        "request": "GET /chat HTTP/1.1\nHost: ws.example.com\nUpgrade: websocket\nConnection: Upgrade\nSec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\nSec-WebSocket-Version: 13",
        "response": "HTTP/1.1 101 Switching Protocols\nUpgrade: websocket\nConnection: Upgrade\nSec-WebSocket-Accept: s3pPLMBiTxaQ9kYGzzhZRbK+xOo=",
    },
    "102": {
        "request": "PROPFIND /documents/ HTTP/1.1\nHost: dav.example.com\nDepth: infinity\nContent-Type: application/xml\n\n<?xml version=\"1.0\"?><D:propfind xmlns:D=\"DAV:\"><D:allprop/></D:propfind>",
        "response": "HTTP/1.1 102 Processing",
    },
    "103": {
        "request": "GET /page HTTP/1.1\nHost: www.example.com\nAccept: text/html",
        "response": "HTTP/1.1 103 Early Hints\nLink: </style.css>; rel=preload; as=style\nLink: </main.js>; rel=preload; as=script",
    },
    "200": {
        "request": "GET /api/users/42 HTTP/1.1\nHost: api.example.com\nAccept: application/json\nAuthorization: Bearer eyJhbG...",
        "response": "HTTP/1.1 200 OK\nContent-Type: application/json\nContent-Length: 82\nCache-Control: max-age=60\n\n{\"id\": 42, \"name\": \"Alice\", \"email\": \"alice@example.com\"}",
    },
    "201": {
        "request": "POST /api/users HTTP/1.1\nHost: api.example.com\nContent-Type: application/json\nAuthorization: Bearer eyJhbG...\n\n{\"name\": \"Bob\", \"email\": \"bob@example.com\"}",
        "response": "HTTP/1.1 201 Created\nContent-Type: application/json\nLocation: /api/users/43\n\n{\"id\": 43, \"name\": \"Bob\", \"email\": \"bob@example.com\"}",
    },
    "202": {
        "request": "POST /api/reports/generate HTTP/1.1\nHost: api.example.com\nContent-Type: application/json\nAuthorization: Bearer eyJhbG...\n\n{\"type\": \"annual\", \"year\": 2025}",
        "response": "HTTP/1.1 202 Accepted\nContent-Type: application/json\nLocation: /api/reports/jobs/7891\n\n{\"job_id\": 7891, \"status\": \"queued\", \"estimated_time\": \"30s\"}",
    },
    "203": {
        "request": "GET /api/weather?city=London HTTP/1.1\nHost: proxy.example.com\nAccept: application/json",
        "response": "HTTP/1.1 203 Non-Authoritative Information\nContent-Type: application/json\nVia: 1.1 proxy.example.com\nWarning: 214 proxy.example.com \"Transformation applied\"\n\n{\"city\": \"London\", \"temp_c\": 14, \"source\": \"cache\"}",
    },
    "204": {
        "request": "DELETE /api/users/42 HTTP/1.1\nHost: api.example.com\nAuthorization: Bearer eyJhbG...",
        "response": "HTTP/1.1 204 No Content",
    },
    "205": {
        "request": "POST /api/cart/clear HTTP/1.1\nHost: shop.example.com\nAuthorization: Bearer eyJhbG...",
        "response": "HTTP/1.1 205 Reset Content\nContent-Length: 0",
    },
    "206": {
        "request": "GET /videos/intro.mp4 HTTP/1.1\nHost: cdn.example.com\nRange: bytes=0-1048575",
        "response": "HTTP/1.1 206 Partial Content\nContent-Type: video/mp4\nContent-Range: bytes 0-1048575/52428800\nContent-Length: 1048576\nAccept-Ranges: bytes\n\n[binary data]",
    },
    "207": {
        "request": "PROPFIND /files/ HTTP/1.1\nHost: dav.example.com\nDepth: 1\nContent-Type: application/xml\nAuthorization: Basic YWxpY2U6cGFzcw==\n\n<?xml version=\"1.0\"?><D:propfind xmlns:D=\"DAV:\"><D:prop><D:displayname/></D:prop></D:propfind>",
        "response": "HTTP/1.1 207 Multi-Status\nContent-Type: application/xml\n\n<?xml version=\"1.0\"?><D:multistatus xmlns:D=\"DAV:\"><D:response><D:href>/files/report.pdf</D:href><D:propstat><D:status>HTTP/1.1 200 OK</D:status></D:propstat></D:response></D:multistatus>",
    },
    "208": {
        "request": "PROPFIND /shared/ HTTP/1.1\nHost: dav.example.com\nDepth: infinity\nContent-Type: application/xml\nAuthorization: Basic YWxpY2U6cGFzcw==",
        "response": "HTTP/1.1 208 Already Reported\nContent-Type: application/xml\n\n<?xml version=\"1.0\"?><D:multistatus xmlns:D=\"DAV:\"><D:response><D:href>/shared/docs</D:href><D:status>HTTP/1.1 208 Already Reported</D:status></D:response></D:multistatus>",
    },
    "226": {
        "request": "GET /feed.xml HTTP/1.1\nHost: www.example.com\nA-IM: feed\nIf-None-Match: \"v5\"",
        "response": "HTTP/1.1 226 IM Used\nContent-Type: application/xml\nETag: \"v6\"\nIM: feed\nCache-Control: no-cache\n\n<feed><entry><title>New post</title></entry></feed>",
    },
    "300": {
        "request": "GET /document/45 HTTP/1.1\nHost: www.example.com\nAccept: application/json, text/html",
        "response": "HTTP/1.1 300 Multiple Choices\nContent-Type: application/json\nLocation: /document/45.json\n\n{\"choices\": [\"/document/45.json\", \"/document/45.html\", \"/document/45.pdf\"]}",
    },
    "301": {
        "request": "GET /old-page HTTP/1.1\nHost: www.example.com",
        "response": "HTTP/1.1 301 Moved Permanently\nLocation: https://www.example.com/new-page\nContent-Length: 0",
    },
    "302": {
        "request": "POST /login HTTP/1.1\nHost: www.example.com\nContent-Type: application/x-www-form-urlencoded\n\nusername=alice&password=secret",
        "response": "HTTP/1.1 302 Found\nLocation: /dashboard\nSet-Cookie: session=abc123; HttpOnly; Secure",
    },
    "303": {
        "request": "POST /api/orders HTTP/1.1\nHost: shop.example.com\nContent-Type: application/json\nAuthorization: Bearer eyJhbG...\n\n{\"items\": [{\"sku\": \"A100\", \"qty\": 2}]}",
        "response": "HTTP/1.1 303 See Other\nLocation: /api/orders/1024\nContent-Length: 0",
    },
    "304": {
        "request": "GET /style.css HTTP/1.1\nHost: www.example.com\nIf-None-Match: \"v2.5.1\"\nIf-Modified-Since: Mon, 24 Mar 2026 00:00:00 GMT",
        "response": "HTTP/1.1 304 Not Modified\nETag: \"v2.5.1\"\nCache-Control: max-age=3600",
    },
    "305": {
        "request": "GET /api/geo/lookup HTTP/1.1\nHost: api.example.com\nAccept: application/json",
        "response": "HTTP/1.1 305 Use Proxy\nLocation: http://proxy.example.com:8080/\nContent-Type: application/json\n\n{\"message\": \"Please use the specified proxy to access this resource\"}",
    },
    "306": {
        "request": "GET /legacy/resource HTTP/1.1\nHost: www.example.com",
        "response": "HTTP/1.1 306 Switch Proxy\nContent-Type: text/plain\n\nSubsequent requests should use the specified proxy.",
    },
    "307": {
        "request": "POST /api/v1/submit HTTP/1.1\nHost: api.example.com\nContent-Type: application/json\n\n{\"data\": \"test\"}",
        "response": "HTTP/1.1 307 Temporary Redirect\nLocation: https://api.example.com/api/v2/submit\nContent-Length: 0",
    },
    "308": {
        "request": "POST /api/upload HTTP/1.1\nHost: old.example.com\nContent-Type: multipart/form-data; boundary=----FormBoundary\n\n------FormBoundary\nContent-Disposition: form-data; name=\"file\"; filename=\"data.csv\"\n\n[file content]",
        "response": "HTTP/1.1 308 Permanent Redirect\nLocation: https://new.example.com/api/upload\nContent-Length: 0",
    },
    "400": {
        "request": "POST /api/users HTTP/1.1\nHost: api.example.com\nContent-Type: application/json\n\n{invalid json",
        "response": "HTTP/1.1 400 Bad Request\nContent-Type: application/json\n\n{\"error\": \"Malformed JSON in request body\"}",
    },
    "401": {
        "request": "GET /api/profile HTTP/1.1\nHost: api.example.com",
        "response": "HTTP/1.1 401 Unauthorized\nWWW-Authenticate: Bearer realm=\"api\"\nContent-Type: application/json\n\n{\"error\": \"Authentication required\"}",
    },
    "402": {
        "request": "POST /api/billing/charge HTTP/1.1\nHost: api.example.com\nContent-Type: application/json\nAuthorization: Bearer eyJhbG...\n\n{\"amount\": 49.99, \"currency\": \"USD\"}",
        "response": "HTTP/1.1 402 Payment Required\nContent-Type: application/json\n\n{\"error\": \"Payment required\", \"detail\": \"Your subscription has expired\", \"upgrade_url\": \"/billing/plans\"}",
    },
    "403": {
        "request": "DELETE /api/admin/users/1 HTTP/1.1\nHost: api.example.com\nAuthorization: Bearer eyJhbG...",
        "response": "HTTP/1.1 403 Forbidden\nContent-Type: application/json\n\n{\"error\": \"Insufficient permissions\"}",
    },
    "404": {
        "request": "GET /api/users/99999 HTTP/1.1\nHost: api.example.com\nAccept: application/json",
        "response": "HTTP/1.1 404 Not Found\nContent-Type: application/json\n\n{\"error\": \"User not found\"}",
    },
    "405": {
        "request": "POST /api/status HTTP/1.1\nHost: api.example.com\nContent-Type: application/json\n\n{\"status\": \"up\"}",
        "response": "HTTP/1.1 405 Method Not Allowed\nAllow: GET, HEAD\nContent-Type: application/json\n\n{\"error\": \"POST not allowed on this endpoint\"}",
    },
    "406": {
        "request": "GET /api/users/42 HTTP/1.1\nHost: api.example.com\nAccept: application/xml",
        "response": "HTTP/1.1 406 Not Acceptable\nContent-Type: application/json\n\n{\"error\": \"Not Acceptable\", \"supported\": [\"application/json\", \"text/html\"]}",
    },
    "407": {
        "request": "GET /external/resource HTTP/1.1\nHost: api.example.com\nAccept: application/json",
        "response": "HTTP/1.1 407 Proxy Authentication Required\nProxy-Authenticate: Basic realm=\"corporate-proxy\"\nContent-Type: text/html\n\n<html><body><h1>Proxy Authentication Required</h1><p>Please authenticate with the proxy.</p></body></html>",
    },
    "408": {
        "request": "POST /api/upload HTTP/1.1\nHost: api.example.com\nContent-Type: application/octet-stream\nContent-Length: 10485760",
        "response": "HTTP/1.1 408 Request Time-out\nConnection: close\nContent-Type: application/json\n\n{\"error\": \"Request time-out\", \"detail\": \"The server did not receive a complete request within 30 seconds\"}",
    },
    "409": {
        "request": "PUT /api/users/42 HTTP/1.1\nHost: api.example.com\nContent-Type: application/json\nIf-Match: \"v3\"\n\n{\"name\": \"Alice Updated\"}",
        "response": "HTTP/1.1 409 Conflict\nContent-Type: application/json\n\n{\"error\": \"Resource was modified by another request\", \"current_etag\": \"v4\"}",
    },
    "410": {
        "request": "GET /api/v1/legacy-endpoint HTTP/1.1\nHost: api.example.com\nAccept: application/json",
        "response": "HTTP/1.1 410 Gone\nContent-Type: application/json\n\n{\"error\": \"This resource has been permanently removed\", \"see\": \"https://api.example.com/docs/migration-v2\"}",
    },
    "411": {
        "request": "POST /api/upload HTTP/1.1\nHost: api.example.com\nContent-Type: application/octet-stream\nTransfer-Encoding: chunked",
        "response": "HTTP/1.1 411 Length Required\nContent-Type: application/json\n\n{\"error\": \"Content-Length header is required\"}",
    },
    "412": {
        "request": "PUT /api/documents/88 HTTP/1.1\nHost: api.example.com\nContent-Type: application/json\nIf-Unmodified-Since: Sat, 01 Jan 2025 00:00:00 GMT\n\n{\"title\": \"Updated Title\"}",
        "response": "HTTP/1.1 412 Precondition Failed\nContent-Type: application/json\nETag: \"v12\"\nLast-Modified: Mon, 15 Mar 2026 10:30:00 GMT\n\n{\"error\": \"Precondition failed\", \"detail\": \"The resource has been modified since the specified date\"}",
    },
    "413": {
        "request": "POST /api/upload HTTP/1.1\nHost: api.example.com\nContent-Type: image/png\nContent-Length: 52428800\nAuthorization: Bearer eyJhbG...",
        "response": "HTTP/1.1 413 Payload Too Large\nContent-Type: application/json\nRetry-After: 3600\n\n{\"error\": \"Payload too large\", \"max_size\": \"10MB\", \"received\": \"50MB\"}",
    },
    "414": {
        "request": "GET /api/search?q=aaaaaaaaaa...&filter=bbbbbbbbbbb...&expand=cccccccccc... HTTP/1.1\nHost: api.example.com\nAccept: application/json",
        "response": "HTTP/1.1 414 URI Too Long\nContent-Type: application/json\n\n{\"error\": \"URI too long\", \"max_length\": 8192, \"suggestion\": \"Use POST /api/search with a request body instead\"}",
    },
    "415": {
        "request": "POST /api/data HTTP/1.1\nHost: api.example.com\nContent-Type: application/xml\n\n<data><name>test</name></data>",
        "response": "HTTP/1.1 415 Unsupported Media Type\nContent-Type: application/json\n\n{\"error\": \"Unsupported media type\", \"supported\": [\"application/json\"]}",
    },
    "416": {
        "request": "GET /files/archive.zip HTTP/1.1\nHost: cdn.example.com\nRange: bytes=99999999-199999999",
        "response": "HTTP/1.1 416 Range Not Satisfiable\nContent-Range: bytes */5242880\nContent-Type: application/json\n\n{\"error\": \"Range not satisfiable\", \"resource_size\": 5242880}",
    },
    "417": {
        "request": "POST /api/upload HTTP/1.1\nHost: api.example.com\nContent-Type: application/octet-stream\nExpect: 100-continue\nContent-Length: 1073741824",
        "response": "HTTP/1.1 417 Expectation Failed\nContent-Type: application/json\n\n{\"error\": \"Expectation failed\", \"detail\": \"Server does not support 100-continue for this endpoint\"}",
    },
    "418": {
        "request": "GET /brew-coffee HTTP/1.1\nHost: teapot.example.com\nAccept: application/coffee",
        "response": "HTTP/1.1 418 I'm a teapot\nContent-Type: text/plain\n\nI'm a teapot, short and stout.",
    },
    "419": {
        "request": "POST /api/settings HTTP/1.1\nHost: www.example.com\nContent-Type: application/x-www-form-urlencoded\nCookie: session=abc123\n\n_token=expired_csrf_token&theme=dark",
        "response": "HTTP/1.1 419 I'm a Fox\nContent-Type: application/json\n\n{\"error\": \"Page expired\", \"detail\": \"Your session has expired. Please refresh and try again.\"}",
    },
    "420": {
        "request": "GET /api/timeline HTTP/1.1\nHost: api.example.com\nAuthorization: Bearer eyJhbG...",
        "response": "HTTP/1.1 420 Enhance Your Calm\nRetry-After: 120\nContent-Type: application/json\n\n{\"error\": \"Enhance your calm\", \"detail\": \"You are being rate limited. Please slow down.\"}",
    },
    "421": {
        "request": "GET /api/data HTTP/1.1\nHost: wrong.example.com\nAccept: application/json",
        "response": "HTTP/1.1 421 Misdirected Request\nContent-Type: application/json\n\n{\"error\": \"Misdirected request\", \"detail\": \"This server is not able to produce a response for the given Host\"}",
    },
    "422": {
        "request": "POST /api/users HTTP/1.1\nHost: api.example.com\nContent-Type: application/json\n\n{\"name\": \"\", \"email\": \"not-an-email\"}",
        "response": "HTTP/1.1 422 Unprocessable Entity\nContent-Type: application/json\n\n{\"errors\": {\"name\": \"cannot be blank\", \"email\": \"invalid format\"}}",
    },
    "423": {
        "request": "PUT /files/quarterly-report.docx HTTP/1.1\nHost: dav.example.com\nContent-Type: application/vnd.openxmlformats-officedocument.wordprocessingml.document\nAuthorization: Basic YWxpY2U6cGFzcw==",
        "response": "HTTP/1.1 423 Locked\nContent-Type: application/json\n\n{\"error\": \"Resource is locked\", \"locked_by\": \"bob@example.com\", \"lock_expires\": \"2026-03-25T18:00:00Z\"}",
    },
    "424": {
        "request": "COPY /files/project/ HTTP/1.1\nHost: dav.example.com\nDestination: /backup/project/\nDepth: infinity\nAuthorization: Basic YWxpY2U6cGFzcw==",
        "response": "HTTP/1.1 424 Failed Dependency\nContent-Type: application/xml\n\n<?xml version=\"1.0\"?><D:multistatus xmlns:D=\"DAV:\"><D:response><D:href>/files/project/locked.doc</D:href><D:status>HTTP/1.1 423 Locked</D:status></D:response></D:multistatus>",
    },
    "425": {
        "request": "POST /api/payment HTTP/1.1\nHost: api.example.com\nContent-Type: application/json\nEarly-Data: 1\n\n{\"amount\": 100.00}",
        "response": "HTTP/1.1 425 Too Early\nContent-Type: application/json\n\n{\"error\": \"Too early\", \"detail\": \"This request cannot be processed using early data. Please retry after TLS handshake completes.\"}",
    },
    "426": {
        "request": "GET /api/secure/data HTTP/1.1\nHost: api.example.com\nAccept: application/json",
        "response": "HTTP/1.1 426 Upgrade Required\nUpgrade: TLS/1.3\nConnection: Upgrade\nContent-Type: application/json\n\n{\"error\": \"Upgrade required\", \"detail\": \"Please switch to TLS 1.3 or higher\"}",
    },
    "428": {
        "request": "PUT /api/documents/88 HTTP/1.1\nHost: api.example.com\nContent-Type: application/json\nAuthorization: Bearer eyJhbG...\n\n{\"title\": \"Updated\"}",
        "response": "HTTP/1.1 428 Precondition Required\nContent-Type: application/json\n\n{\"error\": \"Precondition required\", \"detail\": \"This request must include an If-Match header\"}",
    },
    "429": {
        "request": "GET /api/search?q=parrot HTTP/1.1\nHost: api.example.com\nAuthorization: Bearer eyJhbG...",
        "response": "HTTP/1.1 429 Too Many Requests\nRetry-After: 60\nX-RateLimit-Limit: 100\nX-RateLimit-Remaining: 0\nX-RateLimit-Reset: 1711324800\nContent-Type: application/json\n\n{\"error\": \"Rate limit exceeded. Try again in 60 seconds.\"}",
    },
    "431": {
        "request": "GET /api/data HTTP/1.1\nHost: api.example.com\nCookie: session=abc123; prefs=a]very]long]cookie]value]that]repeats...;\nX-Custom-Header: extremely-long-header-value...\nAccept: application/json",
        "response": "HTTP/1.1 431 Request Header Fields Too Large\nContent-Type: application/json\n\n{\"error\": \"Request header fields too large\", \"max_header_size\": \"8KB\"}",
    },
    "444": {
        "request": "GET / HTTP/1.1\nHost: blocked.example.com\nX-Forwarded-For: 203.0.113.50",
        "response": "HTTP/1.1 444 No Response\nConnection: close",
    },
    "450": {
        "request": "GET /file.exe HTTP/1.1\nHost: www.example.com\nAccept: application/octet-stream",
        "response": "HTTP/1.1 450 Blocked by Windows Parental Controls\nContent-Type: text/html\n\n<html><body><h1>Blocked</h1><p>This content has been blocked by parental controls.</p></body></html>",
    },
    "451": {
        "request": "GET /article/restricted-content HTTP/1.1\nHost: www.example.com\nAccept: text/html",
        "response": "HTTP/1.1 451 Unavailable For Legal Reasons\nLink: <https://www.example.com/legal/takedown-notice>; rel=\"blocked-by\"\nContent-Type: application/json\n\n{\"error\": \"Unavailable for legal reasons\", \"detail\": \"This content is not available in your jurisdiction due to a court order.\"}",
    },
    "494": {
        "request": "GET /api/data HTTP/1.1\nHost: api.example.com\nX-Custom: aaaaaaaaaaaaaaaaaaaaaaaaa...\nAccept: application/json",
        "response": "HTTP/1.1 494 Request Header Too Large\nContent-Type: text/html\nServer: nginx\n\n<html><body><h1>400 Bad Request</h1><p>Request Header Or Cookie Too Large</p></body></html>",
    },
    "498": {
        "request": "GET /api/protected HTTP/1.1\nHost: api.example.com\nAuthorization: Bearer expired.token.value",
        "response": "HTTP/1.1 498 Invalid Token\nContent-Type: application/json\n\n{\"error\": \"Invalid token\", \"detail\": \"The provided token has expired or is malformed\"}",
    },
    "499": {
        "request": "GET /api/slow-query?report=full HTTP/1.1\nHost: api.example.com\nAccept: application/json\nAuthorization: Bearer eyJhbG...",
        "response": "HTTP/1.1 499 Token Required\nConnection: close",
    },
    "500": {
        "request": "GET /api/reports/generate HTTP/1.1\nHost: api.example.com\nAuthorization: Bearer eyJhbG...",
        "response": "HTTP/1.1 500 Internal Server Error\nContent-Type: application/json\n\n{\"error\": \"An unexpected error occurred\"}",
    },
    "501": {
        "request": "PATCH /api/users/42 HTTP/1.1\nHost: api.example.com\nContent-Type: application/json-patch+json\nAuthorization: Bearer eyJhbG...\n\n[{\"op\": \"replace\", \"path\": \"/name\", \"value\": \"Alice\"}]",
        "response": "HTTP/1.1 501 Not Implemented\nContent-Type: application/json\n\n{\"error\": \"Not implemented\", \"detail\": \"PATCH method is not supported by this server\"}",
    },
    "502": {
        "request": "GET /api/data HTTP/1.1\nHost: api.example.com",
        "response": "HTTP/1.1 502 Bad Gateway\nContent-Type: text/html\nServer: nginx/1.24.0\n\n<html><body><h1>502 Bad Gateway</h1></body></html>",
    },
    "503": {
        "request": "GET / HTTP/1.1\nHost: www.example.com",
        "response": "HTTP/1.1 503 Service Unavailable\nRetry-After: 300\nContent-Type: text/html\n\n<html><body><h1>We'll be back shortly</h1></body></html>",
    },
    "504": {
        "request": "GET /api/aggregate?sources=all HTTP/1.1\nHost: api.example.com\nAccept: application/json",
        "response": "HTTP/1.1 504 Gateway Time-out\nContent-Type: text/html\nServer: nginx/1.24.0\n\n<html><body><h1>504 Gateway Timeout</h1><p>The upstream server did not respond in time.</p></body></html>",
    },
    "505": {
        "request": "GET /resource HTTP/0.9\nHost: www.example.com",
        "response": "HTTP/1.1 505 HTTP Version Not Supported\nContent-Type: application/json\n\n{\"error\": \"HTTP version not supported\", \"supported\": [\"HTTP/1.1\", \"HTTP/2\"]}",
    },
    "506": {
        "request": "GET /api/data HTTP/1.1\nHost: api.example.com\nAccept: application/json\nNegotiate: trans",
        "response": "HTTP/1.1 506 Variant Also Negotiates\nContent-Type: application/json\n\n{\"error\": \"Variant also negotiates\", \"detail\": \"Transparent content negotiation resulted in a circular reference\"}",
    },
    "507": {
        "request": "PUT /files/backup.tar.gz HTTP/1.1\nHost: dav.example.com\nContent-Type: application/gzip\nContent-Length: 10737418240\nAuthorization: Basic YWxpY2U6cGFzcw==",
        "response": "HTTP/1.1 507 Insufficient Storage\nContent-Type: application/json\n\n{\"error\": \"Insufficient storage\", \"available\": \"256MB\", \"required\": \"10GB\"}",
    },
    "508": {
        "request": "PROPFIND /files/loop/ HTTP/1.1\nHost: dav.example.com\nDepth: infinity\nAuthorization: Basic YWxpY2U6cGFzcw==",
        "response": "HTTP/1.1 508 Loop Detected\nContent-Type: application/json\n\n{\"error\": \"Loop detected\", \"detail\": \"The server detected an infinite loop while processing the request\"}",
    },
    "509": {
        "request": "GET /popular-page HTTP/1.1\nHost: www.example.com\nAccept: text/html",
        "response": "HTTP/1.1 509 Bandwidth Limit Exceeded\nRetry-After: 3600\nContent-Type: text/html\n\n<html><body><h1>509 Bandwidth Limit Exceeded</h1><p>This site has exceeded its monthly bandwidth allocation.</p></body></html>",
    },
    "510": {
        "request": "GET /api/resource HTTP/1.1\nHost: api.example.com\nAccept: application/json",
        "response": "HTTP/1.1 510 Not Extended\nContent-Type: application/json\n\n{\"error\": \"Not extended\", \"detail\": \"An additional extension is required to fulfill this request\"}",
    },
    "511": {
        "request": "GET /browse HTTP/1.1\nHost: www.example.com\nAccept: text/html",
        "response": "HTTP/1.1 511 Network Authentication Required\nContent-Type: text/html\n\n<html><body><h1>Network Login Required</h1><p>You must <a href=\"https://captive.example.net/login\">log in</a> to access the network.</p></body></html>",
    },
    "530": {
        "request": "GET / HTTP/1.1\nHost: frozen.example.com\nAccept: text/html",
        "response": "HTTP/1.1 530 Site is Frozen\nContent-Type: text/html\n\n<html><body><h1>Site Frozen</h1><p>This site has been frozen. Please contact the site owner.</p></body></html>",
    },
}
