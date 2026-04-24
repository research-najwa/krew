# Krew Deployment Guide — Vercel + Railway

## Architecture

```
[Vercel]                    [Railway]
 Next.js frontend  ──API──>  FastAPI backend
                             PostgreSQL (pgvector)
                             Redis
```

## Step 1: Railway — Backend + Database + Redis

### 1a. Create Railway project
1. Go to https://railway.app and sign in
2. Click **New Project** → **Empty Project**

### 1b. Add PostgreSQL
1. Click **+ New** → **Database** → **PostgreSQL**
2. Railway auto-creates `DATABASE_URL` — note it down
3. Enable pgvector: in the PostgreSQL service settings, run in the **Query** tab:
   ```sql
   CREATE EXTENSION IF NOT EXISTS vector;
   ```

### 1c. Add Redis
1. Click **+ New** → **Database** → **Redis**
2. Railway auto-creates `REDIS_URL` — note it down

### 1d. Deploy Backend
1. Click **+ New** → **GitHub Repo** → select your repo
2. Set **Root Directory** to `backend`
3. Railway detects the Dockerfile automatically

### 1e. Set Environment Variables
In the backend service, go to **Variables** and add:

| Variable | Value |
|----------|-------|
| `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` (Railway reference) |
| `REDIS_URL` | `${{Redis.REDIS_URL}}` (Railway reference) |
| `ANTHROPIC_API_KEY` | Your Anthropic key |
| `OPENAI_API_KEY` | Your OpenAI key |
| `JWT_SECRET` | Generate: `openssl rand -hex 32` |
| `APP_ENV` | `production` |
| `CORS_ORIGINS` | `https://your-app.vercel.app` |
| `LLM_MODEL` | `claude-sonnet-4-6` |
| `EMBEDDING_MODEL` | `text-embedding-3-small` |

**Important:** Replace `DATABASE_URL` prefix from `postgresql://` to `postgresql+asyncpg://` if Railway gives you the sync format.

### 1f. Deploy
Railway auto-deploys on push. The `railway.toml` runs migrations (`alembic upgrade head`) before starting the server.

Note your backend URL: `https://your-backend.up.railway.app`

### 1g. Seed the database
After first deploy, open Railway's terminal for the backend service and run:
```bash
python -m app.scripts.seed  # or whatever your seed script is
```

---

## Step 2: Vercel — Frontend

### 2a. Import project
1. Go to https://vercel.com and sign in
2. Click **Add New** → **Project** → import your GitHub repo
3. Set:
   - **Framework Preset:** Next.js
   - **Root Directory:** `frontend/apps/web`
   - **Build Command:** `cd ../.. && pnpm build`

### 2b. Set Environment Variables

| Variable | Value |
|----------|-------|
| `NEXT_PUBLIC_BACKEND_URL` | `https://your-backend.up.railway.app` |
| `NEXT_PUBLIC_WS_URL` | `wss://your-backend.up.railway.app/api/v1/ws` |

### 2c. Update vercel.json
Edit `frontend/apps/web/vercel.json` and replace `YOUR-RAILWAY-BACKEND.up.railway.app` with your actual Railway backend URL.

### 2d. Deploy
Push to your repo — Vercel auto-deploys.

---

## Step 3: Post-Deploy Checklist

- [ ] Open `https://your-app.vercel.app` — login page loads
- [ ] Login with an employee number + last 4 of national ID
- [ ] Agent sidebar shows and agents respond
- [ ] DM a colleague — messages send/receive
- [ ] DM a deployed agent (Pixel/Turbo) — auto-responds
- [ ] @mention a deployed agent in a human DM — agent responds
- [ ] My Teams section shows your department
- [ ] WebSocket connects (check green dot in status bar)

---

## CORS Configuration

The backend must allow the Vercel frontend origin. In your Railway env vars:
```
CORS_ORIGINS=https://your-app.vercel.app
```

For multiple origins (e.g., custom domain + vercel preview):
```
CORS_ORIGINS=https://your-app.vercel.app,https://krew.yourdomain.com
```

---

## Custom Domain (Optional)

### Vercel
1. Go to project settings → **Domains**
2. Add `app.krew.sa` (or your domain)
3. Update DNS: CNAME to `cname.vercel-dns.com`

### Railway
1. Go to backend service → **Settings** → **Networking** → **Custom Domain**
2. Add `api.krew.sa`
3. Update DNS as Railway instructs
4. Update `NEXT_PUBLIC_BACKEND_URL` and `NEXT_PUBLIC_WS_URL` on Vercel to use the custom domain

---

## Costs (Estimated)

| Service | Plan | Cost |
|---------|------|------|
| Vercel | Pro | $20/month |
| Railway (backend) | Usage-based | ~$5-10/month |
| Railway (PostgreSQL) | Usage-based | ~$5-10/month |
| Railway (Redis) | Usage-based | ~$2-5/month |
| Anthropic API | Pay-per-use | ~$10-50/month (depends on usage) |
| OpenAI API (embeddings) | Pay-per-use | ~$1-5/month |
| **Total** | | **~$43-100/month** |
