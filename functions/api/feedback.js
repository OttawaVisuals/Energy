// Cloudflare Pages Function backing the feedback widget on retrofits.html and
// retrofit-insights.html (assets/feedback.js / assets/feedback.css).
// Ported from C:\Simple_Viz\functions\api\feedback.js (madeclear.ca) — same
// validation, honeypot and per-day/IP/UA dedupe logic. Requires a D1 binding
// named FEEDBACK_DB (separate database from madeclear.ca's — see
// migrations/0001_feedback.sql) and a secret FEEDBACK_HASH_KEY, both set on
// the Cloudflare Pages project. FEEDBACK_ALERT (Email Send binding) and
// FEEDBACK_ALERT_TO are optional — email alerting is skipped if absent.
const RATINGS = new Set(["clear", "almost", "not-yet"]);
const PAGE_SLUG = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
const MAX_BODY_BYTES = 16_384;
const MAX_COMMENT_LENGTH = 1_200;
const MAX_CONTEXT_ITEMS = 20;
const MAX_CONTEXT_ITEM_LENGTH = 200;

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store",
      "x-content-type-options": "nosniff",
    },
  });
}

function normalizeContext(value) {
  if (!Array.isArray(value)) return [];
  return value
    .filter((item) => typeof item === "string")
    .slice(0, MAX_CONTEXT_ITEMS)
    .map((item) => item.trim().slice(0, MAX_CONTEXT_ITEM_LENGTH))
    .filter(Boolean);
}

async function sendFeedbackAlert(env, { page, rating, comment, context }) {
  if (!env.FEEDBACK_ALERT || !env.FEEDBACK_ALERT_TO) return false;
  try {
    const lines = [
      `Page: ${page}`,
      `Rating: ${rating}`,
      comment ? `Comment: ${comment}` : "Comment: (none)",
      context.length ? `Context: ${context.join(" | ")}` : "",
    ].filter(Boolean);
    await env.FEEDBACK_ALERT.send({
      from: "alerts@madeclear.ca",
      to: env.FEEDBACK_ALERT_TO,
      subject: `New feedback: ${page} (${rating})`,
      text: lines.join("\n"),
    });
    return true;
  } catch (err) {
    // Alerting is best-effort only — never let a notification failure block a feedback submission.
    console.error("feedback alert failed", err);
    return false;
  }
}

async function feedbackKey(request, secret, page) {
  const day = new Date().toISOString().slice(0, 10);
  const ip = request.headers.get("cf-connecting-ip") || "unknown";
  const userAgent = request.headers.get("user-agent") || "unknown";
  const material = `${day}\n${page}\n${ip}\n${userAgent}`;
  const encoder = new TextEncoder();
  const key = await crypto.subtle.importKey(
    "raw",
    encoder.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const signature = await crypto.subtle.sign("HMAC", key, encoder.encode(material));
  return Array.from(new Uint8Array(signature), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

async function handlePost({ request, env }) {
  if (!env.FEEDBACK_DB || !env.FEEDBACK_HASH_KEY) {
    return json({ error: "Feedback is not configured." }, 503);
  }

  const origin = request.headers.get("origin");
  if (!origin || origin !== new URL(request.url).origin) {
    return json({ error: "Invalid request origin." }, 403);
  }

  if (!(request.headers.get("content-type") || "").toLowerCase().startsWith("application/json")) {
    return json({ error: "Expected JSON." }, 415);
  }

  const declaredLength = Number(request.headers.get("content-length") || 0);
  if (declaredLength > MAX_BODY_BYTES) {
    return json({ error: "Feedback is too large." }, 413);
  }

  let payload;
  try {
    const body = await request.text();
    if (new TextEncoder().encode(body).byteLength > MAX_BODY_BYTES) {
      return json({ error: "Feedback is too large." }, 413);
    }
    payload = JSON.parse(body);
  } catch {
    return json({ error: "Invalid JSON." }, 400);
  }

  // Quietly accept automated submissions that fill the hidden field.
  if (typeof payload.website === "string" && payload.website.trim()) {
    return json({ ok: true }, 202);
  }

  const page = typeof payload.page === "string" ? payload.page.trim().toLowerCase() : "";
  const rating = typeof payload.rating === "string" ? payload.rating.trim() : "";
  const comment = typeof payload.comment === "string" ? payload.comment.trim() : "";
  const context = normalizeContext(payload.context);

  if (!PAGE_SLUG.test(page) || !RATINGS.has(rating)) {
    return json({ error: "Invalid page or rating." }, 400);
  }
  if (comment.length > MAX_COMMENT_LENGTH) {
    return json({ error: "Comment is too long." }, 400);
  }

  const dedupeKey = await feedbackKey(request, env.FEEDBACK_HASH_KEY, page);
  try {
    await env.FEEDBACK_DB.prepare(
      `INSERT INTO feedback (page_slug, rating, comment, context_json, dedupe_key)
       VALUES (?, ?, ?, ?, ?)
       ON CONFLICT(dedupe_key) DO UPDATE SET
         rating = excluded.rating,
         comment = excluded.comment,
         context_json = excluded.context_json,
         submitted_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')`,
    )
      .bind(page, rating, comment, JSON.stringify(context), dedupeKey)
      .run();
  } catch (err) {
    console.error("feedback write failed", err);
    return json({ error: "Could not save feedback." }, 500);
  }

  const alerted = await sendFeedbackAlert(env, { page, rating, comment, context });
  return json({ ok: true, alerted });
}

export function onRequest(context) {
  if (context.request.method !== "POST") {
    return json({ error: "Method not allowed." }, 405);
  }
  return handlePost(context);
}
