# HTTP Parrots

Every HTTP status code, explained by parrots.

A fun, interactive reference for HTTP status codes featuring cartoon parrot illustrations, detailed explanations, code examples, gamified learning, and developer tools.

## Features

**Browse** - Gallery of 72 HTTP status codes with fuzzy search across all pages, category filtering, bento grid homepage dashboard with smart recommender, POTD badge on featured cards, and an enhanced "Parrot of the Day" section with fun facts and sharing. Global search with live dropdown for instant navigation.

**Learn** - Each status code has:
- Description and history with clickable RFC links
- Real-world examples ("When would I see this?")
- 135 case studies ("In the Wild") across 70 status codes with real-world service examples
- 96 common mistakes across 48 status codes with consequence explanations
- 15 "When NOT to use" sections with guidance on choosing the right code
- Code snippets in 5 languages: Python, Node.js, Go, Java, and Rust
- Example HTTP request/response exchange with syntax highlighting and animated line-by-line display
- Typical response headers
- "Commonly confused with" links to related status codes (with deep links to confusion pair lessons when available)
- Copy-as-curl button for the `/return/<code>` endpoint
- **ELI5 mode** - Toggle "Simple mode" for fun, plain-language analogies (all 72 codes)
- **Interactive parrot clicks** - Click any parrot for code-specific fun facts and category-themed animations (1xx pulses, 2xx glows, 3xx slides, 4xx shakes, 5xx glitches)
- **Share buttons** - Native Share API, Twitter/X, Slack, Discord, copy link
- **Embed codes** - Copy HTML, Markdown, or direct image URL for any parrot

**Structured learning**
- **Confusion Pair Lessons** (`/learn`) - 18 in-depth lesson pages explaining commonly confused status code pairs (e.g. 401 vs 403, 301 vs 302, 502 vs 503, 404 vs 410, 429 vs 503), grouped by category
- **Guided Learning Paths** (`/paths`) - 4 curated tracks (HTTP Foundations, Error Whisperer, Redirect Master, API Designer) with step-by-step checklists mixing visits, practice, quizzes, and lessons; completion certificates on finishing a path
- **Status Code Map** (`/map`) - Interactive relationship visualization showing how codes connect, with click-to-explore connections and category filters
- **Guess the Response** (`/predict`) - Reverse quiz where you type in the status code based on a scenario description
- **Spaced Repetition Review** (`/review`) - Leitner box-based review queue pulling from scenarios, debug exercises, and confusion pairs for long-term retention

**Interactive tools**
- **Quiz** (`/quiz`) - Guess the status code from the parrot image (10 questions per round) with adaptive difficulty weighted by past mistakes and confetti combo escalation
- **Daily Challenge** (`/daily`) - Wordle-style daily quiz with streak tracking, streak freeze, milestones, shareable results, and suggested next actions
- **Weekly Challenge** (`/weekly`) - 5-question themed challenges rotating through 8 themes (Redirect Week, Auth Week, Error Week, etc.) with challenge history; Theme Master feather for perfect scores
- **Scenario Practice** (`/practice`) - 56 real-world API scenarios (including 5 security category) sorted by difficulty (beginner/intermediate/expert) with category filters and results summary
- **Debug Exercises** (`/debug`) - 36 "Debug This Response" exercises with broken HTTP exchanges to diagnose, organized by category, with results summary
- **HTTP Personality Quiz** (`/personality`) - "Which HTTP Status Code Are You?" fun personality quiz
- **Flowchart** (`/flowchart`) - Interactive decision tree to pick the right status code
- **Compare** (`/compare`) - Side-by-side comparison with visual diff, presets (401 vs 403, etc.), swap button, empty state guidance, and smooth page transitions
- **HTTP Tester** (`/tester`) - Enter a URL and see what status code it returns, with GET mode body preview, timing bar, and truncation warning for large responses
- **Response Playground** (`/playground`) - Build custom HTTP responses with live preview and 11 presets
- **Header Explainer** (`/headers`) - Paste HTTP headers for instant color-coded explanations
- **CORS Checker** (`/cors-checker`) - Test CORS policies for any URL with preflight analysis
- **Security Header Audit** (`/security-audit`) - Scan any URL for security header best practices with letter grades (A+ to F)
- **cURL Import/Parse** (`/curl-import`) - Paste a cURL command to break down method, headers, body, and flags; import directly into the Response Playground
- **Redirect Tracer** (`/trace`) - Visualize full redirect chains with timing, headers, and SSRF protection at every hop
- **Fault Simulator** (`/fault-simulator`) - Simulate network faults: configurable delay, byte drip, JSON streaming, random jitter, and unstable endpoints
- **Webhook Inspector** (`/webhook-inspector`) - Create ephemeral request bins to capture and inspect incoming webhooks (1-hour TTL, 50 requests max)
- **Content Negotiation** (`/content-negotiation`) - Interactive tool demonstrating how Accept, Accept-Encoding, and Accept-Language headers affect server responses
- **Cheat Sheet** (`/cheatsheet`) - Printable single-page reference with parrot thumbnails, filter/search, and compact toggle
- **Parrotdex** (`/collection`) - Gamified collection tracker for visited status codes with milestones (10/25/50/72), category progress bars, and Konami code party mode
- **Command Palette** - Press Cmd+K (Mac) or Ctrl+K (Windows/Linux) to open a global command palette for instant navigation

