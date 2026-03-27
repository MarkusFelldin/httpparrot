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
    },
}
