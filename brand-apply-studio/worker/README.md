# Brand Apply Studio — OpenRouter Gateway

Cloudflare Worker stores the OpenRouter API key server-side and exposes:

- `GET /health`
- `POST /api/openrouter/image`

The browser never receives `OPENROUTER_API_KEY`.

## Deploy

```bash
cd brand-apply-studio/worker
npm install
npx wrangler secret put OPENROUTER_API_KEY
npm run deploy
```

Then paste the deployed Worker URL into **OpenRouter Gateway** in Brand Apply Studio, or open the GitHub Pages UI once with:

```
https://kontrakevich.github.io/MarinsFasad/brand-apply-studio/?api=https://YOUR-WORKER.workers.dev
```

The URL is stored in localStorage after that.

## Request contract

```json
{
  "model": "openai/gpt-image-2",
  "prompt": "Reference 1 is MASTER...",
  "quality": "medium",
  "aspect_ratio": "3:2",
  "references": [
    "data:image/png;base64,...",
    "data:image/png;base64,...",
    "data:image/png;base64,..."
  ]
}
```

References are sent to OpenRouter as `input_references`.
