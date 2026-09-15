import { readFileSync } from 'fs';
import dotenv from 'dotenv';
import { createClient, createAccount } from 'genlayer-js';
import { studioDevnet } from 'genlayer-js/chains';


dotenv.config();

const contractAddress = '0x4bA38e58f0d413405C0c4F079328ff7C5848Fa35';
const privateKey = process.env.ACCOUNT_PRIVATE_KEY_1;
const feeProfile = JSON.parse(readFileSync('fee-profile.json', 'utf-8'));

if (!privateKey) {
    throw new Error('ACCOUNT_PRIVATE_KEY_1 not found in .env');
}

const client = createClient({
    chain: studioDevnet,
    account: createAccount(privateKey),
});

const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function waitForFinalized(hash, label) {
    const startedAt = Date.now();
    while (Date.now() - startedAt < 180000) {
        const tx = await client.getTransaction({ hash });
        const status = tx.statusName || tx.status || tx.lifecycle?.state;
        console.log(`[${label}] status=${status}`);
        if (status === 'FINALIZED' || status === 'finalized' || tx.lifecycle?.state === 'finalized') {
            return tx;
        }
        if (status === 'FAILED' || status === 'failed' || status === 'REVERTED' || status === 'reverted') {
            throw new Error(`${label} failed: ${JSON.stringify(tx)}`);
        }
        await wait(2500);
    }
    throw new Error(`${label} did not finalize: ${hash}`);
}

async function writeWithProfile(functionName, args, label) {
    const options = feeProfile.methods[functionName] ?? {};
    const feeEstimate = await client.estimateTransactionFeesForWrite({
        ...options,
        address: contractAddress,
        functionName,
        args,
    });
    console.log(`[${label}] fees=${JSON.stringify(feeEstimate, (_, value) => typeof value === 'bigint' ? value.toString() : value)}`);
    const txHash = await client.writeContract({
        address: contractAddress,
        functionName,
        args,
        value: 0n,
        fees: {
            distribution: feeEstimate.distribution,
            messageAllocations: feeEstimate.messageAllocations,
            feeValue: feeEstimate.feeValue,
        },
    });
    console.log(`[${label}] txHash=${txHash}`);
    const receipt = await waitForFinalized(txHash, label);
    return { txHash, receipt, fees: feeEstimate };
}

const resolve = await writeWithProfile('resolve', [1], 'resolve');
const dealAfterResolve = await client.readContract({
    address: contractAddress,
    functionName: 'get_deal',
    args: [1],
});
console.log('[resolve] deal=' + dealAfterResolve);
console.log('[resolve] receipt=' + JSON.stringify({
    status: resolve.receipt.status,
    statusName: resolve.receipt.statusName,
    txExecutionResult: resolve.receipt.txExecutionResult,
    txExecutionResultName: resolve.receipt.txExecutionResultName,
    result_name: resolve.receipt.result_name,
}, null, 2));

if (JSON.parse(dealAfterResolve).status === 'adjudicated') {
    const finalize = await writeWithProfile('finalize', [1], 'finalize');
    const finalDeal = await client.readContract({
        address: contractAddress,
        functionName: 'get_deal',
        args: [1],
    });
    const payouts = await client.readContract({
        address: contractAddress,
        functionName: 'get_payouts',
        args: [],
    });
    console.log('[finalize] txHash=' + finalize.txHash);
    console.log('[finalize] deal=' + finalDeal);
    console.log('[finalize] payouts=' + payouts);
    console.log('[finalize] receipt=' + JSON.stringify({
        status: finalize.receipt.status,
        statusName: finalize.receipt.statusName,
        txExecutionResult: finalize.receipt.txExecutionResult,
        txExecutionResultName: finalize.receipt.txExecutionResultName,
        result_name: finalize.receipt.result_name,
    }, null, 2));
}
