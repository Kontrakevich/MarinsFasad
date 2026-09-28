# Brand Apply Studio — Project Report

## Project
Brand Apply Studio

## Target action
Apply branding to a photographed product with manually controlled perspective, then optionally use OpenRouter image editing for material realism without re-deciding brand geometry.

## Current stage
MVP 0.3 — Perspective editor + export layers + OpenRouter gateway.

## Progress
92%

## Implemented
- Upload immutable source image.
- Manual P1–P4 perspective grid.
- Lock/unlock perspective.
- Upload branding file.
- Move and scale brand inside the locked projective plane.
- Small grid handles that do not obstruct the source.
- Fullscreen editor.
- Full-resolution composite export.
- Full-resolution transparent perspective logo-layer export.
- Full-resolution monochrome logo mask export.
- OpenRouter post-processing UI.
- Cloudflare Worker gateway that keeps the OpenRouter API key server-side.
- OpenRouter inputs: MASTER + logo layer + mask.
- Default OpenRouter model: `openai/gpt-image-2`.

## Architecture
```
MASTER
  -> P1-P4 surface
  -> projective brand placement
      -> composite.png
      -> logo-layer.png
      -> logo-mask.png
  -> OpenRouter gateway
      -> image edit
```

## Current limitation
The secure OpenRouter gateway code is complete but needs deployment with `OPENROUTER_API_KEY` configured as a Cloudflare Worker secret. Until a Worker URL is supplied to the UI, the AI-processing button cannot call OpenRouter.

## Next validation
1. Test P1-P4 on the MARINS cardholder source.
2. Export logo-layer.png and verify overlay alignment at 100%.
3. Deploy Worker.
4. Run one low/medium-cost OpenRouter edit.
5. Compare AI result against MASTER for camera, object geometry, logo identity, placement, and perspective drift.
