// Adversarial live run against D5 on studio-dev (chain 61997).
//
// Every case here is something a party or a stranger would gain by doing, run
// against the real contract with real transactions. Each case asserts two things:
// the call did not execute, and the on-chain state afterwards is what it should
// still be. The second half matters as much as the first: a rejection that leaves
// half-written state behind is still damage.
//
// What "the call did not execute" means on this chain, measured rather than
// assumed: a contract that raises still ends up statusName FINALIZED with
// result_name MAJORITY_AGREE, because the validators agreed on the outcome of the
// transaction. The field that separates an accepted write from a refused one is
// txExecutionResultName: FINISHED_WITH_RETURN when the method ran, 
// FINISHED_WITH_ERROR when it raised. The transaction record carries no revert
// string, so this run proves refusal and its consequences; the exact rejection
// message for each of these cases is asserted in the direct-mode suite, where
// expect_revert() can see the reason.
//
// Accounts, and why:
//   CLIENT   the throwaway key in this project's .env, the account that deployed
//            D5. It opens the deal and holds the escrow.
//   WORKER   the publicly committed GenLayer devnet test key from
//            gltest.config.yaml, playing the counterparty. It is not a secret: the
//            key is in this repo, which is exactly what makes it a usable adversary
//            on a dev chain, and it is the party that wins the anchor race below.
//   STRANGER a key derived from a fixed seed, funded by CLIENT with a small
//            transfer so it can afford the fee of being refused. Deterministic, so
//            the run is reproducible and no address is lost.
//
// Usage: node scripts/adversarial_live.js
// Reads the contract address from CONTRACT_ADDRESS.txt (which must be D5).
import { createClient, createAccount } from 'genlayer-js';
import { studioDevnet } from 'genlayer-js/chains';
import { createHash } from 'crypto';
import { readFileSync } from 'fs';
import dotenv from 'dotenv';
import { walletPrivateKey } from './wallet_key.js';
import { verifyTx } from './explorer_verify.js';

dotenv.config();

const CONTRACT_ADDRESS = readFileSync('CONTRACT_ADDRESS.txt', 'utf-8').trim();
const CASE_FILE_URL = process.env.CASE_FILE_URL
  || 'https://raw.githubusercontent.com/hoveiser/flight-recorder/d5-signed-events-anchor/demo/case_files/happy_path.json';
const wait = (ms) => new Promise((resolve) => { setTimeout(resolve, ms); });

const CLIENT = createAccount(walletPrivateKey());
const WORKER = createAccount(`0x${'1'.repeat(64)}`);
const STRANGER = createAccount(`0x${createHash('sha256').update('flight-recorder-adversarial-stranger').digest('hex')}`);

const clients = {};
for (const [name, account] of [['client', CLIENT], ['worker', WORKER], ['stranger', STRANGER]]) {
  clients[name] = createClient({ chain: studioDevnet, account });
}

const results = [];
const problems = [];
const state = {};
const log = (line) => { process.stdout.write(`${line}${'\n'}`); };

async function settled(client, hash, label) {
  for (let attempt = 0; attempt < 150; attempt += 1) {
    const tx = await client.getTransaction({ hash });
    const status = tx.statusName || tx.status;
    if (status === 'FINALIZED' || status === 'FAILED' || status === 'REVERTED') return tx;
    await wait(4000);
  }
  throw new Error(`${label}: transaction ${hash} never reached a decision`);
}

async function submit(actor, functionName, args, value, label) {
  const client = clients[actor];
  const fee = await client.estimateTransactionFees();
  const hash = await client.writeContract({
    address: CONTRACT_ADDRESS,
    functionName,
    args,
    value,
    fees: { distribution: fee.distribution, messageAllocations: fee.messageAllocations, feeValue: fee.feeValue },
  });
  log(`  submitted ${label} by ${actor}: ${hash} (fee ${fee.feeValue.toString()} wei)`);
  return hash;
}

