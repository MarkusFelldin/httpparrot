"""Debug This Response exercises — broken HTTP exchanges for users to diagnose."""

DEBUG_EXERCISES = [
    # --- Beginner (6 exercises) ---
    {
        "id": "200-error-body",
        "difficulty": "beginner",
        "title": "200 with Error Body",
        "description": "A client requests a user profile, but the user does not exist. The server sends back this response.",
        "request": "GET /api/users/99999 HTTP/1.1\nHost: api.example.com\nAccept: application/json\nAuthorization: Bearer eyJhbG...",
        "response": 'HTTP/1.1 200 OK\nContent-Type: application/json\n\n{"error": "User not found"}',
        "bugs": [
            {
                "id": "wrong-status",
                "description": "Status code should be 404, not 200",
                "explanation": "A 200 OK tells the client the request succeeded. When a resource is not found, the server must return 404 Not Found so clients, caches, and monitoring tools handle the error correctly.",
            },
        ],
        "related_codes": ["200", "404"],
    },
    {
        "id": "301-no-location",
        "difficulty": "beginner",
        "title": "301 Missing Location",
        "description": "A page has permanently moved to a new URL. The server sends a redirect response.",
        "request": "GET /old-page HTTP/1.1\nHost: www.example.com\nAccept: text/html",
        "response": "HTTP/1.1 301 Moved Permanently\nContent-Type: text/html\nContent-Length: 0",
        "bugs": [
            {
                "id": "missing-location",
                "description": "Missing required Location header",
                "explanation": "A 301 redirect without a Location header is useless -- the client has no idea where to go. Browsers will show an error, and bots will not follow the redirect. Always include Location with 3xx redirects.",
            },
        ],
        "related_codes": ["301"],
    },
    {
        "id": "204-with-body",
        "difficulty": "beginner",
        "title": "204 with Body",
        "description": "A client deletes a resource. The server confirms the deletion.",
        "request": "DELETE /api/posts/42 HTTP/1.1\nHost: api.example.com\nAuthorization: Bearer eyJhbG...",
        "response": 'HTTP/1.1 204 No Content\nContent-Type: application/json\nContent-Length: 35\n\n{"message": "Post deleted successfully"}',
        "bugs": [
            {
                "id": "body-on-204",
                "description": "204 No Content must not include a body",
                "explanation": "RFC 9110 states that a 204 response must not contain a message body. Clients are allowed to ignore any body present. If you want to send a confirmation message, use 200 OK instead.",
            },
            {
                "id": "content-headers-on-204",
                "description": "Content-Type and Content-Length should not be present on a 204",
                "explanation": "Since 204 means no content, including Content-Type and Content-Length headers is misleading and contradicts the status code semantics.",
            },
        ],
        "related_codes": ["204", "200"],
    },
    {
        "id": "401-no-www-auth",
        "difficulty": "beginner",
        "title": "401 Missing WWW-Authenticate",
        "description": "An unauthenticated client tries to access a protected API endpoint.",
        "request": "GET /api/admin/settings HTTP/1.1\nHost: api.example.com\nAccept: application/json",
        "response": 'HTTP/1.1 401 Unauthorized\nContent-Type: application/json\n\n{"error": "Authentication required"}',
        "bugs": [
            {
                "id": "missing-www-authenticate",
                "description": "Missing required WWW-Authenticate header",
                "explanation": "RFC 9110 requires a 401 response to include a WWW-Authenticate header indicating the authentication scheme(s) the server accepts (e.g. Bearer, Basic). Without it, the client has no way to know how to authenticate.",
            },
        ],
        "related_codes": ["401"],
    },
    {
        "id": "201-no-location",
        "difficulty": "beginner",
        "title": "201 Without Location",
        "description": "A client creates a new blog post via the API.",
        "request": 'POST /api/posts HTTP/1.1\nHost: api.example.com\nContent-Type: application/json\nAuthorization: Bearer eyJhbG...\n\n{"title": "Hello World", "body": "My first post"}',
        "response": 'HTTP/1.1 201 Created\nContent-Type: application/json\n\n{"id": 1, "title": "Hello World", "body": "My first post"}',
        "bugs": [
            {
                "id": "missing-location-201",
                "description": "Missing Location header pointing to the new resource",
                "explanation": "When a server returns 201 Created, it should include a Location header with the URI of the newly created resource (e.g. /api/posts/1). This lets clients immediately know where to find the new resource without parsing the body.",
            },
        ],
        "related_codes": ["201"],
    },
    {
        "id": "500-validation-error",
        "difficulty": "beginner",
        "title": "500 for Client Mistake",
        "description": "A client submits a form with an invalid email address.",
        "request": 'POST /api/register HTTP/1.1\nHost: api.example.com\nContent-Type: application/json\n\n{"name": "Alice", "email": "not-an-email"}',
        "response": 'HTTP/1.1 500 Internal Server Error\nContent-Type: application/json\n\n{"error": "Invalid email format"}',
        "bugs": [
            {
                "id": "wrong-status-class",
                "description": "Should be a 4xx client error (400 or 422), not 500",
                "explanation": "A 500 Internal Server Error means the server has a bug. Validation failures are client errors -- the client sent bad data. Use 400 Bad Request or 422 Unprocessable Entity to correctly signal that the client needs to fix their input.",
            },
        ],
        "related_codes": ["500", "400", "422"],
    },
    # --- Intermediate (6 exercises) ---
    {
        "id": "429-no-retry-after",
        "difficulty": "intermediate",
        "title": "429 Without Retry-After",
        "description": "A client exceeds the API rate limit.",
        "request": "GET /api/search?q=parrots HTTP/1.1\nHost: api.example.com\nAuthorization: Bearer eyJhbG...",
        "response": 'HTTP/1.1 429 Too Many Requests\nContent-Type: application/json\n\n{"error": "Rate limit exceeded"}',
        "bugs": [
            {
                "id": "missing-retry-after",
                "description": "Missing Retry-After header",
                "explanation": "Without a Retry-After header, the client has no idea when to retry. Well-behaved clients will use exponential backoff, but providing Retry-After (e.g. 60 seconds) gives concrete guidance and reduces unnecessary retry traffic.",
            },
            {
                "id": "missing-rate-limit-headers",
                "description": "Missing rate limit information headers",
                "explanation": "Best practice is to include X-RateLimit-Limit, X-RateLimit-Remaining, and X-RateLimit-Reset headers so clients can proactively manage their request rate instead of waiting to be throttled.",
            },
        ],
        "related_codes": ["429"],
    },
    {
        "id": "post-301-redirect",
        "difficulty": "intermediate",
        "title": "POST Redirect Uses 301",
        "description": "A client submits a form via POST. The endpoint has moved to a new URL.",
        "request": 'POST /api/v1/submit HTTP/1.1\nHost: api.example.com\nContent-Type: application/json\n\n{"data": "important payload"}',
        "response": "HTTP/1.1 301 Moved Permanently\nLocation: https://api.example.com/api/v2/submit\nContent-Length: 0",
        "bugs": [
            {
                "id": "301-drops-method",
                "description": "301 may cause clients to change POST to GET on redirect",
                "explanation": "Historically, browsers changed POST to GET when following 301 redirects. Use 308 Permanent Redirect instead, which guarantees the HTTP method is preserved. The client's POST body will be re-sent to the new URL.",
            },
        ],
        "related_codes": ["301", "308", "307"],
    },
    {
        "id": "set-cookie-insecure",
        "difficulty": "intermediate",
        "title": "Insecure Set-Cookie",
        "description": "A user logs into a web application over HTTPS. The server sets a session cookie.",
        "request": "POST /login HTTP/1.1\nHost: secure.example.com\nContent-Type: application/x-www-form-urlencoded\n\nusername=alice&password=secret",
        "response": "HTTP/1.1 302 Found\nLocation: /dashboard\nSet-Cookie: session=abc123xyz",
        "bugs": [
            {
                "id": "no-secure-flag",
                "description": "Cookie missing Secure flag",
                "explanation": "Without the Secure flag, the session cookie can be sent over unencrypted HTTP connections, making it vulnerable to interception via man-in-the-middle attacks.",
            },
            {
                "id": "no-httponly-flag",
                "description": "Cookie missing HttpOnly flag",
                "explanation": "Without HttpOnly, JavaScript can access the cookie via document.cookie, making it vulnerable to XSS (cross-site scripting) attacks that steal session tokens.",
            },
            {
                "id": "no-samesite-flag",
                "description": "Cookie missing SameSite attribute",
                "explanation": "Without SameSite, the cookie will be sent with cross-site requests, making it vulnerable to CSRF (cross-site request forgery) attacks. Use SameSite=Lax or SameSite=Strict.",
            },
        ],
        "related_codes": ["302"],
    },
    {
        "id": "cors-missing-origin",
        "difficulty": "intermediate",
        "title": "CORS Missing Allow-Origin",
        "description": "A frontend app on app.example.com makes a cross-origin API request. The server handles CORS but the response is incomplete.",
        "request": "GET /api/data HTTP/1.1\nHost: api.example.com\nOrigin: https://app.example.com\nAccept: application/json",
        "response": 'HTTP/1.1 200 OK\nContent-Type: application/json\nAccess-Control-Allow-Methods: GET, POST\nAccess-Control-Allow-Headers: Content-Type\n\n{"data": "here"}',
        "bugs": [
            {
                "id": "missing-allow-origin",
                "description": "Missing Access-Control-Allow-Origin header",
                "explanation": "Without Access-Control-Allow-Origin, the browser will block the response from being read by the frontend JavaScript. The server must echo back the allowed origin or use * (for public APIs).",
            },
        ],
        "related_codes": ["200"],
    },
    {
        "id": "405-no-allow",
        "difficulty": "intermediate",
        "title": "405 Without Allow Header",
        "description": "A client tries to DELETE a read-only resource.",
        "request": "DELETE /api/system/health HTTP/1.1\nHost: api.example.com\nAuthorization: Bearer eyJhbG...",
        "response": 'HTTP/1.1 405 Method Not Allowed\nContent-Type: application/json\n\n{"error": "DELETE is not allowed on this endpoint"}',
        "bugs": [
            {
                "id": "missing-allow-header",
                "description": "Missing required Allow header listing permitted methods",
                "explanation": "RFC 9110 requires a 405 response to include an Allow header listing the methods the resource supports (e.g. Allow: GET, HEAD). Without it, the client must guess which methods are valid.",
            },
        ],
        "related_codes": ["405"],
    },
    {
        "id": "cache-immutable-revalidate",
        "difficulty": "intermediate",
        "title": "Contradictory Cache Headers",
        "description": "A server returns a static asset (a versioned JavaScript file) with conflicting cache directives.",
        "request": "GET /static/app.v3.2.1.js HTTP/1.1\nHost: cdn.example.com\nAccept: */*",
        "response": "HTTP/1.1 200 OK\nContent-Type: application/javascript\nCache-Control: no-cache, immutable, max-age=31536000\nETag: \"v3.2.1\"",
        "bugs": [
            {
                "id": "contradictory-cache",
                "description": "no-cache contradicts immutable and max-age",
                "explanation": "no-cache forces revalidation on every request, while immutable tells clients the resource will never change. These are contradictory. For versioned static assets, use Cache-Control: public, max-age=31536000, immutable without no-cache.",
            },
        ],
        "related_codes": ["200", "304"],
    },
    # --- Expert (6 exercises) ---
    {
        "id": "preflight-missing-max-age",
        "difficulty": "expert",
        "title": "CORS Preflight Incomplete",
        "description": "A browser sends a CORS preflight request for a cross-origin POST with a JSON body. The server responds, but the response has issues.",
        "request": "OPTIONS /api/data HTTP/1.1\nHost: api.example.com\nOrigin: https://app.example.com\nAccess-Control-Request-Method: POST\nAccess-Control-Request-Headers: Content-Type, Authorization",
        "response": "HTTP/1.1 200 OK\nAccess-Control-Allow-Origin: *\nAccess-Control-Allow-Methods: GET, POST\nAccess-Control-Allow-Headers: Content-Type\nContent-Length: 0",
        "bugs": [
            {
                "id": "wildcard-with-credentials",
                "description": "Wildcard origin (*) will fail if the request includes credentials",
                "explanation": "If the actual request sends cookies or Authorization headers, the browser requires Access-Control-Allow-Origin to echo the exact origin, not *. The wildcard blocks credentialed requests entirely.",
            },
            {
                "id": "missing-auth-header-in-allow",
                "description": "Authorization header not listed in Access-Control-Allow-Headers",
                "explanation": "The preflight requested permission for both Content-Type and Authorization, but the server only allowed Content-Type. The browser will block the actual request because Authorization was not approved.",
            },
            {
                "id": "no-max-age",
                "description": "Missing Access-Control-Max-Age header",
                "explanation": "Without Access-Control-Max-Age, the browser sends a preflight OPTIONS request before every single cross-origin request. Setting a max-age (e.g. 86400) lets browsers cache the preflight result and skip redundant requests.",
            },
        ],
        "related_codes": ["200"],
    },
    {
        "id": "206-wrong-content-range",
        "difficulty": "expert",
        "title": "Partial Content Mismatch",
        "description": "A client requests a byte range of a large video file. The server returns partial content but the headers are inconsistent.",
        "request": "GET /videos/movie.mp4 HTTP/1.1\nHost: cdn.example.com\nRange: bytes=1000-1999",
        "response": "HTTP/1.1 206 Partial Content\nContent-Type: video/mp4\nContent-Range: bytes 1000-1999/50000\nContent-Length: 500\nAccept-Ranges: bytes\n\n[binary data]",
        "bugs": [
            {
                "id": "content-length-mismatch",
                "description": "Content-Length (500) does not match the range size (1000 bytes)",
                "explanation": "The range 1000-1999 is 1000 bytes, but Content-Length says 500. This mismatch will cause clients to either truncate data or hang waiting for more bytes. Content-Length must equal the actual number of bytes in the range.",
            },
        ],
        "related_codes": ["206", "416"],
    },
    {
        "id": "412-missing-etag",
        "difficulty": "expert",
        "title": "412 Without Current State",
        "description": "A client tries to update a document using a conditional request, but the precondition fails.",
        "request": 'PUT /api/documents/88 HTTP/1.1\nHost: api.example.com\nContent-Type: application/json\nIf-Match: "v5"\nAuthorization: Bearer eyJhbG...\n\n{"title": "Updated Title"}',
        "response": 'HTTP/1.1 412 Precondition Failed\nContent-Type: application/json\n\n{"error": "Precondition failed"}',
        "bugs": [
            {
                "id": "missing-current-etag",
                "description": "Should include the current ETag so the client can retry",
                "explanation": "When a 412 response occurs because If-Match failed, the server should include the current ETag header. This lets the client fetch the latest version, resolve conflicts, and retry the update without an extra round trip.",
            },
        ],
        "related_codes": ["412", "428"],
    },
    {
        "id": "303-after-post",
        "difficulty": "expert",
        "title": "POST Success Returns 200",
        "description": "A user submits an order form. The server processes it and returns the order confirmation page directly.",
        "request": 'POST /checkout HTTP/1.1\nHost: shop.example.com\nContent-Type: application/x-www-form-urlencoded\nCookie: session=xyz789\n\nitem=widget&qty=3&card=tok_visa',
        "response": 'HTTP/1.1 200 OK\nContent-Type: text/html\n\n<html><body><h1>Order Confirmed!</h1><p>Order #1024 placed.</p></body></html>',
        "bugs": [
            {
                "id": "should-use-prg",
                "description": "Should use Post/Redirect/Get pattern (303 See Other) instead of 200",
                "explanation": "Returning 200 directly after a POST means the browser's URL still shows /checkout. If the user refreshes, the browser will resubmit the POST (duplicate order!). Use 303 See Other to redirect to /orders/1024 -- this is the Post/Redirect/Get pattern that prevents accidental resubmission.",
            },
        ],
        "related_codes": ["303", "302"],
    },
    {
        "id": "json-wrong-content-type",
        "difficulty": "expert",
        "title": "JSON with Wrong Content-Type",
        "description": "An API returns a JSON response, but something is off about the headers.",
        "request": "GET /api/users/42 HTTP/1.1\nHost: api.example.com\nAccept: application/json\nAuthorization: Bearer eyJhbG...",
        "response": 'HTTP/1.1 200 OK\nContent-Type: text/html\nX-Powered-By: Express\n\n{"id": 42, "name": "Alice", "email": "alice@example.com"}',
        "bugs": [
            {
                "id": "wrong-content-type",
                "description": "Content-Type is text/html but body is JSON",
                "explanation": "When the Content-Type says text/html but the body is JSON, browsers may try to render it as HTML (XSS risk), and API clients may fail to parse it. Use application/json for JSON responses.",
            },
            {
                "id": "leaking-server-info",
                "description": "X-Powered-By header leaks server technology",
                "explanation": "The X-Powered-By header reveals the server framework (Express). This information helps attackers target known vulnerabilities. Remove it in production.",
            },
        ],
        "related_codes": ["200"],
    },
    {
        "id": "hsts-missing-on-https",
        "difficulty": "expert",
        "title": "HTTPS Without HSTS",
        "description": "A banking API serves all traffic over HTTPS but is missing a key security header.",
        "request": "GET /api/account/balance HTTP/1.1\nHost: bank-api.example.com\nAccept: application/json\nAuthorization: Bearer eyJhbG...",
        "response": 'HTTP/1.1 200 OK\nContent-Type: application/json\nCache-Control: no-store\n\n{"balance": 12345.67, "currency": "USD"}',
        "bugs": [
            {
                "id": "missing-hsts",
                "description": "Missing Strict-Transport-Security (HSTS) header",
                "explanation": "Without HSTS, a user's first visit (or after the browser cache expires) could be intercepted and downgraded to HTTP via an SSL stripping attack. Add Strict-Transport-Security: max-age=31536000; includeSubDomains to tell browsers to always use HTTPS.",
            },
            {
                "id": "caching-sensitive-data",
                "description": "no-store is correct, but should also add private",
                "explanation": "For sensitive financial data, Cache-Control: no-store, private ensures that neither the browser nor any intermediate proxy or CDN caches the response. While no-store is the main directive, adding private is defense-in-depth.",
            },
        ],
        "related_codes": ["200"],
    },
]
