// Enkel passordlås for Cloudflare Pages. Reserve hvis du ikke vil bruke Cloudflare Access.
// Gjør ingenting før du setter miljøvariabelen SIDE_PASSORD i Pages-prosjektet
// (Settings > Variables and Secrets, type Secret). Brukernavnet spiller ingen rolle.
export async function onRequest(context) {
  const password = context.env.SIDE_PASSORD;
  if (!password) return context.next();
  const header = context.request.headers.get("Authorization") || "";
  if (header.startsWith("Basic ")) {
    let given = "";
    try {
      const decoded = new TextDecoder().decode(Uint8Array.from(atob(header.slice(6)), c => c.charCodeAt(0)));
      given = decoded.slice(decoded.indexOf(":") + 1);
    } catch (e) {
      given = "";
    }
    if (await same(given, password)) return context.next();
  }
  return new Response("Du må ha passordet for å se denne siden.", {
    status: 401,
    headers: {
      "WWW-Authenticate": 'Basic realm="FC 27-rating", charset="UTF-8"',
      "Content-Type": "text/plain; charset=utf-8",
      "Cache-Control": "no-store",
      "X-Robots-Tag": "noindex, nofollow",
    },
  });
}

// Sammenlign via SHA-256, så tiden ikke avslører hvor mye av passordet som stemte.
async function same(a, b) {
  const enc = new TextEncoder();
  const [x, y] = await Promise.all([a, b].map(s => crypto.subtle.digest("SHA-256", enc.encode(s))));
  const u = new Uint8Array(x), v = new Uint8Array(y);
  let diff = 0;
  for (let i = 0; i < u.length; i++) diff |= u[i] ^ v[i];
  return diff === 0;
}
