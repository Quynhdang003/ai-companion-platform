# Scam test set

`cases.jsonl`: one labelled situation per line, written the way the call agent describes what the caller was told or asked (the `situation` of the `check_scam` tool). Loaded and validated by `scripts/scam_cases.py`.

| Field | |
|---|---|
| `id` | `<group>-<nn>`, unique |
| `level` | Expected risk: `high`, `medium`, `low` or `none` (definitions on `RiskLevel` in `app/models/scam.py`) |
| `scam_type` | `ScamType` value for `medium` and `high`; `null` for harmless cases |
| `tags` | `no_diacritics` (STT-style text), `short` (one sentence), `look_alike` (harmless, but shares words or a story with a scam) |
| `situation` | Vietnamese, ≤ 500 characters, no names or phone numbers |

Contents: 35 high-risk cases (4–5 per scam type, `other` included), 5 medium, 5 low and 8 none; 8 are written without diacritics.

What the tests check on layer 1 (`app/services/scam/rules.py`):
- it never calls a case high unless it is labelled high, and then with the right type;
- every high case gets at least medium, so the caller is warned even if the classifier fails;
- no harmless (`none`) case gets more than low.

The cases and the layer-1 phrases were written together (SCAM-02), so layer-1 results on this set are optimistic. Add cases written by someone else to measure it fairly, and run the whole engine with `scripts.eval_scam` (SCAM-03).
