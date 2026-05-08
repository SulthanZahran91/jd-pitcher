# jd-pitcher — Implementation Plan

> A minimal, config-driven Go service that lets recruiters paste a job description and receive a persuasive, anonymized pitch for why *you* are the right hire. Designed as a forkable portfolio template.

---

## 1. Philosophy

- **Single binary.** One `main.go` (or a flat `internal/` package tree). No framework bloat.
- **Config-driven.** Zero hardcoded personal data. Fork → fill YAML → deploy.
- **Agent-friendly.** The `/pitch` endpoint is a clean API. Agents can POST a JD and get structured JSON *or* rendered HTML.
- **Cheap.** DeepSeek Chat by default. ~$0.001–0.003 per request.
- **Isolated.** Docker-only bind-mount: `./config/` and `./data/`. No vault access.

---

## 2. Directory Structure

```
jd-pitcher/
├── PLAN.md                 # this file
├── README.md               # user-facing setup guide
├── go.mod
├── main.go                 # entrypoint: router + server
├── .env.example            # template for environment variables
├── Dockerfile              # multi-stage build, distroless or alpine
├── docker-compose.yml      # one-command deploy
├── config/
│   ├── profile.yaml        # USER-FILLED: experience, projects, skills
│   ├── masks.yaml          # USER-FILLED: entity → anonymized string
│   └── prompt.md           # USER-EDITABLE: LLM system prompt
├── internal/
│   ├── config.go           # load YAML + env
│   ├── limiter.go          # IP + global rate limiting
│   ├── anonymizer.go       # mask entities before LLM call
│   ├── llm.go              # DeepSeek HTTP client
│   ├── renderer.go         // HTML template rendering
│   └── logger.go           // SQLite usage logging
├── web/
│   ├── index.html          // landing page (Go template or static)
│   ├── style.css           // single-file CSS, dark/light support
│   └── result.tmpl         // HTML card template for the pitch output
└── data/
    └── .gitkeep            // runtime: logs.sqlite created here
```

---

## 3. Config Schemas

### 3.1 `config/profile.yaml`

```yaml
name: "Sulthan Zahran"
tagline: "Software Engineer · Smart Factory · LLM Tooling"

experience:
  - role: "Software Engineer"
    company_ref: "lg_sinarmas"
    duration: "2024–Present"
    highlights:
      - "Deployed edge AI pipelines for manufacturing QA"
      - "Built internal logistics platform processing 10k+ events/day"

projects:
  - name: "Clanker"
    url: "https://github.com/SulthanZahran91/clanker"
    description: "AI-assisted engineering wiki system"

skills:
  - category: "Backend"
    items: ["Go", "Python", "PostgreSQL"]
  - category: "ML/AI"
    items: ["LLM orchestration", "OpenAI API", "prompt engineering"]

meta:
  interests: ["industrial IoT", "physics-informed ML"]
  location: "Jakarta, Indonesia"
```

### 3.2 `config/masks.yaml`

```yaml
entities:
  lg_sinarmas: "a Fortune 500 industrial conglomerate in Southeast Asia"
  ditra: "an internal logistics intelligence platform"
  xiaomi: "a global consumer electronics manufacturer"
```

**Rule:** `company_ref` values in `profile.yaml` are replaced verbatim by the masked value before the LLM prompt is constructed.

### 3.3 `config/prompt.md`

Jinja/Go-template style prompt. The application injects the masked profile and the raw JD.

```markdown
You are {{.Name}}'s career advocate. A recruiter posted this JD:

--- JD ---
{{.JD}}
--- END ---

Here is {{.Name}}'s background. Company names have been anonymized:
{{.MaskedProfile}}

Write a 200–300 word pitch explaining why {{.Name}} is an exceptional fit.
- Map specific JD requirements to evidence from the background
- Use the anonymized company names exactly as provided
- Do not invent or assume anything not in the profile
- Tone: confident but not arrogant, evidence-driven
```

### 3.4 `.env` (runtime)

```bash
# Server
PORT=8080

# LLM (DeepSeek default, but any OpenAI-compatible endpoint works)
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_API_KEY=sk-...
LLM_MODEL=deepseek-chat
LLM_MAX_TOKENS=600
LLM_TEMPERATURE=0.6

# Rate Limits
RATE_LIMIT_IP_HOUR=5          # per-IP bucket (rolling window)
RATE_LIMIT_GLOBAL_DAY=50      # global daily cap
MAX_JD_LENGTH=8000            # character cap, not token cap

# Logging
LOG_DB_PATH=data/logs.sqlite
```

---

## 4. API Design

