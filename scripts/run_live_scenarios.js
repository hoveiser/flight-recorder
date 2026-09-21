import { spawn } from 'child_process';
import { readFileSync, unlinkSync } from 'fs';
import { createHash } from 'crypto';
import { join } from 'path';
import { tmpdir } from 'os';
import { createClient, createAccount } from 'genlayer-js';
import { studioDevnet } from 'genlayer-js/chains';
import dotenv from 'dotenv';

dotenv.config();

const CONTRACT_ADDRESS = readFileSync('CONTRACT_ADDRESS.txt', 'utf-8').trim();
const WORKER = '0x1111111111111111111111111111111111111111';
const HAPPY_URL = 'https://raw.githubusercontent.com/hoveiser/flight-recorder/main/demo/case_files/happy_path.json';
const HAPPY_HASH = 'ac00e51fd82e9dff1df4e2fd120cf35fbf8229f6fd415a8b89154ed152733cf7';
// Off-chain deal the happy-path case file comes from. Sealed before its dispute.
const HAPPY_OFFCHAIN_DEAL_ID = 'scraper_deal_001';

/** Mirrors src/hash_chain.canonical_json: sorted keys, no whitespace. */
function canonicalJson(obj) {
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

// open_deal commits SHA-256(canonical_json(definition_of_done)) and the contract
// recomputes that digest over the case file's own definition_of_done, refusing
// to adjudicate if the two disagree. The happy path therefore has to be opened
// with the hash of the very terms it later submits, not a placeholder.
const HAPPY_AGREEMENT_HASH = createHash('sha256')
  .update(canonicalJson(JSON.parse(readFileSync('demo/case_files/happy_path.json', 'utf-8')).definition_of_done))
  .digest('hex');
const EXPLORER = 'https://explorer-studio-dev.genlayer.com';
const account = createAccount(process.env.ACCOUNT_PRIVATE_KEY_1);
const client = createClient({ chain: studioDevnet, account });
const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function waitFinalized(hash, label) {
  for (let attempt = 0; attempt < 120; attempt += 1) {
    const tx = await client.getTransaction({ hash });
    const status = tx.statusName || tx.status || tx.lifecycle?.state;
    console.log(`[${label}] ${status}`);
    if (status === 'FINALIZED' || status === 'finalized' || tx.lifecycle?.state === 'finalized') return tx;
    if (['FAILED', 'REVERTED', 'failed', 'reverted'].includes(status)) throw new Error(`${label} failed: ${JSON.stringify(tx)}`);
    await wait(5000);
  }
  throw new Error(`${label} did not finalize`);
}

async function write(functionName, args, value, label) {
  const fee = functionName === 'resolve'
    ? await client.estimateTransactionFeesForWrite({ address: CONTRACT_ADDRESS, functionName, args, value })
    : await client.estimateTransactionFees();
  const txHash = await client.writeContract({ address: CONTRACT_ADDRESS, functionName, args, value,
    fees: { distribution: fee.distribution, messageAllocations: fee.messageAllocations, feeValue: fee.feeValue } });
  console.log(`[${label}] tx=${txHash}`);
  return { txHash, receipt: await waitFinalized(txHash, label), fee: String(fee.feeValue) };
}

async function readDeal(id) { return JSON.parse(await client.readContract({ address: CONTRACT_ADDRESS, functionName: 'get_deal', args: [id] })); }
async function readPayouts() { return JSON.parse(await client.readContract({ address: CONTRACT_ADDRESS, functionName: 'get_payouts', args: [] })); }
async function findDealId(externalId) {
  for (let id = 1; id < 100; id += 1) if ((await readDeal(id)).external_deal_id === externalId) return id;
  throw new Error(`Could not find deal ${externalId}`);
}
function explorer(hash) { return `${EXPLORER}/tx/${hash}`; }
function txsOf(result) { return Object.fromEntries(Object.entries(result.txs).filter(([, hash]) => hash).map(([key, hash]) => [key, explorer(hash)])); }

async function createOnchainDeal(externalId, windowSec = 300, agreementHash = '0'.repeat(64)) {
  const open = await write('open_deal', [externalId, agreementHash, WORKER, windowSec], 100000000000000000n, `${externalId}.open_deal`);
  return { id: await findDealId(externalId), open };
}

async function runHappy() {
  const { id, open } = await createOnchainDeal(`demo_happy_${Date.now()}`, 300, HAPPY_AGREEMENT_HASH);
  // Seal immediately before the dispute so the evidence log cannot grow after
  // the case-file hash is anchored. Best effort: the happy-path case file is a
  // static URL, so a missing local API is not fatal here.
  let sealed = null;
  try { sealed = await sealOffchain('http://localhost:8000', HAPPY_OFFCHAIN_DEAL_ID, account.address); } catch (error) { console.error(`[happy] seal skipped: ${String(error.message || error)}`); }
  const dispute = await write('dispute', [id, HAPPY_URL, HAPPY_HASH], 0n, 'happy.dispute');
  const resolve = await write('resolve', [id], 0n, 'happy.resolve');
  let deal = await readDeal(id);
  let finalize = null;
  if (deal.status === 'adjudicated') { finalize = await write('finalize', [id], 0n, 'happy.finalize'); deal = await readDeal(id); }
  return { id, txs: { open_deal: open.txHash, dispute: dispute.txHash, resolve: resolve.txHash, finalize: finalize?.txHash || null }, deal, payouts: await readPayouts() };
}

async function apiJson(url, options) { const response = await fetch(url, options); const body = await response.json(); if (!response.ok) throw new Error(`${response.status} ${JSON.stringify(body)}`); return body; }

// Freeze the off-chain log before disputing. The contract adjudicates against
// the bytes hashed at dispute time, so sealing first is what makes the anchored
// hash describe a record that can never grow afterwards. Kept in the same script
// as the dispute transaction so the two cannot drift apart.
async function sealOffchain(apiBase, dealId, actor) {
  const sealed = await apiJson(`${apiBase}/deals/${dealId}/seal`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ actor }),
  });
  console.log(`[${dealId}] evidence log sealed, chain_head=${sealed.chain_head}`);
  return sealed.chain_head;
}
async function runAnchor() {
  // Isolated DB so repeated runs never collide with a previous off-chain deal.
  const dbPath = join(tmpdir(), `flight_recorder_anchor_${Date.now()}.db`);
  const server = spawn('python3', ['-m', 'uvicorn', 'src.main:app', '--port', '8000'], {
    stdio: 'ignore',
    env: { ...process.env, FLIGHT_RECORDER_DB: dbPath },
  });
  const serverError = new Promise((_, reject) => server.once('error', reject));
  try {
    for (let attempt = 0; attempt < 20; attempt += 1) {
      try { await fetch('http://localhost:8000/docs'); break; } catch (_) { await Promise.race([wait(500), serverError]); }
    }
    const id = `anchor_demo_${Date.now()}`;
    await apiJson('http://localhost:8000/deals', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ deal_id: id, definition_of_done: { success_criteria: 'test' }, agreement_hash: '0'.repeat(64), parties: [account.address, WORKER] }) });
    for (const eventType of ['REQUEST', 'DELIVERY', 'VALIDATION']) await apiJson('http://localhost:8000/events', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ deal_id: id, actor: account.address, event_type: eventType, payload: { scenario: 'anchor' } }) });
    const verification = await apiJson(`http://localhost:8000/deals/${id}/verify`);
    const onchain = await createOnchainDeal(id);
    const anchor = await write('anchor_milestone', [onchain.id, 'delivery', verification.last_hash], 0n, 'anchor.anchor_milestone');
    const deal = await readDeal(onchain.id);
    return { id: onchain.id, offchain_deal_id: id, chain_head: verification.last_hash, txs: { open_deal: onchain.open.txHash, anchor_milestone: anchor.txHash }, deal, payouts: await readPayouts() };
  } finally { server.kill('SIGTERM'); try { unlinkSync(dbPath); } catch (_) { /* best effort */ } }
}

