# jd-pitcher

Recruiter-facing mini app: paste a job description, get a short anonymized pitch for why the profile owner fits the role.

Designed to be embedded in a personal portfolio.

## What it does

- Reads profile evidence from `config/profile.yaml`
- Masks sensitive company names with `config/masks.yaml`
- Sends the masked profile + JD to an OpenAI-compatible LLM
- Returns a concise bullet-point pitch
- Logs requests to SQLite for monitoring

The default prompt is strict: it should only use direct evidence from the profile and avoid invented claims.

## Quick start

```bash
cp .env.example .env
cp config/profile.yaml.example config/profile.yaml
cp config/masks.yaml.example config/masks.yaml

vim .env                 # set LLM_API_KEY
vim config/profile.yaml  # add your actual profile evidence
vim config/masks.yaml    # map company_ref keys to anonymized names

docker compose up -d --build
```

Open:

```text
http://localhost:9100
```

Docker maps host port `9100` to container port `8080`.

## Configuration

Required env:

```bash
LLM_API_KEY=your_key_here
```

Main env knobs:

```bash
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
RATE_LIMIT_IP_HOUR=5
RATE_LIMIT_GLOBAL_DAY=50
MAX_JD_LENGTH=8000
LOG_DB_PATH=data/logs.sqlite
```

Main config files:

- `config/profile.yaml` — factual profile evidence: name, tagline, education, experience, projects, skills, meta
- `config/masks.yaml` — anonymized labels for every `company_ref`
- `config/prompt.md` — output rules, tone, and template variables

Prompt variables:

- `{{.Name}}`
- `{{.JD}}`
- `{{.MaskedProfile}}`

After profile, mask, prompt, or env changes:

```bash
docker compose restart
```

If Go code changed:

```bash
docker compose up -d --build
```

## Integrate into a website

### Iframe

```html
<iframe src="/recruit" width="100%" height="650" frameborder="0" loading="lazy"></iframe>
```

### Reverse proxy

Run the app on `9100:8080`, then route your portfolio path, for example `/recruit`, to the app.

Current compose mapping:

```yaml
ports:
  - "9100:8080"
```

The app serves from `/`, so the proxy should forward `/recruit` traffic to the app and preserve form/API requests under that path.

### API

```bash
curl -X POST https://yourdomain.com/recruit/api/pitch \
  -H "Content-Type: application/json" \
  -d '{"jd":"Paste JD here..."}'
```

Response:

```json
{
  "pitch": "...",
  "model_used": "deepseek-chat",
  "cached": false
}
```

## My live setup

My portfolio serves this app at `/recruit` behind a reverse proxy.

Runtime shape:

- Docker service: `jd-pitcher`
- Container port: `8080`
- Host port: `9100`
- Reverse proxy route: `/recruit`
- Bind mounts: `config/` and `data/`

Common commands from the project directory:

```bash
docker compose up -d --build          # rebuild after code changes
docker compose restart                # reload config/prompt/env changes
./scripts/last-log.py                 # latest pitch
./scripts/last-log.py -n 10 --compact # recent compact logs
docker compose logs -f jd-pitcher     # live logs
```

## Sync profile from a source file

Optional helper for generating `profile.yaml` and `masks.yaml` from a local source-of-truth Markdown file:

```bash
python3 scripts/sync_profile.py                 # dry run
python3 scripts/sync_profile.py --apply         # write files + rebuild
python3 scripts/sync_profile.py --force --apply # force rebuild
```

The script is idempotent: if generated files are unchanged, it skips rewriting them.

## Monitoring and safety

- Per-IP rate limit
- Global daily request cap
- Max JD length guard
- SQLite request logs
- Hashed IP logging
- Company-name masking before LLM calls

## Tech stack

- Go
- chi router
- SQLite via `modernc.org/sqlite`
- Docker Compose
- DeepSeek / OpenAI-compatible chat API

## License

MIT
