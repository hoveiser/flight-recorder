"""Cross-runtime agreement-hash canonicalization.

`open_deal` commits SHA-256(canonical_json(definition_of_done)), and the
contract recomputes that digest during `resolve` to prove the case file carries
the terms the client actually agreed to. That only works while "canonical_json"
means the same thing on both sides of the boundary.

It does not, for non-ASCII terms:

* CPython `json.dumps(..., sort_keys=True, separators=(",", ":"))` -- used by
  src/hash_chain.compute_agreement_hash and by the contract -- escapes every
  non-ASCII character (the accented "e" becomes "\\u00e9").
* The browser's `canonicalJson` in index.html builds on `JSON.stringify`, which
  emits the literal UTF-8 character instead.

The digests below were measured, not derived: the BROWSER_* values come from
running index.html's exact canonicalJson body under V8 (node), the PYTHON_*
values from hashlib over CPython's serialization. They pin the invariant, so a
change to either serializer fails loudly here instead of silently refunding
valid deals on-chain.
"""

from src.hash_chain import canonical_json, compute_agreement_hash

ASCII_DOD = {"success_criteria": "demo delivery"}
NESTED_DOD = {"rule": "1000 rows", "spec": {"rows": 1000, "accept": "oui"}}
# "livrable livre" with an accented e, plus a check-mark: typical of a real
# agreement written by a non-English speaker. Written with escapes so this file
# stays ASCII, exactly as CPython's own serializer would render it.
NON_ASCII_DOD = {"success_criteria": "livrable livr\u00e9 \u2713"}
NON_ASCII_BROWSER_FORM = '{"success_criteria":"livrable livr\u00e9 \u2713"}'

BROWSER_ASCII = "b835f0013a2c8409dac81087ae8c709d60244e7bb6e803edf17e41bc070a185e"
BROWSER_NESTED = "19e4b8bdbcc4e585166ce5ff5132d328f0a6c07da8386b67b53fc26904c4804a"
BROWSER_NON_ASCII = "8a98bd3906168aa41af08f3bcddd028de4b991d5b629c0edcc3b6f8fee2ace19"
PYTHON_NON_ASCII = "2b092ebbb03c1aaf8cfb4ab0f12ed303595cbcb5dca8452215bf810520c35825"


def test_ascii_agreement_hash_matches_the_browser():
    """The path today's demo uses: both runtimes must agree byte for byte."""
    assert compute_agreement_hash(ASCII_DOD) == BROWSER_ASCII


def test_nested_ascii_agreement_hash_matches_the_browser():
    """Key sorting is recursive on both sides, so nesting stays compatible."""
    assert compute_agreement_hash(NESTED_DOD) == BROWSER_NESTED


def test_non_ascii_terms_diverge_between_python_and_the_browser():
    """The confirmed audit finding, pinned as a characterization test.

    A client who opens a deal with an accented term from the browser commits
    BROWSER_NON_ASCII, while src/main.py's own compute_agreement_hash produces
    PYTHON_NON_ASCII for the identical object. Anything that recomputes only the
    Python form -- which is what contracts/settlement.py did before the audit --
    therefore verdicts AGREEMENT_MISMATCH and refunds the client on a deal whose
    terms were never changed. The contract now accepts both digests; this test
    fails if either serialization stops producing these values, which is exactly
    when the accepted set has to be revisited.
    """
    assert compute_agreement_hash(NON_ASCII_DOD) == PYTHON_NON_ASCII
    assert PYTHON_NON_ASCII != BROWSER_NON_ASCII
    assert canonical_json(NON_ASCII_DOD) != NON_ASCII_BROWSER_FORM
