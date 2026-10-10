// Resolve the throwaway signing key for the local scripts.
//
// .env holds GENLAYER_PRIVATE_KEY (a disposable, hackathon-funded test key).
// ACCOUNT_PRIVATE_KEY_1 is accepted as a legacy alias so an older .env still
// works. The key is never printed: callers only use it through genlayer-js.
export function walletPrivateKey(env = process.env) {
  const key = env.GENLAYER_PRIVATE_KEY || env.ACCOUNT_PRIVATE_KEY_1;
  if (!key) {
    throw new Error(
      'No wallet key in the environment. Put GENLAYER_PRIVATE_KEY=<throwaway key> in .env.',
    );
  }
  return key;
}