### 4.1 `GET /`
Serve `web/index.html` — the landing page with a single textarea and submit button.

### 4.2 `POST /api/pitch`
**Request:**
```json
{
  "jd": "string (required, max 8000 chars)"
}
```

**Response (JSON):**
```json
{
  "pitch": "string",
  "model_used": "deepseek-chat",
  "cached": false
}
```

**Agent Integration Note:**
Agents can hit `/api/pitch` with `Accept: application/json` and skip the UI entirely.

### 4.3 `POST /pitch` (form / HTMX / vanilla JS)
Accept `application/x-www-form-urlencoded` or `multipart/form-data`.
Returns rendered `web/result.tmpl` HTML card directly.

This keeps the frontend JS-free or near-JS-free.

---

## 5. Core Components

### 5.1 Rate Limiter (`internal/limiter.go`)

Two-tier in-memory limiting (no Redis needed for this scale):

1. **Per-IP bucket:** Token bucket, refill 1 token every `60 / RATE_LIMIT_IP_HOUR` minutes. Key by SHA-256(IP + daily salt) so IPs aren't stored raw.
2. **Global daily cap:** Atomic counter, resets at 00:00 UTC (or on restart — acceptable for MVP).

If a limit is hit, return `429 Too Many Requests` with a `Retry-After` header.

### 5.2 Anonymizer (`internal/anonymizer.go`)

- Load `masks.yaml` into a `map[string]string`.
- Walk `profile.yaml` after unmarshalling. Replace every `company_ref` value with its mask.
- Serialize the masked profile into a Markdown string for injection into the prompt.
- **Fail-safe:** If a `company_ref` has no mask entry, error at startup (fail fast).

### 5.3 LLM Client (`internal/llm.go`)

- OpenAI-compatible HTTP client. DeepSeek's API is `/chat/completions` compatible.
- Request structure:
  ```json
  {
    "model": "deepseek-chat",
    "messages": [
      {"role": "system", "content": "<rendered prompt.md>"},
      {"role": "user", "content": "<JD>"}
    ],
    "max_tokens": 600,
    "temperature": 0.6
  }
  ```
- Timeout: 30s.
- Parse only `choices[0].message.content`.

### 5.4 HTML Renderer (`internal/renderer.go`)

- Load `web/result.tmpl` at startup.
- Inject the pitch text into a clean card layout.
- The card shares CSS variables with `web/style.css` so it matches the landing page exactly.

### 5.5 Logger (`internal/logger.go`)

SQLite append-only table:
```sql
CREATE TABLE IF NOT EXISTS requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    ip_hash TEXT NOT NULL,
    jd_length INTEGER,
    jd_prefix TEXT,          -- first 80 chars for dedup/debug
    model_used TEXT,
    status TEXT              -- 'success', 'rate_limited', 'error'
);
```

**No PII:** IP is SHA-256 hashed with a daily rotating salt.

---

## 6. Frontend

### 6.1 Landing Page (`web/index.html`)

- Dark mode default (matches portfolio aesthetic).
- Single `<textarea>` placeholder: *"Paste the full job description here…"*
- Submit button: *"Generate Pitch"*
- Small footer copy: *"This tool uses anonymized background data to explain fit. No personal contact info is shared."*

### 6.2 HTML Card (`web/result.tmpl`)

Rendered inline or on a new page:

```html
<article class="pitch-card">
  <header>
    <h2>Why {{.Name}} is a strong fit</h2>
    <span class="badge">Generated via AI</span>
  </header>
  <div class="pitch-body">
    {{.Pitch | markdownToHTML}}
  </div>
  <footer>
    <p class="disclaimer">This pitch is auto-generated from anonymized profile data.</p>
  </footer>
</article>
```

**CSS Requirements:**
- Single `style.css`.
- CSS custom properties for colors so the card is themeable.
- Mobile-first, max-width ~640px for readability.

### 6.3 Minimal JS

Zero-framework. Optional vanilla JS to POST via `fetch` and swap the DOM, or use a simple form POST to `/pitch` and let the server return the full card HTML.

For agents: they don't touch the UI at all.

---

## 7. Docker & Deployment

### 7.1 Dockerfile

Multi-stage:
1. `golang:1.23-alpine` → build static binary with `CGO_ENABLED=0`.
2. `scratch` or `alpine` → copy binary, `config/`, `web/`.

### 7.2 docker-compose.yml

```yaml
services:
  jd-pitcher:
    build: .
    ports:
      - "127.0.0.1:9100:8080"
    env_file: .env
    volumes:
      - ./config:/app/config:ro
      - ./data:/app/data
    restart: unless-stopped
```

