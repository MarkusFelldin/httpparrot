"""Example HTTP request/response pairs for status codes."""

HTTP_EXAMPLES = {
    "200": {
        "request": "GET /api/users/42 HTTP/1.1\nHost: api.example.com\nAccept: application/json\nAuthorization: Bearer eyJhbG...",
        "response": "HTTP/1.1 200 OK\nContent-Type: application/json\nContent-Length: 82\nCache-Control: max-age=60\n\n{\"id\": 42, \"name\": \"Alice\", \"email\": \"alice@example.com\"}",
    },
    "201": {
        "request": "POST /api/users HTTP/1.1\nHost: api.example.com\nContent-Type: application/json\nAuthorization: Bearer eyJhbG...\n\n{\"name\": \"Bob\", \"email\": \"bob@example.com\"}",
        "response": "HTTP/1.1 201 Created\nContent-Type: application/json\nLocation: /api/users/43\n\n{\"id\": 43, \"name\": \"Bob\", \"email\": \"bob@example.com\"}",
    },
    "204": {
        "request": "DELETE /api/users/42 HTTP/1.1\nHost: api.example.com\nAuthorization: Bearer eyJhbG...",
        "response": "HTTP/1.1 204 No Content",
    },
    "301": {
        "request": "GET /old-page HTTP/1.1\nHost: www.example.com",
        "response": "HTTP/1.1 301 Moved Permanently\nLocation: https://www.example.com/new-page\nContent-Length: 0",
    },
    "302": {
        "request": "POST /login HTTP/1.1\nHost: www.example.com\nContent-Type: application/x-www-form-urlencoded\n\nusername=alice&password=secret",
        "response": "HTTP/1.1 302 Found\nLocation: /dashboard\nSet-Cookie: session=abc123; HttpOnly; Secure",
    },
    "304": {
        "request": "GET /style.css HTTP/1.1\nHost: www.example.com\nIf-None-Match: \"v2.5.1\"\nIf-Modified-Since: Mon, 24 Mar 2026 00:00:00 GMT",
        "response": "HTTP/1.1 304 Not Modified\nETag: \"v2.5.1\"\nCache-Control: max-age=3600",
    },
    "400": {
        "request": "POST /api/users HTTP/1.1\nHost: api.example.com\nContent-Type: application/json\n\n{invalid json",
        "response": "HTTP/1.1 400 Bad Request\nContent-Type: application/json\n\n{\"error\": \"Malformed JSON in request body\"}",
    },
    "401": {
        "request": "GET /api/profile HTTP/1.1\nHost: api.example.com",
        "response": "HTTP/1.1 401 Unauthorized\nWWW-Authenticate: Bearer realm=\"api\"\nContent-Type: application/json\n\n{\"error\": \"Authentication required\"}",
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
    "409": {
        "request": "PUT /api/users/42 HTTP/1.1\nHost: api.example.com\nContent-Type: application/json\nIf-Match: \"v3\"\n\n{\"name\": \"Alice Updated\"}",
        "response": "HTTP/1.1 409 Conflict\nContent-Type: application/json\n\n{\"error\": \"Resource was modified by another request\", \"current_etag\": \"v4\"}",
    },
    "418": {
        "request": "GET /brew-coffee HTTP/1.1\nHost: teapot.example.com\nAccept: application/coffee",
        "response": "HTTP/1.1 418 I'm a Teapot\nContent-Type: text/plain\n\nI'm a teapot, short and stout.",
    },
    "422": {
        "request": "POST /api/users HTTP/1.1\nHost: api.example.com\nContent-Type: application/json\n\n{\"name\": \"\", \"email\": \"not-an-email\"}",
        "response": "HTTP/1.1 422 Unprocessable Entity\nContent-Type: application/json\n\n{\"errors\": {\"name\": \"cannot be blank\", \"email\": \"invalid format\"}}",
    },
    "429": {
        "request": "GET /api/search?q=parrot HTTP/1.1\nHost: api.example.com\nAuthorization: Bearer eyJhbG...",
        "response": "HTTP/1.1 429 Too Many Requests\nRetry-After: 60\nX-RateLimit-Limit: 100\nX-RateLimit-Remaining: 0\nX-RateLimit-Reset: 1711324800\nContent-Type: application/json\n\n{\"error\": \"Rate limit exceeded. Try again in 60 seconds.\"}",
    },
    "500": {
        "request": "GET /api/reports/generate HTTP/1.1\nHost: api.example.com\nAuthorization: Bearer eyJhbG...",
        "response": "HTTP/1.1 500 Internal Server Error\nContent-Type: application/json\n\n{\"error\": \"An unexpected error occurred\"}",
    },
    "502": {
        "request": "GET /api/data HTTP/1.1\nHost: api.example.com",
        "response": "HTTP/1.1 502 Bad Gateway\nContent-Type: text/html\nServer: nginx/1.24.0\n\n<html><body><h1>502 Bad Gateway</h1></body></html>",
    },
    "503": {
        "request": "GET / HTTP/1.1\nHost: www.example.com",
        "response": "HTTP/1.1 503 Service Unavailable\nRetry-After: 300\nContent-Type: text/html\n\n<html><body><h1>We'll be back shortly</h1></body></html>",
    },
}
