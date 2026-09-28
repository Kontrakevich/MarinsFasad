const DEFAULT_ALLOWED_ORIGINS = [
  "https://kontrakevich.github.io",
  "http://127.0.0.1:8015",
  "http://localhost:8015"
];

function corsHeaders(request, env) {
  const origin = request.headers.get("Origin") || "";
  const configured = (env.ALLOWED_ORIGINS || "")
    .split(",")
    .map(value => value.trim())
    .filter(Boolean);

  const allowed = configured.length ? configured : DEFAULT_ALLOWED_ORIGINS;
  const allowOrigin = allowed.includes(origin) ? origin : allowed[0];

  return {
    "Access-Control-Allow-Origin": allowOrigin,
    "Access-Control-Allow-Methods": "POST,OPTIONS,GET",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Max-Age": "86400",
    "Vary": "Origin"
  };
}

function json(body, status, request, env) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      ...corsHeaders(request, env)
    }
  });
}

function validReference(value) {
  return typeof value === "string" &&
    /^data:image\/(png|jpeg|jpg|webp);base64,/i.test(value) &&
    value.length < 18_000_000;
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (request.method === "OPTIONS") {
      return new Response(null, {
        status: 204,
        headers: corsHeaders(request, env)
      });
    }

    if (request.method === "GET" && url.pathname === "/health") {
      return json({
        ok: true,
        service: "brand-apply-openrouter",
        model_default: env.OPENROUTER_IMAGE_MODEL || "openai/gpt-image-2"
      }, 200, request, env);
    }

    if (request.method !== "POST" || url.pathname !== "/api/openrouter/image") {
      return json({ error: "Not found" }, 404, request, env);
    }

    if (!env.OPENROUTER_API_KEY) {
      return json({ error: "OPENROUTER_API_KEY is not configured" }, 503, request, env);
    }

    let body;
    try {
      body = await request.json();
    } catch {
      return json({ error: "Invalid JSON" }, 400, request, env);
    }

    const references = Array.isArray(body.references) ? body.references : [];
    if (references.length < 1 || references.length > 4 || !references.every(validReference)) {
      return json({ error: "references must contain 1-4 valid image data URLs" }, 400, request, env);
    }

    const model = String(
      body.model ||
      env.OPENROUTER_IMAGE_MODEL ||
      "openai/gpt-image-2"
    ).trim();

    const prompt = String(body.prompt || "").trim();
    if (!prompt) {
      return json({ error: "prompt is required" }, 400, request, env);
    }

    const quality = ["low", "medium", "high", "auto"].includes(body.quality)
      ? body.quality
      : "medium";

    const payload = {
      model,
      prompt,
      n: 1,
      quality,
      aspect_ratio: body.aspect_ratio || "auto",
      input_references: references.map(value => ({
        type: "image_url",
        image_url: { url: value }
      }))
    };

    let upstream;
    try {
      upstream = await fetch("https://openrouter.ai/api/v1/images", {
        method: "POST",
        headers: {
          "Authorization": "Bearer " + env.OPENROUTER_API_KEY,
          "Content-Type": "application/json",
          "HTTP-Referer": env.OPENROUTER_HTTP_REFERER || "https://kontrakevich.github.io/MarinsFasad/brand-apply-studio/",
          "X-Title": env.OPENROUTER_APP_TITLE || "Brand Apply Studio"
        },
        body: JSON.stringify(payload)
      });
    } catch (error) {
      return json({ error: "OpenRouter connection failed", detail: String(error) }, 502, request, env);
    }

    const text = await upstream.text();
    let result;
    try {
      result = JSON.parse(text);
    } catch {
      return json({
        error: "OpenRouter returned non-JSON response",
        status: upstream.status,
        detail: text.slice(0, 1000)
      }, 502, request, env);
    }

    if (!upstream.ok) {
      return json({
        error: result.error?.message || result.message || "OpenRouter request failed",
        status: upstream.status,
        upstream: result
      }, upstream.status, request, env);
    }

    const item = result.data?.[0];
    if (!item?.b64_json) {
      return json({ error: "OpenRouter returned no image", upstream: result }, 502, request, env);
    }

    return json({
      b64_json: item.b64_json,
      media_type: item.media_type || "image/png",
      usage: result.usage || null,
      model
    }, 200, request, env);
  }
};
