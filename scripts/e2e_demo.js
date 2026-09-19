import crypto from 'crypto';
import { readFileSync, writeFileSync } from 'fs';
import dotenv from 'dotenv';
import { createClient, createAccount } from 'genlayer-js';
import { studioDevnet } from 'genlayer-js/chains';

dotenv.config();

const CONTRACT_ADDRESS = readFileSync('CONTRACT_ADDRESS.txt', 'utf-8').trim();
const FEE_PROFILE = JSON.parse(readFileSync('fee-profile.json', 'utf-8'));
const PRIVATE_KEY = process.env.ACCOUNT_PRIVATE_KEY_1;
const ACCOUNT_ADDRESS = '0x1111111111111111111111111111111111111111';
const CASE_FILE_URL = 'https://raw.githubusercontent.com/microsoft/TypeScript/main/package.json';
const API_BASE = 'http://localhost:8000';
const OFFCHAIN_DEAL_ID = 'demo_scraper_001';

if (!PRIVATE_KEY) {
    console.error('ACCOUNT_PRIVATE_KEY_1 not found in .env');
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

    console.log('Using deployed contract address:', CONTRACT_ADDRESS);
    console.log('Worker address:', ACCOUNT_ADDRESS);

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

    // Seal the off-chain log right before disputing, so the anchored hash
    // describes a record that can no longer be appended to. Best effort: this
    // script does not start the API itself, and the case file it disputes is a
    // static GitHub URL rather than a live off-chain deal.
    try {
        const sealResponse = await fetch(`${API_BASE}/deals/${OFFCHAIN_DEAL_ID}/seal`, { method: 'POST' });
        const sealResult = await sealResponse.json();
        console.log('[dispute] evidence log sealed, chain_head:', sealResult.chain_head);
    } catch (error) {
        console.log('[dispute] seal skipped (off-chain API not reachable):', error.message);
    }

    const disputeResult = await writeWithFees({
        functionName: 'dispute',
        args: [1, CASE_FILE_URL, caseFile.hash],
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
}

try {
    await main();
} catch (error) {
    console.error('\n=== E2E demo failed ===');
    console.error(error);
    process.exitCode = 1;
}
