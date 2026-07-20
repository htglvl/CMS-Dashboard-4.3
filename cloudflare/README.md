# Cloudflare Worker — Tunnel Redirect

A tiny Cloudflare Worker that redirects visitors to the latest CMS Dashboard tunnel URL.

## How it works

```
User visits: https://cms-tunnel-redirect.workers.dev
  → Worker reads "tunnel_url" from KV
  → 302 redirect to https://abc-123.trycloudflare.com
```

`capture_tunnel_url.py` pushes a new URL to KV on every tunnel restart.

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

# Visit the Worker URL — should redirect to example.com
curl -I https://cms-tunnel-redirect.<your-subdomain>.workers.dev
```

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| "No tunnel URL configured yet" | KV is empty. Start the dashboard or set a test value. |
| "Cloudflare KV env vars not set" | Check `.env` has all three `CF_*` variables. |
| Worker not deploying | Run `wrangler login` again. |
