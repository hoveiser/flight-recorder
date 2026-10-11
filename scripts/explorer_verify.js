// Independent verification of a transaction hash against the studio-dev explorer.
//
// Every hash this round writes into a doc or a PR goes through here first. The
// scripts already poll the RPC for a decision, but that only proves what the node
// we are talking to believes; the explorer is a separate reader of the same chain,
// so it is the check that catches a hash that was mistyped, truncated or never
// submitted at all.
//
// Endpoint shape (probed on Oct 10, 2026, and confirmed against a real deploy):
//   GET https://explorer-studio-dev.genlayer.com/api/transactions/{hash}
//   -> { transaction: { hash, status, from_address, to_address, value, ... },
//        triggeredTransactions, parentTransaction }
const EXPLORER_API = 'https://explorer-studio-dev.genlayer.com/api/transactions';
const EXPLORER_WEB = 'https://explorer-studio-dev.genlayer.com/tx';

/** Return the explorer's own record of `hash`, or throw if it has no such tx. */
export async function verifyTx(hash, { attempts = 6, delayMs = 5000 } = {}) {
  let last = null;
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    const response = await fetch(`${EXPLORER_API}/${hash}`, { headers: { accept: 'application/json' } });
    if (response.status === 404) {
      last = `the explorer has no transaction ${hash}`;
    } else if (!response.ok) {
      last = `explorer HTTP ${response.status}`;
    } else {
      const body = await response.json();
      const tx = body?.transaction;
      if (!tx || tx.hash?.toLowerCase() !== String(hash).toLowerCase()) {
        last = `explorer returned no matching hash for ${hash}`;
      } else {
        return {
          hash: tx.hash,
          status: tx.status,
          from: tx.from_address,
          to: tx.to_address,
          value: tx.value,
          link: `${EXPLORER_WEB}/${hash}`,
        };
      }
    }
    await new Promise((resolve) => { setTimeout(resolve, delayMs); });
  }
  throw new Error(`could not verify ${hash} against the explorer: ${last}`);
}

/**
 * Assert that the explorer agrees the transaction exists and, when a status list
 * is given, ended in one of `expectedStatuses`. Pass null for `expectedStatuses`
 * when the status itself is the thing under test: the adversarial run expects
 * rejections, so what must never happen is a hash the chain does not know about.
 */
export async function requireTx(hash, expectedStatuses = ['FINALIZED'], label = '') {
  let record = null;
  // A decision can reach the chain before the explorer's reader catches up, and a
  // PENDING record proves nothing yet. Poll until it settles, then judge.
  for (let attempt = 0; attempt < 6; attempt += 1) {
    record = await verifyTx(hash);
    if (record.status !== 'PENDING') break;
    await new Promise((resolve) => { setTimeout(resolve, 5000); });
  }
  if (expectedStatuses !== null && !expectedStatuses.includes(record.status)) {
    throw new Error(
      `${label} ${hash}: explorer status is ${record.status}, expected one of ${expectedStatuses.join('/')}`,
    );
  }
  console.log(`[verified] ${label} ${record.status} ${record.link}`);
  return record;
}
