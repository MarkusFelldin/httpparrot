"""Real-world examples, code snippets, and typical headers for status codes."""

STATUS_EXTRA = {
    "100": {
        "examples": [
            "Uploading a large file — the client checks if the server will accept it before sending the full body",
            "API requests with large JSON payloads using the Expect: 100-continue header",
        ],
        "headers": ["Expect: 100-continue"],
        "code": {
            "python": 'return "", 100',
            "node": "res.writeContinue();",
            "go": "http.StatusContinue // 100",
        },
    },
    "101": {
        "examples": [
            "Opening a WebSocket connection — the browser sends an Upgrade request and gets 101 back",
            "Upgrading from HTTP/1.1 to HTTP/2 via the Upgrade header",
        ],
        "headers": ["Upgrade: websocket", "Connection: Upgrade"],
        "code": {
            "python": "# Handled by WebSocket libraries like flask-sock",
            "node": 'server.on("upgrade", (req, socket, head) => { ... });',
            "go": "// Use gorilla/websocket or nhooyr.io/websocket",
        },
    },
    "102": {
        "examples": [
            "WebDAV operations that take a long time, like recursively copying a large folder",
            "Long-running server processes where the client needs a keep-alive signal",
        ],
        "headers": [],
        "code": {
            "python": 'return "", 102',
            "node": "res.writeProcessing();",
            "go": "http.StatusProcessing // 102",
        },
    },
    "103": {
        "examples": [
            "A CDN sending Link headers early so the browser can preload CSS and fonts while the origin server builds the page",
            "Cloudflare and Fastly use this to speed up page loads",
        ],
        "headers": ["Link: </style.css>; rel=preload; as=style"],
        "code": {
            "python": "# Supported at the server/CDN level, not application code",
            "node": "res.writeEarlyHints({ link: '</style.css>; rel=preload; as=style' });",
            "go": "// Requires HTTP/2 server push support",
        },
    },
    "200": {
        "examples": [
            "Loading any web page successfully",
            "An API returning data from a GET request",
            "A form submission processed without errors",
        ],
        "headers": ["Content-Type: application/json"],
        "code": {
            "python": 'return jsonify({"status": "ok"}), 200',
            "node": "res.status(200).json({ status: 'ok' });",
            "go": 'w.WriteHeader(http.StatusOK)\nw.Write([]byte("OK"))',
        },
    },
    "201": {
        "examples": [
            "Creating a new user account via POST /api/users",
            "Uploading a file that creates a new resource",
            "Adding a new item to a database through a REST API",
        ],
        "headers": ["Location: /api/users/123", "Content-Type: application/json"],
        "code": {
            "python": 'return jsonify(user), 201',
            "node": "res.status(201).json(newUser);",
            "go": "w.WriteHeader(http.StatusCreated)",
        },
    },
    "202": {
        "examples": [
            "Submitting a batch job that will be processed later",
            "Sending an email — the server accepts it but hasn't delivered it yet",
            "Triggering a CI/CD pipeline that runs asynchronously",
        ],
        "headers": ["Location: /api/jobs/456"],
        "code": {
            "python": 'return jsonify({"job_id": "456"}), 202',
            "node": "res.status(202).json({ jobId: '456' });",
            "go": "w.WriteHeader(http.StatusAccepted)",
        },
    },
    "204": {
        "examples": [
            "Successfully deleting a resource — DELETE /api/users/123",
            "Saving settings with no response body needed",
            "A preflight CORS OPTIONS request",
        ],
        "headers": [],
        "code": {
            "python": 'return "", 204',
            "node": "res.status(204).end();",
            "go": "w.WriteHeader(http.StatusNoContent)",
        },
    },
    "301": {
        "examples": [
            "A website permanently moving from http:// to https://",
            "Changing your domain name from old.com to new.com",
            "Restructuring URLs from /blog/post/123 to /posts/123",
        ],
        "headers": ["Location: https://new.example.com/page"],
        "code": {
            "python": "return redirect('https://new.example.com', code=301)",
            "node": "res.redirect(301, 'https://new.example.com');",
            "go": "http.Redirect(w, r, url, http.StatusMovedPermanently)",
        },
    },
    "302": {
        "examples": [
            "Redirecting to a login page when not authenticated",
            "A short URL service like bit.ly redirecting to the full URL",
            "Redirecting after a successful form submission",
        ],
        "headers": ["Location: /login"],
        "code": {
            "python": "return redirect('/login')",
            "node": "res.redirect('/login');",
            "go": "http.Redirect(w, r, \"/login\", http.StatusFound)",
        },
    },
    "304": {
        "examples": [
            "Browser requests a page it already has cached — server says 'use your cache'",
            "CDN validating that cached content is still fresh",
            "API clients using ETags to avoid re-downloading unchanged data",
        ],
        "headers": ["ETag: \"abc123\"", "Cache-Control: max-age=3600"],
        "code": {
            "python": "# Flask handles this automatically with ETags",
            "node": "res.status(304).end();",
            "go": "w.WriteHeader(http.StatusNotModified)",
        },
    },
    "400": {
        "examples": [
            "Sending malformed JSON in an API request",
            "Missing required fields in a form submission",
            "Sending an invalid date format to an API",
        ],
        "headers": ["Content-Type: application/json"],
        "code": {
            "python": 'return jsonify({"error": "Invalid input"}), 400',
            "node": "res.status(400).json({ error: 'Invalid input' });",
            "go": 'http.Error(w, "Bad Request", http.StatusBadRequest)',
        },
    },
    "401": {
        "examples": [
            "Calling an API without an authentication token",
            "Your JWT token has expired",
            "Entering wrong username/password on basic auth",
        ],
        "headers": ["WWW-Authenticate: Bearer", "Content-Type: application/json"],
        "code": {
            "python": 'return jsonify({"error": "Unauthorized"}), 401',
            "node": "res.status(401).json({ error: 'Unauthorized' });",
            "go": 'http.Error(w, "Unauthorized", http.StatusUnauthorized)',
        },
    },
    "403": {
        "examples": [
            "Trying to access an admin page as a regular user",
            "An API key that doesn't have permission for the requested resource",
            "Accessing a file on a server where directory listing is disabled",
        ],
        "headers": [],
        "code": {
            "python": "abort(403)",
            "node": "res.status(403).json({ error: 'Forbidden' });",
            "go": 'http.Error(w, "Forbidden", http.StatusForbidden)',
        },
    },
    "404": {
        "examples": [
            "Visiting a URL that doesn't exist on a website",
            "Requesting a deleted resource from an API",
            "A typo in a URL",
        ],
        "headers": [],
        "code": {
            "python": "abort(404)",
            "node": "res.status(404).json({ error: 'Not found' });",
            "go": 'http.NotFound(w, r)',
        },
    },
    "405": {
        "examples": [
            "Sending a POST request to an endpoint that only accepts GET",
            "Trying to DELETE a read-only resource",
        ],
        "headers": ["Allow: GET, HEAD"],
        "code": {
            "python": "abort(405)",
            "node": "res.status(405).set('Allow', 'GET').json({ error: 'Method not allowed' });",
            "go": 'http.Error(w, "Method Not Allowed", http.StatusMethodNotAllowed)',
        },
    },
    "409": {
        "examples": [
            "Two users trying to edit the same document at the same time",
            "Creating a username that already exists",
            "Trying to update a resource that was modified since you last read it",
        ],
        "headers": [],
        "code": {
            "python": 'return jsonify({"error": "Conflict"}), 409',
            "node": "res.status(409).json({ error: 'Username already exists' });",
            "go": 'http.Error(w, "Conflict", http.StatusConflict)',
        },
    },
    "418": {
        "examples": [
            "Google's famous teapot page at google.com/teapot (now removed)",
            "Easter eggs in APIs that implement the joke RFC",
            "Developers having fun with HTTP specifications",
        ],
        "headers": [],
        "code": {
            "python": 'return "I\'m a teapot", 418',
            "node": "res.status(418).send(\"I'm a teapot\");",
            "go": 'http.Error(w, "I\'m a teapot", 418)',
        },
    },
    "422": {
        "examples": [
            "A form with valid JSON but failing business logic validation",
            "Creating a user with an email that fails format validation",
            "Rails/Laravel APIs returning validation errors",
        ],
        "headers": ["Content-Type: application/json"],
        "code": {
            "python": 'return jsonify({"errors": {"email": "invalid"}}), 422',
            "node": "res.status(422).json({ errors: { email: 'invalid' } });",
            "go": "w.WriteHeader(http.StatusUnprocessableEntity)",
        },
    },
    "429": {
        "examples": [
            "Hitting the Twitter/GitHub/Stripe API rate limit",
            "Too many login attempts in a short period",
            "A scraper being throttled by a website",
        ],
        "headers": ["Retry-After: 60", "X-RateLimit-Remaining: 0"],
        "code": {
            "python": 'return jsonify({"error": "Too many requests"}), 429',
            "node": "res.status(429).set('Retry-After', '60').json({ error: 'Rate limited' });",
            "go": 'w.Header().Set("Retry-After", "60")\nhttp.Error(w, "Too Many Requests", 429)',
        },
    },
    "500": {
        "examples": [
            "An unhandled exception in your application code",
            "A database query failing unexpectedly",
            "A null pointer / undefined reference in production",
        ],
        "headers": [],
        "code": {
            "python": "# Don't return 500 intentionally — Flask does it on unhandled exceptions",
            "node": "// Express returns 500 automatically on unhandled errors",
            "go": 'http.Error(w, "Internal Server Error", http.StatusInternalServerError)',
        },
    },
    "502": {
        "examples": [
            "Nginx can't reach your application server (it crashed or isn't running)",
            "A load balancer gets an invalid response from a backend",
            "Cloudflare can't connect to your origin server",
        ],
        "headers": [],
        "code": {
            "python": "# Typically returned by reverse proxies, not application code",
            "node": "// Usually an nginx/load balancer error, not app-level",
            "go": 'http.Error(w, "Bad Gateway", http.StatusBadGateway)',
        },
    },
    "503": {
        "examples": [
            "A website during a deployment or maintenance window",
            "Server overwhelmed by a traffic spike",
            "A dependent microservice is down",
        ],
        "headers": ["Retry-After: 300"],
        "code": {
            "python": 'return "Service temporarily unavailable", 503',
            "node": "res.status(503).set('Retry-After', '300').send('Maintenance');",
            "go": 'w.Header().Set("Retry-After", "300")\nhttp.Error(w, "Service Unavailable", 503)',
        },
    },
    "504": {
        "examples": [
            "Your API gateway times out waiting for a slow microservice",
            "Nginx proxy_read_timeout exceeded",
            "A database query taking too long behind a load balancer",
        ],
        "headers": [],
        "code": {
            "python": "# Returned by reverse proxies when upstream times out",
            "node": "// Configure proxy timeout: proxy_read_timeout 60s;",
            "go": "// Set http.Server.ReadTimeout and WriteTimeout",
        },
    },
}
