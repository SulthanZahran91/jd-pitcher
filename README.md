# jd-pitcher

> Let recruiters paste a job description and receive a persuasive, anonymized pitch for why *you* are the right hire. Designed as a forkable portfolio template.

---

## Quick Start

1. **Fork this repo**
2. **Fill your profile**
   ```bash
   cp config/profile.yaml.example config/profile.yaml
   cp config/masks.yaml.example config/masks.yaml
   # Edit both files with your background and anonymized entity mappings
   ```
3. **Add your API key**
   ```bash
   cp .env.example .env
   # Edit .env and set LLM_API_KEY
   ```
4. **Run**
   ```bash
   docker compose up -d
   ```
5. **Embed in your portfolio**
   ```html
   <iframe src="/recruit" width="100%" height="600" frameborder="0"></iframe>
   ```

---

## How It Works

1. Recruiter pastes a JD into the textarea
2. The app anonymizes your profile (company names are masked per `masks.yaml`)
3. A cheap LLM (DeepSeek Chat by default) generates a tailored pitch
4. The result is rendered as a clean HTML card

---

## Configuration

### `config/profile.yaml`

Your background data. Use `company_ref` keys that map to `masks.yaml`.

```yaml
name: "Your Name"
tagline: "Your tagline"
experience:
  - role: "Software Engineer"
    company_ref: "current_employer"
    duration: "2024–Present"
    highlights:
      - "Built thing X"
projects:
  - name: "CoolProject"
    url: "https://github.com/..."
    description: "What it does"
skills:
  - category: "Backend"
    items: ["Go", "Rust"]
meta:
  interests: ["distributed systems"]
  location: "City, Country"
```

### `config/masks.yaml`

Anonymize company names. The LLM prompt explicitly instructs the model to use these exact strings.

```yaml
entities:
  current_employer: "a Series B fintech startup"
  previous_employer: "a Fortune 500 cloud provider"
```

### `config/prompt.md`

Edit the system prompt to change tone, length, or style. Available template variables:
- `{{.Name}}` — your name
- `{{.JD}}` — the recruiter's pasted JD
- `{{.MaskedProfile}}` — your profile with company names replaced

---

## API (Agent-Friendly)

Agents can skip the UI entirely:

```bash
curl -X POST https://yourdomain.com/recruit/api/pitch \
  -H "Content-Type: application/json" \
  -d '{"jd": "Paste JD here..."}'
```

Response:
```json
{
  "pitch": "...",
  "model_used": "deepseek-chat",
  "cached": false
}
```

---

## Rate Limits & Safety

- **Per-IP:** Token bucket, configurable (default 5/hour)
- **Global:** Daily cap (default 50/day) to protect your API wallet
- **Max JD length:** 8000 characters
- **Logging:** SQLite append-only with SHA-256 hashed IPs (daily salt rotation)

## Monitoring

Check the latest submission and generated answer from the host:

```bash
cd /home/dev/hosted_projects/jd-pitcher
./scripts/last-log.py
```

Show the last 10 requests:

```bash
./scripts/last-log.py -n 10
```

Compact mode:

```bash
./scripts/last-log.py -n 10 --compact
```

Runtime logs:

```bash
docker compose logs -f jd-pitcher
```

---

## How I Use This

This section documents my personal workflow running this tool on my own portfolio.

### Live Setup

The service runs as a Docker container on my VPS, fronted by a Traefik reverse proxy at `zahranm.cloud/recruit`:

- **Deploy path:** `/home/dev/hosted_projects/jd-pitcher/`
- **Port:** container 8080 mapped to `172.17.0.1:9100` (Docker bridge for Traefik)
- **Rebuild & restart (binary changed):**
  ```bash
  docker compose up -d --build
  ```
- **Restart only (config/prompt changes):**
  ```bash
  docker compose restart
  ```

The `config/` and `data/` directories are bind-mounted, so editing YAML on the host takes effect after a container restart — no rebuild needed unless the Go binary changed.

### Populating profile.yaml

I keep `config/profile.yaml` current by editing it directly:

1. **Experience** — Each role uses a `company_ref` key that maps to an anonymized mask in `masks.yaml`. When I add a new role or update highlights, I edit the YAML and ensure the ref has a mask entry.
2. **Projects** — I add portfolio projects with their GitHub URL and a short description. The LLM uses these as evidence.
3. **Skills & meta** — Updated when I pick up new tools or interests relevant to my job search.

**Validation:** The app checks at startup that every `company_ref` in profile.yaml has a corresponding mask. If a ref is missing, the server refuses to start with a clear error message.

### Keeping Updated

There's no automated sync yet (a Hermes cron that pulls from Obsidian is in the backlog). Current workflow:

```bash
cd /home/dev/hosted_projects/jd-pitcher

# Edit profile
vim config/profile.yaml

# If I added a new company_ref, update masks too
vim config/masks.yaml

# Restart container
docker compose restart

# Verify
./scripts/last-log.py -n 3
```

For tone/style changes I edit `config/prompt.md` directly. Available template variables: `{{.Name}}`, `{{.JD}}`, `{{.MaskedProfile}}`.

### Monitoring

```bash
# Latest pitch
./scripts/last-log.py

# Last 10 compact
./scripts/last-log.py -n 10 --compact

# Live tail
docker compose logs -f jd-pitcher
```

My `.env` uses higher rate limits (100/hr IP, 1000/day global) than the fork defaults — this is my personal instance behind a reverse proxy with its own rate limiting and abuse protection upstream.

---

## Tech Stack

- **Go 1.23+** — single binary, no framework bloat
- **chi** — minimal router
- **modernc.org/sqlite** — pure Go SQLite (no CGO)
- **DeepSeek Chat** — OpenAI-compatible, ~$0.0015 per request

---

## License

MIT
