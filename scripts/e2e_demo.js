import crypto from 'crypto';
import { spawn } from 'child_process';
import { join } from 'path';
import { tmpdir } from 'os';
import { readFileSync, appendFileSync, unlinkSync } from 'fs';
import dotenv from 'dotenv';
import { createClient, createAccount } from 'genlayer-js';
import { studioDevnet } from 'genlayer-js/chains';
import { walletPrivateKey } from './wallet_key.js';
import { apiJson, recordSignedEvent, sealOffchain } from './event_signing.js';

dotenv.config();

const CONTRACT_ADDRESS = readFileSync('CONTRACT_ADDRESS.txt', 'utf-8').trim();
const FEE_PROFILE = JSON.parse(readFileSync('fee-profile.json', 'utf-8'));
const ACCOUNT_ADDRESS = '0x1111111111111111111111111111111111111111';
const CASE_FILE_URL = 'https://raw.githubusercontent.com/microsoft/TypeScript/main/package.json';
const API_BASE = process.env.FLIGHT_RECORDER_URL || 'http://localhost:8000';

let PRIVATE_KEY;
try {
    PRIVATE_KEY = walletPrivateKey();
} catch (error) {
    console.error(error.message);
    process.exit(1);
}

const account = createAccount(PRIVATE_KEY);
const client = createClient({
    chain: studioDevnet,
    account,
});

function wait(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
}

// The recorder is where the head being anchored comes from, so the demo needs one
// running. Reuse whatever is already on API_BASE, otherwise start a throwaway
// instance against a temp database so no previous log can influence the run.
async function ensureRecorderApi() {
    try {
        const probe = await fetch(`${API_BASE}/docs`);
        if (probe.ok) return {};
    } catch (_) { /* not running yet */ }

    const dbPath = join(tmpdir(), `flight_recorder_e2e_${Date.now()}.db`);
    const python = process.platform === 'win32' ? 'python' : 'python3';
    const port = new URL(API_BASE).port || '8000';
    const server = spawn(python, ['-m', 'uvicorn', 'src.main:app', '--port', port], {
        stdio: 'ignore',
        env: { ...process.env, FLIGHT_RECORDER_DB: dbPath },
    });
    for (let attempt = 0; attempt < 60; attempt += 1) {
        try {
            const probe = await fetch(`${API_BASE}/docs`);
            if (probe.ok) return { server, dbPath };
        } catch (_) { /* keep waiting */ }
        await wait(500);
    }
    server.kill();
    throw new Error(`could not reach or start the evidence API at ${API_BASE}`);
}

async function getFinalizedTx(hash, label) {
    console.log(`\n[${label}] Waiting for tx finalization: ${hash}`);
    const startedAt = Date.now();
    const timeoutMs = 180000;

    while (Date.now() - startedAt < timeoutMs) {
        const tx = await client.getTransaction({ hash });
        const status = tx.statusName || tx.status || tx.lifecycle?.state;
        console.log(`[${label}] status=${status} execution=${tx.txExecutionResultName}`);

        if (status === 'FINALIZED' || status === 'finalized') {
            // A decided transaction is not a successful call. On studio-dev a
            // contract that raises still ends FINALIZED with MAJORITY_AGREE, and
            // only txExecutionResultName says whether the method ran. Without this
            // check a reverted write looks like a pass to everything downstream.
            const execution = tx.txExecutionResultName;
            if (execution && execution !== 'FINISHED_WITH_RETURN' && execution !== 'FINISHED') {
                throw new Error(`${label} tx ${hash} was decided but the contract refused it: ${execution}`);
            }
            return tx;
        }

        if (status === 'REVERTED' || status === 'reverted' || status === 'FAILED' || status === 'failed') {
            throw new Error(`${label} tx reverted or failed: ${JSON.stringify(tx)}`);
        }

        await wait(2500);
    }

    throw new Error(`${label} tx did not finalize within ${timeoutMs}ms: ${hash}`);
}

