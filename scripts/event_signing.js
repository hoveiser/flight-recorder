// Shared client-side signing for the off-chain evidence API (scripts and demos).
//
// The recorder accepts an event only if an EIP-191 personal_sign signature over
// the canonical event message recovers to the claimed actor, that actor is a
// party to the deal, and that actor owns the session token. So every caller has
// to: read the current head, sign (deal id, head, type, payload digest, its own
// timestamp), and post with its own session. A signature never travels between
// positions in the chain, which is why a client that loses a write race must
// re-read the head and sign again rather than resend the same body.
//
// canonicalJson mirrors src/hash_chain.canonical_json exactly: sorted keys, no
// whitespace, and ASCII-only payloads (Python escapes non-ASCII by default).
import { createHash } from 'crypto';

export const EVENT_DOMAIN = 'flight-recorder-event-v1';
export const GENESIS = 'GENESIS';

export function canonicalJson(obj) {
  if (Array.isArray(obj)) return `[${obj.map(canonicalJson).join(',')}]`;
  if (obj && typeof obj === 'object') {
    const body = Object.keys(obj)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${canonicalJson(obj[key])}`)
      .join(',');
    return `{${body}}`;
  }
  return JSON.stringify(obj);
}

export function payloadHash(payload) {
  return createHash('sha256').update(canonicalJson(payload)).digest('hex');
}

export function eventMessage({ dealId, previousEventHash, eventType, digest, clientTimestamp }) {
  return [EVENT_DOMAIN, dealId, previousEventHash, eventType, digest, clientTimestamp].join('\n');
}

export async function apiJson(url, options = {}) {
  const response = await fetch(url, options);
  const body = await response.json().catch(() => null);
  if (!response.ok) throw new Error(`${response.status} ${JSON.stringify(body ?? response.statusText)}`);
  return body;
}

export async function sessionHeaders(apiBase, actor) {
  const { nonce } = await apiJson(`${apiBase}/api/auth/nonce`, { method: 'POST' });
  const signature = await actor.signMessage({ message: nonce });
  const session = await apiJson(`${apiBase}/api/auth/verify`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ address: actor.address, signature, nonce }),
  });
  return { 'content-type': 'application/json', Authorization: `Bearer ${session.session_token}` };
}

export async function chainHead(apiBase, dealId) {
  const events = await apiJson(`${apiBase}/deals/${dealId}/events`);
  return events.length > 0 ? events[events.length - 1].event_hash : GENESIS;
}

export async function recordSignedEvent(apiBase, actor, dealId, eventType, payload) {
  const headers = await sessionHeaders(apiBase, actor);
  const digest = payloadHash(payload);
  let previousEventHash = await chainHead(apiBase, dealId);
  for (let attempt = 0; attempt < 3; attempt += 1) {
    const clientTimestamp = new Date().toISOString();
    const signature = await actor.signMessage({
      message: eventMessage({ dealId, previousEventHash, eventType, digest, clientTimestamp }),
    });
    try {
      return await apiJson(`${apiBase}/events`, {
        method: 'POST',
        headers,
        body: JSON.stringify({
          deal_id: dealId,
          actor: actor.address,
          event_type: eventType,
          payload,
          signature,
          client_timestamp: clientTimestamp,
        }),
      });
    } catch (error) {
      // Somebody appended underneath us: re-read the head and sign for that spot.
      if (!String(error.message).startsWith('403')) throw error;
      previousEventHash = await chainHead(apiBase, dealId);
    }
  }
  throw new Error(`could not append ${eventType} to ${dealId}: every position was taken`);
}

export async function sealOffchain(apiBase, actor, dealId) {
  const headers = await sessionHeaders(apiBase, actor);
  const sealed = await apiJson(`${apiBase}/deals/${dealId}/seal`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ actor: actor.address }),
  });
  console.log(`[${dealId}] evidence log sealed, chain_head=${sealed.chain_head}`);
  return sealed.chain_head;
}
