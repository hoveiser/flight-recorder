// Settle the deals that the live runs on D5 left open, so no test escrow stays
// locked on the dev chain and every deal on D5 ends in a decided state.
//
// Reads each deal first and only sends what the contract still accepts. Deal 2 is
// special: it was opened by the second e2e run (before the script looked its deal
// id up), so it is still funded and has to be disputed before it can be resolved.
// Its dispute anchors the head that run's own sealed log produced, which is the
// head that run actually signed and sealed, not one invented here.
import { createClient, createAccount } from 'genlayer-js';
import { studioDevnet } from 'genlayer-js/chains';
import { readFileSync } from 'fs';
import dotenv from 'dotenv';
import { walletPrivateKey } from './wallet_key.js';
import { verifyTx } from './explorer_verify.js';

dotenv.config();

const CONTRACT_ADDRESS = readFileSync('CONTRACT_ADDRESS.txt', 'utf-8').trim();
const account = createAccount(walletPrivateKey());
const client = createClient({ chain: studioDevnet, account });
const wait = (ms) => new Promise((resolve) => { setTimeout(resolve, ms); });

const TS_PACKAGE_URL = 'https://raw.githubusercontent.com/microsoft/TypeScript/main/package.json';
const TS_PACKAGE_HASH = '2828c1d269bd9c80d634131ec107ac69f1cfc3bf1f98d24c112c825c8acd7902';
const RUN2_SEALED_HEAD = '3b36423aa4e54a8de73df29802092b9c3dbf7137c80ecf5264c5b48c7f3ed371';

async function call(functionName, args, label) {
  const fee = functionName === 'resolve'
    ? await client.estimateTransactionFeesForWrite({ address: CONTRACT_ADDRESS, functionName, args, value: 0n })
    : await client.estimateTransactionFees();
  const hash = await client.writeContract({
    address: CONTRACT_ADDRESS,
    functionName,
    args,
    value: 0n,
    fees: { distribution: fee.distribution, messageAllocations: fee.messageAllocations, feeValue: fee.feeValue },
  });
  console.log(`[${label}] ${functionName} tx ${hash}`);
  let tx;
  for (let attempt = 0; attempt < 90; attempt += 1) {
    tx = await client.getTransaction({ hash });
    const status = tx.statusName || tx.status;
    if (['FINALIZED', 'FAILED', 'REVERTED'].includes(status)) break;
    await wait(4000);
  }
  const record = await verifyTx(hash);
  console.log(`[${label}] execution=${tx.txExecutionResultName} explorer=${record.status}`);
  return hash;
}

async function readDeal(id) {
  return JSON.parse(await client.readContract({ address: CONTRACT_ADDRESS, functionName: 'get_deal', args: [id] }));
}

async function main() {
  const ids = process.argv.slice(2).map(Number).filter(Number.isInteger);
  for (const id of ids) {
    let deal = await readDeal(id);
    console.log(`\ndeal ${id} (${deal.external_deal_id}) status=${deal.status} verdict=${deal.verdict} anchor=${deal.milestones?.delivery || 'none'}`);
    if (deal.status === 'refunded' || deal.status === 'released') {
      console.log(`  already settled, nothing to do`);
      continue;
    }
    if (deal.status === 'funded') {
      if (id !== 2) {
        console.log('  funded but not deal 2, leaving it: this script only knows the case file for deal 2');
        continue;
      }
      await call('dispute', [id, TS_PACKAGE_URL, TS_PACKAGE_HASH, RUN2_SEALED_HEAD], `deal ${id}`);
      deal = await readDeal(id);
      console.log(`  status now ${deal.status}`);
    }
    if (deal.status === 'disputed') {
      await call('resolve', [id], `deal ${id}`);
      deal = await readDeal(id);
      console.log(`  status now ${deal.status} verdict ${deal.verdict} payout ${deal.payout_status} reasoning ${deal.reasoning}`);
    }
  }
  console.log(`\nget_payouts(): ${await client.readContract({ address: CONTRACT_ADDRESS, functionName: 'get_payouts', args: [] })}`);
}

await main();