async function readDeal(client, id) {
  try {
    const raw = await client.readContract({ address: CONTRACT_ADDRESS, functionName: 'get_deal', args: [id] });
    return JSON.parse(raw);
  } catch (error) {
    log(`  get_deal(${id}) unreadable: ${String(error.shortMessage || error.message).slice(0, 120)}`);
    return null;
  }
}

/**
 * Which deal ids the contract actually holds. The honest check on a rejected
 * open_deal: `next_id` is not a public view, so the ids themselves are what can be
 * read back.
 */
async function existingDealIds(client, upperBound) {
  const ids = [];
  for (let id = 1; id <= upperBound; id += 1) {
    const deal = await readDeal(client, id);
    if (deal && deal.external_deal_id) ids.push(id);
  }
  return ids;
}

/**
 * Run one case.
 *
 * want is 'revert' or 'success'. `message` is what the contract's own guard says,
 * recorded for the table and asserted in the direct-mode suite. `check` receives the
 * post-state and returns a string when something is wrong, which turns the case red:
 * a refusal that quietly changed state is not a pass.
 *
 * opts.guardDeal compares the whole deal against the state read immediately before
 * this attempt. That is the strongest statement a rejection can make: not one field
 * moved. The snapshot has to be taken here rather than once at setup, because a
 * legitimate earlier step (the counterparty's anchor) has already changed the deal,
 * and comparing against a stale picture reports a harness bug as a contract bug.
 */
async function caseRun(name, actor, functionName, args, value, want, message, check = null, opts = {}) {
  let hash = null;
  let execution = 'submission failed';
  let explorerStatus = 'no transaction';
  let link = null;
  let stateNote = '';
  let ok = false;
  const beforeDeal = opts.guardDeal ? await readDeal(clients.client, opts.guardDeal) : null;
  try {
    hash = await submit(actor, functionName, args, value, name);
    const tx = await settled(clients[actor], hash, name);
    execution = String(tx.txExecutionResultName || tx.statusName);
    const record = await verifyTx(hash);
    explorerStatus = record.status;
    link = record.link;
    const ran = execution === 'FINISHED_WITH_RETURN' || execution === 'FINISHED';
    ok = want === 'success' ? ran : !ran;
    if (opts.guardDeal) {
      const now = await readDeal(clients.client, opts.guardDeal);
      const keys = new Set([...Object.keys(beforeDeal || {}), ...Object.keys(now || {})]);
      for (const key of keys) {
        if (JSON.stringify(now?.[key]) !== JSON.stringify(beforeDeal?.[key])) {
          stateNote = `${key} moved from ${JSON.stringify(beforeDeal?.[key])} to ${JSON.stringify(now?.[key])}`;
          ok = false;
          break;
        }
      }
    }
    if (check) {
      const problem = await check({ ran, execution });
      if (problem) { stateNote = stateNote || problem; ok = false; }
    }
  } catch (error) {
    execution = `error: ${String(error.shortMessage || error.message).slice(0, 140)}`;
    ok = false;
  }
  const row = { name, actor, functionName, want, message, hash, execution, explorerStatus, link, stateNote, pass: ok };
  results.push(row);
  log(`${ok ? 'PASS' : 'FAIL'} ${name} [${actor}] ${functionName} want=${want} execution=${execution} explorer=${explorerStatus}${stateNote ? ` state=${stateNote}` : ''}`);
  return row;
}