async function writeWithFees({ functionName, args, value = 0n, label, address = CONTRACT_ADDRESS }) {
    const feeOptions = FEE_PROFILE.methods[functionName] || {};
    let feeEstimate;
    if (functionName === 'resolve') {
        // Ask the node to price this exact call. The recorded profile in
        // fee-profile.json carries a messageAllocation measured against another
        // contract and another sender, and the node refuses an allocation that
        // does not match a message the transaction really produces
        // (MessageNoMatchingAllocation), so it is only a fallback here.
        try {
            feeEstimate = await client.estimateTransactionFeesForWrite({
                address,
                functionName,
                args,
                value,
            });
        } catch (cause) {
            console.log(`[${label}] fee estimate failed (${String(cause.details || cause.message)}), using the recorded profile`);
            feeEstimate = await client.estimateTransactionFeesForWrite({
                ...feeOptions,
                address,
                functionName,
                args,
                value,
            });
        }
    } else {
        feeEstimate = await client.estimateTransactionFees(feeOptions);
    }
    console.log(`[${label}] estimated feeValue=${feeEstimate.feeValue.toString()}`);

    const txHash = await client.writeContract({
        address,
        functionName,
        args,
        value,
        fees: {
            distribution: feeEstimate.distribution,
            messageAllocations: feeEstimate.messageAllocations,
            feeValue: feeEstimate.feeValue,
        },
    });

    console.log(`[${label}] txHash=${txHash}`);
    const finalizedTx = await getFinalizedTx(txHash, label);
    return {
        txHash,
        finalizedTx,
        feeValue: BigInt(feeEstimate.feeValue),
    };
}

async function readDeal(dealId) {
    const value = await client.readContract({
        address: CONTRACT_ADDRESS,
        functionName: 'get_deal',
        args: [dealId],
    });

    return value;
}

/**
 * The contract's own id for an external deal id. `open_deal` returns the id in the
 * transaction's return value, which this script cannot read back, and hardcoding 1
 * silently picked up a deal left over from an earlier run: the second run of the
 * demo disputed the first run's deal instead of its own. Looking the id up from the
 * chain is the only honest way to point at what was just created.
 */
async function findDealId(externalId) {
    for (let id = 1; id <= 60; id += 1) {
        const raw = await readDeal(id);
        let deal = null;
        try { deal = typeof raw === 'string' ? JSON.parse(raw) : raw; } catch (_) { deal = null; }
        if (deal && deal.external_deal_id === externalId) return id;
    }
    throw new Error(`no deal with external id ${externalId} on ${CONTRACT_ADDRESS}`);
}

async function readPayouts() {
    return await client.readContract({
        address: CONTRACT_ADDRESS,
        functionName: 'get_payouts',
        args: [],
    });
}

async function fetchCaseFileHash(url) {
    const response = await fetch(url);
    if (!response.ok) {
        throw new Error(`Failed to fetch case file URL: ${response.status} ${response.statusText}`);
    }

    const text = await response.text();
    const hash = crypto.createHash('sha256').update(text).digest('hex');
    return { text, hash };
}