**Note:** Expose on `127.0.0.1:9100` only. The main portfolio's reverse proxy (nginx/Traefik) routes `zahranm.cloud/recruit` → `jd-pitcher:8080`.

### 7.3 Embedding into zahranm.cloud (Iframe)

The app runs as a self-contained page embedded in your portfolio via `<iframe>`.

**Reverse proxy route:**
```yaml
# Traefik
http:
  routers:
    jd-pitcher:
      rule: "Host(`zahranm.cloud`) && PathPrefix(`/recruit`)"
      service: jd-pitcher
      middlewares:
        - jd-pitcher-strip
      tls:
        certResolver: letsencrypt
  services:
    jd-pitcher:
      loadBalancer:
        servers:
          - url: "http://172.17.0.1:9100"
  middlewares:
    jd-pitcher-strip:
      stripPrefix:
        prefixes:
          - "/recruit"
```

**Portfolio HTML snippet:**
```html
<section id="recruit">
  <h2>Hiring? Paste your JD</h2>
  <iframe src="/recruit" width="100%" height="600" frameborder="0" loading="lazy">
  </iframe>
</section>
```

**Why iframe:**
- The Go app owns its own CSS and layout — no style leaking or conflicts with your portfolio.
- The template remains forkable: others embed the same way without rebuilding your frontend.
- Mobile sizing handled by the iframe container (CSS `aspect-ratio` or fixed height).

**Go app routing:** Serves from root (`/`, `/api/pitch`, `/pitch`) since the proxy strips `/recruit`. Internal links stay relative.

---

## 8. Agent Integration

Since the user mentioned people will integrate this with agents:

- **Endpoint:** `/api/pitch` accepts JSON, returns JSON.
- **No auth required** (rate limits are the gate).
- **Idempotent-ish:** Same JD + same profile config = same-ish output. No caching layer for MVP.
- **Structured output option:** Later we could support a `?format=structured` query param that returns JSON with `matches[]` array (JD req → evidence mapping). Out of scope for v1.

---

## 9. Implementation Phases

### Phase 1 — Skeleton & Config (1–2 hrs)
- [ ] `go mod init github.com/SulthanZahran91/jd-pitcher`
- [ ] `main.go` with `chi` router: `GET /`, `POST /api/pitch`, `POST /pitch`
- [ ] `internal/config.go`: load `.env`, `profile.yaml`, `masks.yaml`, `prompt.md`
- [ ] Validate at startup: all `company_ref`s must have a mask entry.
- [ ] Static file server for `web/`.

### Phase 2 — Core Logic (2–3 hrs)
- [ ] `internal/anonymizer.go`: mask profile into Markdown string.
- [ ] `internal/llm.go`: DeepSeek chat completions client.
- [ ] `internal/limiter.go`: in-memory token bucket + global counter.
- [ ] Wire them into the `POST /api/pitch` handler.

### Phase 3 — Frontend (1–2 hrs)
- [ ] `web/index.html` + `web/style.css` (dark, clean, single-file).
- [ ] `web/result.tmpl` card template.
- [ ] `POST /pitch` form handler that renders the template.

### Phase 4 — Logging & Safety (1 hr)
- [ ] `internal/logger.go`: SQLite setup + write on every request.
- [ ] IP hashing with daily salt.
- [ ] `MAX_JD_LENGTH` enforcement.

### Phase 5 — Docker & Deploy (1 hr)
- [ ] Dockerfile + docker-compose.yml.
- [ ] Traefik router config.
- [ ] Test end-to-end on `jd.zahranm.cloud`.

### Phase 6 — GitHub & Docs (1 hr)
- [ ] Public repo.
- [ ] `README.md`: fork instructions, schema docs, deploy guide.
- [ ] `.env.example` and `config/*.example.yaml`.

---

## 10. Open Questions (Post-v1)

1. **Profile sync cron:** A dedicated Hermes cron that rebuilds `profile.yaml` + `masks.yaml` from your Obsidian vault. This lives *outside* the container and commits to the repo.
2. **Structured output:** `?format=json` returning `{matches: [{jd_req, evidence, strength}]}` for agents that want to reason over the fit.
3. **Cache layer:** Redis or in-memory LRU to avoid re-paying for identical JDs.

---

## 11. Cost Projection

| Metric | Value |
|--------|-------|
| DeepSeek Chat input | ~2k tokens (prompt + JD) |
| DeepSeek Chat output | ~400 tokens |
| Cost per request | ~$0.0015 |
| Daily cap (50 req) | ~$0.075 / day = ~$2.25 / month |

Very survivable.

---

Ready to start Phase 1 when you are.
