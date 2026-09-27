# Cloudflare Worker — Dashboard Reverse Proxy

A Cloudflare Worker that proxies the dashboard through a permanent address.
Visitors stay on the Worker URL and can bookmark it safely. The tunnel still
connects Cloudflare to the local dashboard, but is no longer a browser redirect.

## How it works

```
User visits: https://cms.cms-tunnel-redirect.workers.dev
  → Worker reads "tunnel_url" from KV and forwards the request
  → Tunnel → local nginx → Streamlit / OpenClaw
  → Response returned through the Worker, keeping the permanent browser URL
```

`capture_tunnel_url.py` pushes a new URL to KV on every tunnel restart.
The proxy preserves paths, query strings, request bodies, and WebSocket upgrades.
Redirects back to the tunnel hostname are rewritten to the permanent hostname.
Existing bookmarks of old temporary tunnel URLs cannot be recovered by this change;
users should replace them with the permanent Worker address.

Run `run_dashboard.bat` from the project root for normal startup. It deploys the
Worker automatically using `CF_API_TOKEN`, `CF_ACCOUNT_ID`, and
`CF_KV_NAMESPACE_ID` from `.env`, starts the local services and tunnel, and waits
up to two minutes for the public Streamlit health endpoint. No separate Wrangler
command or login is needed. The token needs Workers Scripts Edit and Workers KV
Storage Edit; the namespace ID must match `wrangler.toml`. The account must
already have a workers.dev subdomain.

The permanent address is saved in `worker_url.txt`, displayed by the launcher,
and copied to the clipboard by the tunnel manager. Tunnel diagnostics go to
`logs/cloudflare-tunnel.log`. Deployment errors stop startup; readiness timeouts
leave local services running with a warning so they can be investigated.
The launcher's stop action also terminates the tunnel and its child process.

For a manual deployment only, run `python cloudflare/deploy_worker.py` from the
project root (or use `npx wrangler deploy` from this directory).
Keep the local dashboard and tunnel running. After deployment, check `/`, `/home`,
`/home/`, dashboard interactions, and `/oclaw` in a browser. The address bar
should remain on the Worker hostname, and WebSocket connections should succeed.

## One-time setup (~5 minutes)

### 1. Install Wrangler (Cloudflare CLI)

```bash
npm install -g wrangler
wrangler login
```

### 2. Create KV namespace

```bash
cd cloudflare
npx wrangler kv:namespace create TUNNEL_KV
```

Copy the `id` from the output and paste it into `wrangler.toml`:

```toml
[[kv_namespaces]]
binding = "TUNNEL_KV"
id = "PASTE_YOUR_ID_HERE"
```

### 3. Deploy the Worker

```bash
npx wrangler deploy
```

Your Worker is now live at `https://cms-tunnel-redirect.<your-subdomain>.workers.dev`.

### 4. Create an API token

1. Go to https://dash.cloudflare.com/profile/api-tokens
2. Click **Create Token**
3. Use the **Edit Cloudflare Workers** template (or custom with `Workers Scripts: Edit` + `Workers KV Storage: Edit` permissions)
4. Copy the token

### 5. Get your Account ID

1. Go to https://dash.cloudflare.com → select any domain (or Workers)
2. The Account ID is in the URL: `https://dash.cloudflare.com/<ACCOUNT_ID>`
3. Or find it on the right sidebar of any domain's **Overview** page

### 6. Set environment variables

Add to your `.env` file:

```
CF_API_TOKEN=your_token_here
CF_ACCOUNT_ID=your_account_id_here
CF_KV_NAMESPACE_ID=your_namespace_id_here
```

## Testing

```bash
# Manually set a test value
curl -X PUT \
  "https://api.cloudflare.com/client/v4/accounts/<ACCOUNT_ID>/storage/kv/namespaces/<NAMESPACE_ID>/values/tunnel_url" \
  -H "Authorization: Bearer <TOKEN>" \
  -d "https://example.com"

# Visit the Worker URL — should serve example.com through the Worker
curl -I https://cms-tunnel-redirect.<your-subdomain>.workers.dev
```

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| "No tunnel URL configured yet" | KV is empty. Start the dashboard or set a test value. |
| "Cloudflare KV env vars not set" | Check `.env` has all three `CF_*` variables. |
| Worker not deploying | Run `wrangler login` again. |