async function main() {
    const steps = [];
    const recorder = await ensureRecorderApi();
    try {
        console.log('Using deployed contract address:', CONTRACT_ADDRESS);
        console.log('Worker address:', ACCOUNT_ADDRESS);
        console.log('Evidence API:', API_BASE);

        const externalDealId = `demo_scraper_${Date.now()}`;
        const openDealValue = 100000000000000000n;
        const openDealResult = await writeWithFees({
            functionName: 'open_deal',
            args: [externalDealId, 'a'.repeat(64), ACCOUNT_ADDRESS, 300],
            value: openDealValue,
            label: 'open_deal',
        });
        steps.push({ label: 'open_deal', ...openDealResult });

        const dealId = await findDealId(externalDealId);
        const openDealView = await readDeal(dealId);
        console.log(`\n[open_deal] deal ${dealId} (${externalDealId}):`, openDealView);

        const caseFile = await fetchCaseFileHash(CASE_FILE_URL);
        console.log('\n[dispute] case file hash:', caseFile.hash);
        console.log('[dispute] case file URL:', CASE_FILE_URL);

        // Record a real signed log, then seal it. The head the seal returns is the
        // only thing a dispute may anchor from D5 on, and it is immutable once
        // written, so the anchored value can never describe a log that grew later.
        const offchainDealId = `demo_scraper_${Date.now()}`;
        await apiJson(`${API_BASE}/deals`, {
            method: 'POST',
            headers: { 'content-type': 'application/json' },
            body: JSON.stringify({
                deal_id: offchainDealId,
                definition_of_done: { success_criteria: '1000 valid product records' },
                parties: [account.address, ACCOUNT_ADDRESS],
            }),
        });
        await recordSignedEvent(API_BASE, account, offchainDealId, 'REQUEST', { request: 'collect 1000 records' });
        await recordSignedEvent(API_BASE, account, offchainDealId, 'DELIVERY', { valid_records: 500 });
        const chainHead = await sealOffchain(API_BASE, account, offchainDealId);

        const disputeResult = await writeWithFees({
            functionName: 'dispute',
            args: [dealId, CASE_FILE_URL, caseFile.hash, chainHead],
            label: 'dispute',
        });
        steps.push({ label: 'dispute', ...disputeResult });

        const disputeViewRaw = await readDeal(dealId);
        const disputeView = JSON.parse(disputeViewRaw);
        console.log(`\n[dispute] get_deal(${dealId}):`, disputeViewRaw);
        // Read the state back rather than trusting the decision: the whole point of
        // the dispute is the anchor, so the anchor on chain must be this head.
        if (disputeView.status !== 'disputed') {
            throw new Error(`dispute did not put deal ${dealId} into disputed: ${disputeView.status}`);
        }
        if (disputeView.milestones?.delivery !== chainHead) {
            throw new Error(`anchored head is ${disputeView.milestones?.delivery}, expected ${chainHead}`);
        }

        const resolveResult = await writeWithFees({
            functionName: 'resolve',
            args: [dealId],
            label: 'resolve',
        });
        steps.push({ label: 'resolve', ...resolveResult });

        const resolvedDeal = await readDeal(dealId);
        console.log(`\n[resolve] get_deal(${dealId}):`, resolvedDeal);
        const resolvedView = JSON.parse(resolvedDeal);

        // finalize() is only for a verdict that still has to be paid. An evidence
        // verdict (this run lands on AGREEMENT_MISMATCH) refunds inside resolve()
        // and leaves the deal refunded, so calling finalize afterwards is refused by
        // the contract, and the honest demo says so instead of pretending the tx
        // belonged there.
        let finalizeResult = null;
        if (resolvedView.status === 'adjudicated') {
            finalizeResult = await writeWithFees({
                functionName: 'finalize',
                args: [dealId],
                label: 'finalize',
            });
            steps.push({ label: 'finalize', ...finalizeResult });
        } else {
            console.log(`\n[finalize] skipped: deal ${dealId} is ${resolvedView.status} with verdict ${resolvedView.verdict}, the payout already happened in resolve()`);
        }

        const finalDeal = await readDeal(dealId);
        const payouts = await readPayouts();

        console.log(`\n[finalize] get_deal(${dealId}):`, finalDeal);
        console.log('[finalize] get_payouts():', payouts);

        const totalFees = steps.reduce((sum, step) => sum + step.feeValue, 0n);
        const summary = `# Settlement E2E Demo Summary

- Contract: ${CONTRACT_ADDRESS}
- Network: studio-dev
- Worker: ${ACCOUNT_ADDRESS}
- On-chain deal: ${dealId} (${externalDealId}), anchored delivery head ${chainHead}
- Off-chain deal: ${offchainDealId} (2 signed events, sealed at ${chainHead})
- Case file: ${CASE_FILE_URL}
- Note: this static case file carries no definition_of_done, so the expected
  outcome is the DISAGREEMENT path (labeled AGREEMENT_MISMATCH) refunding the
  client inside resolve(). It exercises the pipeline, not a happy verdict.
- Finalize: ${finalizeResult ? `paid out by finalize in tx ${finalizeResult.txHash}` : `not needed, resolve() already settled the deal (status ${resolvedView.status})`}
- Final deal: ${finalDeal}
- Final payouts: ${payouts}
- Total fees spent: ${totalFees.toString()} wei

## Transactions

| Step | TX hash | Explorer | Fee (wei) |
| --- | --- | --- | ---: |
${steps.map((step) => `| ${step.label} | ${step.txHash} | https://explorer-studio-dev.genlayer.com/tx/${step.txHash} | ${step.feeValue.toString()} |`).join('\n')}
`;

        // Append, never overwrite. This file is the running record of every round
        // against every deployment, and a demo run that rewrote it deleted the
        // history of D1 to D4 (it did, on Oct 10, and the file came back from git).
        const stamp = new Date().toISOString();
        appendFileSync('scripts/e2e_results.md', `\n\n---\n\n# E2E demo run ${stamp}\n${summary}`);
        console.log('\nSummary appended to scripts/e2e_results.md');
        console.log(summary);
    } finally {
        if (recorder.server) recorder.server.kill('SIGTERM');
        if (recorder.dbPath) { try { unlinkSync(recorder.dbPath); } catch (_) { /* best effort */ } }
    }
}

try {
    await main();
} catch (error) {
    console.error('\n=== E2E demo failed ===');
    console.error(error);
    process.exitCode = 1;
}
