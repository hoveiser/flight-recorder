import { spawn } from 'child_process';
import { readFileSync, unlinkSync } from 'fs';
import { createHash } from 'crypto';
import { join } from 'path';
import { tmpdir } from 'os';
import { createClient, createAccount } from 'genlayer-js';
import { studioDevnet } from 'genlayer-js/chains';
import dotenv from 'dotenv';
import { walletPrivateKey } from './wallet_key.js';
import {
  apiJson,
  canonicalJson,
  recordSignedEvent,
  sealOffchain,
} from './event_signing.js';

dotenv.config();

const CONTRACT_ADDRESS = readFileSync('CONTRACT_ADDRESS.txt', 'utf-8').trim();
const WORKER = '0x1111111111111111111111111111111111111111';
// The case file validators can actually fetch. During a round that has not been
// merged yet, point CASE_FILE_URL at the branch's raw file so the served bytes,
// the anchored head and the agreement hash all describe the same evidence.
const HAPPY_URL = process.env.CASE_FILE_URL
  || 'https://raw.githubusercontent.com/hoveiser/flight-recorder/main/demo/case_files/happy_path.json';
const API_BASE = process.env.FLIGHT_RECORDER_URL || 'http://localhost:8000';
// Windows ships `python`, POSIX environments ship `python3`.
const PYTHON = process.platform === 'win32' ? 'python' : 'python3';

/** sha256 over the exact served bytes, plus the head those bytes declare. */
async function servedEvidence() {
  const response = await fetch(HAPPY_URL);
  if (!response.ok) throw new Error(`Could not fetch ${HAPPY_URL}: HTTP ${response.status}`);
  const text = await response.text();
  const digest = createHash('sha256').update(text).digest('hex');
  const caseFile = JSON.parse(text);
  const declaredHead = caseFile?.chain_integrity?.last_hash;
  if (!/^[0-9a-f]{64}$/.test(String(declaredHead || ''))) {
    throw new Error(
      `The served case file declares no 64-hex chain head (chain_integrity.last_hash=${declaredHead}). `
      + 'Since D5 a dispute must anchor one, so this evidence cannot be used.',
    );
  }
  // open_deal commits SHA-256(canonical_json(definition_of_done)) and the contract
  // recomputes that digest over the case file's own terms, so both come from the
  // served bytes: hashing a local copy that has not been published yet would make
  // every resolve land on AGREEMENT_MISMATCH for the wrong reason.
  const agreementHash = createHash('sha256')
    .update(canonicalJson(caseFile.definition_of_done))
    .digest('hex');
  return { text, digest, declaredHead, agreementHash, caseFile };
}

const EXPLORER = 'https://explorer-studio-dev.genlayer.com';
const account = createAccount(walletPrivateKey());
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
  const evidence = await servedEvidence();
  console.log(`[happy] served_bytes=${evidence.text.length} digest=${evidence.digest}`);
  console.log(`[happy] declared_head=${evidence.declaredHead}`);
  const { id, open } = await createOnchainDeal(`demo_happy_${Date.now()}`, 300, evidence.agreementHash);
  // The dispute anchors a head, and from D5 on that anchor is immutable for the
  // deal. Since D6 the contract recomputes the chain itself and pays only if its
  // own digest equals the anchor, so the anchored value must be the head the
  // fetched events actually produce. For this published case file the declared
  // head and the recomputable head are the same value (a genuine v2 chain), which
  // is why anchoring evidence.declaredHead here still settles APPROVED.
  const dispute = await write('dispute', [id, HAPPY_URL, evidence.digest, evidence.declaredHead], 0n, 'happy.dispute');
  const resolve = await write('resolve', [id], 0n, 'happy.resolve');
  let deal = await readDeal(id);
  let finalize = null;
  if (deal.status === 'adjudicated') { finalize = await write('finalize', [id], 0n, 'happy.finalize'); deal = await readDeal(id); }
  return { id, case_file_url: HAPPY_URL, anchored_head: evidence.declaredHead, txs: { open_deal: open.txHash, dispute: dispute.txHash, resolve: resolve.txHash, finalize: finalize?.txHash || null }, deal, payouts: await readPayouts() };
}
async function runAnchor() {
  // Isolated DB so repeated runs never collide with a previous off-chain deal.
  const dbPath = join(tmpdir(), `flight_recorder_anchor_${Date.now()}.db`);
  const apiPort = new URL(API_BASE).port || '8000';
  const server = spawn(PYTHON, ['-m', 'uvicorn', 'src.main:app', '--port', apiPort], {
    stdio: 'ignore',
    env: { ...process.env, FLIGHT_RECORDER_DB: dbPath },
  });
  const serverError = new Promise((_, reject) => server.once('error', reject));
  try {
    for (let attempt = 0; attempt < 20; attempt += 1) {
      try { await fetch(`${API_BASE}/docs`); break; } catch (_) { await Promise.race([wait(500), serverError]); }
    }
    const id = `anchor_demo_${Date.now()}`;
    // Parties are addresses: since the recorder verifies an EIP-191 signature per
    // event, a name is not enough to record anything.
    await apiJson(`${API_BASE}/deals`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ deal_id: id, definition_of_done: { success_criteria: 'test' }, parties: [account.address, WORKER] }) });
    for (const eventType of ['REQUEST', 'DELIVERY', 'VALIDATION']) {
      await recordSignedEvent(API_BASE, account, id, eventType, { scenario: 'anchor', event: eventType });
    }
    // Sealing freezes the log; the head it returns is what a dispute must anchor.
    const head = await sealOffchain(API_BASE, account, id);
    const verification = await apiJson(`${API_BASE}/deals/${id}/verify`);
    if (verification.last_hash !== head) throw new Error(`seal head ${head} != verify head ${verification.last_hash}`);
    if (verification.signature_status !== 'PASS') throw new Error(`events are not all signed: ${JSON.stringify(verification.signatures)}`);
    const onchain = await createOnchainDeal(id);
    const anchor = await write('anchor_milestone', [onchain.id, 'delivery', head], 0n, 'anchor.anchor_milestone');
    // The counterparty's dispute has to accept the head that is already on record.
    const dispute = await write('dispute', [onchain.id, HAPPY_URL, (await servedEvidence()).digest, head], 0n, 'anchor.dispute');
    const deal = await readDeal(onchain.id);
    if (deal.milestones?.delivery !== head) throw new Error(`anchored head mismatch on chain: ${JSON.stringify(deal.milestones)}`);
    return { id: onchain.id, offchain_deal_id: id, chain_head: head, milestones: deal.milestones, txs: { open_deal: onchain.open.txHash, anchor_milestone: anchor.txHash, dispute: dispute.txHash }, deal, payouts: await readPayouts() };
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
  const evidence = await servedEvidence();
  const wrongHash = corruptHash(evidence.digest);
  console.log(`[mismatch] evidence url=${HAPPY_URL}`);
  console.log(`[mismatch] served_bytes=${evidence.text.length} true_hash=${evidence.digest}`);
  console.log(`[mismatch] anchored_hash=${wrongHash} (deliberately wrong)`);

  const { id, open } = await createOnchainDeal(externalId, 300, evidence.agreementHash);
  // The head is the honest one; only the case-file digest is corrupted, so the
  // dispute gets past the anchor gate and the served-bytes check is what fails.
  const dispute = await write('dispute', [id, HAPPY_URL, wrongHash, evidence.declaredHead], 0n, 'mismatch.dispute');
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
    served_bytes: evidence.text.length,
    true_hash: evidence.digest,
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
