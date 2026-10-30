// Cloudflare Pages Function: POST /api/contact. Emails the site author via Resend.
// Backs the "Get in touch" card on index.html. Uses the secrets already set for
// feedback.js (RESEND_API_KEY, FEEDBACK_ALERT_TO); no database. The author's
// address never reaches the browser. Spam is bounded by a honeypot, an origin
// allow-list, size limits and a minimum fill time -- not eliminated: a script that
// fakes the Origin header can still send, capped by the Resend plan's daily limit.
const ALLOWED_ORIGINS = new Set(["https://ottawavisuals.github.io", "https://energy.madeclear.ca"]);
const MAX_BODY_BYTES = 8_192;
const MAX_NAME = 80;
const MAX_EMAIL = 120;
const MAX_MESSAGE = 2_000;
const MIN_FILL_MS = 3_000; // a human takes longer than this to fill the form
const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

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

function withCors(request, response) {
  const origin = request.headers.get("origin");
  if (ALLOWED_ORIGINS.has(origin)) {
    response.headers.set("access-control-allow-origin", origin);
    response.headers.set("vary", "Origin");
  }
  return response;
}

const oneLine = (value, max) => String(value || "").replace(/[\r\n]+/g, " ").trim().slice(0, max);

async function handlePost({ request, env }) {
  if (!env.RESEND_API_KEY || !env.FEEDBACK_ALERT_TO) return json({ error: "Contact is not configured." }, 503);
  if (!ALLOWED_ORIGINS.has(request.headers.get("origin"))) return json({ error: "Invalid request origin." }, 403);
  if (!(request.headers.get("content-type") || "").toLowerCase().startsWith("application/json")) {
    return json({ error: "Expected JSON." }, 415);
  }

  let payload;
  try {
    const body = await request.text();
    if (new TextEncoder().encode(body).byteLength > MAX_BODY_BYTES) return json({ error: "Message is too large." }, 413);
    payload = JSON.parse(body);
  } catch {
    return json({ error: "Invalid JSON." }, 400);
  }

  // Bots fill the hidden field or submit instantly: accept quietly, send nothing.
  if ((typeof payload.website === "string" && payload.website.trim()) || !(Number(payload.fillMs) >= MIN_FILL_MS)) {
    return json({ ok: true }, 202);
  }

  const name = oneLine(payload.name, MAX_NAME);
  const email = oneLine(payload.email, MAX_EMAIL);
  const message = String(payload.message || "").trim();
  if (!EMAIL.test(email) || !message || message.length > MAX_MESSAGE) {
    return json({ error: "Please enter a valid email and a message under 2,000 characters." }, 400);
  }

  try {
    const response = await fetch("https://api.resend.com/emails", {
      method: "POST",
      headers: { authorization: `Bearer ${env.RESEND_API_KEY}`, "content-type": "application/json" },
      body: JSON.stringify({
        from: "alerts@madeclear.ca",
        to: [env.FEEDBACK_ALERT_TO],
        reply_to: email,
        subject: `Site contact: ${name || email}`,
        text: `From: ${name || "(no name)"} <${email}>\n\n${message}`,
      }),
    });
    if (!response.ok) throw new Error(`Resend responded ${response.status}`);
  } catch (err) {
    console.error("contact send failed", err);
    return json({ error: "Could not send. Please try again later." }, 502);
  }
  return json({ ok: true });
}

export async function onRequest(context) {
  const { request } = context;
  if (request.method === "OPTIONS") {
    if (!ALLOWED_ORIGINS.has(request.headers.get("origin"))) return json({ error: "Method not allowed." }, 405);
    return withCors(
      request,
      new Response(null, {
        status: 204,
        headers: {
          "access-control-allow-methods": "POST, OPTIONS",
          "access-control-allow-headers": "content-type",
          "access-control-max-age": "86400",
        },
      }),
    );
  }
  if (request.method !== "POST") return withCors(request, json({ error: "Method not allowed." }, 405));
  return withCors(request, await handlePost(context));
}
