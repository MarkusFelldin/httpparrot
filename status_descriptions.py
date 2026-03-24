"""Brief descriptions and history for each HTTP status code."""

STATUS_INFO = {
    "100": {
        "description": "The server has received the request headers and the client should proceed to send the request body. This allows the client to check if the server is willing to accept the request before sending a large body.",
        "history": "Introduced in HTTP/1.1 (RFC 2068, 1997) to optimize requests with large payloads. A client sends 'Expect: 100-continue' and waits for this response before transmitting the body, saving bandwidth if the server would reject it.",
    },
    "101": {
        "description": "The server is switching to a different protocol as requested by the client via an Upgrade header. Commonly used when upgrading an HTTP connection to WebSocket.",
        "history": "Defined in HTTP/1.1 (RFC 2068, 1997). Became widely used with the rise of WebSockets (RFC 6455, 2011), where it signals the upgrade from HTTP to the WebSocket protocol.",
    },
    "102": {
        "description": "The server has received and is processing the request, but no response is available yet. This prevents the client from timing out while waiting for a long-running operation.",
        "history": "Introduced in WebDAV (RFC 2518, 1999) for operations that could take a long time, such as recursive file operations on a remote server.",
    },
    "103": {
        "description": "Used to return some response headers before the final HTTP message. Allows the browser to start preloading resources (like stylesheets and scripts) while the server is still preparing the full response.",
        "history": "Proposed by Kazuho Oku in 2017 and standardized in RFC 8297. Adopted by major browsers and CDNs to improve page load performance by enabling early resource hints.",
    },
    "200": {
        "description": "The request has succeeded. The meaning of the success depends on the HTTP method: GET returns the resource, POST returns the result of the action, etc.",
        "history": "Part of the original HTTP specification since HTTP/0.9 (1991). The most common HTTP status code on the web, indicating that everything worked as expected.",
    },
    "201": {
        "description": "The request has been fulfilled and a new resource has been created. The response typically includes a Location header pointing to the newly created resource.",
        "history": "Present since HTTP/1.0 (RFC 1945, 1996). Commonly returned by REST APIs after successful POST requests that create new resources.",
    },
    "202": {
        "description": "The request has been accepted for processing, but the processing has not been completed. The request might or might not eventually be acted upon.",
        "history": "Defined in HTTP/1.0 (RFC 1945, 1996). Useful for asynchronous operations where the server queues work for later processing, such as batch jobs or email sending.",
    },
    "203": {
        "description": "The server successfully processed the request, but is returning information that may be from another source. The returned metadata is not exactly the same as what the origin server would have provided.",
        "history": "Introduced in HTTP/1.1 (RFC 2068, 1997). Commonly seen when a transforming proxy modifies the response, such as adding annotations or changing content.",
    },
    "204": {
        "description": "The server has successfully fulfilled the request but there is no content to return in the response body. Commonly used for successful DELETE operations or form submissions that don't navigate away.",
        "history": "Defined in HTTP/1.0 (RFC 1945, 1996). Widely used in REST APIs and single-page applications where the client doesn't need a response body.",
    },
    "205": {
        "description": "The server has fulfilled the request and the client should reset the document view that caused the request. For example, clearing a form after submission.",
        "history": "Introduced in HTTP/1.1 (RFC 2068, 1997). Rarely used in practice, as most modern web applications handle form resets client-side with JavaScript.",
    },
    "206": {
        "description": "The server is delivering only part of the resource due to a Range header sent by the client. Used for resumable downloads and streaming media.",
        "history": "Introduced in HTTP/1.1 (RFC 2068, 1997). Essential for video streaming, download managers, and any scenario where large files need to be fetched in chunks.",
    },
    "207": {
        "description": "A Multi-Status response conveys information about multiple resources in situations where multiple status codes might be appropriate. The response body is an XML message with individual status codes for each sub-request.",
        "history": "Introduced in WebDAV (RFC 2518, 1999). Used when a single request affects multiple resources, such as copying a folder with many files where some operations succeed and others fail.",
    },
    "208": {
        "description": "Used inside a Multi-Status response to indicate that a DAV member has already been enumerated in a previous part of the response and is not being included again.",
        "history": "Defined in RFC 5842 (2010) as part of WebDAV Binding Extensions. Prevents infinite loops when listing resources that have multiple bindings (like symbolic links).",
    },
    "226": {
        "description": "The server has fulfilled a GET request for the resource and the response represents the result of one or more instance-manipulations applied to the current instance.",
        "history": "Defined in RFC 3229 (2002) for Delta Encoding in HTTP. Allows servers to send only the changes since the client's last request, reducing bandwidth. Rarely used in practice.",
    },
    "300": {
        "description": "The requested resource has multiple representations, each with its own specific location. The user or user agent can select a preferred representation.",
        "history": "Part of HTTP/1.0 (RFC 1945, 1996). Intended for agent-driven content negotiation, but rarely used in practice. Most servers use 301 or 302 redirects instead.",
    },
    "301": {
        "description": "The requested resource has been permanently moved to a new URL. All future requests should use the new URL. Search engines will update their index to the new location.",
        "history": "Defined in HTTP/1.0 (RFC 1945, 1996). One of the most important status codes for SEO. Commonly used when websites change domain names or restructure their URL paths.",
    },
    "302": {
        "description": "The requested resource temporarily resides at a different URL. The client should continue to use the original URL for future requests.",
        "history": "Defined in HTTP/1.0 (RFC 1945, 1996). Historically misimplemented by browsers which changed POST to GET on redirect, leading to the creation of 303 and 307 in HTTP/1.1 to clarify the behavior.",
    },
    "303": {
        "description": "The response to the request can be found at another URL using a GET method. Typically used to redirect after a POST request to prevent form resubmission.",
        "history": "Introduced in HTTP/1.1 (RFC 2068, 1997) to clarify the behavior that browsers were already doing with 302: changing POST to GET on redirect. Part of the Post/Redirect/Get pattern.",
    },
    "304": {
        "description": "The resource has not been modified since the version specified by the request's If-Modified-Since or If-None-Match headers. The client can use its cached copy.",
        "history": "Defined in HTTP/1.0 (RFC 1945, 1996). A cornerstone of HTTP caching, saving bandwidth by telling clients to use their cached version instead of downloading the resource again.",
    },
    "305": {
        "description": "The requested resource must be accessed through the proxy specified in the Location header. For security reasons, many HTTP clients do not honor this status code.",
        "history": "Defined in HTTP/1.1 (RFC 2068, 1997). Deprecated due to security concerns — it could be used to redirect traffic through a malicious proxy. Most browsers ignore it.",
    },
    "306": {
        "description": "Originally meant 'Switch Proxy', indicating that subsequent requests should use the specified proxy. This status code is no longer used and the code is reserved.",
        "history": "Defined in an early HTTP/1.1 draft but was removed before the final specification. The code is reserved to prevent future reuse, as some implementations may still reference it.",
    },
    "307": {
        "description": "The requested resource temporarily resides at another URL. Unlike 302, the request method must not be changed when following the redirect — a POST stays a POST.",
        "history": "Introduced in HTTP/1.1 (RFC 2616, 1999) to fix the ambiguity of 302, where browsers incorrectly changed POST to GET. 307 guarantees the method and body are preserved.",
    },
    "308": {
        "description": "The resource has permanently moved to a new URL, and future requests should use the new URL. Unlike 301, the request method must not be changed — a POST stays a POST.",
        "history": "Defined in RFC 7538 (2015). The permanent counterpart to 307, just as 301 is to 302. Created to fill the gap where a permanent redirect needed to preserve the HTTP method.",
    },
    "400": {
        "description": "The server cannot process the request due to something perceived to be a client error, such as malformed syntax, invalid request message framing, or deceptive request routing.",
        "history": "Part of the original HTTP specification (RFC 1945, 1996). The most generic client error status code, used as a catch-all when more specific 4xx codes don't apply.",
    },
    "401": {
        "description": "The request requires authentication. The server must include a WWW-Authenticate header indicating the authentication scheme to use.",
        "history": "Defined in HTTP/1.0 (RFC 1945, 1996). Triggers the browser's built-in authentication dialog. In modern APIs, often used to indicate an expired or missing authentication token.",
    },
    "402": {
        "description": "Reserved for future use. Originally intended for digital payment systems, this code is not yet standardized but is sometimes used by APIs to indicate that a payment or subscription is required.",
        "history": "Reserved in HTTP/1.1 (RFC 2068, 1997) for future digital cash or micropayment schemes that never materialized. Some services like Shopify and Stripe use it informally to indicate payment-related issues.",
    },
    "403": {
        "description": "The server understood the request but refuses to authorize it. Unlike 401, re-authenticating will not help — the client simply does not have permission to access this resource.",
        "history": "Defined in HTTP/1.0 (RFC 1945, 1996). Commonly seen when accessing resources without proper permissions, IP-restricted content, or directory listings that are disabled.",
    },
    "404": {
        "description": "The server cannot find the requested resource. This is the most famous HTTP error code, familiar to virtually every internet user.",
        "history": "Defined in HTTP/1.0 (RFC 1945, 1996). Legend has it the code was named after Room 404 at CERN where the original web servers were housed, though this is likely apocryphal. Custom 404 pages have become an art form on the web.",
    },
    "405": {
        "description": "The HTTP method used is not allowed for the requested resource. For example, sending a POST request to a read-only resource. The response must include an Allow header listing the supported methods.",
        "history": "Introduced in HTTP/1.1 (RFC 2068, 1997). Common in REST APIs when a client tries to use an unsupported method on an endpoint.",
    },
    "406": {
        "description": "The server cannot produce a response matching the criteria given by the client's Accept headers (content type, language, encoding, etc.).",
        "history": "Introduced in HTTP/1.1 (RFC 2068, 1997) as part of content negotiation. In practice, servers often ignore Accept headers and return content anyway rather than sending this error.",
    },
    "407": {
        "description": "Similar to 401, but the client must first authenticate with a proxy server. The proxy must return a Proxy-Authenticate header with the challenge.",
        "history": "Introduced in HTTP/1.1 (RFC 2068, 1997). Common in corporate environments where internet access requires proxy authentication.",
    },
    "408": {
        "description": "The server timed out waiting for the request. The client did not produce a request within the time that the server was prepared to wait.",
        "history": "Introduced in HTTP/1.1 (RFC 2068, 1997). Often seen when a client's network connection is slow or interrupted during the request. Some servers send this to close idle connections.",
    },
    "409": {
        "description": "The request conflicts with the current state of the server. Often used when trying to create a resource that already exists, or when there's an edit conflict.",
        "history": "Introduced in HTTP/1.1 (RFC 2068, 1997). Common in REST APIs for concurrent modification conflicts, version mismatches, or duplicate resource creation attempts.",
    },
    "410": {
        "description": "The resource is permanently gone and will not be available again. Unlike 404, this is a deliberate indication that the resource has been intentionally removed.",
        "history": "Introduced in HTTP/1.1 (RFC 2068, 1997). Useful for APIs deprecating endpoints, or websites that want search engines to remove pages from their index permanently.",
    },
    "411": {
        "description": "The server refuses the request because it requires a Content-Length header that was not included. The client should resend the request with the appropriate header.",
        "history": "Introduced in HTTP/1.1 (RFC 2068, 1997). Less common today since most HTTP clients and frameworks automatically include Content-Length when sending request bodies.",
    },
    "412": {
        "description": "One or more preconditions in the request headers (such as If-Match or If-Unmodified-Since) evaluated to false. The request was not performed.",
        "history": "Introduced in HTTP/1.1 (RFC 2068, 1997). Used in conditional requests to prevent the 'lost update' problem, where two clients try to modify the same resource simultaneously.",
    },
    "413": {
        "description": "The request body is larger than the server is willing to process. The server may close the connection or return a Retry-After header.",
        "history": "Introduced in HTTP/1.1 (RFC 2068, 1997). Originally named 'Request Entity Too Large'. Commonly triggered by file upload size limits configured on web servers or reverse proxies.",
    },
    "414": {
        "description": "The URI provided in the request is too long for the server to process. This rare condition usually occurs when a form submission using GET has too much data, or when a client has fallen into a redirect loop.",
        "history": "Introduced in HTTP/1.1 (RFC 2068, 1997). Originally named 'Request-URI Too Long'. Most servers limit URLs to 8,192 bytes, though the HTTP spec sets no specific limit.",
    },
    "415": {
        "description": "The server refuses the request because the media type of the request body is not supported. For example, sending XML to an endpoint that only accepts JSON.",
        "history": "Introduced in HTTP/1.1 (RFC 2068, 1997). Common in APIs when the Content-Type header doesn't match what the server expects.",
    },
    "416": {
        "description": "The client asked for a portion of the file via a Range header, but the server cannot supply that portion. For example, requesting bytes beyond the end of the file.",
        "history": "Introduced in HTTP/1.1 (RFC 2068, 1997). Originally named 'Requested Range Not Satisfiable'. Seen when download managers or media players request invalid byte ranges.",
    },
    "417": {
        "description": "The expectation given in the request's Expect header could not be met by the server. Commonly returned when a server doesn't support 'Expect: 100-continue'.",
        "history": "Introduced in HTTP/1.1 (RFC 2068, 1997). Relatively rare in modern web usage, as most servers handle the Expect header gracefully or simply ignore it.",
    },
    "418": {
        "description": "I'm a teapot. The server refuses to brew coffee because it is, permanently, a teapot. A teapot should not be asked to brew coffee; the resulting entity body may be short and stout.",
        "history": "Defined in RFC 2324 (1998), the Hyper Text Coffee Pot Control Protocol, published as an April Fools' joke. Despite being a joke, it was implemented by many real servers and became a beloved part of internet culture. Google once had an interactive 418 page at google.com/teapot.",
    },
    "419": {
        "description": "An unofficial status code, sometimes used to indicate that a CSRF token is missing or expired (Laravel framework), or humorously as 'I'm a Fox' in reference to 418's teapot joke.",
        "history": "Not part of any official RFC. In the Laravel PHP framework, 419 indicates a CSRF token mismatch. The 'I'm a Fox' variant is a humorous community extension of the 418 teapot joke.",
    },
    "420": {
        "description": "Returned by the old Twitter API (v1) when a client was being rate limited. An unofficial status code meaning the client should calm down and reduce request frequency.",
        "history": "Used by Twitter's API v1 as a rate-limiting response, referencing the 1993 movie Demolition Man where 'Enhance your calm' is a catchphrase. Twitter later switched to the standard 429 code.",
    },
    "421": {
        "description": "The request was directed at a server that is not able to produce a response. This can happen when a connection is reused for a request to a different host that the server doesn't handle.",
        "history": "Defined in RFC 7540 (2015) as part of HTTP/2. Addresses scenarios where connection coalescing sends a request to a server that doesn't serve that particular hostname.",
    },
    "422": {
        "description": "The server understands the content type and syntax of the request, but it was unable to process the contained instructions. Often used for semantic validation errors.",
        "history": "Introduced in WebDAV (RFC 2518, 1999). Adopted widely by REST APIs (especially Ruby on Rails) to indicate validation errors that are distinct from syntax errors (400).",
    },
    "423": {
        "description": "The resource that is being accessed is locked. This means the resource is currently in use by another process and cannot be modified.",
        "history": "Introduced in WebDAV (RFC 2518, 1999). Used in collaborative editing systems where file locking prevents concurrent modifications.",
    },
    "424": {
        "description": "The request failed because it depended on another request that itself failed. If one operation in a batch fails, dependent operations return this code.",
        "history": "Introduced in WebDAV (RFC 2518, 1999). Part of the multi-status response mechanism where operations can have dependencies on each other.",
    },
    "425": {
        "description": "The server is unwilling to risk processing a request that might be replayed. Used with TLS Early Data (0-RTT) where the server can't guarantee the request isn't a replay attack.",
        "history": "Defined in RFC 8470 (2018). Created specifically for TLS 1.3 early data, where the lack of replay protection means servers need a way to reject potentially replayed requests.",
    },
    "426": {
        "description": "The server refuses to perform the request using the current protocol. The client should switch to a different protocol specified in the Upgrade header.",
        "history": "Introduced in HTTP/1.1 (RFC 2817, 2000). Used when a server requires the client to upgrade to a newer protocol version, such as switching from HTTP/1.1 to HTTP/2.",
    },
    "428": {
        "description": "The server requires the request to be conditional (include If-Match, If-None-Match, etc.). This prevents the 'lost update' problem where a client overwrites another client's changes.",
        "history": "Defined in RFC 6585 (2012). Created to allow servers to require conditional requests, preventing accidental data loss from concurrent updates.",
    },
    "429": {
        "description": "The user has sent too many requests in a given amount of time (rate limiting). The response should include a Retry-After header indicating when to try again.",
        "history": "Defined in RFC 6585 (2012). Has become one of the most commonly encountered 4xx codes due to the ubiquity of API rate limiting. Replaced Twitter's unofficial 420 code.",
    },
    "431": {
        "description": "The server is unwilling to process the request because its header fields are too large. The request may be resubmitted after reducing the size of the headers.",
        "history": "Defined in RFC 6585 (2012). Often triggered by oversized cookies or excessively long authorization tokens. Most servers limit total header size to 8-16 KB.",
    },
    "444": {
        "description": "An nginx-specific status code where the server returns no information to the client and closes the connection. Used to deter malicious requests or bots.",
        "history": "Proprietary to the nginx web server. Not part of any RFC. Nginx uses this internally to instruct the server to return no response at all, effectively dropping the connection silently.",
    },
    "450": {
        "description": "A Microsoft extension indicating that the requested resource is blocked by Windows Parental Controls. The client should request access via the parental controls interface.",
        "history": "A Microsoft-proprietary status code used in Windows family safety features. Not part of any IETF standard.",
    },
    "451": {
        "description": "The server is denying access to the resource as a consequence of a legal demand. Named after Ray Bradbury's dystopian novel about censorship.",
        "history": "Defined in RFC 7725 (2016). The code number 451 was chosen as a reference to Fahrenheit 451, Bradbury's 1953 novel about a future society that burns books. Proposed by Tim Bray in 2012 and championed by the EFF.",
    },
    "494": {
        "description": "An nginx-specific status code indicating that the client sent too large of a request header. Similar to 431 but specific to nginx's internal handling.",
        "history": "Proprietary to the nginx web server. Used internally when the request header exceeds nginx's large_client_header_buffers configuration limit.",
    },
    "498": {
        "description": "An unofficial status code used by some services (notably ArcGIS) to indicate that an authentication token has expired or is otherwise invalid.",
        "history": "Used by Esri's ArcGIS Server. Not part of any IETF standard. Some other services have adopted it informally for token-related authentication failures.",
    },
    "499": {
        "description": "An unofficial status code. In nginx, it means the client closed the connection before the server could send a response. Also used by some services to indicate a required token is missing.",
        "history": "Used internally by nginx to log cases where the client disconnects early. Also used by ArcGIS and some other services for missing authentication tokens.",
    },
    "500": {
        "description": "The server encountered an unexpected condition that prevented it from fulfilling the request. The most generic server error response.",
        "history": "Part of the original HTTP specification (RFC 1945, 1996). The go-to server error code when something goes wrong that doesn't fit a more specific 5xx code. Every developer's least favorite status code.",
    },
    "501": {
        "description": "The server does not support the functionality required to fulfill the request. The server does not recognize the request method or lacks the ability to fulfill it.",
        "history": "Defined in HTTP/1.0 (RFC 1945, 1996). Returned when a server doesn't support a particular HTTP method. For example, a server that only handles GET and POST would return 501 for a PATCH request.",
    },
    "502": {
        "description": "The server, while acting as a gateway or proxy, received an invalid response from the upstream server it accessed while attempting to fulfill the request.",
        "history": "Defined in HTTP/1.0 (RFC 1945, 1996). Common when a reverse proxy (like nginx or Cloudflare) can't get a valid response from the application server behind it.",
    },
    "503": {
        "description": "The server is currently unable to handle the request due to temporary overloading or scheduled maintenance. The condition is expected to be temporary.",
        "history": "Defined in HTTP/1.0 (RFC 1945, 1996). Should include a Retry-After header. Commonly seen during deployments, traffic spikes, or when backend services are down.",
    },
    "504": {
        "description": "The server, while acting as a gateway or proxy, did not receive a timely response from the upstream server. The upstream server took too long to respond.",
        "history": "Defined in HTTP/1.0 (RFC 1945, 1996). Common when backend services are slow or unresponsive. Often seen with reverse proxies that have timeout limits.",
    },
    "505": {
        "description": "The server does not support the HTTP protocol version that was used in the request. For example, if a client sends an HTTP/2 request to a server that only supports HTTP/1.1.",
        "history": "Introduced in HTTP/1.1 (RFC 2068, 1997). Rare in practice since most servers support multiple HTTP versions and negotiate the version during connection setup.",
    },
    "506": {
        "description": "The server has an internal configuration error: transparent content negotiation for the request results in a circular reference.",
        "history": "Defined in RFC 2295 (1998) as part of Transparent Content Negotiation. An experimental protocol that was never widely adopted.",
    },
    "507": {
        "description": "The server is unable to store the representation needed to complete the request. The server's storage is full or the allocation for the user has been exceeded.",
        "history": "Introduced in WebDAV (RFC 2518, 1999). Can occur when a WebDAV server runs out of disk space or when a user exceeds their storage quota.",
    },
    "508": {
        "description": "The server detected an infinite loop while processing the request. This typically occurs in WebDAV when a resource is configured to reference itself.",
        "history": "Defined in RFC 5842 (2010) as part of WebDAV Binding Extensions. Detects circular references that would cause infinite recursion when traversing resource hierarchies.",
    },
    "509": {
        "description": "An unofficial status code used by some hosting providers to indicate that the website has exceeded its allocated bandwidth limit.",
        "history": "Not part of any RFC. Used by Apache and cPanel hosting environments when a site's monthly bandwidth allocation is exhausted. The site owner must wait for the limit to reset or upgrade their plan.",
    },
    "510": {
        "description": "The policy for accessing the resource has not been met in the request. The server requires additional extensions to fulfill the request.",
        "history": "Defined in RFC 2774 (2000) as part of HTTP Extension Framework. Indicates that the server needs specific extensions that the client didn't provide. Rarely encountered.",
    },
    "511": {
        "description": "The client needs to authenticate to gain network access. Typically used by captive portals (like hotel or airport WiFi) that intercept traffic and require login.",
        "history": "Defined in RFC 6585 (2012). Created specifically for captive portal scenarios. Before this code existed, captive portals would return misleading 200 responses with their login page.",
    },
    "530": {
        "description": "An unofficial status code used by some services (notably Cloudflare) to indicate that the origin server has been frozen or is otherwise inaccessible.",
        "history": "Used by Cloudflare and some hosting providers. Not part of any IETF standard. Pantheon hosting platform uses it to indicate that a site has been put into a frozen state.",
    },
}