async function runTimeout() {
  const { id, open } = await createOnchainDeal(`demo_timeout_${Date.now()}`);
  console.log('[timeout] waiting 320 seconds before timeout_release');
  await wait(320000);
  let timeout = null; let error = null;
  try { timeout = await write('timeout_release', [id], 0n, 'timeout.timeout_release'); } catch (cause) { error = String(cause.message || cause); }
  const deal = await readDeal(id);
  if (!error && deal.status === 'funded') error = 'Timeout not reached (7 days)';
  if (error) console.error(`[timeout] ${error}`);
  return { id, txs: { open_deal: open.txHash, timeout_release: timeout?.txHash || null }, deal, payouts: await readPayouts(), error };
}

/** Flip the last hex character so the digest is still 64 hex chars but wrong. */
function corruptHash(hash) {
  const last = hash.slice(-1);
  const flipped = (parseInt(last, 16) ^ 0xf).toString(16);
  return hash.slice(0, -1) + flipped;
}

/**
 * Scenario 4: anchor a deliberately WRONG case-file hash.
 *
 * The evidence itself is genuine: we fetch the very bytes the happy path uses
 * and hash them locally. Only the hash committed in dispute() is corrupted, so
 * validators re-fetch the real file, recompute the true digest, and compare it
 * against what was anchored. The mismatch is therefore a property of the
 * on-chain record, not of the fetch, and it is deterministic: validators hash
 * identical public bytes and must all land on MISMATCH.
 *
 * MISMATCH is an EVIDENCE_VERDICT, so resolve() refunds the client immediately
 * and sets status="refunded" — the payout happens inside resolve(), not in
 * finalize(). That is why no finalize transaction appears below.
 */
