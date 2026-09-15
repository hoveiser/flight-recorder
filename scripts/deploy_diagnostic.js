import { createClient, createAccount } from 'genlayer-js';
import { studioDevnet } from 'genlayer-js/chains';
import { readFileSync, writeFileSync } from 'fs';
import dotenv from 'dotenv';

dotenv.config();

const privateKey = process.env.ACCOUNT_PRIVATE_KEY_1;
if (!privateKey) {
    console.error('ACCOUNT_PRIVATE_KEY_1 not found in .env');
    process.exit(1);
}

const account = createAccount(privateKey);
const client = createClient({
    chain: studioDevnet,
    account,
});

const contractSource = readFileSync('contracts/diagnostic.py', 'utf-8');

console.log('Deploying Diagnostic contract to studio-dev...');

const feeEstimate = await client.estimateTransactionFees();
console.log('Estimated fee value:', feeEstimate.feeValue.toString());

const result = await client.deployContract({
    code: contractSource,
    args: [],
    value: 0n,
    fees: {
        distribution: feeEstimate.distribution,
        feeValue: feeEstimate.feeValue,
    },
});

console.log('Transaction hash:', result);
console.log('Waiting for deployment...');

const receipt = await client.waitForTransactionReceipt({
    hash: result,
    waitUntil: 'decided',
    retries: 200,
});

const deployedAddress =
    receipt.contractAddress ||
    receipt?.txDataDecoded?.contractAddress ||
    receipt.to_address ||
    receipt.recipient;
if (!deployedAddress) {
    throw new Error(`Deployment receipt did not contain a contract address: ${JSON.stringify(receipt)}`);
}

console.log('Contract deployed at:', deployedAddress);
console.log('Explorer:', `https://explorer-studio-dev.genlayer.com/address/${deployedAddress}`);
writeFileSync('DIAGNOSTIC_ADDRESS.txt', deployedAddress);
console.log('Contract address saved to DIAGNOSTIC_ADDRESS.txt');

const schema = await client.getContractSchema({ address: deployedAddress });
console.log('\nContract methods:');
console.log(JSON.stringify(schema.methods, null, 2));
