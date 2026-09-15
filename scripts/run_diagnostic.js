import dotenv from 'dotenv';
import { createClient, createAccount } from 'genlayer-js';
import { studioDevnet } from 'genlayer-js/chains';

import { readFileSync } from 'fs';

dotenv.config();

const contractAddress = readFileSync('DIAGNOSTIC_ADDRESS.txt', 'utf-8').trim();
const caseFileUrl = 'https://raw.githubusercontent.com/microsoft/TypeScript/main/package.json';
const privateKey = process.env.ACCOUNT_PRIVATE_KEY_1;

if (!privateKey) {
    throw new Error('ACCOUNT_PRIVATE_KEY_1 not found in .env');
}

const client = createClient({
    chain: studioDevnet,
    account: createAccount(privateKey),
});

function wait(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
}

async function waitForFinalized(hash, label) {
    const timeoutMs = 180000;
    const startedAt = Date.now();

    while (Date.now() - startedAt < timeoutMs) {
        const tx = await client.getTransaction({ hash });
        const status = tx.statusName || tx.status || tx.lifecycle?.state;
        console.log(`[${label}] status=${status}`);

        if (status === 'FINALIZED' || status === 'finalized' || tx.lifecycle?.state === 'finalized') {
            return tx;
        }

        if (status === 'REVERTED' || status === 'reverted' || status === 'FAILED' || status === 'failed') {
            throw new Error(`${label} failed: ${JSON.stringify(tx)}`);
        }

        await wait(2500);
    }

    throw new Error(`${label} did not finalize within ${timeoutMs}ms: ${hash}`);
}

async function callAndRead({ label, functionName, args, resultKey }) {
    const feeEstimate = await client.estimateTransactionFees();
    console.log(`[${label}] feeValue=${feeEstimate.feeValue.toString()}`);

    const txHash = await client.writeContract({
        address: contractAddress,
        functionName,
        args,
        value: 0n,
        fees: {
            distribution: feeEstimate.distribution,
            feeValue: feeEstimate.feeValue,
        },
    });

    console.log(`[${label}] txHash=${txHash}`);
    await waitForFinalized(txHash, label);

    const storedResult = await client.readContract({
        address: contractAddress,
        functionName: 'get_result',
        args: [resultKey],
    });

    console.log(`[${label}] stored=${storedResult}`);
    return { txHash, storedResult };
}

console.log(`Diagnostic contract: ${contractAddress}`);
console.log(`Case file URL: ${caseFileUrl}`);

const results = {};
results.web_fetch = await callAndRead({
    label: 'test_web_fetch',
    functionName: 'test_web_fetch',
    args: [caseFileUrl],
    resultKey: 'web_fetch',
});
results.llm_call = await callAndRead({
    label: 'test_llm_call',
    functionName: 'test_llm_call',
    args: [],
    resultKey: 'llm_call',
});
results.combined = await callAndRead({
    label: 'test_combined',
    functionName: 'test_combined',
    args: [caseFileUrl],
    resultKey: 'combined',
});

console.log('\nDIAGNOSTIC_JSON=' + JSON.stringify(results));
