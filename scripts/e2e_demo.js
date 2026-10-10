import crypto from 'crypto';
import { spawn } from 'child_process';
import { join } from 'path';
import { tmpdir } from 'os';
import { readFileSync, writeFileSync, unlinkSync } from 'fs';
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
        console.log(`[${label}] status=${status}`);

        if (status === 'FINALIZED' || status === 'finalized') {
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
    const feeEstimate = functionName === 'resolve'
        ? await client.estimateTransactionFeesForWrite({
            ...feeOptions,
            address,
            functionName,
            args,
            value,
        })
        : await client.estimateTransactionFees(feeOptions);
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

        const openDealValue = 100000000000000000n;
        const openDealResult = await writeWithFees({
            functionName: 'open_deal',
            args: ['demo_scraper_001', 'a'.repeat(64), ACCOUNT_ADDRESS, 300],
            value: openDealValue,
            label: 'open_deal',
        });
        steps.push({ label: 'open_deal', ...openDealResult });

        const openDealView = await readDeal(1);
        console.log('\n[open_deal] get_deal(1):', openDealView);

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
            args: [1, CASE_FILE_URL, caseFile.hash, chainHead],
            label: 'dispute',
        });
        steps.push({ label: 'dispute', ...disputeResult });

        const disputeView = await readDeal(1);
        console.log('\n[dispute] get_deal(1):', disputeView);

        const resolveResult = await writeWithFees({
            functionName: 'resolve',
            args: [1],
            label: 'resolve',
        });
        steps.push({ label: 'resolve', ...resolveResult });

        const resolvedDeal = await readDeal(1);
        console.log('\n[resolve] get_deal(1):', resolvedDeal);

        const finalizeResult = await writeWithFees({
            functionName: 'finalize',
            args: [1],
            label: 'finalize',
        });
        steps.push({ label: 'finalize', ...finalizeResult });

        const finalDeal = await readDeal(1);
        const payouts = await readPayouts();

        console.log('\n[finalize] get_deal(1):', finalDeal);
        console.log('[finalize] get_payouts():', payouts);

        const totalFees = steps.reduce((sum, step) => sum + step.feeValue, 0n);
        const summary = `# Settlement E2E Demo Summary

- Contract: ${CONTRACT_ADDRESS}
- Network: studio-dev
- Worker: ${ACCOUNT_ADDRESS}
- Off-chain deal: ${offchainDealId} (2 signed events, sealed at ${chainHead})
- Case file: ${CASE_FILE_URL}
- Note: this static case file carries no definition_of_done, so the expected
  outcome is the DISAGREEMENT path (labeled AGREEMENT_MISMATCH) refunding the
  client inside resolve(). It exercises the pipeline, not a happy verdict.
- Final deal: ${finalDeal}
- Final payouts: ${payouts}
- Total fees spent: ${totalFees.toString()} wei

## Transactions

| Step | TX hash | Explorer | Fee (wei) |
| --- | --- | --- | ---: |
${steps.map((step) => `| ${step.label} | ${step.txHash} | https://explorer-studio-dev.genlayer.com/tx/${step.txHash} | ${step.feeValue.toString()} |`).join('\n')}
`;

        writeFileSync('scripts/e2e_results.md', summary);
        console.log('\nSummary saved to scripts/e2e_results.md');
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
