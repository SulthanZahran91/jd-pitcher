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

---

## Tech Stack

- **Go 1.23+** — single binary, no framework bloat
- **chi** — minimal router
- **modernc.org/sqlite** — pure Go SQLite (no CGO)
- **DeepSeek Chat** — OpenAI-compatible, ~$0.0015 per request

---

## License

MIT
