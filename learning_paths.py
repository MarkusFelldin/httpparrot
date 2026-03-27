"""Guided Learning Paths — curated sequences of activities for structured HTTP learning.

Each path has an id, title, description, difficulty level, and an ordered list
of steps.  Step types match existing app features:

- visit   : view a status-code detail page (target = code string)
- practice: complete a scenario exercise   (target = scenario id)
- debug   : complete a debug exercise      (target = exercise id string)
- quiz    : take a quiz round              (target = number of questions)
- learn   : study a confusion pair lesson  (target = pair slug)
"""

LEARNING_PATHS = [
    {
        "id": "http-foundations",
        "title": "HTTP Foundations",
        "description": "Start your HTTP journey with the most common success, redirect, and error codes. Build a solid base before tackling the tricky stuff.",
        "difficulty": "beginner",
        "steps": [
            {"type": "visit", "target": "200", "label": "Visit 200 OK"},
            {"type": "visit", "target": "201", "label": "Visit 201 Created"},
            {"type": "visit", "target": "204", "label": "Visit 204 No Content"},
            {"type": "practice", "target": 1, "label": "Practice: successful GET request"},
            {"type": "practice", "target": 3, "label": "Practice: successful POST creation"},
            {"type": "practice", "target": 6, "label": "Practice: successful resource deletion"},
            {"type": "learn", "target": "200-vs-204", "label": "Learn: 200 OK vs 204 No Content"},
            {"type": "quiz", "target": 5, "label": "Quiz: 5 questions"},
            {"type": "visit", "target": "301", "label": "Visit 301 Moved Permanently"},
            {"type": "visit", "target": "302", "label": "Visit 302 Found"},
            {"type": "visit", "target": "404", "label": "Visit 404 Not Found"},
            {"type": "practice", "target": 2, "label": "Practice: page not found"},
            {"type": "practice", "target": 5, "label": "Practice: moved permanently"},
            {"type": "practice", "target": 7, "label": "Practice: unauthorized access"},
        ],
    },
    {
        "id": "error-whisperer",
        "title": "Error Whisperer",
        "description": "Master the 4xx and 5xx error codes that trip up even experienced developers. Learn to diagnose, distinguish, and debug them.",
        "difficulty": "intermediate",
        "steps": [
            {"type": "visit", "target": "400", "label": "Visit 400 Bad Request"},
            {"type": "visit", "target": "401", "label": "Visit 401 Unauthorized"},
            {"type": "visit", "target": "403", "label": "Visit 403 Forbidden"},
            {"type": "visit", "target": "404", "label": "Visit 404 Not Found"},
            {"type": "visit", "target": "500", "label": "Visit 500 Internal Server Error"},
            {"type": "learn", "target": "401-vs-403", "label": "Learn: 401 vs 403"},
            {"type": "learn", "target": "400-vs-422", "label": "Learn: 400 vs 422"},
            {"type": "debug", "target": "200-error-body", "label": "Debug: 200 with error body"},
            {"type": "debug", "target": "403-instead-of-401", "label": "Debug: 403 instead of 401"},
            {"type": "debug", "target": "500-validation-error", "label": "Debug: 500 for validation error"},
            {"type": "debug", "target": "404-for-method", "label": "Debug: 404 for wrong method"},
            {"type": "debug", "target": "401-no-www-auth", "label": "Debug: 401 without WWW-Authenticate"},
            {"type": "practice", "target": 9, "label": "Practice: rate-limited API"},
            {"type": "practice", "target": 10, "label": "Practice: wrong HTTP method"},
            {"type": "practice", "target": 11, "label": "Practice: conflict on update"},
            {"type": "practice", "target": 12, "label": "Practice: payload too large"},
            {"type": "practice", "target": 13, "label": "Practice: unsupported media type"},
        ],
    },
    {
        "id": "redirect-master",
        "title": "Redirect Master",
        "description": "Conquer the full family of 3xx redirect codes. Understand when to use permanent vs temporary, and when method preservation matters.",
        "difficulty": "advanced",
        "steps": [
            {"type": "visit", "target": "300", "label": "Visit 300 Multiple Choices"},
            {"type": "visit", "target": "301", "label": "Visit 301 Moved Permanently"},
            {"type": "visit", "target": "302", "label": "Visit 302 Found"},
            {"type": "visit", "target": "303", "label": "Visit 303 See Other"},
            {"type": "visit", "target": "304", "label": "Visit 304 Not Modified"},
            {"type": "visit", "target": "307", "label": "Visit 307 Temporary Redirect"},
            {"type": "visit", "target": "308", "label": "Visit 308 Permanent Redirect"},
            {"type": "learn", "target": "301-vs-302", "label": "Learn: 301 vs 302"},
            {"type": "learn", "target": "307-vs-308", "label": "Learn: 307 vs 308"},
            {"type": "learn", "target": "302-vs-307", "label": "Learn: 302 vs 307"},
            {"type": "practice", "target": 18, "label": "Practice: permanent API move"},
            {"type": "practice", "target": 19, "label": "Practice: method-preserving redirect"},
            {"type": "practice", "target": 20, "label": "Practice: POST/redirect/GET pattern"},
            {"type": "practice", "target": 21, "label": "Practice: conditional caching"},
            {"type": "practice", "target": 22, "label": "Practice: partial content response"},
            {"type": "debug", "target": "301-no-location", "label": "Debug: 301 missing Location"},
            {"type": "debug", "target": "302-post-form", "label": "Debug: 302 drops POST body"},
            {"type": "debug", "target": "post-301-redirect", "label": "Debug: POST with 301 redirect"},
        ],
    },
]

# Quick lookup by path id
LEARNING_PATHS_BY_ID = {p["id"]: p for p in LEARNING_PATHS}
