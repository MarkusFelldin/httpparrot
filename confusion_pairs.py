"""Data for confusion pair lesson pages.

Each pair describes two commonly confused HTTP status codes with a TL;DR,
decision tree, annotated examples, and mini-quiz questions.
"""

CONFUSION_PAIRS = [
    {
        "slug": "401-vs-403",
        "codes": ["401", "403"],
        "title": "401 Unauthorized vs 403 Forbidden",
        "category": "Auth pairs",
        "tldr": "401 means the server doesn't know who you are (missing or invalid credentials); 403 means it knows who you are but you're not allowed.",
        "decision_tree": [
            {"question": "Did the client send valid credentials?", "yes": "403", "no": "401"},
            {"question": "Would logging in (or re-authenticating) fix the problem?", "yes": "401", "no": "403"},
            {"question": "Does the server want to hide that the resource exists?", "yes": "404 (not 403)", "no": "403"},
        ],
        "examples": [
            {"scenario": "A user hits GET /admin/dashboard without a session cookie or auth token.", "code": "401", "explanation": "The server has no idea who is making the request \u2014 authentication is required."},
            {"scenario": "A logged-in user with 'viewer' role tries to DELETE /api/users/42.", "code": "403", "explanation": "The server knows the user but the 'viewer' role lacks delete permissions."},
            {"scenario": "An API call sends an expired JWT in the Authorization header.", "code": "401", "explanation": "The credential is present but invalid \u2014 the client needs to re-authenticate."},
        ],
        "quiz": [
            {"scenario": "A mobile app sends a request with no Authorization header to a protected endpoint.", "correct": "401", "wrong": "403"},
            {"scenario": "An authenticated 'free-tier' user tries to access a premium-only endpoint.", "correct": "403", "wrong": "401"},
            {"scenario": "A browser sends a cookie that the server doesn't recognize (e.g., from a different domain).", "correct": "401", "wrong": "403"},
        ],
    },
    {
        "slug": "301-vs-302",
        "codes": ["301", "302"],
        "title": "301 Moved Permanently vs 302 Found",
        "category": "Redirect pairs",
        "tldr": "301 says 'this URL has permanently moved \u2014 update your bookmarks'; 302 says 'temporarily go here, but keep using the original URL'.",
        "decision_tree": [
            {"question": "Is the old URL going away forever?", "yes": "301", "no": "302"},
            {"question": "Should search engines update their index to the new URL?", "yes": "301", "no": "302"},
            {"question": "Might the redirect change or be removed in the future?", "yes": "302", "no": "301"},
        ],
        "examples": [
            {"scenario": "A site moves from http://old-domain.com to https://new-domain.com.", "code": "301", "explanation": "The domain change is permanent \u2014 search engines and browsers should remember the new location."},
            {"scenario": "A user who is not logged in is sent to /login before accessing /dashboard.", "code": "302", "explanation": "Once the user logs in, /dashboard will work directly \u2014 the redirect is temporary."},
            {"scenario": "A company rebrands and /about-acme is now /about-newname forever.", "code": "301", "explanation": "The old path will never serve content again; all link equity should transfer."},
        ],
        "quiz": [
            {"scenario": "An e-commerce site redirects /summer-sale to /deals during July only.", "correct": "302", "wrong": "301"},
            {"scenario": "A blog moves all posts from /blog/YYYY/title to /posts/title permanently.", "correct": "301", "wrong": "302"},
            {"scenario": "A URL shortener (like bit.ly) redirects to the full URL.", "correct": "301", "wrong": "302"},
        ],
    },
    {
        "slug": "307-vs-308",
        "codes": ["307", "308"],
        "title": "307 Temporary Redirect vs 308 Permanent Redirect",
        "category": "Redirect pairs",
        "tldr": "Both preserve the original HTTP method (unlike 301/302 which may change POST to GET); 307 is temporary and 308 is permanent.",
        "decision_tree": [
            {"question": "Should the client use the new URL for all future requests?", "yes": "308", "no": "307"},
            {"question": "Must the HTTP method be preserved (e.g., POST stays POST)?", "yes": "307 or 308", "no": "Consider 301 or 302"},
            {"question": "Is this a permanent URL change?", "yes": "308", "no": "307"},
        ],
        "examples": [
            {"scenario": "An API gateway temporarily routes POST /api/orders to a backup server during maintenance.", "code": "307", "explanation": "The redirect is temporary and the POST method must be preserved so the order data is sent correctly."},
            {"scenario": "An API permanently moves its endpoint from /v1/users to /v2/users and clients POST to it.", "code": "308", "explanation": "The URL change is permanent and the method must remain POST."},
            {"scenario": "A load balancer temporarily sends traffic to a different region during a failover.", "code": "307", "explanation": "Once the primary region recovers, traffic should go back to the original URL."},
        ],
        "quiz": [
            {"scenario": "A POST /api/submit endpoint permanently moves to /api/v2/submit. The body must be re-sent.", "correct": "308", "wrong": "307"},
            {"scenario": "A CDN temporarily reroutes a PUT request to a backup origin.", "correct": "307", "wrong": "308"},
            {"scenario": "A REST API permanently relocates and needs to preserve DELETE requests.", "correct": "308", "wrong": "307"},
        ],
    },
    {
        "slug": "400-vs-422",
        "codes": ["400", "422"],
        "title": "400 Bad Request vs 422 Unprocessable Entity",
        "category": "Client error pairs",
        "tldr": "400 means the request is malformed (bad syntax, unparseable); 422 means the syntax is valid but the content is semantically wrong.",
        "decision_tree": [
            {"question": "Can the server parse the request body at all?", "yes": "422", "no": "400"},
            {"question": "Is the JSON/XML well-formed?", "yes": "422 (if validation fails)", "no": "400"},
            {"question": "Are required fields present but with invalid values?", "yes": "422", "no": "400"},
        ],
        "examples": [
            {"scenario": "A client sends POST /api/users with body: {name: invalid json (missing quotes).", "code": "400", "explanation": "The request body is not valid JSON \u2014 the server cannot even parse it."},
            {"scenario": 'A client sends valid JSON: {"email": "not-an-email", "age": -5}.', "code": "422", "explanation": "The JSON is well-formed but the email format is invalid and age cannot be negative."},
            {"scenario": "A request has a malformed Content-Type header like 'application/jso'.", "code": "400", "explanation": "The request itself is malformed at the HTTP level, not a data validation issue."},
        ],
        "quiz": [
            {"scenario": 'A POST body is valid JSON but the "start_date" is after the "end_date".', "correct": "422", "wrong": "400"},
            {"scenario": "A request body contains truncated XML that cannot be parsed.", "correct": "400", "wrong": "422"},
            {"scenario": 'A valid JSON request is missing the required "email" field.', "correct": "422", "wrong": "400"},
        ],
    },
    {
        "slug": "404-vs-410",
        "codes": ["404", "410"],
        "title": "404 Not Found vs 410 Gone",
        "category": "Client error pairs",
        "tldr": "404 means the resource was not found (it may appear later or may never have existed); 410 means it existed but was deliberately and permanently removed.",
        "decision_tree": [
            {"question": "Did the resource ever exist on this server?", "yes": "Could be 410", "no": "404"},
            {"question": "Was it intentionally and permanently removed?", "yes": "410", "no": "404"},
            {"question": "Might the resource come back at this URL in the future?", "yes": "404", "no": "410"},
        ],
        "examples": [
            {"scenario": "A user requests /blog/post-about-cats but no such post has ever been published.", "code": "404", "explanation": "The resource was never created \u2014 this is a standard not-found."},
            {"scenario": "A company deletes a product page after discontinuing the product.", "code": "410", "explanation": "The page existed but the company intentionally removed it forever. Search engines should de-index it."},
            {"scenario": "A typo in a URL: /usres/42 instead of /users/42.", "code": "404", "explanation": "The path is simply wrong \u2014 no resource was removed."},
        ],
        "quiz": [
            {"scenario": "A social media platform permanently deletes a user's account and all their post URLs.", "correct": "410", "wrong": "404"},
            {"scenario": "A user types /api/v1/prodcuts (typo) in the browser.", "correct": "404", "wrong": "410"},
            {"scenario": "A regulatory requirement forces a company to permanently remove a page.", "correct": "410", "wrong": "404"},
        ],
    },
    {
        "slug": "500-vs-502",
        "codes": ["500", "502"],
        "title": "500 Internal Server Error vs 502 Bad Gateway",
        "category": "Error pairs",
        "tldr": "500 means the server itself encountered an unexpected error; 502 means the server is a proxy/gateway and got an invalid response from an upstream service.",
        "decision_tree": [
            {"question": "Is the server acting as a proxy or gateway?", "yes": "Could be 502", "no": "500"},
            {"question": "Did the error originate in the server's own code?", "yes": "500", "no": "502"},
            {"question": "Did an upstream/backend service return a bad or unintelligible response?", "yes": "502", "no": "500"},
        ],
        "examples": [
            {"scenario": "A Python app raises an unhandled exception in a request handler.", "code": "500", "explanation": "The error is in the application's own code \u2014 no upstream service involved."},
            {"scenario": "Nginx forwards a request to a Node.js backend that returns a garbled response.", "code": "502", "explanation": "The proxy (Nginx) received an invalid response from the upstream (Node.js) service."},
            {"scenario": "A database query fails because the SQL has a bug.", "code": "500", "explanation": "The error is internal to the server's logic, even though a database is involved."},
        ],
        "quiz": [
            {"scenario": "A load balancer receives a connection reset from a crashed backend server.", "correct": "502", "wrong": "500"},
            {"scenario": "An application throws a NullPointerException in its business logic.", "correct": "500", "wrong": "502"},
            {"scenario": "An API gateway gets a malformed HTTP response from a microservice.", "correct": "502", "wrong": "500"},
        ],
    },
    {
        "slug": "500-vs-503",
        "codes": ["500", "503"],
        "title": "500 Internal Server Error vs 503 Service Unavailable",
        "category": "Error pairs",
        "tldr": "500 is an unexpected bug or crash; 503 means the server is temporarily unable to handle requests (overloaded, in maintenance, etc.).",
        "decision_tree": [
            {"question": "Is the server aware it cannot handle requests right now?", "yes": "503", "no": "500"},
            {"question": "Is this a planned maintenance window or expected overload?", "yes": "503", "no": "500"},
            {"question": "Should the client retry later?", "yes": "503 (with Retry-After header)", "no": "500"},
        ],
        "examples": [
            {"scenario": "A server is deployed with a configuration error that crashes every request.", "code": "500", "explanation": "The failure is unexpected \u2014 the server isn't intentionally refusing requests."},
            {"scenario": "A server returns a maintenance page during a scheduled deploy.", "code": "503", "explanation": "The server knows it's temporarily unavailable and can include a Retry-After header."},
            {"scenario": "A server hits its maximum connection pool and starts rejecting new requests.", "code": "503", "explanation": "The server is overloaded but healthy \u2014 it can recover when load decreases."},
        ],
        "quiz": [
            {"scenario": "A website shows a 'We'll be back in 30 minutes' page during planned maintenance.", "correct": "503", "wrong": "500"},
            {"scenario": "A server crashes because of an out-of-memory error in application code.", "correct": "500", "wrong": "503"},
            {"scenario": "A rate limiter at the infrastructure level rejects requests because the server is at capacity.", "correct": "503", "wrong": "500"},
        ],
    },
    {
        "slug": "200-vs-204",
        "codes": ["200", "204"],
        "title": "200 OK vs 204 No Content",
        "category": "Success pairs",
        "tldr": "Both mean success, but 200 includes a response body while 204 intentionally sends no body at all.",
        "decision_tree": [
            {"question": "Does the response need to include data in the body?", "yes": "200", "no": "204"},
            {"question": "Is this a DELETE or PUT that succeeded with nothing to return?", "yes": "204", "no": "200"},
            {"question": "Should the client reset its form/view after the response?", "yes": "Consider 205", "no": "204 if no body needed"},
        ],
        "examples": [
            {"scenario": "GET /api/users returns a list of users in the body.", "code": "200", "explanation": "The request succeeded and there is data to send back to the client."},
            {"scenario": "DELETE /api/users/42 succeeds and there is nothing to return.", "code": "204", "explanation": "The deletion was successful but there is intentionally no response body."},
            {"scenario": "PUT /api/settings updates a preference. The server confirms success but doesn't echo the data back.", "code": "204", "explanation": "The update succeeded; the client already has the data it sent."},
        ],
        "quiz": [
            {"scenario": "A search API returns matching results in the body.", "correct": "200", "wrong": "204"},
            {"scenario": "A 'mark as read' endpoint succeeds with nothing to return.", "correct": "204", "wrong": "200"},
            {"scenario": "An endpoint that accepts a webhook payload and just acknowledges receipt.", "correct": "204", "wrong": "200"},
        ],
    },
    {
        "slug": "302-vs-307",
        "codes": ["302", "307"],
        "title": "302 Found vs 307 Temporary Redirect",
        "category": "Redirect pairs",
        "tldr": "Both are temporary redirects, but 302 may change POST to GET (and often does in practice) while 307 guarantees the HTTP method is preserved.",
        "decision_tree": [
            {"question": "Must the original HTTP method (e.g., POST) be preserved?", "yes": "307", "no": "302 is fine"},
            {"question": "Are you redirecting a form submission or API POST?", "yes": "307", "no": "302"},
            {"question": "Is this a simple browser GET redirect?", "yes": "302", "no": "307 is safer"},
        ],
        "examples": [
            {"scenario": "After login, a user is temporarily redirected from /login to /dashboard via GET.", "code": "302", "explanation": "The redirect is temporary and the method change from POST to GET is actually desired (Post/Redirect/Get pattern)."},
            {"scenario": "An API temporarily reroutes POST /api/orders to a backup server.", "code": "307", "explanation": "The POST body must be re-sent to the new URL \u2014 changing to GET would lose the order data."},
            {"scenario": "A website temporarily redirects /sale to /deals during a promotional period.", "code": "302", "explanation": "It's a simple GET redirect with no method preservation concerns."},
        ],
        "quiz": [
            {"scenario": "A payment gateway temporarily redirects a POST with credit card data to a backup processor.", "correct": "307", "wrong": "302"},
            {"scenario": "A marketing page temporarily redirects to a seasonal landing page.", "correct": "302", "wrong": "307"},
            {"scenario": "An API endpoint temporarily moves and clients must re-send their PUT body to the new location.", "correct": "307", "wrong": "302"},
        ],
    },
    {
        "slug": "502-vs-504",
        "codes": ["502", "504"],
        "title": "502 Bad Gateway vs 504 Gateway Timeout",
        "category": "Error pairs",
        "tldr": "502 means the gateway/proxy received an invalid response from the upstream server; 504 means the upstream server didn't respond in time.",
        "decision_tree": [
            {"question": "Did the upstream server respond at all?", "yes": "502 (bad response)", "no": "504 (no response)"},
            {"question": "Did the proxy/gateway hit a timeout waiting for the upstream?", "yes": "504", "no": "502"},
            {"question": "Was the upstream response received but malformed or unintelligible?", "yes": "502", "no": "504"},
        ],
        "examples": [
            {"scenario": "Nginx proxies a request to a Node.js backend that returns a garbled, unparseable response.", "code": "502", "explanation": "The upstream responded, but its response was invalid \u2014 the proxy can't forward it."},
            {"scenario": "An API gateway waits 30 seconds for a microservice that never responds, then gives up.", "code": "504", "explanation": "The upstream service didn't respond before the gateway's timeout expired."},
            {"scenario": "A load balancer connects to a backend that immediately resets the TCP connection.", "code": "502", "explanation": "The upstream responded with an error (connection reset), not a valid HTTP response."},
        ],
        "quiz": [
            {"scenario": "A reverse proxy tries to reach a backend that is hung in an infinite loop and never sends a response.", "correct": "504", "wrong": "502"},
            {"scenario": "A CDN edge server receives a response from the origin with missing HTTP headers and garbage data.", "correct": "502", "wrong": "504"},
            {"scenario": "A microservice mesh times out after waiting 60 seconds for a downstream service.", "correct": "504", "wrong": "502"},
        ],
    },
    {
        "slug": "401-vs-407",
        "codes": ["401", "407"],
        "title": "401 Unauthorized vs 407 Proxy Authentication Required",
        "category": "Auth pairs",
        "tldr": "401 means the origin server requires authentication; 407 means an intermediate proxy requires authentication before it will forward the request.",
        "decision_tree": [
            {"question": "Is authentication required by the origin server or by a proxy?", "yes": "If proxy: 407; if origin: 401", "no": "Neither applies"},
            {"question": "Does the response include a Proxy-Authenticate header?", "yes": "407", "no": "401"},
            {"question": "Is the client expected to use the Authorization header or Proxy-Authorization header?", "yes": "Authorization \u2192 401; Proxy-Authorization \u2192 407", "no": "Check which layer needs credentials"},
        ],
        "examples": [
            {"scenario": "A user hits a REST API without a Bearer token and gets a WWW-Authenticate challenge.", "code": "401", "explanation": "The origin server needs the client to authenticate \u2014 the WWW-Authenticate header confirms this."},
            {"scenario": "A corporate proxy intercepts a request and demands credentials via Proxy-Authenticate.", "code": "407", "explanation": "The proxy, not the target server, needs authentication before forwarding the request."},
            {"scenario": "An API call fails because the OAuth access token is expired.", "code": "401", "explanation": "The origin server rejected the credential \u2014 the client needs to refresh its token."},
        ],
        "quiz": [
            {"scenario": "A developer's HTTP request is blocked by a company firewall proxy that requires a username and password.", "correct": "407", "wrong": "401"},
            {"scenario": "A mobile app sends a request with no API key to a protected endpoint.", "correct": "401", "wrong": "407"},
            {"scenario": "An enterprise proxy requires NTLM authentication before allowing outbound requests.", "correct": "407", "wrong": "401"},
        ],
    },
    {
        "slug": "204-vs-205",
        "codes": ["204", "205"],
        "title": "204 No Content vs 205 Reset Content",
        "category": "Success pairs",
        "tldr": "Both return no body, but 204 simply means 'success, nothing to send back' while 205 tells the client to reset its document view (e.g., clear a form).",
        "decision_tree": [
            {"question": "Should the client reset its form or UI after the response?", "yes": "205", "no": "204"},
            {"question": "Is this a simple acknowledgement with no UI side-effects?", "yes": "204", "no": "205"},
            {"question": "Does the server want the browser to clear the input fields?", "yes": "205", "no": "204"},
        ],
        "examples": [
            {"scenario": "DELETE /api/users/42 succeeds and the server has nothing to return.", "code": "204", "explanation": "The resource is deleted; there's no body and no need for the client to reset its view."},
            {"scenario": "A form submits feedback and the server wants the browser to clear all form fields.", "code": "205", "explanation": "205 tells the user agent to reset the document that initiated the request \u2014 clearing the form."},
            {"scenario": "A PUT /settings request succeeds and the client already has all the data it sent.", "code": "204", "explanation": "No body is needed and the client should stay on the same view."},
        ],
        "quiz": [
            {"scenario": "A search filter form is submitted and the server wants the browser to clear all filter inputs.", "correct": "205", "wrong": "204"},
            {"scenario": "A 'mark as read' endpoint succeeds with nothing to return.", "correct": "204", "wrong": "205"},
            {"scenario": "A data entry form is submitted and the server instructs the browser to reset for a new entry.", "correct": "205", "wrong": "204"},
        ],
    },
    {
        "slug": "409-vs-412",
        "codes": ["409", "412"],
        "title": "409 Conflict vs 412 Precondition Failed",
        "category": "Client error pairs",
        "tldr": "409 means the request conflicts with the current resource state (e.g., a concurrent edit); 412 means a precondition header (If-Match, If-Unmodified-Since) evaluated to false.",
        "decision_tree": [
            {"question": "Did the client send precondition headers (If-Match, If-None-Match, If-Unmodified-Since)?", "yes": "412 if they fail", "no": "409"},
            {"question": "Is the conflict due to the resource's current state vs. the request's intent?", "yes": "409", "no": "412"},
            {"question": "Is this an optimistic locking / ETag mismatch scenario using conditional headers?", "yes": "412", "no": "409"},
        ],
        "examples": [
            {"scenario": "Two users edit the same document; the second save conflicts with the first's changes.", "code": "409", "explanation": "The resource state has changed in a way that conflicts with the update \u2014 no precondition headers were used."},
            {"scenario": "A PUT request includes If-Match with a stale ETag; the server's current ETag doesn't match.", "code": "412", "explanation": "The If-Match precondition failed \u2014 the resource has been modified since the client last fetched it."},
            {"scenario": "A user tries to create an account with a username that is already taken.", "code": "409", "explanation": "The request conflicts with existing state (duplicate username) \u2014 it's not a precondition header issue."},
        ],
        "quiz": [
            {"scenario": "A client sends PUT with If-Unmodified-Since, but the resource was updated after that timestamp.", "correct": "412", "wrong": "409"},
            {"scenario": "A CI/CD pipeline tries to deploy version 2, but version 3 has already been deployed by another pipeline.", "correct": "409", "wrong": "412"},
            {"scenario": "An API uses ETags for optimistic concurrency and the client's If-Match header doesn't match.", "correct": "412", "wrong": "409"},
        ],
    },
    {
        "slug": "301-vs-308",
        "codes": ["301", "308"],
        "title": "301 Moved Permanently vs 308 Permanent Redirect",
        "category": "Redirect pairs",
        "tldr": "Both are permanent redirects, but 301 may change POST to GET (browsers historically do this) while 308 guarantees the HTTP method is preserved.",
        "decision_tree": [
            {"question": "Must the original HTTP method (e.g., POST) be preserved after the redirect?", "yes": "308", "no": "301 is fine"},
            {"question": "Are you permanently redirecting an API endpoint that receives POST/PUT/DELETE?", "yes": "308", "no": "301"},
            {"question": "Is this a simple permanent redirect of a browser-visited page (GET)?", "yes": "301", "no": "308 is safer"},
        ],
        "examples": [
            {"scenario": "A website permanently moves from /old-page to /new-page and all traffic is GET.", "code": "301", "explanation": "Since it's a GET-only page, method preservation is irrelevant \u2014 301 is the standard choice."},
            {"scenario": "An API permanently moves POST /v1/orders to /v2/orders and clients must keep POSTing.", "code": "308", "explanation": "308 guarantees clients will re-send the POST body to the new URL instead of converting to GET."},
            {"scenario": "A company rebrands its website domain and wants SEO link equity to transfer for all pages.", "code": "301", "explanation": "For a domain-wide redirect of user-facing pages (GET), 301 is universally supported and understood by search engines."},
        ],
        "quiz": [
            {"scenario": "A REST API permanently relocates its POST /api/payments endpoint to a new domain.", "correct": "308", "wrong": "301"},
            {"scenario": "A blog permanently moves all its articles from /blog/ to /articles/ (GET traffic only).", "correct": "301", "wrong": "308"},
            {"scenario": "An endpoint that accepts file uploads via PUT permanently moves to a new path.", "correct": "308", "wrong": "301"},
        ],
    },
    {
        "slug": "503-vs-504",
        "codes": ["503", "504"],
        "title": "503 Service Unavailable vs 504 Gateway Timeout",
        "category": "Error pairs",
        "tldr": "503 means the server itself is temporarily unable to handle requests (overload, maintenance); 504 means a gateway/proxy timed out waiting for an upstream server.",
        "decision_tree": [
            {"question": "Is the server reporting its own unavailability (maintenance, overload)?", "yes": "503", "no": "504"},
            {"question": "Is a proxy or gateway involved, and did it time out waiting for an upstream?", "yes": "504", "no": "503"},
            {"question": "Can the server include a Retry-After header because it knows when it will recover?", "yes": "503", "no": "504 (the gateway doesn't know when the upstream will recover)"},
        ],
        "examples": [
            {"scenario": "A web server returns a maintenance page during a scheduled deploy window.", "code": "503", "explanation": "The server itself is aware it's temporarily unavailable and can suggest a Retry-After time."},
            {"scenario": "An API gateway waits 30 seconds for an upstream service that never responds.", "code": "504", "explanation": "The gateway timed out \u2014 the upstream service didn't respond in time."},
            {"scenario": "A server is overwhelmed by traffic and starts rejecting new connections.", "code": "503", "explanation": "The server recognises it's at capacity \u2014 this is its own state, not a proxy timeout."},
        ],
        "quiz": [
            {"scenario": "A load balancer's connection to a backend microservice times out after 60 seconds.", "correct": "504", "wrong": "503"},
            {"scenario": "A web application enables a maintenance mode flag and rejects all traffic with Retry-After: 3600.", "correct": "503", "wrong": "504"},
            {"scenario": "A reverse proxy gives up after waiting for an unresponsive upstream database service.", "correct": "504", "wrong": "503"},
        ],
    },
]

# Quick lookup by slug
CONFUSION_PAIRS_BY_SLUG = {pair["slug"]: pair for pair in CONFUSION_PAIRS}

# Mapping from status code to list of slugs that involve it
CONFUSION_PAIRS_BY_CODE = {}
for _pair in CONFUSION_PAIRS:
    for _code in _pair["codes"]:
        CONFUSION_PAIRS_BY_CODE.setdefault(_code, []).append(_pair["slug"])

# Ordered list of category names (display order) and pairs grouped by category
CONFUSION_PAIR_CATEGORY_ORDER = [
    "Auth pairs", "Redirect pairs", "Success pairs",
    "Client error pairs", "Error pairs",
]
PAIRS_BY_CATEGORY = {}
for _pair in CONFUSION_PAIRS:
    _cat = _pair.get("category", "Other")
    PAIRS_BY_CATEGORY.setdefault(_cat, []).append(_pair)
