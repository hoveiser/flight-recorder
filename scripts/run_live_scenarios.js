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
  const dispute = await write('dispute', [id, HAPPY_URL, HAPPY_HASH], 0n, 'happy.dispute');
  const resolve = await write('resolve', [id], 0n, 'happy.resolve');
  let deal = await readDeal(id);
  let finalize = null;
  if (deal.status === 'adjudicated') { finalize = await write('finalize', [id], 0n, 'happy.finalize'); deal = await readDeal(id); }
  return { id, txs: { open_deal: open.txHash, dispute: dispute.txHash, resolve: resolve.txHash, finalize: finalize?.txHash || null }, deal, payouts: await readPayouts() };
}

async function apiJson(url, options) { const response = await fetch(url, options); const body = await response.json(); if (!response.ok) throw new Error(`${response.status} ${JSON.stringify(body)}`); return body; }
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

async function main() {
  const results = {};
  const requested = process.argv.slice(2);
  const shouldRun = (name) => requested.length === 0 || requested.includes(`--${name}`);
  if (shouldRun('happy')) try { results.happy = await runHappy(); console.log('SCENARIO_HAPPY=' + JSON.stringify(results.happy)); console.log('EXPLORERS=' + JSON.stringify(txsOf(results.happy))); } catch (error) { results.happy = { error: String(error.message || error) }; console.error('SCENARIO_HAPPY_ERROR=' + results.happy.error); }
  if (shouldRun('anchor')) try { results.anchor = await runAnchor(); console.log('SCENARIO_ANCHOR=' + JSON.stringify(results.anchor)); console.log('EXPLORERS_ANCHOR=' + JSON.stringify(txsOf(results.anchor))); } catch (error) { results.anchor = { error: String(error.message || error) }; console.error('SCENARIO_ANCHOR_ERROR=' + results.anchor.error); }
  if (shouldRun('timeout')) try { results.timeout = await runTimeout(); console.log('SCENARIO_TIMEOUT=' + JSON.stringify(results.timeout)); console.log('EXPLORERS_TIMEOUT=' + JSON.stringify(txsOf(results.timeout))); } catch (error) { results.timeout = { error: String(error.message || error) }; console.error('SCENARIO_TIMEOUT_ERROR=' + results.timeout.error); }
  try { results.balance = String(await client.getBalance({ address: account.address })); } catch (error) { results.balance_error = String(error.message || error); }
  console.log('SCENARIOS=' + JSON.stringify(results));
}

await main();
