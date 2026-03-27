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
        "eli5": "Imagine texting someone a long message and they reply 'keep going, I'm listening' before you finish. The server is saying 'Yep, send me the rest!'",
        "case_studies": [
            {"api": "cURL / libcurl", "scenario": "cURL sends Expect: 100-continue by default for POST bodies larger than 1024 bytes, waiting for 100 before uploading", "lesson": "Some servers don't support 100 Continue — set a short timeout for the 100 response so uploads don't stall on legacy servers"},
            {"api": "AWS S3", "scenario": "S3 uses Expect: 100-continue for PutObject — if the bucket policy rejects the upload, the client learns immediately without sending the full body", "lesson": "100 Continue saves bandwidth on large uploads to restrictive endpoints — the server can reject before the body is transferred"},
        ],
        "common_mistakes": [
            {"mistake": "Not setting a timeout for the 100 Continue response before sending the body", "consequence": "If the server does not support 100 Continue, the client waits forever. Set a short timeout and send the body anyway if no 100 arrives."},
            {"mistake": "Sending Expect: 100-continue on small request bodies", "consequence": "The round trip waiting for 100 adds latency for no benefit. Only use Expect: 100-continue on large payloads where aborting early saves significant bandwidth."},
        ],
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
        "eli5": "You're talking to your friend through a walkie-talkie, but you both agree to switch to a video call instead. The server is saying 'Sure, let's change how we're talking!'",
        "case_studies": [
            {"api": "Slack / Discord", "scenario": "Real-time messaging apps upgrade HTTP connections to WebSocket with 101, enabling bidirectional push without polling", "lesson": "WebSocket upgrades via 101 are essential for real-time apps — always handle upgrade failures gracefully and fall back to long-polling"},
            {"api": "gRPC (HTTP/2 upgrade)", "scenario": "gRPC clients may use the Upgrade header to switch from HTTP/1.1 to HTTP/2, receiving 101 on success", "lesson": "Protocol upgrades with 101 only apply to HTTP/1.1 — HTTP/2 connections use ALPN at the TLS layer instead"},
        ],
        "common_mistakes": [
            {"mistake": "Not handling WebSocket upgrade failures gracefully", "consequence": "If the server rejects the upgrade, the client may hang or crash. Always implement a fallback to long-polling or server-sent events."},
            {"mistake": "Attempting protocol upgrade over HTTP/2 connections", "consequence": "101 Switching Protocols only works with HTTP/1.1. HTTP/2 uses ALPN during the TLS handshake for protocol negotiation instead."},
        ],
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
        "eli5": "You asked your mom to bake a big cake. She pokes her head out of the kitchen and says 'Still working on it, don't go anywhere!' so you don't think she forgot.",
        "case_studies": [
            {"api": "Microsoft Exchange (WebDAV)", "scenario": "Recursive property searches on deep mailbox folder hierarchies return 102 as a keep-alive signal before the final 207 Multi-Status", "lesson": "102 Processing prevents clients from timing out on long-running WebDAV operations — essential for recursive PROPFIND on large collections"},
            {"api": "Apache mod_dav", "scenario": "Large COPY or MOVE operations on WebDAV collections send 102 interim responses to keep the connection alive", "lesson": "Use 102 only for WebDAV — for REST APIs, prefer 202 Accepted with a polling endpoint for long-running tasks"},
        ],
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
        "eli5": "While a chef is still cooking your main course, the waiter brings you bread and water first so you're not just sitting there waiting. Early hints to get you started!",
        "case_studies": [
            {"api": "Cloudflare", "scenario": "Cloudflare sends 103 Early Hints with Link headers to preload CSS and fonts while the origin server generates the HTML response", "lesson": "103 Early Hints can cut page load times by 100-500ms by letting the browser start fetching critical assets before the full response arrives"},
            {"api": "Shopify", "scenario": "Shopify uses 103 Early Hints to preload storefront CSS and JavaScript, reducing Largest Contentful Paint on merchant sites", "lesson": "Combine 103 with rel=preload for render-blocking resources — the browser starts downloading immediately without waiting for the HTML"},
        ],
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
        "eli5": "You asked for something and got exactly what you wanted. Like asking mom for a cookie and she hands you one right away. Everything worked perfectly!",
        "case_studies": [
            {"api": "Most REST APIs", "scenario": "Standard successful GET response", "lesson": "Always check the body — some APIs return 200 with error objects"},
            {"api": "Stripe", "scenario": "Successful charge returns 200 with charge object", "lesson": "Even a 200 may contain a 'failure_code' field inside the body — always inspect nested status"},
        ],
        "common_mistakes": [
            {
                "mistake": "Returning 200 with an error body like {\"error\": \"not found\"}",
                "consequence": "Monitoring tools won't detect errors. Clients treat it as success and may display broken data.",
            },
            {
                "mistake": "Using 200 for every response and encoding the real status in the JSON body",
                "consequence": "Breaks HTTP caching, proxies, and browser built-in error handling. Clients must parse the body to detect failures.",
            },
        ],
        "dont_use_when": [
            "The request created a new resource — use 201 Created instead",
            "The action was accepted but not yet completed — use 202 Accepted instead",
            "The request succeeded but there is no body to return — use 204 No Content instead",
            "There was an error but you want to hide it in the response body — use the proper 4xx or 5xx code",
        ],
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
        "eli5": "You asked someone to build you a LEGO house, and they did! Now there's a brand new LEGO house that didn't exist before. It was just created, fresh and new!",
        "case_studies": [
            {"api": "GitHub API", "scenario": "Creating a repository returns 201 with the repo object and Location header", "lesson": "Always return the created resource and a Location header so the client knows where to find it"},
            {"api": "Stripe", "scenario": "Creating a customer or subscription returns 201", "lesson": "Idempotency keys prevent duplicate creates — use them with POST/201 flows"},
        ],
        "common_mistakes": [
            {
                "mistake": "Returning 201 without a Location header pointing to the new resource",
                "consequence": "Clients have no way to find the created resource. The Location header is how REST APIs communicate where the new thing lives.",
            },
            {
                "mistake": "Using 201 for idempotent operations that return an existing resource",
                "consequence": "201 means 'created something new.' If the resource already existed, use 200 or 409 instead.",
            },
        ],
        "dont_use_when": [
            "The resource already existed and was returned as-is — use 200 OK instead",
            "The creation is asynchronous and hasn't completed yet — use 202 Accepted instead",
            "A PUT or PATCH updated an existing resource — use 200 OK instead",
            "The request conflicted with an existing resource — use 409 Conflict instead",
        ],
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
        "eli5": "You drop off your clothes at the dry cleaner and they say 'Got it, we'll work on it!' They accepted your stuff, but it's not done yet. Come back later to pick it up.",
        "case_studies": [
            {"api": "Twilio", "scenario": "Sending an SMS returns 202 with a message SID — the message is queued, not yet delivered", "lesson": "Always return a job/resource ID with 202 so clients can poll for completion status"},
            {"api": "AWS S3 Glacier", "scenario": "Initiating a vault retrieval returns 202 — the data takes hours to restore", "lesson": "For long-running operations, 202 with a status URL is far better than blocking the client with a slow 200"},
        ],
        "common_mistakes": [
            {
                "mistake": "Treating 202 as if the operation already completed successfully",
                "consequence": "The operation is only queued, not done. Clients must poll or use webhooks to confirm completion before acting on the result.",
            },
            {
                "mistake": "Returning 202 without a way to check the job status (no Location header or job ID)",
                "consequence": "Clients have no way to find out when the async task finishes. Always include a status URL or job identifier.",
            },
        ],
    },
    "203": {
        "examples": [
            "A proxy modifying response headers or body before forwarding to the client",
            "A CDN returning cached content that may have been transformed from the origin",
            "A middleware stripping internal headers before returning the response",
        ],
        "headers": ["Content-Type: application/json"],
        "code": {
            "python": 'return jsonify(data), 203',
            "node": "res.status(203).json(transformedData);",
            "go": "w.WriteHeader(http.StatusNonAuthoritativeInfo)",
        },
        "eli5": "You asked your friend about yesterday's homework, but they heard it from someone else, not the teacher. The answer is probably right, but it's secondhand information!",
        "case_studies": [
            {"api": "CDN proxies (Cloudflare, Akamai)", "scenario": "CDN edge servers modify response headers (adding X-Cache, removing internal headers) and return 203 to signal the response was transformed", "lesson": "203 warns the client that metadata may have been altered — most clients treat it identically to 200, but security-sensitive apps should verify headers against the origin"},
            {"api": "API gateway middleware", "scenario": "An API gateway strips internal debugging headers before forwarding to external clients, using 203 to indicate the response was modified", "lesson": "In practice, most proxies return 200 instead of 203 even when modifying responses — 203 is technically correct but rarely used"},
        ],
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
        "eli5": "You asked your friend to throw away your drawing, and they did. But they just nod silently — there's nothing to hand back to you because, well, it's gone!",
        "case_studies": [
            {"api": "GitHub API", "scenario": "Successful DELETE returns 204 with no body", "lesson": "If the client needs confirmation details like a timestamp, use 200 with a body instead"},
        ],
        "common_mistakes": [
            {
                "mistake": "Including a response body with 204",
                "consequence": "The HTTP spec says 204 MUST NOT contain a body. Some clients will ignore it; others will break. If you need to send data, use 200.",
            },
            {
                "mistake": "Using 204 when the client needs confirmation details",
                "consequence": "Clients get no feedback about what happened. Use 200 with a body if the client needs to know specifics like a timestamp or ID.",
            },
        ],
        "dont_use_when": [
            "The client needs confirmation details like a timestamp or modified resource — use 200 OK with a body",
            "A new resource was created — use 201 Created with a Location header",
            "The operation is asynchronous — use 202 Accepted with a job status URL",
            "The resource was not found to delete — use 404 Not Found instead",
        ],
    },
    "205": {
        "examples": [
            "A form submission where the server wants the browser to clear the form fields",
            "Resetting a search filter UI after clearing saved filters on the server",
            "A chat app telling the client to clear the message input after sending",
        ],
        "headers": [],
        "code": {
            "python": 'return "", 205',
            "node": "res.status(205).end();",
            "go": "w.WriteHeader(http.StatusResetContent)",
        },
        "eli5": "You turn in your test and the teacher says 'Great, now erase everything on your desk and start fresh.' Time to clear the slate and reset!",
        "case_studies": [
            {"api": "HTML form-based apps", "scenario": "After a successful form POST, the server returns 205 to tell the browser to clear the form fields without navigating away", "lesson": "205 is rarely used in practice — most apps use 303 See Other to redirect after POST, but 205 is ideal for single-page form interactions"},
            {"api": "RESTful search APIs", "scenario": "A POST to /api/filters/reset returns 205 to signal the client to clear cached filter state", "lesson": "Use 205 when the client needs to reset its view without fetching new content — it says 'clear your state' without providing a new document"},
        ],
    },
    "206": {
        "examples": [
            "Streaming a video — the browser requests byte ranges so you can seek without downloading the whole file",
            "Resuming a large file download that was interrupted",
            "A download manager fetching a file in parallel chunks",
        ],
        "headers": ["Content-Range: bytes 0-999/8000", "Accept-Ranges: bytes", "Content-Length: 1000"],
        "code": {
            "python": "# Flask: use send_file with range support or flask-rangeresponse",
            "node": "res.status(206).set('Content-Range', 'bytes 0-999/8000').send(chunk);",
            "go": "http.ServeContent(w, r, name, modtime, content) // handles ranges automatically",
        },
        "eli5": "Like downloading a big file but only getting half now and the rest later. You asked for a piece of the puzzle, and that's exactly what you got — a partial delivery!",
        "case_studies": [
            {"api": "YouTube / Netflix", "scenario": "Video streaming uses Range requests to fetch chunks, allowing seek without downloading the full file", "lesson": "Always return Content-Range and Accept-Ranges headers so clients know how to request subsequent chunks"},
            {"api": "AWS S3", "scenario": "Multipart downloads use Range headers to fetch large objects in parallel chunks", "lesson": "Splitting large downloads into ranges enables parallel fetching and seamless resume after network failures"},
        ],
        "common_mistakes": [
            {
                "mistake": "Returning 206 without a correct Content-Range header",
                "consequence": "Clients cannot determine which part of the resource they received or how to request the next chunk. Download resume and seeking break completely.",
            },
            {
                "mistake": "Returning 200 instead of 206 when the client sent a Range header",
                "consequence": "The client expects a partial response but gets the full file. Download managers and video players will misinterpret the byte offsets.",
            },
        ],
    },
    "207": {
        "examples": [
            "A WebDAV PROPFIND returning status for multiple files in a directory",
            "A batch API where some operations succeed and others fail",
            "CalDAV/CardDAV syncing multiple contacts or events at once",
        ],
        "headers": ["Content-Type: application/xml"],
        "code": {
            "python": 'return multi_status_xml, 207',
            "node": "res.status(207).type('application/xml').send(multiStatusXml);",
            "go": "w.WriteHeader(207) // http.StatusMultiStatus",
        },
        "eli5": "You gave your teacher five homework assignments at once. She hands them back with different grades on each one — some got A's and some got F's. One response, multiple results!",
        "case_studies": [
            {"api": "Microsoft Graph API", "scenario": "Batch endpoint returns 207 with individual status codes for each sub-request in a $batch call", "lesson": "Clients must inspect each sub-response individually — a 207 top-level status does not mean all operations succeeded"},
            {"api": "CalDAV / CardDAV", "scenario": "Syncing multiple calendar events returns 207 with per-item status", "lesson": "Batch APIs should always include per-item error details so clients can retry only the failed items"},
        ],
        "common_mistakes": [
            {"mistake": "Assuming 207 means all sub-operations succeeded", "consequence": "207 only means the server processed multiple operations. Each sub-response has its own status code — some may be errors. Always check every item."},
            {"mistake": "Not including per-item error details in the 207 response", "consequence": "Clients cannot tell which items failed or why. Include individual status codes and error messages for each sub-operation."},
        ],
    },
    "208": {
        "examples": [
            "WebDAV reporting that members of a collection have already been listed in a previous part of the response",
            "Avoiding infinite loops when a DAV binding points to a resource already enumerated",
        ],
        "headers": ["Content-Type: application/xml"],
        "code": {
            "python": 'return already_reported_xml, 208',
            "node": "res.status(208).type('application/xml').send(alreadyReportedXml);",
            "go": "w.WriteHeader(208) // http.StatusAlreadyReported",
        },
        "eli5": "You're taking attendance and you already called someone's name. No need to call it again — 'Already counted!' It avoids repeating information you've already shared.",
        "case_studies": [
            {"api": "WebDAV servers (Apache, Nginx)", "scenario": "Recursive PROPFIND on a collection with DAV bindings returns 208 for already-enumerated members", "lesson": "208 prevents infinite loops when collections reference each other — critical for any recursive directory traversal"},
        ],
    },
    "226": {
        "examples": [
            "A server applying delta encoding — sending only the changes since the client's cached version",
            "Using the A-IM (Accept-Instance-Manipulation) header to request a diff instead of the full resource",
        ],
        "headers": ["IM: feed", "Delta-Base: \"abc123\""],
        "code": {
            "python": 'return delta_content, 226',
            "node": "res.status(226).set('IM', 'feed').send(delta);",
            "go": "w.WriteHeader(226) // http.StatusIMUsed",
        },
        "eli5": "Instead of sending you the whole newspaper again, they just send you the corrections and new articles since yesterday. Only the changes, not the whole thing!",
        "case_studies": [
            {"api": "RSS / Atom feed readers", "scenario": "Feed aggregators use A-IM headers to request only new entries since last fetch, server responds 226", "lesson": "Delta encoding dramatically reduces bandwidth for frequently polled resources like feeds and API lists"},
        ],
    },
    "300": {
        "examples": [
            "A URL that has multiple representations — e.g., a document available in English and French",
            "Content negotiation where the server offers several media types and lets the client choose",
            "A resource available in different formats like JSON, XML, and CSV",
        ],
        "headers": ["Content-Type: application/json", "Location: /resource.en"],
        "code": {
            "python": 'return jsonify({"choices": ["/resource.en", "/resource.fr"]}), 300',
            "node": "res.status(300).json({ choices: ['/resource.en', '/resource.fr'] });",
            "go": 'w.WriteHeader(http.StatusMultipleChoices)',
        },
        "eli5": "You ask for a drink and the waiter says 'We have lemonade, orange juice, AND apple juice — which one do you want?' Multiple options, your pick!",
        "case_studies": [
            {"api": "Content negotiation (RFC 7231)", "scenario": "A multilingual website returns 300 with links to /page.en, /page.fr, and /page.de when the Accept-Language header is ambiguous", "lesson": "300 is rarely used in practice — most servers perform server-driven negotiation and return 200 with the best match instead of asking the client to choose"},
            {"api": "REST API versioning", "scenario": "An API endpoint returns 300 with links to /v1/resource and /v2/resource when no version is specified in the request", "lesson": "Prefer explicit versioning in the URL or Accept header over 300 — most HTTP clients do not handle 300 responses gracefully"},
        ],
        "common_mistakes": [
            {"mistake": "Using 300 when the server should just pick the best representation via content negotiation", "consequence": "Most clients do not know how to handle 300. Use server-driven content negotiation (checking Accept headers) and return 200 with the best match instead."},
            {"mistake": "Not including a Location header pointing to the preferred choice", "consequence": "RFC 7231 recommends including a Location header with the preferred option. Without it, clients must parse the body to find the choices."},
        ],
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
        "eli5": "Your friend moved to a new house — forever! Now every time you want to visit them, you go to the new address. The old house has a sign on the door saying 'We moved to 123 New Street!'",
        "case_studies": [
            {"api": "URL shorteners (bit.ly)", "scenario": "Short URL permanently redirects to destination", "lesson": "Browsers cache 301s aggressively — use 302 if the redirect might change"},
            {"api": "Google Search", "scenario": "Follows 301s and transfers PageRank to the new URL", "lesson": "Use 301 for domain migrations to preserve SEO rankings"},
        ],
        "common_mistakes": [
            {
                "mistake": "Using 301 for temporary moves",
                "consequence": "Browsers cache 301 permanently. Users will never see the original URL again, even after you remove the redirect.",
            },
            {
                "mistake": "Using 301 for POST endpoints",
                "consequence": "Most browsers change POST to GET on 301 redirect, losing the request body. Use 308 to preserve the method.",
            },
        ],
        "dont_use_when": [
            "The redirect is temporary — use 302 Found or 307 Temporary Redirect instead",
            "You need to preserve POST/PUT method across the redirect — use 308 Permanent Redirect instead",
            "You're redirecting after a form submission (PRG pattern) — use 303 See Other instead",
            "The URL shortener destination might change — use 302 to avoid permanent browser caching",
        ],
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
        "eli5": "You go to the toy store but it's closed for painting. There's a note saying 'Go to our other store down the street for today!' Tomorrow they'll be back here though.",
        "case_studies": [
            {"api": "OAuth providers (Google, GitHub)", "scenario": "Redirect to authorization server, then back to callback URL with 302", "lesson": "OAuth flows rely on 302 — using 301 would cause the browser to skip the authorization server on future logins"},
        ],
        "common_mistakes": [
            {
                "mistake": "Using 302 when you mean 301 (permanent redirect)",
                "consequence": "Search engines won't transfer page rank to the new URL. Users keep hitting the old URL, adding latency from the redirect hop.",
            },
            {
                "mistake": "Creating redirect loops (A -> B -> A)",
                "consequence": "Browsers will detect the loop and show an error. Always verify redirect targets don't point back.",
            },
        ],
        "dont_use_when": [
            "The move is permanent — use 301 Moved Permanently for SEO and caching benefits",
            "You need to preserve the POST method — use 307 Temporary Redirect instead (302 may change POST to GET)",
            "You are redirecting after a POST form submission — use 303 See Other (explicit POST-to-GET semantics)",
            "The API endpoint moved permanently and must preserve the method — use 308 Permanent Redirect",
        ],
    },
    "303": {
        "examples": [
            "Redirecting to a confirmation page after a POST form submission (Post/Redirect/Get pattern)",
            "After creating a resource via POST, redirecting to the new resource's GET URL",
            "OAuth callback redirecting the user back to the app after authorization",
        ],
        "headers": ["Location: /order/123/confirmation"],
        "code": {
            "python": "return redirect('/order/123/confirmation', code=303)",
            "node": "res.redirect(303, '/order/123/confirmation');",
            "go": 'http.Redirect(w, r, "/order/123/confirmation", http.StatusSeeOther)',
        },
        "eli5": "You filled out a form and hit submit. The server says 'Thanks! Now go look at this other page to see your results.' It's like being told to check the bulletin board after handing in your test.",
        "case_studies": [
            {"api": "Stripe Checkout", "scenario": "After completing payment via POST, Stripe redirects to success_url with 303 to prevent double charges on refresh", "lesson": "Post/Redirect/Get (PRG) with 303 prevents duplicate form submissions — always redirect after a state-changing POST"},
            {"api": "OAuth 2.0 flows", "scenario": "Authorization server redirects back to the client callback with 303 after user consent", "lesson": "303 explicitly converts POST to GET, making it the correct choice for PRG patterns unlike the ambiguous 302"},
        ],
        "common_mistakes": [
            {
                "mistake": "Using 303 to redirect non-POST requests like GET or HEAD",
                "consequence": "303 is designed for Post/Redirect/Get. For GET-to-GET redirects, use 302 or 307. Using 303 for GET is technically valid but confusing and unconventional.",
            },
            {
                "mistake": "Using 302 instead of 303 after a POST form submission",
                "consequence": "302 does not guarantee the browser will switch to GET. 303 explicitly says 'use GET to fetch the redirect target,' which is exactly what PRG needs.",
            },
        ],
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
        "eli5": "You ask your teacher 'Did the homework change since yesterday?' and the teacher says 'Nope, same as before!' So you just use the copy you already have.",
        "case_studies": [
            {"api": "CDNs (Cloudflare, Fastly)", "scenario": "Browser sends If-None-Match with ETag, CDN responds 304", "lesson": "ETags and If-None-Match save bandwidth dramatically for static assets — always enable them"},
            {"api": "GitHub API", "scenario": "Conditional requests with If-None-Match don't count against rate limits", "lesson": "Use conditional requests to reduce API rate limit consumption on frequently polled endpoints"},
        ],
        "common_mistakes": [
            {
                "mistake": "Including a body in a 304 response",
                "consequence": "304 MUST NOT contain a body. The whole point is to save bandwidth. Sending a body defeats the purpose and may confuse clients.",
            },
            {
                "mistake": "Sending 304 without proper ETag or Last-Modified headers",
                "consequence": "Clients have no way to validate their cache. They may serve stale content forever or never cache at all.",
            },
        ],
    },
    "305": {
        "examples": [
            "A server telling the client it must access the resource through a specific proxy",
            "Corporate networks requiring requests to go through an internal proxy for certain resources",
        ],
        "headers": ["Location: http://proxy.example.com:8080"],
        "code": {
            "python": 'return "", 305, {"Location": "http://proxy.example.com:8080"}',
            "node": "res.status(305).set('Location', 'http://proxy.example.com:8080').end();",
            "go": '// Deprecated — most clients ignore 305 for security reasons',
        },
        "eli5": "You want to talk to the principal, but the secretary says 'You can't go directly — you have to go through your teacher first.' You need a middleman to get there.",
        "case_studies": [
            {"api": "Legacy corporate proxies", "scenario": "Internal network appliances returned 305 to force clients through a caching proxy for bandwidth management and content filtering", "lesson": "305 is deprecated and ignored by modern browsers due to security concerns — an attacker could redirect traffic through a malicious proxy"},
            {"api": "Squid proxy (historical)", "scenario": "Squid's access controls once used 305 to redirect clients to an authenticated proxy endpoint before allowing external access", "lesson": "Use explicit proxy configuration (PAC files or WPAD) instead of 305 — no modern client honors this status code"},
        ],
    },
    "306": {
        "examples": [
            "Originally meant for 'Switch Proxy' — telling the client to use a different proxy for subsequent requests",
            "No longer used in practice; reserved in the HTTP spec as a historical artifact",
        ],
        "headers": [],
        "code": {
            "python": "# 306 is unused/reserved — don't return it in production",
            "node": "// 306 is reserved and no longer used",
            "go": "// 306 Switch Proxy is deprecated and unused",
        },
        "eli5": "This is like an old phone number that's been disconnected and nobody uses anymore. It was reserved for something once, but now it just sits there collecting dust.",
        "case_studies": [
            {"api": "HTTP/1.1 spec (RFC 7231)", "scenario": "306 was defined in an earlier HTTP draft for Switch Proxy but was removed before the final RFC — it remains reserved to prevent reuse", "lesson": "306 is a historical curiosity — never return it in production code, but knowing it exists helps understand why the spec jumps from 305 to 307"},
            {"api": "Security scanners (Nessus, Burp Suite)", "scenario": "Penetration testing tools flag 306 responses as anomalous since no legitimate server should return this deprecated code", "lesson": "If you see 306 in the wild, it likely indicates a misconfigured or custom server — investigate immediately as it suggests non-standard behavior"},
        ],
    },
    "307": {
        "examples": [
            "HSTS (HTTP Strict Transport Security) redirecting HTTP to HTTPS while preserving the request method",
            "Temporarily redirecting a POST request — unlike 302, the client must keep using POST",
            "An API endpoint temporarily moved but the client should resend with the same method and body",
        ],
        "headers": ["Location: https://example.com/api/resource"],
        "code": {
            "python": "return redirect('/new-endpoint', code=307)",
            "node": "res.redirect(307, '/new-endpoint');",
            "go": 'http.Redirect(w, r, "/new-endpoint", http.StatusTemporaryRedirect)',
        },
        "eli5": "The toy store is closed for painting today and there's a note saying 'Go to our other store for now!' But unlike 302, you have to go there doing exactly the same thing you were doing — if you were carrying a package, keep carrying it!",
        "case_studies": [
            {"api": "HSTS (all major browsers)", "scenario": "Browsers internally redirect HTTP to HTTPS with 307 via HSTS, preserving the original request method and body", "lesson": "HSTS 307 redirects happen inside the browser before the request leaves — no round trip to the server needed"},
            {"api": "Stripe API", "scenario": "Temporary endpoint migration uses 307 to preserve POST body during payment processing", "lesson": "Use 307 instead of 302 when redirecting POST/PUT/PATCH requests — 302 may silently convert to GET and drop the body"},
        ],
        "common_mistakes": [
            {
                "mistake": "Using 307 when the move is permanent",
                "consequence": "Clients will keep checking the original URL every time. Use 308 for permanent method-preserving redirects.",
            },
            {
                "mistake": "Using 302 instead of 307 for POST redirects",
                "consequence": "302 lets browsers change POST to GET, losing the request body. 307 guarantees the method is preserved.",
            },
        ],
        "dont_use_when": [
            "The move is permanent — use 308 Permanent Redirect to preserve the method permanently",
            "You want the client to switch to GET — use 303 See Other for explicit method change semantics",
            "The resource has not moved but the client needs to re-authenticate — use 401 Unauthorized instead",
            "You are doing a permanent domain migration — use 301 to signal search engines to update their indexes",
        ],
    },
    "308": {
        "examples": [
            "Permanently moving an API endpoint while preserving the HTTP method (POST stays POST)",
            "Google APIs using 308 for resumable upload redirects",
            "A REST API changing its URL structure permanently but needing to keep POST/PUT intact",
        ],
        "headers": ["Location: https://api.example.com/v2/resource"],
        "code": {
            "python": "return redirect('/v2/resource', code=308)",
            "node": "res.redirect(308, '/v2/resource');",
            "go": 'http.Redirect(w, r, "/v2/resource", http.StatusPermanentRedirect)',
        },
        "eli5": "The store you used to go to moved permanently to a new address — and whatever you were doing when you walked in, keep doing it the same way at the new place. Update your bookmark!",
        "case_studies": [
            {"api": "Google APIs", "scenario": "Resumable uploads use 308 to redirect to the upload URI while preserving the PUT method and partial body", "lesson": "308 is the permanent equivalent of 307 — the client should update its bookmarks AND preserve the method"},
            {"api": "YouTube Data API", "scenario": "Resumable video uploads return 308 with Range header indicating bytes received so far", "lesson": "308 in Google's upload protocol means 'resume incomplete' — always check the Range header to know where to continue"},
        ],
        "common_mistakes": [
            {
                "mistake": "Using 301 instead of 308 when the redirect must preserve the HTTP method",
                "consequence": "301 allows browsers to change POST to GET, losing the request body. 308 guarantees the method and body are preserved on permanent redirects.",
            },
            {
                "mistake": "Confusing 308 with 307 — using 308 for temporary redirects",
                "consequence": "308 is permanent; browsers and search engines cache it like 301. If the redirect might change, use 307 (temporary) instead.",
            },
        ],
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
        "eli5": "You tried to order a pizza but said 'I want a pizza with blarghhh topping.' The pizza place doesn't understand what you're asking for because it doesn't make sense!",
        "case_studies": [
            {"api": "Stripe", "scenario": "Invalid card number or missing required field returns 400 with detailed error object", "lesson": "Include machine-readable error codes alongside human-readable messages so clients can programmatically handle specific failures"},
            {"api": "Slack API", "scenario": "Malformed JSON or missing token returns 400", "lesson": "Validate request bodies early and return clear error messages — don't let bad data reach your business logic"},
        ],
        "common_mistakes": [
            {
                "mistake": "Using 400 as a catch-all for any client error",
                "consequence": "Hides the real issue. Use 401, 403, 404, 409, 422 etc. for specific problems so clients can react appropriately.",
            },
            {
                "mistake": "Returning 400 without explaining what was wrong",
                "consequence": "Clients have no idea how to fix their request. Always include a clear error message or validation details.",
            },
        ],
        "dont_use_when": [
            "The user is not authenticated — use 401 Unauthorized instead",
            "The user is authenticated but lacks permission — use 403 Forbidden instead",
            "The request is well-formed but fails business validation — use 422 Unprocessable Entity instead",
            "The requested resource doesn't exist — use 404 Not Found instead",
        ],
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
        "eli5": "You try to walk into a secret clubhouse, but the guard says 'What's the password?' You don't know it, so you can't come in. Tell them who you are first!",
        "case_studies": [
            {"api": "GitHub API", "scenario": "Missing or expired OAuth token returns 401 with WWW-Authenticate header", "lesson": "Implement token refresh flows so users don't have to re-login constantly"},
            {"api": "AWS S3", "scenario": "Expired or invalid signature returns 401", "lesson": "Clock skew between client and server is a common cause of surprise 401s — sync NTP"},
        ],
        "common_mistakes": [
            {
                "mistake": "Using 401 when the user IS authenticated but lacks permission",
                "consequence": "That's 403. 401 means 'not authenticated at all' and should trigger a login prompt.",
            },
            {
                "mistake": "Returning 401 without the WWW-Authenticate header",
                "consequence": "The HTTP spec requires WWW-Authenticate with 401. Without it, clients don't know what auth scheme to use.",
            },
        ],
        "dont_use_when": [
            "The user IS authenticated but lacks permission — use 403 Forbidden instead",
            "The user's subscription or payment expired — use 402 Payment Required instead",
            "You want to hide the resource's existence from unauthenticated users — use 404 Not Found instead",
            "The user is rate limited — use 429 Too Many Requests instead",
        ],
    },
    "402": {
        "examples": [
            "A SaaS API returning this when the user's subscription has expired",
            "Hitting a paywall on a news site or content platform",
            "Stripe or payment APIs indicating a payment is required before proceeding",
        ],
        "headers": ["Content-Type: application/json"],
        "code": {
            "python": 'return jsonify({"error": "Payment required"}), 402',
            "node": "res.status(402).json({ error: 'Payment required' });",
            "go": 'http.Error(w, "Payment Required", http.StatusPaymentRequired)',
        },
        "eli5": "You walk into an arcade and try to play a game, but the machine says 'INSERT COIN.' You gotta pay first before you can play!",
        "case_studies": [
            {"api": "Stripe API", "scenario": "Stripe uses 402 when a payment fails during checkout — the response body contains detailed decline codes for the client to display", "lesson": "Include machine-readable decline codes and human-readable messages so the client can show appropriate next steps like 'try another card'"},
            {"api": "SaaS APIs (Slack, GitHub)", "scenario": "GitHub returns 402 when a repository feature requires a paid plan upgrade", "lesson": "402 was originally reserved for future use but is now widely adopted for paywall and subscription enforcement — include an upgrade URL in the response"},
        ],
        "common_mistakes": [
            {"mistake": "Using 402 as a generic 'access denied' instead of specifically for payment issues", "consequence": "Clients and monitoring tools interpret 402 as a billing problem. Using it for non-payment access control confuses automated retry logic and billing dashboards."},
            {"mistake": "Not including upgrade URL or pricing information in the 402 response body", "consequence": "Users hit a paywall with no way forward. Include a link to the pricing page or upgrade endpoint so they can resolve the issue without contacting support."},
        ],
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
        "eli5": "The guard at the clubhouse knows exactly who you are, but says 'Sorry, you're not allowed in the VIP room.' You can see the door, but you're just not on the list!",
        "case_studies": [
            {"api": "AWS IAM", "scenario": "IAM policy denies access to an S3 bucket", "lesson": "Return enough context for the user to know which permission they need — 'Access Denied' alone is frustrating to debug"},
            {"api": "GitHub API", "scenario": "Trying to push to a repo you can only read returns 403", "lesson": "Distinguish 403 from 404 carefully — 403 confirms the resource exists, which may be a security leak"},
        ],
        "common_mistakes": [
            {
                "mistake": "Using 403 to hide the existence of a resource",
                "consequence": "Use 404 instead if you don't want to confirm the resource exists. 403 reveals that something is there but guarded.",
            },
            {
                "mistake": "Confusing 403 with 401",
                "consequence": "401 means 'who are you?' (not authenticated). 403 means 'I know who you are, but you can't do this' (not authorized).",
            },
        ],
        "dont_use_when": [
            "The user is not authenticated at all — use 401 Unauthorized instead",
            "You want to hide that the resource exists — use 404 Not Found to avoid leaking information",
            "The content is blocked for legal reasons — use 451 Unavailable For Legal Reasons instead",
            "The user's request is malformed — use 400 Bad Request instead",
        ],
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
        "eli5": "Imagine you ask the librarian for a book, but that book doesn't exist in the library. The librarian shrugs and says 'Sorry, never heard of it!'",
        "case_studies": [
            {"api": "Twitter/X API", "scenario": "Requesting a deleted tweet returns 404", "lesson": "Consider using 410 Gone if the resource was deliberately deleted — it tells clients to stop looking"},
            {"api": "REST APIs generally", "scenario": "GET /users/12345 when user doesn't exist", "lesson": "Return a structured error body with 404 — just the status code alone doesn't help the caller understand what was missing"},
        ],
        "common_mistakes": [
            {
                "mistake": "Returning 404 for validation errors",
                "consequence": "Clients can't distinguish 'URL wrong' from 'resource doesn't exist.' Use 400 or 422 for validation failures.",
            },
            {
                "mistake": "Returning a 200 with a 'not found' message instead of 404",
                "consequence": "Search engines index the error page as real content. Monitoring misses the failure. Use the proper status code.",
            },
        ],
        "dont_use_when": [
            "The resource existed before but was permanently deleted — use 410 Gone instead",
            "The user lacks permission to access the resource — use 403 Forbidden (or 404 to hide existence)",
            "The URL is valid but the HTTP method is wrong — use 405 Method Not Allowed instead",
            "The user is not authenticated — use 401 Unauthorized instead",
        ],
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
        "eli5": "You try to open a door by pushing, but there's a big sign that says 'PULL ONLY.' The door is right there, but you're doing it the wrong way!",
        "case_studies": [
            {"api": "REST APIs generally", "scenario": "POST to a read-only collection endpoint", "lesson": "Always include the Allow header so clients know which methods are accepted"},
        ],
        "common_mistakes": [
            {
                "mistake": "Returning 405 without the Allow header listing valid methods",
                "consequence": "The HTTP spec requires the Allow header with 405. Without it, clients must guess which methods are supported.",
            },
            {
                "mistake": "Confusing 405 with 404",
                "consequence": "405 means the URL exists but the method is wrong. 404 means the URL itself doesn't exist. The distinction matters for debugging.",
            },
        ],
    },
    "406": {
        "examples": [
            "Requesting application/xml from an API that only serves JSON",
            "Sending an Accept header the server can't satisfy",
            "A client asking for a language the server doesn't support via Accept-Language",
        ],
        "headers": ["Content-Type: application/json"],
        "code": {
            "python": 'return jsonify({"error": "Not Acceptable"}), 406',
            "node": "res.status(406).json({ error: 'Not Acceptable' });",
            "go": 'http.Error(w, "Not Acceptable", http.StatusNotAcceptable)',
        },
        "eli5": "You go to an Italian restaurant and ask for sushi. They say 'Sorry, we only have pasta and pizza!' You asked for something they just can't serve you in that format.",
        "case_studies": [
            {"api": "GitHub API", "scenario": "Requesting an unsupported media type via Accept header returns 406", "lesson": "Document your supported media types clearly — most APIs support application/json but may also offer XML, CSV, or protocol buffers"},
            {"api": "Content negotiation (RFC 7231)", "scenario": "A client sends Accept: application/xml to a JSON-only endpoint", "lesson": "Return a 406 with a body listing supported types so the client knows what formats are available"},
        ],
        "common_mistakes": [
            {
                "mistake": "Returning the response in a different content type anyway instead of returning 406",
                "consequence": "Clients explicitly asked for a format they can parse. Ignoring the Accept header and returning a different type may cause parse failures.",
            },
            {
                "mistake": "Not listing the supported content types in the 406 response body",
                "consequence": "Clients receive 'Not Acceptable' but have no idea which formats ARE available. Include a list of supported media types.",
            },
        ],
    },
    "407": {
        "examples": [
            "A corporate proxy requiring authentication before allowing outbound requests",
            "Squid or other forward proxies demanding credentials",
        ],
        "headers": ["Proxy-Authenticate: Basic realm=\"proxy\""],
        "code": {
            "python": 'return "", 407, {"Proxy-Authenticate": "Basic"}',
            "node": "res.status(407).set('Proxy-Authenticate', 'Basic').end();",
            "go": 'w.Header().Set("Proxy-Authenticate", "Basic")\nhttp.Error(w, "Proxy Auth Required", 407)',
        },
        "eli5": "There's a security guard at the gate between you and the building. Even before you get to the front door, the guard says 'Show me YOUR ID first!' The middleman needs to know who you are.",
        "case_studies": [
            {"api": "Squid proxy", "scenario": "Corporate networks using Squid require NTLM or Basic proxy auth before any outbound HTTP traffic is allowed", "lesson": "407 is from the proxy, not the origin server — debug by checking proxy logs, not application logs"},
            {"api": "Charles / Fiddler (debugging proxies)", "scenario": "Developer debugging proxies return 407 when configured with authentication, confusing developers who forget the proxy is intercepting", "lesson": "If you see 407 in development, check if a debugging proxy (Charles, Fiddler, mitmproxy) is running with auth enabled"},
        ],
        "common_mistakes": [
            {"mistake": "Confusing 407 (proxy auth) with 401 (origin auth) and debugging the wrong server", "consequence": "Developers waste hours debugging their application server when the 407 is coming from a corporate proxy. Check the response headers — 407 uses Proxy-Authenticate, not WWW-Authenticate."},
            {"mistake": "Not handling 407 in HTTP client libraries that go through corporate proxies", "consequence": "Applications work in development but fail in corporate environments. Configure proxy credentials in your HTTP client or environment variables (HTTP_PROXY, HTTPS_PROXY)."},
        ],
    },
    "408": {
        "examples": [
            "A client opens a connection but takes too long to send the request",
            "A slow mobile client on a flaky network that doesn't finish sending headers in time",
            "Server closing an idle keep-alive connection that sat too long without a new request",
        ],
        "headers": ["Connection: close"],
        "code": {
            "python": 'return jsonify({"error": "Request Timeout"}), 408',
            "node": "res.status(408).json({ error: 'Request Timeout' });",
            "go": 'http.Error(w, "Request Timeout", http.StatusRequestTimeout)',
        },
        "eli5": "You called your friend on the phone, they picked up, but then you just sat there saying nothing for a really long time. Eventually they said 'Hello?? I'm hanging up!' and hung up.",
        "case_studies": [
            {"api": "AWS ELB", "scenario": "Load balancer closes idle connections after 60 seconds of inactivity with 408", "lesson": "Configure client-side keep-alive intervals shorter than the server/LB idle timeout to prevent surprise 408s"},
            {"api": "Cloudflare", "scenario": "Cloudflare returns 408 when the client takes too long to send the complete request headers or body", "lesson": "Slow clients on mobile networks often trigger 408s — consider increasing timeouts for upload-heavy endpoints"},
        ],
        "common_mistakes": [
            {
                "mistake": "Confusing 408 (Request Timeout) with 504 (Gateway Timeout)",
                "consequence": "408 means the client was too slow sending the request. 504 means the upstream server was too slow responding. Different root cause, different fix.",
            },
            {
                "mistake": "Not including Connection: close with 408 responses",
                "consequence": "The server should close the connection after 408. Leaving it open can cause the client to send more requests on a stale connection.",
            },
        ],
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
        "eli5": "Two people tried to edit the same document at the same time and now there's a conflict about whose changes to keep. It's like two kids grabbing the last toy at the same time!",
        "case_studies": [
            {"api": "Git hosting (GitHub/GitLab)", "scenario": "Merge conflict when pushing a branch that diverged", "lesson": "Use ETags or version numbers with conditional requests (If-Match) to detect conflicts before they happen"},
            {"api": "Kubernetes API", "scenario": "Concurrent edits to the same resource return 409 with resourceVersion mismatch", "lesson": "Optimistic concurrency with resource versions avoids locking while still preventing lost updates"},
        ],
        "common_mistakes": [
            {
                "mistake": "Using 400 instead of 409 for duplicate resource conflicts",
                "consequence": "400 means the request syntax is wrong. 409 tells the client the request was valid but conflicts with the current state.",
            },
            {
                "mistake": "Not explaining how to resolve the conflict in the response body",
                "consequence": "Clients get 'conflict' but don't know what conflicted or how to fix it. Include the conflicting field or resource version.",
            },
        ],
        "dont_use_when": [
            "The request body itself is malformed — use 400 Bad Request instead",
            "The resource simply doesn't exist — use 404 Not Found instead",
            "The request fails validation rules — use 422 Unprocessable Entity instead",
            "The client needs to retry with different credentials — use 401 or 403 instead",
        ],
    },
    "410": {
        "examples": [
            "An API endpoint that was intentionally removed and won't come back",
            "A social media post that was permanently deleted",
            "A deprecated API version that has been shut down",
        ],
        "headers": [],
        "code": {
            "python": "abort(410)",
            "node": "res.status(410).json({ error: 'Gone' });",
            "go": 'http.Error(w, "Gone", http.StatusGone)',
        },
        "eli5": "The toy you wanted isn't just out of stock — the store stopped making it forever. It's gone and it's never coming back. Time to find a different toy!",
        "case_studies": [
            {"api": "Twitter/X API", "scenario": "Deleted tweets return 410 Gone instead of 404 to signal permanent removal", "lesson": "Use 410 instead of 404 when a resource was deliberately deleted — search engines and clients will stop requesting it"},
            {"api": "Google APIs (deprecated endpoints)", "scenario": "Sunset API versions return 410 with a Sunset header pointing to the migration guide", "lesson": "Pair 410 with a response body explaining the replacement — clients need to know where to go next"},
        ],
        "common_mistakes": [
            {
                "mistake": "Using 410 for temporarily unavailable resources",
                "consequence": "410 means gone forever. Search engines and clients will remove it from their indexes. Use 404 if the resource might come back.",
            },
            {
                "mistake": "Not setting proper cache headers with 410 responses",
                "consequence": "Without Cache-Control, some clients may keep re-checking the URL. Set a long cache TTL since the resource is permanently gone.",
            },
        ],
    },
    "411": {
        "examples": [
            "Sending a POST/PUT request without a Content-Length header",
            "A server or proxy that requires Content-Length and rejects chunked transfer encoding",
        ],
        "headers": [],
        "code": {
            "python": 'return jsonify({"error": "Length Required"}), 411',
            "node": "res.status(411).json({ error: 'Length Required' });",
            "go": 'http.Error(w, "Length Required", http.StatusLengthRequired)',
        },
        "eli5": "You're sending a package but you forgot to write how heavy it is on the label. The post office says 'We need to know the size before we accept it!'",
        "case_studies": [
            {"api": "AWS S3 (older SDKs)", "scenario": "Older AWS SDK versions sent PUT requests with chunked encoding — S3 rejected them with 411 because it requires Content-Length for integrity verification", "lesson": "Always include Content-Length for PUT/POST requests to storage services — chunked encoding may not be supported by all intermediaries"},
            {"api": "Nginx (proxy_request_buffering off)", "scenario": "When Nginx has request buffering disabled, upstream servers may reject requests without Content-Length, returning 411", "lesson": "If your reverse proxy strips Content-Length for streaming, ensure your backend can handle chunked encoding or re-enable buffering"},
        ],
    },
    "412": {
        "examples": [
            "Using If-Match with an ETag that no longer matches — the resource was modified",
            "Conditional update failing because If-Unmodified-Since check didn't pass",
            "Optimistic concurrency control rejecting a stale update",
        ],
        "headers": ["ETag: \"current-etag\""],
        "code": {
            "python": 'return jsonify({"error": "Precondition Failed"}), 412',
            "node": "res.status(412).json({ error: 'Precondition Failed' });",
            "go": 'http.Error(w, "Precondition Failed", http.StatusPreconditionFailed)',
        },
        "eli5": "You said 'I'll only trade my card if you still have the same one from last week.' But they already traded it away, so the deal's off. Your condition wasn't met!",
        "case_studies": [
            {"api": "GitHub API", "scenario": "Conditional update with If-Match fails because the resource was modified since last read — returns 412", "lesson": "412 is the backbone of optimistic concurrency — always return the current ETag so the client can retry with fresh data"},
            {"api": "AWS S3", "scenario": "PUT with If-None-Match: * returns 412 if the object already exists, preventing overwrites", "lesson": "Use If-None-Match: * with PUT to implement create-if-not-exists semantics without race conditions"},
        ],
        "common_mistakes": [
            {
                "mistake": "Using the wrong ETag format (forgetting quotes or using weak ETags with If-Match)",
                "consequence": "If-Match requires strong ETags. Weak ETags (W/\"...\") are only for If-None-Match. Mismatched ETag formats cause unexpected 412 failures.",
            },
            {
                "mistake": "Returning 412 without including the current ETag in the response",
                "consequence": "The client knows their precondition failed but has no way to get the current version. Always include the latest ETag so they can retry.",
            },
        ],
    },
    "413": {
        "examples": [
            "Uploading a file that exceeds the server's size limit",
            "Sending a JSON body larger than the API allows",
            "Nginx returning this when client_max_body_size is exceeded",
        ],
        "headers": ["Retry-After: 3600"],
        "code": {
            "python": "# Flask: set MAX_CONTENT_LENGTH = 16 * 1024 * 1024",
            "node": "// Express: app.use(express.json({ limit: '10mb' }))",
            "go": 'http.Error(w, "Request Entity Too Large", http.StatusRequestEntityTooLarge)',
        },
        "eli5": "You tried to stuff a giant teddy bear into a tiny mailbox. The mailbox says 'That's way too big! Bring something smaller!'",
        "case_studies": [
            {"api": "Nginx", "scenario": "Nginx returns 413 when the request body exceeds client_max_body_size, which defaults to 1MB — a frequent surprise for file upload endpoints", "lesson": "Always configure client_max_body_size explicitly and return the limit in the error body so clients know what size is acceptable"},
            {"api": "AWS API Gateway", "scenario": "API Gateway enforces a 10MB payload limit and returns 413 for Lambda proxy integrations that exceed it", "lesson": "For large payloads, use presigned S3 upload URLs instead of passing data through API Gateway — it avoids the 10MB hard limit entirely"},
        ],
        "common_mistakes": [
            {"mistake": "Not telling the client what the size limit is in the error response", "consequence": "Clients know the body was too big but not how big is allowed. Include the maximum allowed size so they can resize and retry."},
            {"mistake": "Returning 413 for requests that could be split into smaller chunks", "consequence": "Consider supporting chunked uploads or multipart uploads for large files instead of hard-rejecting with 413."},
        ],
    },
    "414": {
        "examples": [
            "A search query with so many parameters the URL exceeds the server's limit",
            "Accidentally putting a huge base64 blob in a GET query string",
            "Browsers or servers rejecting URLs longer than ~8KB",
        ],
        "headers": [],
        "code": {
            "python": 'return jsonify({"error": "URI Too Long"}), 414',
            "node": "res.status(414).json({ error: 'URI Too Long' });",
            "go": 'http.Error(w, "URI Too Long", http.StatusRequestURITooLong)',
        },
        "eli5": "You wrote an address on an envelope that's so long it wraps around the whole package three times. The postal worker says 'This address is way too long, I can't read this!'",
        "common_mistakes": [
            {"mistake": "Putting large data payloads in query strings instead of using POST with a body", "consequence": "GET URLs have practical limits (~8KB). Use POST for large search queries, filter parameters, or data payloads to avoid 414 errors."},
            {"mistake": "Encoding large JSON or base64 data directly in the URL", "consequence": "URLs are not designed for large data transfer. Use request body for payloads and pass only identifiers or short keys in the URL."},
        ],
    },
    "415": {
        "examples": [
            "Sending text/plain to an endpoint that only accepts application/json",
            "Uploading a .exe file to an endpoint that only accepts images",
            "Missing Content-Type header on a POST request with a body",
        ],
        "headers": ["Accept: application/json"],
        "code": {
            "python": 'return jsonify({"error": "Unsupported Media Type"}), 415',
            "node": "res.status(415).json({ error: 'Unsupported Media Type' });",
            "go": 'http.Error(w, "Unsupported Media Type", http.StatusUnsupportedMediaType)',
        },
        "eli5": "You handed in your homework written in crayon on a napkin, but the teacher only accepts typed papers. 'I can't grade this — wrong format!'",
        "case_studies": [
            {"api": "Slack API", "scenario": "Sending form-urlencoded data to an endpoint expecting application/json returns 415", "lesson": "Always set the Content-Type header explicitly — many HTTP clients default to form encoding, not JSON"},
            {"api": "AWS API Gateway", "scenario": "Uploading a binary file without the correct Content-Type mapping returns 415", "lesson": "Configure binary media types in API Gateway when accepting file uploads — the default only allows text-based content types"},
        ],
        "common_mistakes": [
            {
                "mistake": "Not checking the Content-Type header at all and just trying to parse the body",
                "consequence": "Parsing XML as JSON (or vice versa) causes cryptic errors deep in your code. Validate Content-Type early and return 415 immediately if unsupported.",
            },
            {
                "mistake": "Accepting any Content-Type silently instead of validating it",
                "consequence": "Clients may accidentally send the wrong format and get confusing 500 errors. An explicit 415 tells them exactly what to fix.",
            },
        ],
    },
    "416": {
        "examples": [
            "Requesting bytes 9000-9999 of a file that's only 5000 bytes long",
            "A broken download resumption sending an invalid Range header",
            "A video player seeking past the end of a file",
        ],
        "headers": ["Content-Range: bytes */5000"],
        "code": {
            "python": 'return "", 416, {"Content-Range": "bytes */5000"}',
            "node": "res.status(416).set('Content-Range', 'bytes */5000').end();",
            "go": 'http.Error(w, "Range Not Satisfiable", http.StatusRequestedRangeNotSatisfiable)',
        },
        "eli5": "You asked for pages 500 through 600 of a book that only has 200 pages. The librarian says 'Those pages don't exist!'",
        "common_mistakes": [
            {"mistake": "Not including Content-Range: bytes */total_size in the 416 response", "consequence": "The client knows the range was invalid but not what the valid range is. Include the total file size so the client can adjust its request."},
            {"mistake": "Returning 200 with the full file instead of 416 when the range is invalid", "consequence": "Download managers and video players expect 416 for out-of-range requests. Sending 200 with the full file wastes bandwidth and confuses range-aware clients."},
        ],
    },
    "417": {
        "examples": [
            "Sending Expect: 100-continue but the server doesn't support that expectation",
            "A proxy rejecting an Expect header it can't fulfill",
        ],
        "headers": [],
        "code": {
            "python": 'return jsonify({"error": "Expectation Failed"}), 417',
            "node": "res.status(417).json({ error: 'Expectation Failed' });",
            "go": 'http.Error(w, "Expectation Failed", http.StatusExpectationFailed)',
        },
        "eli5": "You told the bouncer 'I expect VIP treatment when I walk in.' The bouncer says 'Nope, can't promise that.' Your expectations didn't match what they can deliver!",
        "case_studies": [
            {"api": "cURL / libcurl", "scenario": "cURL sends Expect: 100-continue by default for large POST bodies — servers that don't support it return 417, causing the upload to fail unexpectedly", "lesson": "If you see 417 from a server, disable the Expect header with curl -H 'Expect:' or handle the fallback by sending the body after a short timeout"},
            {"api": "IIS (Internet Information Services)", "scenario": "Older versions of IIS return 417 for any request with an Expect header, even Expect: 100-continue, breaking many HTTP client libraries", "lesson": "Test your API against IIS specifically if clients use Expect headers — many enterprise environments still run legacy IIS versions that reject the header outright"},
        ],
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
        "eli5": "You ask a teapot to make you some coffee. The teapot says 'Excuse me, I'm a TEAPOT! I make TEA, not coffee!' It's a silly joke that programmers put in the rules of the internet.",
        "case_studies": [
            {"api": "Google (google.com/teapot)", "scenario": "Google once hosted an interactive teapot page at /teapot as a playful Easter egg implementing RFC 2324", "lesson": "RFC 2324 was an April Fools' joke, but 418 is now preserved in HTTP specs because removing it would break the internet's sense of humor"},
            {"api": "Node.js core", "scenario": "The Node.js HTTP module includes 418 in its STATUS_CODES map after a heated debate about removing it", "lesson": "Developer experience matters — sometimes keeping a harmless joke is better for community morale than strict spec compliance"},
        ],
        "common_mistakes": [
            {"mistake": "Using 418 in production APIs as a real status code", "consequence": "418 is an April Fools joke from RFC 2324. Monitoring tools, proxies, and clients do not handle it properly. Use a real 4xx code instead."},
            {"mistake": "Relying on 418 for rate limiting or bot blocking instead of 429", "consequence": "Some developers use 418 to confuse bots, but well-behaved clients and monitoring tools cannot interpret it. Use standard codes like 429 or 403."},
        ],
    },
    "419": {
        "examples": [
            "Laravel returning this when a CSRF token is missing or expired on a form submission",
            "A session timeout in a PHP framework — the user's login session expired mid-action",
        ],
        "headers": [],
        "code": {
            "python": "# Not a standard code — used by Laravel for expired CSRF tokens",
            "node": "// Non-standard; Laravel uses 419 for CSRF/session expiry",
            "go": '// Non-standard; consider using 403 or 440 instead',
        },
        "eli5": "You were playing a video game and walked away for too long. When you came back, the game kicked you out and said 'Your session expired — start over!' Your hall pass timed out.",
        "case_studies": [
            {"api": "Laravel (PHP framework)", "scenario": "Laravel returns 419 when a form submission has a missing or expired CSRF token, which commonly happens when users leave a form open overnight", "lesson": "Implement token refresh via AJAX or show a user-friendly 'session expired' message with a reload button instead of a raw 419 error page"},
            {"api": "WordPress plugins", "scenario": "Some WordPress security plugins return 419 for expired nonces on admin AJAX actions, breaking dashboard functionality after idle sessions", "lesson": "419 is non-standard — if you need CSRF expiry semantics, consider using 403 with a descriptive body for broader client compatibility"},
        ],
    },
    "420": {
        "examples": [
            "Twitter's old API used this for rate limiting before 429 was standardized",
            "Sometimes used as a humorous 'Enhance Your Calm' response",
            "Spring Framework using this as a custom 'Method Failure' status",
        ],
        "headers": [],
        "code": {
            "python": "# Non-standard — use 429 for rate limiting instead",
            "node": "// Non-standard; Twitter's old 'Enhance Your Calm' code",
            "go": '// Non-standard; prefer 429 Too Many Requests',
        },
        "eli5": "You're bouncing off the walls with too much energy and someone tells you to chill out. 'Enhance your calm!' Take a deep breath and slow down a little.",
        "case_studies": [
            {"api": "Twitter API v1 (historical)", "scenario": "Twitter's original API returned 420 Enhance Your Calm for rate-limited requests before HTTP 429 was standardized in RFC 6585", "lesson": "420 was a creative non-standard choice, but once 429 Too Many Requests was standardized, Twitter migrated to it — always prefer standardized codes"},
            {"api": "Spring Framework", "scenario": "Spring's HttpStatus.METHOD_FAILURE (420) was used internally for method-level failures before being deprecated in favor of standard 4xx codes", "lesson": "Non-standard codes create confusion for monitoring tools and client libraries — use 429 for rate limiting and appropriate 4xx codes for other client errors"},
        ],
    },
    "421": {
        "examples": [
            "An HTTP/2 request routed to a server that can't produce a response for that host",
            "A TLS connection being reused for a domain the certificate doesn't cover",
            "A reverse proxy forwarding a request to the wrong backend server",
        ],
        "headers": [],
        "code": {
            "python": 'return jsonify({"error": "Misdirected Request"}), 421',
            "node": "res.status(421).json({ error: 'Misdirected Request' });",
            "go": 'http.Error(w, "Misdirected Request", http.StatusMisdirectedRequest)',
        },
        "eli5": "You wrote a letter to Grandma but accidentally mailed it to Grandpa's house. Grandpa says 'This isn't for me — you sent it to the wrong place!'",
        "case_studies": [
            {"api": "Cloudflare / HTTP/2 connection coalescing", "scenario": "When HTTP/2 connection coalescing routes a request to a server whose TLS certificate doesn't cover the requested hostname, the server returns 421", "lesson": "421 is the correct response when a server receives a request it cannot authoritatively handle — clients should retry on a new connection to the correct server"},
            {"api": "Apache httpd (mod_ssl)", "scenario": "Apache returns 421 when SNI-based virtual hosting routes a request to a vhost whose SSL certificate doesn't match the Host header", "lesson": "Ensure all hostnames sharing an IP have proper TLS certificates or use SAN certificates — 421 errors often indicate TLS misconfiguration in multi-tenant setups"},
        ],
        "common_mistakes": [
            {"mistake": "Returning 421 when the issue is actually a DNS or routing misconfiguration rather than a misdirected request", "consequence": "421 specifically means the server cannot produce a response for the target URI on the current connection. Use 502 or 503 for backend routing problems."},
            {"mistake": "Not retrying on a new connection after receiving 421 from an HTTP/2 server", "consequence": "421 means the connection was reused incorrectly. The client should open a fresh connection to the correct server — the request itself is valid."},
        ],
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
        "eli5": "Your homework has all the right words and good handwriting, but the answers are wrong. The teacher says 'I can read it just fine, but the content doesn't make sense!'",
        "case_studies": [
            {"api": "GitHub API", "scenario": "Creating a pull request with invalid branch references returns 422 with a validation errors array", "lesson": "Return structured field-level errors with 422 so clients can highlight exactly which input needs fixing"},
            {"api": "Stripe API", "scenario": "Creating a charge with an invalid currency code returns 422 with a clear error message", "lesson": "Distinguish 400 (malformed JSON syntax) from 422 (valid JSON but semantically invalid) to help clients handle errors differently"},
        ],
        "common_mistakes": [
            {
                "mistake": "Using 400 instead of 422 for semantic validation errors",
                "consequence": "400 means the syntax is wrong (malformed JSON). 422 means the syntax is fine but the content fails validation (invalid email).",
            },
            {
                "mistake": "Returning 422 without structured validation errors",
                "consequence": "Clients can't programmatically show field-level errors. Include a machine-readable error object like {\"errors\": {\"field\": \"reason\"}}.",
            },
        ],
        "dont_use_when": [
            "The request body itself is malformed (invalid JSON syntax) — use 400 Bad Request instead",
            "The request conflicts with existing data (duplicate username) — use 409 Conflict instead",
            "The request is well-formed and valid but the user lacks permission — use 403 Forbidden instead",
            "The endpoint or resource doesn't exist — use 404 Not Found instead",
        ],
    },
    "423": {
        "examples": [
            "A WebDAV resource that is locked by another user for editing",
            "Trying to modify a file in SharePoint that someone else has checked out",
            "A collaborative editing system preventing concurrent writes",
        ],
        "headers": ["Content-Type: application/xml"],
        "code": {
            "python": 'return jsonify({"error": "Resource is locked"}), 423',
            "node": "res.status(423).json({ error: 'Locked' });",
            "go": 'http.Error(w, "Locked", 423)',
        },
        "eli5": "Someone else is already using the bathroom and the door is locked. You'll have to wait until they're done before you can go in!",
        "case_studies": [
            {"api": "Microsoft SharePoint (WebDAV)", "scenario": "SharePoint returns 423 when a document is checked out by another user, preventing concurrent edits that could cause data loss", "lesson": "Always include lock owner and lock timeout information in the 423 response so clients can display who holds the lock and when it expires"},
            {"api": "Subversion (SVN)", "scenario": "SVN servers return 423 when a commit targets a path that is locked by another working copy, enforcing exclusive write access", "lesson": "Implement lock timeouts and forced unlock capabilities for administrators — stale locks from crashed clients can block entire teams"},
        ],
    },
    "424": {
        "examples": [
            "A WebDAV batch operation where one action failed, causing dependent actions to fail too",
            "A multi-step transaction where step 2 fails because step 1 didn't complete",
        ],
        "headers": ["Content-Type: application/xml"],
        "code": {
            "python": 'return jsonify({"error": "Failed Dependency"}), 424',
            "node": "res.status(424).json({ error: 'Failed Dependency' });",
            "go": 'http.Error(w, "Failed Dependency", 424)',
        },
        "eli5": "You can't ice the cake because the oven broke and the cake never got baked. Step two failed because step one didn't work out. One domino knocked the other one down!",
        "case_studies": [
            {"api": "CalDAV / CardDAV servers", "scenario": "A bulk calendar update via PROPPATCH returns 424 for properties that couldn't be set because a prerequisite property change in the same request failed", "lesson": "424 tells the client which operations were skipped due to an earlier failure — include the dependency chain in the response so clients know what to fix first"},
            {"api": "Microsoft Graph API (batch requests)", "scenario": "Batch requests to Microsoft Graph return 424 for dependent requests when a prerequisite request in the batch fails", "lesson": "When designing batch APIs, clearly document dependency ordering — 424 should identify which prior request caused the cascade so clients can retry intelligently"},
        ],
    },
    "425": {
        "examples": [
            "A server rejecting a request sent in TLS early data (0-RTT) to prevent replay attacks",
            "An API refusing to process a request that arrived before the TLS handshake completed",
        ],
        "headers": [],
        "code": {
            "python": 'return jsonify({"error": "Too Early"}), 425',
            "node": "res.status(425).json({ error: 'Too Early' });",
            "go": 'http.Error(w, "Too Early", 425)',
        },
        "eli5": "You tried to run into the classroom before the teacher even unlocked the door. 'Whoa, slow down! It's too early — wait until everything is properly set up!'",
        "case_studies": [
            {"api": "Cloudflare / TLS 1.3", "scenario": "TLS 1.3 0-RTT early data can be replayed by attackers — servers return 425 to reject state-changing requests sent in early data", "lesson": "Never allow POST, PUT, or DELETE in TLS 0-RTT early data — replay attacks could duplicate transactions like payments"},
            {"api": "CDN edge servers", "scenario": "Edge servers reject early data for non-idempotent requests to prevent replay-based cache poisoning", "lesson": "Use 425 as a signal to retry the request after the full TLS handshake completes — the request itself is fine, just the timing was wrong"},
        ],
        "common_mistakes": [
            {"mistake": "Allowing state-changing requests (POST, PUT, DELETE) in TLS 1.3 0-RTT early data", "consequence": "Early data can be replayed by attackers, potentially duplicating payments or creating duplicate resources. Only allow idempotent GET/HEAD in 0-RTT."},
            {"mistake": "Not implementing automatic retry after receiving 425", "consequence": "425 means 'try again after the full handshake' — clients that don't retry automatically will fail on the first request of every new TLS 1.3 connection."},
        ],
    },
    "426": {
        "examples": [
            "A server requiring the client to switch to HTTPS or HTTP/2",
            "An endpoint that only works over WebSocket telling a plain HTTP client to upgrade",
            "A server refusing HTTP/1.0 and requiring at least HTTP/1.1",
        ],
        "headers": ["Upgrade: h2c", "Connection: Upgrade"],
        "code": {
            "python": 'return "", 426, {"Upgrade": "TLS/1.2", "Connection": "Upgrade"}',
            "node": "res.status(426).set('Upgrade', 'TLS/1.2').json({ error: 'Upgrade Required' });",
            "go": 'w.Header().Set("Upgrade", "TLS/1.2")\nhttp.Error(w, "Upgrade Required", 426)',
        },
        "eli5": "You're trying to talk through a tin-can telephone, but the other person says 'Get a real phone first, then call me!' You need to upgrade your equipment before they'll talk to you.",
        "case_studies": [
            {"api": "Let's Encrypt / ACME protocol", "scenario": "ACME servers return 426 with Upgrade: TLS/1.2 when clients attempt certificate issuance over plain HTTP or outdated TLS versions", "lesson": "426 with the Upgrade header tells clients exactly which protocol to use — always include the required protocol version so automated clients can adapt"},
            {"api": "WebSocket endpoints", "scenario": "REST endpoints that only accept WebSocket connections return 426 when accessed via plain HTTP, indicating the client must upgrade to WebSocket", "lesson": "Return 426 with Upgrade: websocket and Connection: Upgrade headers to guide HTTP clients toward the correct protocol for real-time endpoints"},
        ],
    },
    "428": {
        "examples": [
            "An API requiring If-Match or If-Unmodified-Since headers to prevent lost updates",
            "A PUT endpoint that mandates conditional requests for concurrency safety",
            "GitHub's API requiring conditional requests for certain update operations",
        ],
        "headers": [],
        "code": {
            "python": 'return jsonify({"error": "Precondition Required"}), 428',
            "node": "res.status(428).json({ error: 'Precondition Required' });",
            "go": 'http.Error(w, "Precondition Required", 428)',
        },
        "eli5": "You want to change something, but first you need to prove you're working with the latest version. It's like a teacher saying 'Show me you've read the latest instructions before you edit anything!'",
        "case_studies": [
            {"api": "GitHub API", "scenario": "Certain update operations require If-Match header — omitting it returns 428", "lesson": "Require conditional headers (If-Match, If-Unmodified-Since) on write endpoints to prevent accidental overwrites in concurrent environments"},
            {"api": "Kubernetes API", "scenario": "Updates to resources without a resourceVersion field are rejected with 428", "lesson": "428 forces clients into an optimistic concurrency pattern — read the latest version, then update with the version token"},
        ],
        "common_mistakes": [
            {
                "mistake": "Requiring conditional headers (428) on every endpoint, even simple reads",
                "consequence": "Overusing 428 adds friction for API consumers. Reserve it for write endpoints where concurrent updates are a real risk.",
            },
            {
                "mistake": "Returning 428 without explaining which precondition headers are required",
                "consequence": "Clients know they need a precondition but not which one (If-Match? If-Unmodified-Since?). Document the required headers clearly.",
            },
        ],
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
        "eli5": "You keep asking 'Are we there yet? Are we there yet? Are we there yet?' so many times that your parents finally say 'STOP ASKING! Wait 5 minutes before you ask again!'",
        "case_studies": [
            {"api": "Twitter/X API", "scenario": "Rate limit exceeded, returns Retry-After header", "lesson": "Always implement exponential backoff, never hammer a 429"},
            {"api": "GitHub API", "scenario": "60 unauthenticated requests/hour, 5000 authenticated", "lesson": "Check X-RateLimit-Remaining headers proactively to avoid hitting limits at all"},
            {"api": "Shopify API", "scenario": "Leaky bucket rate limiter returns 429 with Retry-After", "lesson": "Different rate limit algorithms (fixed window, sliding window, leaky bucket) require different backoff strategies"},
        ],
        "common_mistakes": [
            {
                "mistake": "Not including a Retry-After header",
                "consequence": "Clients have no idea when to try again. They may retry immediately, making the overload worse. Always include Retry-After.",
            },
            {
                "mistake": "Rate limiting without providing rate limit headers (X-RateLimit-Remaining, etc.)",
                "consequence": "Clients can't proactively slow down before hitting the limit. Good APIs tell you how many requests you have left.",
            },
        ],
        "dont_use_when": [
            "The server is overloaded and cannot process any requests — use 503 Service Unavailable instead",
            "The user's account is suspended or banned — use 403 Forbidden instead",
            "The request is malformed or invalid — use 400 Bad Request instead",
            "The user needs to pay to continue — use 402 Payment Required instead",
        ],
    },
    "431": {
        "examples": [
            "Sending too many or too large cookies causing the request headers to exceed the server limit",
            "A request with a massive Authorization header or a ridiculous number of custom headers",
            "Nginx returning this when large_client_header_buffers is exceeded",
        ],
        "headers": [],
        "code": {
            "python": 'return jsonify({"error": "Request Header Fields Too Large"}), 431',
            "node": "res.status(431).json({ error: 'Request Header Fields Too Large' });",
            "go": 'http.Error(w, "Request Header Fields Too Large", 431)',
        },
        "eli5": "You're writing a letter but the envelope has so many stickers and notes on the outside that the mailman can't even read the address. Too much stuff in the header!",
        "case_studies": [
            {"api": "Cloudflare / Nginx", "scenario": "Accumulated cookies from third-party trackers cause headers to exceed 8KB, triggering 431", "lesson": "Monitor total cookie size across your domains — cookie bloat from analytics and A/B testing is the most common cause of 431"},
            {"api": "AWS ALB", "scenario": "JWT tokens stored in cookies grow too large with embedded claims, exceeding the default 16KB header limit", "lesson": "Store large tokens server-side and use a session ID cookie instead — JWTs with many claims can easily exceed header limits"},
        ],
        "common_mistakes": [
            {
                "mistake": "Not monitoring or limiting the size of cookies and custom headers your application sets",
                "consequence": "Cookie bloat from analytics, A/B testing, and large JWTs accumulates over time. By the time users hit 431, it's hard to diagnose.",
            },
            {
                "mistake": "Using the default server header size limit without tuning it for your use case",
                "consequence": "The default limit (8KB on Nginx, 16KB on AWS ALB) may be too small for apps with many cookies. Tune it, but also fix the root cause of large headers.",
            },
        ],
    },
    "444": {
        "examples": [
            "Nginx silently closing the connection without sending any response — used to block malicious clients",
            "Dropping connections from bots or scanners without wasting bandwidth on a response",
            "Nginx deny rules that just kill the connection",
        ],
        "headers": [],
        "code": {
            "python": "# Nginx-specific: return 444; in nginx.conf closes the connection",
            "node": "// Nginx-only; req.socket.destroy() is the closest equivalent",
            "go": "// Nginx-specific; in Go you'd use conn.Close() or hijack the connection",
        },
        "eli5": "Someone knocks on your door, but when you open it, nobody's there — they already ran away. So you just close the door without saying anything. Conversation over!",
        "case_studies": [
            {"api": "Nginx", "scenario": "Nginx's return 444 directive silently drops connections from known bad IPs or malicious user agents without sending any response", "lesson": "444 saves bandwidth against scanners and bots — no response means no information leaked about your server"},
            {"api": "Cloudflare WAF", "scenario": "Cloudflare uses connection-drop behavior similar to 444 when blocking DDoS traffic at the edge", "lesson": "Silent connection drops are effective against automated attacks but confusing for legitimate debugging — log dropped connections server-side"},
        ],
    },
    "450": {
        "examples": [
            "Microsoft's 'Blocked by Windows Parental Controls' — a child's account is prevented from accessing content",
            "Windows family safety features blocking a website for a managed account",
        ],
        "headers": [],
        "code": {
            "python": "# Non-standard Microsoft code — not used in general web development",
            "node": "// Microsoft-specific; 450 Blocked by Parental Controls",
            "go": "// Non-standard; only relevant to Microsoft/Windows environments",
        },
        "eli5": "Your parents set up parental controls on the computer, and when you try to visit a website, the screen says 'Nope, your parents blocked this!' Grounded from the internet.",
        "case_studies": [
            {"api": "Microsoft Windows Family Safety", "scenario": "Windows Family Safety intercepts HTTP requests and returns 450 when a child account tries to access a blocked website category", "lesson": "450 is Microsoft-specific and not part of any HTTP standard — if you see it, it's coming from a Windows content filter, not your origin server"},
            {"api": "Microsoft ISA Server / TMG", "scenario": "Microsoft's Threat Management Gateway used 450 to block content categories like gambling or adult content for managed network users", "lesson": "Unlike 403 which comes from the origin, 450 comes from a client-side proxy — troubleshoot by checking local Windows parental control or network filter settings"},
        ],
    },
    "451": {
        "examples": [
            "A website blocked in a country due to government censorship",
            "Content removed due to a DMCA takedown notice",
            "A page unavailable due to court-ordered legal restrictions (named after Fahrenheit 451)",
        ],
        "headers": ["Link: <https://example.com/legal>; rel=\"blocked-by\""],
        "code": {
            "python": 'return jsonify({"error": "Unavailable For Legal Reasons"}), 451',
            "node": "res.status(451).json({ error: 'Unavailable For Legal Reasons' });",
            "go": 'http.Error(w, "Unavailable For Legal Reasons", 451)',
        },
        "eli5": "That book you wanted has been banned by the authorities. The library isn't allowed to give it to you because of the law. Named after the book Fahrenheit 451 about burning books!",
        "case_studies": [
            {"api": "GitHub (DMCA takedowns)", "scenario": "Repositories removed due to DMCA notices return 451 with a link to the takedown request", "lesson": "Always include a Link header with rel=blocked-by pointing to the legal authority or notice — transparency matters"},
            {"api": "Reddit / Twitter", "scenario": "Content geo-blocked due to local laws returns 451 in regions where the content is restricted", "lesson": "451 was specifically designed to distinguish legal censorship from access control (403) — use it to promote transparency about government-mandated blocks"},
        ],
        "common_mistakes": [
            {"mistake": "Using 403 instead of 451 for legally mandated content blocks", "consequence": "403 hides the reason. 451 explicitly signals legal restrictions, promoting transparency and helping users understand the block is external, not a permission issue."},
            {"mistake": "Not including a Link header with rel=blocked-by pointing to the legal authority", "consequence": "Users have no way to learn why the content is blocked or who ordered it. The Link header is how 451 communicates accountability."},
        ],
    },
    "494": {
        "examples": [
            "Nginx rejecting a request because a header exceeded the configured size limit",
            "A client sending a single header line that's unreasonably large",
        ],
        "headers": [],
        "code": {
            "python": "# Nginx-specific: returned when a request header is too large",
            "node": "// Nginx-only code; Node has --max-http-header-size for similar limits",
            "go": "// Nginx-specific; Go's default MaxHeaderBytes is 1MB",
        },
        "eli5": "One of the labels on your package is so huge it's bigger than the box itself. The post office says 'This single label is way too big — trim it down!'",
        "case_studies": [
            {"api": "Nginx", "scenario": "Nginx returns 494 when a single request header line exceeds large_client_header_buffers size limit", "lesson": "494 is Nginx-specific — if you see it in logs, increase large_client_header_buffers or investigate why a header is abnormally large"},
            {"api": "WAF / Security appliances", "scenario": "Web application firewalls that proxy through Nginx may trigger 494 when injecting large security headers into forwarded requests", "lesson": "Check both client-sent and proxy-injected headers when debugging 494 — the oversized header may come from your own infrastructure"},
        ],
    },
    "498": {
        "examples": [
            "ArcGIS Server returning this when an expired or invalid token is provided",
            "Esri APIs rejecting a request because the authentication token has expired",
        ],
        "headers": [],
        "code": {
            "python": "# Non-standard; used by ArcGIS/Esri for invalid tokens",
            "node": "// Esri-specific; prefer 401 for token issues in standard APIs",
            "go": "// Non-standard; specific to ArcGIS Server",
        },
        "eli5": "Your movie ticket expired — the showing was an hour ago! You need to get a fresh, valid ticket before they'll let you in. The old one is no good anymore.",
        "case_studies": [
            {"api": "ArcGIS Server (Esri)", "scenario": "ArcGIS REST services return 498 when a token parameter is expired, revoked, or malformed", "lesson": "498 is Esri-specific — standard APIs should use 401 for token issues, but if you integrate with ArcGIS, handle 498 as a token refresh trigger"},
            {"api": "ArcGIS Online", "scenario": "Hosted feature services return 498 when the OAuth token has expired during a long editing session", "lesson": "Implement proactive token refresh before expiry rather than waiting for 498 — check the token expiration claim and refresh with 30 seconds of buffer"},
        ],
    },
    "499": {
        "examples": [
            "Nginx logging this when the client closes the connection before the server finishes responding",
            "A user navigating away or cancelling a slow page load",
            "A load balancer timing out and closing the connection to the backend",
        ],
        "headers": [],
        "code": {
            "python": "# Nginx-specific log code — you'll see this in access logs, not in app code",
            "node": "// Nginx logs 499 when client disconnects; handle 'close' event on req",
            "go": "// Check r.Context().Done() to detect client disconnection",
        },
        "eli5": "You ordered food at a restaurant, but you got impatient and left before it was ready. The waiter comes back with your plate and says 'They already left!' Nobody to serve it to.",
        "case_studies": [
            {"api": "Nginx access logs", "scenario": "Nginx logs 499 when a user navigates away from a slow page before the backend finishes generating the response", "lesson": "High 499 rates in Nginx logs indicate slow backend responses — investigate backend latency, not Nginx configuration"},
            {"api": "AWS ALB + Nginx", "scenario": "ALB idle timeout (60s default) closes connections to Nginx backends, which logs these as 499 client-closed-request", "lesson": "Set Nginx proxy_read_timeout higher than ALB idle timeout, or use keep-alive to prevent ALB from closing connections prematurely"},
        ],
        "common_mistakes": [
            {"mistake": "Ignoring high 499 rates in Nginx logs because they seem like a client problem", "consequence": "499 spikes usually indicate slow backend responses, not impatient users. Investigate backend latency and optimize slow endpoints before blaming clients."},
            {"mistake": "Setting Nginx proxy_read_timeout lower than the load balancer's idle timeout", "consequence": "The load balancer closes the connection before Nginx finishes, generating 499s. Nginx timeouts should always exceed the upstream load balancer's idle timeout."},
        ],
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
        "eli5": "The ice cream machine at the restaurant just broke. It's nobody's fault outside — something went wrong inside the machine. The worker says 'Sorry, something broke in the back. We're fixing it!'",
        "case_studies": [
            {"api": "Any production service", "scenario": "Unhandled exception crashes the request handler", "lesson": "Never expose stack traces to end users — log them server-side and return a generic error with a request ID for debugging"},
            {"api": "AWS Lambda", "scenario": "Function throws unhandled error, API Gateway returns 500", "lesson": "Wrap Lambda handlers in try/catch and return proper 4xx/5xx — unhandled errors give callers no useful information"},
        ],
        "common_mistakes": [
            {
                "mistake": "Catching all exceptions and returning 500 with the stack trace",
                "consequence": "Leaks internal implementation details (file paths, library versions, database names). Log the trace server-side, return a generic message.",
            },
            {
                "mistake": "Using 500 for expected errors like invalid input",
                "consequence": "500 means something broke on the server. If the client sent bad data, use 4xx. False 500s trigger on-call alerts and mask real outages.",
            },
        ],
        "dont_use_when": [
            "The client sent invalid data — use 400 Bad Request or 422 Unprocessable Entity instead",
            "An upstream/backend server failed — use 502 Bad Gateway instead",
            "The server is temporarily overloaded — use 503 Service Unavailable with Retry-After",
            "A dependency timed out — use 504 Gateway Timeout instead",
        ],
    },
    "501": {
        "examples": [
            "A server receiving a PATCH request it doesn't know how to handle",
            "An HTTP method like PROPFIND hitting a server that doesn't support WebDAV",
            "A minimal server that only implements GET and POST",
        ],
        "headers": [],
        "code": {
            "python": 'return jsonify({"error": "Not Implemented"}), 501',
            "node": "res.status(501).json({ error: 'Not Implemented' });",
            "go": 'http.Error(w, "Not Implemented", http.StatusNotImplemented)',
        },
        "eli5": "You asked the robot to do a backflip, but it was only programmed to walk and wave. 'Sorry, I don't know how to do that yet! Nobody taught me!'",
        "case_studies": [
            {"api": "Nginx (minimal config)", "scenario": "A server that only handles GET and POST returns 501 for PATCH, PUT, or DELETE requests", "lesson": "501 means the server doesn't recognize the method at all — unlike 405, which means the method is known but not allowed for this resource"},
            {"api": "Legacy proxy servers", "scenario": "Older HTTP proxies return 501 when they encounter HTTP/2 or WebSocket upgrade requests they cannot process", "lesson": "Use 501 sparingly — in modern APIs, if you receive a valid HTTP method, return 405 with an Allow header instead"},
        ],
        "common_mistakes": [
            {
                "mistake": "Using 501 when the server had an internal error (confusing with 500)",
                "consequence": "501 means the server does not support the functionality. 500 means it tried and broke. Using 501 for bugs misleads clients into thinking the feature does not exist.",
            },
            {
                "mistake": "Returning 501 for a known HTTP method that the specific resource does not support",
                "consequence": "That is 405 (Method Not Allowed). 501 means the server does not recognize the method at all, not that the resource does not accept it.",
            },
        ],
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
        "eli5": "You tell your big sister to ask mom for a cookie. Your sister goes to mom, but mom says something confusing that doesn't make sense. Your sister comes back and says 'I tried, but I got a weird answer!'",
        "case_studies": [
            {"api": "Cloudflare", "scenario": "Origin server is down, CDN returns 502", "lesson": "502 means the gateway is working but the upstream server isn't — check your origin, not the CDN"},
            {"api": "AWS ALB", "scenario": "Target group has no healthy instances, ALB returns 502", "lesson": "Set up health checks and auto-scaling so there is always at least one healthy backend to route to"},
        ],
        "common_mistakes": [
            {
                "mistake": "Returning 502 from application code",
                "consequence": "502 should come from proxies/load balancers, not your app. If your code has an error, that's 500. 502 means the gateway got a bad response from upstream.",
            },
            {
                "mistake": "Confusing 502 with 503",
                "consequence": "502 means the upstream returned garbage. 503 means the service is temporarily unavailable. The fix is different: 502 = check upstream health; 503 = wait and retry.",
            },
        ],
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
        "eli5": "Picture a restaurant so busy they put up a 'Please wait to be seated' sign. The kitchen is still there, just too slammed right now. Come back in a little bit!",
        "case_studies": [
            {"api": "Heroku", "scenario": "Dyno overload or boot timeout returns 503", "lesson": "Include a Retry-After header so clients know when to come back instead of hammering retries"},
            {"api": "GitHub", "scenario": "Planned maintenance returns 503 with maintenance page", "lesson": "Use 503 for temporary downtime, not permanent removal — search engines treat 503 as 'come back later'"},
        ],
        "common_mistakes": [
            {
                "mistake": "Not including a Retry-After header",
                "consequence": "Clients and crawlers don't know when to come back. Search engines may de-index your site if they keep seeing 503 without guidance.",
            },
            {
                "mistake": "Using 503 as a permanent error",
                "consequence": "503 implies 'try again later.' If the service is gone for good, use 410 (Gone) or remove the endpoint entirely.",
            },
        ],
        "dont_use_when": [
            "The server crashed due to a bug — use 500 Internal Server Error instead",
            "An upstream server returned an invalid response — use 502 Bad Gateway instead",
            "An upstream server timed out — use 504 Gateway Timeout instead",
            "The client is sending too many requests — use 429 Too Many Requests instead",
        ],
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
        "eli5": "You ask your sister to ask mom for a cookie, but mom is taking a nap and won't wake up. Your sister waits and waits, and finally gives up and says 'Sorry, mom didn't answer in time!'",
        "case_studies": [
            {"api": "Nginx", "scenario": "proxy_read_timeout exceeded waiting for upstream, returns 504", "lesson": "Tune timeouts per-endpoint — a report generation endpoint needs a longer timeout than a health check"},
            {"api": "AWS API Gateway", "scenario": "Lambda function exceeds 29-second integration timeout", "lesson": "For long-running operations, return 202 Accepted with a polling URL instead of blocking until completion"},
        ],
        "common_mistakes": [
            {
                "mistake": "Confusing 504 with 408 (Request Timeout)",
                "consequence": "408 means the client was too slow sending the request. 504 means the upstream server was too slow responding. Different root cause, different fix.",
            },
            {
                "mistake": "Setting proxy timeouts too low",
                "consequence": "Legitimate slow requests (reports, exports, file uploads) get killed prematurely. Tune timeouts per-endpoint when possible.",
            },
        ],
    },
    "505": {
        "examples": [
            "A server that only supports HTTP/1.1 receiving an HTTP/2 request it can't handle",
            "An ancient client sending an HTTP/0.9 request to a modern server",
        ],
        "headers": [],
        "code": {
            "python": 'return jsonify({"error": "HTTP Version Not Supported"}), 505',
            "node": "res.status(505).json({ error: 'HTTP Version Not Supported' });",
            "go": 'http.Error(w, "HTTP Version Not Supported", http.StatusHTTPVersionNotSupported)',
        },
        "eli5": "You tried to play a Blu-ray disc in an old DVD player. The player says 'I don't understand this format — I'm not new enough!' You're speaking a language version it doesn't know.",
        "case_studies": [
            {"api": "Legacy corporate proxies", "scenario": "Enterprise proxy appliances that only support HTTP/1.0 return 505 when clients send HTTP/1.1 or HTTP/2 requests", "lesson": "505 is rare in modern systems — most servers support HTTP/1.1 and HTTP/2, but legacy infrastructure can still surprise you"},
            {"api": "Embedded IoT devices", "scenario": "Minimal HTTP servers on microcontrollers only implement HTTP/1.0 and reject newer protocol versions with 505", "lesson": "When building clients for constrained devices, always fall back gracefully to HTTP/1.0 if the server rejects your protocol version"},
        ],
        "common_mistakes": [
            {"mistake": "Confusing 505 with 426 (Upgrade Required)", "consequence": "426 means the server wants the client to switch to a newer protocol. 505 means the server cannot handle the protocol version the client used. Opposite directions."},
            {"mistake": "Returning 505 when the issue is actually a misconfigured proxy", "consequence": "A proxy stripping HTTP/2 or downgrading the protocol version can trigger false 505s. Check the full request chain before blaming the client."},
        ],
    },
    "506": {
        "examples": [
            "A server misconfigured so the chosen content variant itself tries to negotiate, creating a loop",
            "Transparent content negotiation resulting in a circular reference",
        ],
        "headers": [],
        "code": {
            "python": 'return jsonify({"error": "Variant Also Negotiates"}), 506',
            "node": "res.status(506).json({ error: 'Variant Also Negotiates' });",
            "go": 'http.Error(w, "Variant Also Negotiates", 506)',
        },
        "eli5": "You asked your friend to pick a restaurant, and they said 'Ask my other friend,' who said 'Ask the first friend.' Now nobody can decide and everyone's going in circles!",
        "case_studies": [
            {"api": "Apache mod_negotiation", "scenario": "Misconfigured content negotiation where a .var type-map file references a variant that itself requires further negotiation, creating an infinite loop", "lesson": "506 indicates a server misconfiguration, not a client error — check your content negotiation type-maps for circular references"},
            {"api": "Transparent Content Negotiation (RFC 2295)", "scenario": "A resource returns a choice response where the selected variant also has an Alternates header, triggering recursive negotiation", "lesson": "506 is extremely rare in modern APIs — if you encounter it, the server's content negotiation setup is broken and needs admin intervention"},
        ],
    },
    "507": {
        "examples": [
            "A WebDAV server running out of disk space while trying to store a resource",
            "A cloud storage service hitting its quota limit",
            "A mail server rejecting an upload because the user's mailbox is full",
        ],
        "headers": [],
        "code": {
            "python": 'return jsonify({"error": "Insufficient Storage"}), 507',
            "node": "res.status(507).json({ error: 'Insufficient Storage' });",
            "go": 'http.Error(w, "Insufficient Storage", http.StatusInsufficientStorage)',
        },
        "eli5": "Your closet is completely stuffed and you're trying to cram in one more toy. The closet door won't close — there's just no room left! Time to clean up or get a bigger closet.",
        "case_studies": [
            {"api": "Google Drive / Dropbox", "scenario": "Uploading a file when the user's storage quota is full returns 507", "lesson": "Include the current usage and quota limit in the error response so the user knows exactly how much space they need to free up"},
            {"api": "Exchange / SharePoint (WebDAV)", "scenario": "Mailbox or document library exceeds its storage quota, returning 507 on write operations", "lesson": "Set up monitoring and alerts for storage quotas well before they fill up — a 507 means writes are already failing"},
        ],
        "common_mistakes": [
            {"mistake": "Using 507 for application-level quota limits (like API request quotas) instead of actual storage exhaustion", "consequence": "507 specifically means the server cannot store the representation needed to complete the request. Use 429 for rate limits and 403 for quota-based access denial."},
            {"mistake": "Not including storage usage and quota details in the 507 error response", "consequence": "Users see 'insufficient storage' but don't know how much space they have or need. Include current_usage, quota_limit, and required_space in the response body."},
        ],
    },
    "508": {
        "examples": [
            "A WebDAV operation detecting an infinite loop in a collection of resources with internal bindings",
            "A server following resource references that eventually point back to themselves",
        ],
        "headers": [],
        "code": {
            "python": 'return jsonify({"error": "Loop Detected"}), 508',
            "node": "res.status(508).json({ error: 'Loop Detected' });",
            "go": 'http.Error(w, "Loop Detected", http.StatusLoopDetected)',
        },
        "eli5": "You follow a sign that says 'This way!' but it leads to another sign pointing back to where you started. And then another, and another. You're going in circles forever!",
        "case_studies": [
            {"api": "WebDAV (Apache mod_dav)", "scenario": "A COPY or MOVE operation encounters a bind loop in a collection, returning 508 to break the cycle", "lesson": "Always implement loop detection in recursive operations — without it, a single circular reference can consume infinite resources"},
            {"api": "Symlink-heavy file systems", "scenario": "A file server following symlinks encounters a circular reference chain and returns 508", "lesson": "Set a maximum recursion depth for any operation that follows references — 508 should be the safety net, not the first line of defense"},
        ],
    },
    "509": {
        "examples": [
            "A shared hosting provider shutting down a site that used too much bandwidth",
            "A web host enforcing a monthly traffic limit on a plan",
            "cPanel/WHM returning this when a site exceeds its allocated bandwidth",
        ],
        "headers": ["Retry-After: 86400"],
        "code": {
            "python": "# Non-standard; used by some hosting providers for bandwidth limits",
            "node": "// Non-standard; Apache/cPanel use 509 for bandwidth exceeded",
            "go": "// Non-standard; prefer 429 or 503 with Retry-After in standard APIs",
        },
        "eli5": "You used up all your monthly data on your phone plan. Your carrier says 'You've used too much bandwidth this month — come back next month or upgrade your plan!'",
        "case_studies": [
            {"api": "cPanel / WHM hosting", "scenario": "Shared hosting providers using cPanel return 509 when a site exceeds its monthly bandwidth allocation, effectively taking the site offline", "lesson": "509 is non-standard — use a CDN to offload bandwidth and monitor usage to avoid hitting hosting limits during traffic spikes"},
            {"api": "Apache (non-standard)", "scenario": "Apache's mod_bw or hosting-specific modules return 509 to enforce per-site bandwidth quotas on shared servers", "lesson": "If you see 509, contact your hosting provider — the fix is usually a plan upgrade or CDN integration, not a code change"},
        ],
    },
    "510": {
        "examples": [
            "A server requiring additional extensions in the request to fulfill it",
            "An HTTP Extension Framework response indicating the client needs to extend the request",
        ],
        "headers": [],
        "code": {
            "python": 'return jsonify({"error": "Not Extended"}), 510',
            "node": "res.status(510).json({ error: 'Not Extended' });",
            "go": 'http.Error(w, "Not Extended", http.StatusNotExtended)',
        },
        "eli5": "You tried to use a special feature on a walkie-talkie, but you need an extra antenna attachment first. The server says 'I need more extensions to handle your request!'",
        "case_studies": [
            {"api": "HTTP Extension Framework (RFC 2774)", "scenario": "A request requires mandatory extensions (via Man or Opt headers) that the server cannot fulfill", "lesson": "510 is extremely rare in practice — most modern APIs handle capability negotiation through API versioning or feature flags instead"},
        ],
    },
    "511": {
        "examples": [
            "A Wi-Fi captive portal (hotel, airport, coffee shop) intercepting your request to show a login page",
            "A network requiring you to accept terms of service before granting internet access",
            "Corporate guest networks redirecting to an authentication page",
        ],
        "headers": ["Content-Type: text/html"],
        "code": {
            "python": 'return render_template("captive_portal.html"), 511',
            "node": "res.status(511).send('<html>Please log in to the network</html>');",
            "go": 'http.Error(w, "Network Authentication Required", http.StatusNetworkAuthenticationRequired)',
        },
        "eli5": "You open your laptop at a coffee shop and try to browse the internet, but first a page pops up saying 'Agree to our Wi-Fi terms and log in before you can go anywhere!'",
        "case_studies": [
            {"api": "Hotel / Airport Wi-Fi", "scenario": "Captive portals intercept HTTP requests and return 511 to trigger the browser's captive portal detection flow", "lesson": "511 should only be generated by the network, not by origin servers — it tells the client to authenticate with the network layer, not the application"},
            {"api": "Apple / Google captive portal detection", "scenario": "iOS and Android make background requests to known URLs — a 511 triggers the captive portal login UI automatically", "lesson": "Use 511 with a simple HTML login form in the body — avoid JavaScript-heavy pages that may not render in captive portal browsers"},
        ],
        "common_mistakes": [
            {
                "mistake": "Not implementing captive portal detection in mobile or desktop apps",
                "consequence": "Apps fail with generic network errors instead of showing the captive portal login. Check for 511 and open a webview to let users authenticate.",
            },
            {
                "mistake": "Returning 511 from application servers instead of the network layer",
                "consequence": "511 should only come from captive portals and network intermediaries, not origin servers. Use 401 or 403 for app-level authentication.",
            },
        ],
    },
    "530": {
        "examples": [
            "Cloudflare returning this when the origin server returns an unexpected error and the site is frozen",
            "A hosting provider using this to indicate the site is suspended or frozen",
        ],
        "headers": [],
        "code": {
            "python": "# Non-standard; Cloudflare/hosting-specific frozen site indicator",
            "node": "// Non-standard; Cloudflare uses 530 alongside a 1XXX error code",
            "go": "// Non-standard; check Cloudflare's error documentation for details",
        },
        "eli5": "The website is frozen solid like a popsicle. The hosting company put it on ice, maybe because of a problem or unpaid bills. Nobody can visit until it thaws out!",
        "case_studies": [
            {"api": "Cloudflare", "scenario": "Origin server returns an error and Cloudflare presents a 530 error page alongside a 1XXX error code", "lesson": "530 is Cloudflare-specific — check the accompanying 1XXX error code and Cloudflare's error docs to diagnose the actual origin issue"},
            {"api": "Shared hosting providers", "scenario": "A site suspended for TOS violation or unpaid billing returns 530 from the hosting platform", "lesson": "If you see 530 in production, check your hosting provider's control panel first — it usually means an account-level issue, not a code bug"},
        ],
    },
}