**XP & gamification**
- **XP System** - Earn XP from quizzes, daily challenges, practice scenarios, debug exercises, and exploration
- **Profile Page** (`/profile`) - View total XP, rank, activity history, weekly history chart, and earned badges
- **Customizable Profile** - Choose a spirit parrot avatar and theme accent color from the profile page
- **Profile Sharing** - Share your profile via flock codes so others can see your progress
- **Flock Formation Celebrations** - Animated celebrations when sharing or viewing flock profiles
- **10 Ranks** - Progress from Fledgling through Nestling, Feathered Apprentice, Wing Cadet, Parrot Scout, Plume Knight, Wing Commander, Sky Captain, Grand Macaw, to Legendary Lorikeet
- **29 Achievement Badges** ("Feathers") - 23 base feathers (First Flight, Quiz Whiz, Perfect 10, Streak Starter, On Fire, Centurion, Wing Commander, Completionist, Error Expert, Server Sage, Egg Hunter, Scholar, Night Owl, Speed Demon, Frozen Solid, Memory Master, Parrot Petter, Photographic Memory, Loyal Parrot, Theme Master, Explorer 10, Explorer 25, Explorer 50) + 6 meta feathers (Explorer, Polyglot, Streak Lord, Triple Threat, Full Spectrum, Parrot Polymath)
- **Meta-Feather Unlock Animations** - Egg-hatch pre-animation (wobble → crack → pop) then golden confetti burst and screen shake
- **Prestige System** - After reaching Legendary Lorikeet, reset XP for a permanent +10% XP bonus per prestige level (up to 10 stars)
- **Weekly Leaderboard Tiers** - Bronze/Silver/Gold/Platinum tiers based on weekly XP with progress bar on profile
- **Achievement Progress Indicators** - Locked feathers show progress bars (e.g., Quiz Whiz 7/10, Explorer 25 shows 18/25)
- **Top 3 Rarest Feathers Showcase** - Shareable profile card highlights your rarest achievements
- **Parrot Mood Ring** - XP badge color shifts with category-specific pulse animations (cyan/teal/gold/coral/purple) based on recent browsing
- **Parrot Collector Badges** - Green/silver/gold checkmarks on homepage cards for visited status codes
- **XP Multiplier Chain** - Consecutive daily visits build a 1.0x to 2.0x XP multiplier, shown as a glowing gold badge indicator
- **Weekly Bingo** (`/bingo`) - 5x5 bingo card of status codes, mark off by visiting pages, auto-syncs with Parrotdex, detects rows/cols/diagonals, 75 XP per weekly bingo
- **Daily Horoscope** (`/horoscope`) - Personalized HTTP-themed fortune based on spirit parrot, with lucky codes and share button; 30-day streak easter egg
- **Category Speed Runs** - Timed challenge to visit all codes in a category, triggered by category filter on homepage
- **Status Code Mastery** - Per-code mastery tracking (0-3 stars) based on visits, quiz, and practice performance
- **Quiz Confetti Combos** - Streaks of 5/10/15 trigger escalating confetti bursts with "COMBO!", "SUPER COMBO!", and "MEGA COMBO!" text
- **Daily Login Rewards** - Calendar-based daily rewards for visiting the site, completing a full 7-day cycle earns the Loyal Parrot badge
- **Daily Streak** tracking with streak freeze support and milestone celebrations
- All gamification state stored client-side in localStorage (no account required)