async function main() {
  log(`contract ${CONTRACT_ADDRESS}`);
  log(`client   ${CLIENT.address}`);
  log(`worker   ${WORKER.address}`);
  log(`stranger ${STRANGER.address}`);

  const strangerBalance = await clients.stranger.getBalance({ address: STRANGER.address });
  if (strangerBalance < 300000000000000000n) {
    log('funding the stranger account with test GEN so it can pay to be refused');
    const hash = await clients.client.sendTransaction({ to: STRANGER.address, value: 400000000000000000n });
    const record = await verifyTx(hash);
    log(`  funding tx ${hash} ${record.status}`);
    await wait(5000);
  }

  const HEAD_A = 'a'.repeat(64);
  const HEAD_B = 'b'.repeat(64);
  const served = await (await fetch(CASE_FILE_URL)).text();
  const digest = createHash('sha256').update(served).digest('hex');
  const declaredHead = JSON.parse(served).chain_integrity.last_hash;
  log(`case file ${CASE_FILE_URL}`);
  log(`case file digest ${digest} declared head ${declaredHead}`);

  // A real deal to attack. Its own id is looked up from the chain: assuming id 1
  // would point at whatever a previous run left behind.
  const externalId = `adv_live_${Date.now()}`;
  await caseRun('open_deal', 'client', 'open_deal', [externalId, '0'.repeat(64), WORKER.address, 300],
    100000000000000000n, 'success', 'n/a (setup)', async () => {
      for (let id = 1; id <= 40; id += 1) {
        const deal = await readDeal(clients.client, id);
        if (deal && deal.external_deal_id === externalId) {
          if (deal.status !== 'funded') return `deal ${id} status is ${deal.status}`;
          state.dealId = id;
          state.snapshot = deal;
          log(`  deal ${id} funded, escrow ${deal.amount}`);
          return null;
        }
      }
      return `no deal with external id ${externalId}`;
    });
  const dealId = state.dealId;
  if (!dealId) throw new Error('setup failed: no deal to attack');

  // Case 1: a dispute with no chain head at all. The guard is the whole deal, field
  // by field, against the state read a moment before the attempt.
  await caseRun('missing_head', 'worker', 'dispute', [dealId, CASE_FILE_URL, digest, ''], 0n, 'revert',
    'chain_head must be 64 lowercase hex characters', null, { guardDeal: dealId });

  // Case 2: a stranger disputes a deal it has no part in.
  await caseRun('non_party_dispute', 'stranger', 'dispute', [dealId, CASE_FILE_URL, digest, HEAD_A], 0n, 'revert',
    'Only parties', null, { guardDeal: dealId });

  // Case 3: the counterparty anchors a head first, then a dispute arrives carrying
  // a different one. This is the race that the separate anchor call used to leave
  // open, and the reason the anchor is now written inside dispute().
  await caseRun('anchor_head_a', 'worker', 'anchor_milestone', [dealId, 'delivery', HEAD_A], 0n, 'success',
    'n/a (setup: the counterparty anchors first)', async () => {
      const now = await readDeal(clients.client, dealId);
      if (now.milestones?.delivery !== HEAD_A) return `anchor is ${now.milestones?.delivery}`;
      return null;
    });
  await caseRun('wrong_head_after_anchor', 'client', 'dispute', [dealId, CASE_FILE_URL, digest, HEAD_B], 0n, 'revert',
    'ANCHOR_MISMATCH: chain head does not match the anchored delivery head', async () => {
      const now = await readDeal(clients.client, dealId);
      if (now.status !== 'funded') return `status became ${now.status}`;
      if (now.milestones?.delivery !== HEAD_A) return `anchor moved to ${now.milestones?.delivery}`;
      if (now.case_file_hash) return `case file hash was stored anyway: ${now.case_file_hash}`;
      return null;
    }, { guardDeal: dealId });

  // Case 4: try to move the anchor that is already on record.
  await caseRun('anchor_overwrite', 'worker', 'anchor_milestone', [dealId, 'delivery', HEAD_B], 0n, 'revert',
    'Milestone already anchored', async () => {
      const now = await readDeal(clients.client, dealId);
      if (now.milestones?.delivery !== HEAD_A) return `anchor moved to ${now.milestones?.delivery}`;
      return null;
    }, { guardDeal: dealId });

  // Case 5: finalize a deal that was never adjudicated.
  await caseRun('finalize_out_of_order', 'client', 'finalize', [dealId], 0n, 'revert', 'Not adjudicated',
    async () => {
      const now = await readDeal(clients.client, dealId);
      if (now.status !== 'funded') return `status became ${now.status}`;
      if (now.payout_status) return `payout_status became ${now.payout_status}`;
      return null;
    }, { guardDeal: dealId });

  // Case 6: a stranger burns the deal's dispute allowance by calling resolve.
  await caseRun('resolve_by_stranger', 'stranger', 'resolve', [dealId], 0n, 'revert', 'Only parties can resolve',
    async () => {
      const now = await readDeal(clients.client, dealId);
      if (now.status !== 'funded') return `status became ${now.status}`;
      if (now.fetch_failures !== 0) return `fetch_failures moved to ${now.fetch_failures}`;
      return null;
    }, { guardDeal: dealId });

  // Case 7: open a deal that promises an escrow it never pays.
  const idsBefore = await existingDealIds(clients.client, dealId + 3);
  await caseRun('zero_value_open_deal', 'client', 'open_deal', ['adv_live_zero', '0'.repeat(64), WORKER.address, 300],
    0n, 'revert', 'open_deal requires payable value');
  const idsAfter = await existingDealIds(clients.client, dealId + 3);
  if (JSON.stringify(idsBefore) !== JSON.stringify(idsAfter)) {
    problems.push(`zero_value_open_deal: deal ids changed from ${idsBefore} to ${idsAfter}`);
  }
  log(`  deal ids before=${JSON.stringify(idsBefore)} after=${JSON.stringify(idsAfter)}`);

  // Case 8: the honest path still works after all that, with the head that is really
  // on record. Without this the run would only show refusals and prove nothing about
  // the useful case.
  await caseRun('honest_dispute_with_anchored_head', 'client', 'dispute', [dealId, CASE_FILE_URL, digest, HEAD_A],
    0n, 'success', 'n/a (the head that is on record is accepted)', async () => {
      const now = await readDeal(clients.client, dealId);
      if (now.status !== 'disputed') return `status is ${now.status}`;
      if (now.milestones?.delivery !== HEAD_A) return `anchor is ${now.milestones?.delivery}`;
      if (now.case_file_hash !== digest) return `anchored case file hash is ${now.case_file_hash}`;
      state.final = now;
      return null;
    });

  log('');
  log('| case | actor | call | wanted | contract guard (asserted in direct mode) | tx | execution | explorer | result |');
  log('| --- | --- | --- | --- | --- | --- | --- | --- | --- |');
  for (const r of results) {
    log(`| ${r.name} | ${r.actor} | ${r.functionName} | ${r.want} | ${r.message} | ${r.hash ? `\`${r.hash}\`` : 'no tx'} | ${r.execution} | ${r.explorerStatus} | ${r.pass ? 'pass' : '**FAIL**'} |`);
  }

  const failed = results.filter((r) => !r.pass);
  if (problems.length > 0) {
    log('STATE PROBLEMS:');
    for (const p of problems) log(`  - ${p}`);
  }
  log('');
  log(`SUMMARY ${JSON.stringify({
    contract: CONTRACT_ADDRESS,
    deal_id: dealId,
    cases: results.length,
    passed: results.length - failed.length,
    failed: failed.length,
    state_problems: problems,
    final_status: state.final?.status || null,
    final_delivery_head: state.final?.milestones?.delivery || null,
    final_case_file_hash: state.final?.case_file_hash || null,
    txs: Object.fromEntries(results.filter((r) => r.hash).map((r) => [r.name, r.hash])),
  })}`);
  if (failed.length > 0 || problems.length > 0) process.exitCode = 1;
}

await main().catch((error) => {
  log(`run aborted: ${String(error.shortMessage || error.message)}`);
  process.exitCode = 1;
});