async function runMismatch() {
  const externalId = 'mismatch_live_001';
  const response = await fetch(HAPPY_URL);
  if (!response.ok) throw new Error(`Could not fetch evidence for hashing: HTTP ${response.status}`);
  const served = Buffer.from(await response.arrayBuffer());
  const trueHash = createHash('sha256').update(served).digest('hex');
  const wrongHash = corruptHash(trueHash);
  console.log(`[mismatch] evidence url=${HAPPY_URL}`);
  console.log(`[mismatch] served_bytes=${served.length} true_hash=${trueHash}`);
  console.log(`[mismatch] anchored_hash=${wrongHash} (deliberately wrong)`);

  const { id, open } = await createOnchainDeal(externalId, 300, HAPPY_AGREEMENT_HASH);
  const dispute = await write('dispute', [id, HAPPY_URL, wrongHash], 0n, 'mismatch.dispute');
  const resolve = await write('resolve', [id], 0n, 'mismatch.resolve');
  let deal = await readDeal(id);
  let finalize = null;
  // Defensive: refunds for evidence verdicts happen inside resolve(). If the
  // contract ever moves the payout to finalize, run it and record the tx.
  if (deal.status === 'adjudicated') { finalize = await write('finalize', [id], 0n, 'mismatch.finalize'); deal = await readDeal(id); }
  const payouts = await readPayouts();
  const refund = payouts.filter((p) => String(p.to).toLowerCase() === String(deal.client).toLowerCase());
  console.log(`[mismatch] verdict=${deal.verdict} status=${deal.status} payout_status=${deal.payout_status}`);
  console.log(`[mismatch] client=${deal.client} refund_entries=${JSON.stringify(refund)}`);
  if (deal.verdict !== 'EVIDENCE_MISMATCH') {
    throw new Error(`Expected EVIDENCE_MISMATCH but got verdict=${deal.verdict} status=${deal.status} reasoning=${deal.reasoning}`);
  }
  return {
    id,
    external_deal_id: externalId,
    case_file_url: HAPPY_URL,
    served_bytes: served.length,
    true_hash: trueHash,
    anchored_hash: wrongHash,
    refund,
    txs: { open_deal: open.txHash, dispute: dispute.txHash, resolve: resolve.txHash, finalize: finalize?.txHash || null },
    deal,
    payouts,
  };
}

async function main() {
  const results = {};
  const requested = process.argv.slice(2);
  // SCENARIOS=mismatch (or "happy,anchor") narrows the run to just those
  // scenarios; the argv --happy/--anchor/--timeout/--mismatch flags still work.
  const envScenarios = (process.env.SCENARIOS || '').split(',').map((s) => s.trim().toLowerCase()).filter(Boolean);
  const shouldRun = (name) => (envScenarios.length > 0
    ? envScenarios.includes(name)
    : requested.length === 0 || requested.includes(`--${name}`));
  if (shouldRun('happy')) try { results.happy = await runHappy(); console.log('SCENARIO_HAPPY=' + JSON.stringify(results.happy)); console.log('EXPLORERS=' + JSON.stringify(txsOf(results.happy))); } catch (error) { results.happy = { error: String(error.message || error) }; console.error('SCENARIO_HAPPY_ERROR=' + results.happy.error); }
  if (shouldRun('anchor')) try { results.anchor = await runAnchor(); console.log('SCENARIO_ANCHOR=' + JSON.stringify(results.anchor)); console.log('EXPLORERS_ANCHOR=' + JSON.stringify(txsOf(results.anchor))); } catch (error) { results.anchor = { error: String(error.message || error) }; console.error('SCENARIO_ANCHOR_ERROR=' + results.anchor.error); }
  if (shouldRun('timeout')) try { results.timeout = await runTimeout(); console.log('SCENARIO_TIMEOUT=' + JSON.stringify(results.timeout)); console.log('EXPLORERS_TIMEOUT=' + JSON.stringify(txsOf(results.timeout))); } catch (error) { results.timeout = { error: String(error.message || error) }; console.error('SCENARIO_TIMEOUT_ERROR=' + results.timeout.error); }
  if (shouldRun('mismatch')) try { results.mismatch = await runMismatch(); console.log('SCENARIO_MISMATCH=' + JSON.stringify({ id: results.mismatch.id, external_deal_id: results.mismatch.external_deal_id, case_file_url: results.mismatch.case_file_url, served_bytes: results.mismatch.served_bytes, true_hash: results.mismatch.true_hash, anchored_hash: results.mismatch.anchored_hash, refund: results.mismatch.refund, verdict: results.mismatch.deal.verdict, status: results.mismatch.deal.status, payout_status: results.mismatch.deal.payout_status, reasoning: results.mismatch.deal.reasoning, txs: results.mismatch.txs })); console.log('EXPLORERS_MISMATCH=' + JSON.stringify(txsOf(results.mismatch))); } catch (error) { results.mismatch = { error: String(error.message || error) }; console.error('SCENARIO_MISMATCH_ERROR=' + results.mismatch.error); }
  try { results.balance = String(await client.getBalance({ address: account.address })); } catch (error) { results.balance_error = String(error.message || error); }
  console.log('SCENARIOS=' + JSON.stringify(results));
}

await main();