**Interactive details & visual polish**
- Category-themed hover effects: 1xx pulses, 2xx glows, 3xx slides sideways, 4xx shakes, 5xx glitches
- Interactive parrot clicks with category-specific animations on detail pages
- Speech bubbles with typewriter effect -- each parrot has a witty one-liner
- 25+ easter eggs: 204 fades to nothing, 418 has steam, 429 spawns tiny parrots, 508 spins, Konami code, `/coffee` page, barrel roll, parrot whisperer, click frenzy, footer party, midnight insomnia parrot (11PM-4AM with absurdist tips), 200th page visit celebration, time-based messages, console API, and more
- 404 memory card game -- find matching parrot pairs on the 404 page with replay and best time tracking
- Procedural sound effects for interactions
- View transitions between pages
- Seasonal themes
- Animated HTTP request/response exchanges with syntax highlighting
- Enhanced bento grid homepage dashboard with smart recommender
- Aurora gradient background with animated floating orbs
- Glassmorphism card hover effects with category-colored inner glow
- CSS scroll-driven animations with diagonal cascade card entry
- Scroll progress indicator
- Breadcrumb navigation
- Back-to-top buttons on long pages
- Tactile micro-interactions (spring-physics easing, bounce, press states)
- Breathing animation on idle elements
- CSS design system with full tokenization (spacing, color, typography hierarchy, and elevation tokens)
- Skeleton loading animations with shimmer effect for async tool results
- Global toast notification system for copy/action feedback
- HTTP method filter pills on homepage (GET/POST/PUT/DELETE/PATCH)
- Button hover lift micro-animations with unified 3-level depth system and CSS ripple feedback
- Touch swipe navigation on mobile detail pages (swipe left/right for prev/next code)
- Page load fade-in animation (translateY + opacity with reduced-motion support)
- Mobile polish (optimized for 320px-375px, expanded quiz touch targets to 56px)
- Request history panel on URL Tester with search, replay, cURL/HAR export
- Cross-tool linking: test a URL then jump to Redirect Tracer, Security Audit, or CORS Checker
- Empty state patterns for Review and Parrotdex pages
- Complete light theme support with boosted color saturation and enhanced depth
- Print stylesheet for cheat sheet and all pages
- Double-click-to-copy on code example blocks
- Form validation on all tool pages (tester, headers, CORS checker, security audit, trace, playground, curl import)

**API** - Programmatic access to all data:
- `GET /<code>` with `Accept: application/json` returns JSON
- `GET /<code>.jpg` returns the parrot image directly
- `GET /return/<code>` returns an actual HTTP response with that status code (supports `?delay=N` for simulated latency)
- `GET /api/check-url?url=<url>` checks what status code a URL returns
- `GET /api/fetch-url?url=<url>` fetches a URL with GET and returns status, headers, and body preview
- `GET /api/diff?code1=X&code2=Y` compares two status codes
- `GET /api/search?q=keyword` searches codes by name, description, or number (with fuzzy fallback)
- `POST /api/mock-response` creates custom HTTP responses (JSON body: status_code, headers, body)
- `GET /api/check-cors?url=<url>&origin=<origin>` tests CORS policies with preflight analysis
- `GET /api/security-audit?url=<url>` audits response headers for security best practices
- `GET /api/trace-redirects?url=<url>` follows redirect chains and returns each hop with timing
- `GET /api/delay/<seconds>` delays response by N seconds (max 10)
- `GET /api/drip?duration=N&numbytes=N` streams bytes slowly over a duration
- `GET /api/stream/<n>` streams n JSON lines, one per second
- `GET /api/jitter?min=N&max=N` responds after random delay in ms range
- `GET /api/unstable?failure_rate=0.5` randomly returns 200 or 500
- `POST /api/bin/create` creates a webhook bin and returns its hook URL
- `GET /api/bin/<bin_id>` retrieves captured requests for a bin
- `GET /echo` echoes requests back (all methods, `?format=pretty|curl`)
- `GET /redirect/<n>` chain of n redirects ending at 200
- `GET /feed.xml` RSS feed with daily parrot
- `GET /random` redirects to a random status code
- `GET /sitemap.xml` dynamic XML sitemap

Full API documentation at `/api-docs`, including Slack and Discord bot integration guides.

**Accessibility**
- WCAG AA color contrast compliance
- Full ARIA labels, roles, and live regions across all pages
- Keyboard navigable with visible focus indicators
- Keyboard shortcuts overlay (press `?` to show)
- Screen reader support for quiz scores, streaks, and dynamic content
- `prefers-reduced-motion` support (disables all animations)
- `prefers-color-scheme: light` theme (complete coverage)
- Print stylesheet for all pages (optimized for cheat sheet)
- Responsive hamburger menu for mobile navigation

## Keyboard shortcuts

| Key | Page | Action |
|-----|------|--------|
| `?` | Any page | Toggle keyboard shortcuts overlay |
| `/` | Homepage | Focus search |
| `Escape` | Homepage | Blur search |
| Arrow keys | Homepage | Navigate the grid |
| `Enter` | Homepage | Open focused card |
| `<` `>` | Detail page | Previous / next status code |
| `1`-`4` | Quiz | Select answer |
| `Enter` | Quiz | Next question |
| `1`-`4` | Daily challenge | Select answer |
| `1`-`4` | Weekly challenge | Select answer |
| `Cmd+K` / `Ctrl+K` | Any page | Open command palette |

## CLI

Look up HTTP status codes from the terminal:

```bash
./cli/httpparrot 404        # Look up a code
./cli/httpparrot 4xx        # List a category
./cli/httpparrot all        # List all codes
./cli/httpparrot teapot     # Search by keyword
./cli/httpparrot redirect   # Search descriptions
```

No dependencies required -- just Python 3.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
flask --app index run
```

## Running tests

```bash
pip install -r requirements-dev.txt
python -m pytest test_app.py test_cli.py -v
```

There are 1766 automated tests covering routes, API endpoints, security, gamification, and CLI.

## Tech stack

- Python 3.11 / Flask 3.1
- Jinja2 templates with template inheritance (31 templates)
- Custom CSS with design tokens, glassmorphism, scroll-driven animations, view transitions, seasonal themes, light/dark modes (no framework dependencies)
- Vanilla JavaScript with localStorage-based gamification (no external dependencies)
- 1766 automated tests with 97%+ code coverage
- gzip compression via flask-compress

## Security

- SSRF protection with IP validation and DNS rebinding prevention on all outbound-request endpoints
- Content Security Policy with per-request nonces (no unsafe-inline)
- HSTS, X-Frame-Options, X-Content-Type-Options, Referrer-Policy, and Permissions-Policy headers
- XSS-safe templates (Jinja2 auto-escaping, safe DOM APIs in JavaScript)
- Rate limiting on outbound request endpoints (10 requests/minute per IP)
- Sensitive header stripping on echo and webhook endpoints (Authorization, Cookie, etc.)
- Security-sensitive headers blocked in mock-response endpoint
- CRLF injection prevention in custom headers
- 1MB request body limit
- No external JavaScript dependencies

## Deployment

The included `Procfile` runs the app with gunicorn:

```
web: gunicorn index:app --preload --workers 2
```

Set the `SECRET_KEY` environment variable in production.

## License

See [LICENSE](LICENSE).
