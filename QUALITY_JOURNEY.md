# Quality journey: how this product was tested, broken, and hardened

An honest audit of every failure found during the build, how each was
diagnosed, at which layer it was fixed, and what now prevents its return.
All failures below were real (observed in traces or eval runs), and every
number was verified against SQL/pandas ground truth computed independently
of the agent.

## The loop

1. **Define "good" executably.** Eval cases with hand-derived ground truth,
   written before and during the build, not after.
2. **Test three ways.** Automated suite (deterministic checks + audited LLM
   judge), deterministic unit tests on the tool layer, and human red-teaming
   against a prepared question battery with in-product feedback capture.
3. **Diagnose from traces, not vibes.** Every conversation logs question,
   tool calls, and answer to CSV. Failures were read from traces and coded
   into root-cause classes (the same open/axial coding you'd apply to any
   qualitative failure data).
4. **Fix at the right layer.** The recurring decision: does this failure
   move into deterministic code, into the behavioral contract (prompt), or
   into the harness? Rule of thumb that emerged: anything involving
   completeness, counting, arithmetic, filtering, or provenance moves to
   code; tone, persistence, and disclosure behaviors go to the prompt; and
   every observed failure becomes a regression test either way.
5. **Ratchet, never slide.** The suite only grows: 12 → 13 → 17 → 19 → 25
   LLM eval cases plus 26 tool-layer unit tests. Observed wrong answers are
   encoded as forbidden patterns, so the exact historical bugs can never
   silently return.

## Score timeline

| Round | Gate | Result | What it caught |
|---|---|---|---|
| 1 | Eval suite v1 (12 keyword cases) | 8/12 | 3 infra crashes (API rate limits), 1 refusal phrased outside keyword list |
| 2 | Suite v1.1 (13 cases, retry/backoff) | 10/13 | Dropped high-severity signal; vague discount answer; missing calendar disclosure |
| 3 | Suite v1.1 rerun after fixes | 13/13 | (temperature 0.2, completeness rules) |
| 4 | Harness redesigned: two-tier (deterministic + cross-provider LLM judge) after critique that keyword lists can't test refusals | 13/13 | Methodology fix, not score fix |
| 5 | Manual verification vs ground truth (7 questions) | 3 major failures | Model-side arithmetic (€1M pipeline error), truncated-view recall (missing declining account), capability misstatement |
| 6 | Suite v2 (19 cases incl. exact-number and exact-set classes) | 18/19 | One flaky case (knowledge lookup stopped a hop early) |
| 7 | Human red-team: 27-question battery, feedback captured in-product | 14 clean, 12 discrepancies, 1 flakiness note | The two worst bugs of the project (below) |
| 8 | Suite v3 (25 cases incl. 2 scripted multi-turn) + 26 unit tests | 25/25 and 26/26 single-run | Full suite green on a single pass |
| 9 | Reliability@3: every case run 3x on both providers (claude-sonnet-5 and gpt-4o) | 24/25 cases fully green per provider (74/75 and 73/75 at run level) | One residual flaky case per provider, and they differ: a multi-turn ambiguity case on one, the discount guardrail on the other. This is the known nondeterminism gap, now measured instead of assumed. |

## Error taxonomy: what failed, why, and where it was fixed

| # | Failure (observed, not hypothetical) | Root cause | Fix layer | Regression guard |
|---|---|---|---|---|
| 1 | Cited a battlecard section it never read (section didn't exist) | Model narrating unread sources | Prompt: cite only retrieved docs | Eval: tool-call assertions |
| 2 | "IT Manager" became "CTO" | Title inflation | Prompt: exact ROLE_TITLE | Eval: forbidden `\bCTO\b` |
| 3 | Claimed "no matching case study" without checking; twice | Reliance on model to remember retrieval | **Code**: reference matching became a deterministic signal (industry/region/size/competitor-tag scoring) | Eval: reference must appear |
| 4 | Missed churn-risk account in "which customers are declining" (2 of 3 named) | Answered a set question from a top-5 ranked view; silent truncation | **Code**: `scan_book_signals`, exhaustive scan with self-describing coverage ("41 scanned, 3 flagged") | Eval: exact-set case; unit test: exactly 3 accounts |
| 5 | Pipeline value wrong by ~€1M; 24 accounts counted as 23; 24+15 reported as "39 total"; average off by €9 | Model doing arithmetic over rows (LLM arithmetic is nondeterministically wrong) | **Code**: `get_stats` computes every count/sum/avg in SQL; list payloads carry authoritative `count`/`total_eur` | Evals with exact numbers; observed wrong values as forbidden patterns; unit tests |
| 6 | "No support tickets exist" for the account with the most tickets (6) | Follow-up turn passed the company *name* as account_id; empty result narrated as "no data" | **Code**: input validation; malformed/nonexistent ids return instructive errors, never empty successes | Unit tests; multi-turn eval |
| 7 | "Nobody is engaged" from a hallucinated id ('001') | Same class as #6, deep in a long conversation | Same fix | Multi-turn eval requires the real contact's name |
| 8 | Set-membership answer produced with ZERO tool calls, dressed in the method-disclosure format (5 accounts named; truth: 11) | Conversation memory used as a data source | Prompt: data claims require same-turn tool calls | Multi-turn evals; must_call assertions |
| 9 | 7 of 11 renewals reported for a 60-day window | Model did date filtering over raw rows, dropped edge cases | **Code**: SQL-side `opp_type` / `closing_within_days` filters; window stated in method block | Eval requires edge-of-window accounts; unit test: count = 11 |
| 10 | Usage span mixed an averaged start with a point-value end (178→93) | Metric mixing | Prompt: point-to-point with months, or sweep evidence verbatim | Red-team battery item |
| 11 | Generic positioning quoted for a specific objection ("Bloom is cheaper") | Wrong retrieval granularity | Prompt: objection-specific talk tracks first | Eval: answer must contain the specific track's substance |
| 12 | Drafted a customer email despite the design cut | Prompt forbade *sending*, never *drafting* | Prompt: no customer-facing text, with rationale, offer prep instead | Judge-rubric eval + forbidden `Subject:` |
| 13 | Another AE's account discussed without noting ownership | Soft rule, model non-compliance | **Code**: ownership note machine-authored into tool payloads | Unit test |
| 14 | Stale CRM field made an active account look disengaged | Data trap: denormalized LAST_INTERACTION field lies | **Code**: engagement computed from the activity log | Unit test on enriched contacts |
| 15 | Impossible negative usage values | Data trap | **Code**: excluded from trends, flagged in output | Judge-rubric eval |
| 16 | Same question, different answers on different days ("who has the most accounts") | LLM nondeterminism | Temperature 0.2 + moving decisions into code; residual risk acknowledged | Pinned: N-run pass-rate mode |
| 17 | Suite crashes on provider rate limits | Infra | Retry with backoff + inter-case pacing | Built into runner |

## What guards quality now

**Before any change ships:** `python evals/unit_tests.py` (26 deterministic
checks, seconds, no API cost) then `python evals/run_evals.py` (25 cases:
capability with exact ground truth, four grounding traps where refusal is the
only pass, aggregate cases with exact numbers, exact-set recall cases, two
scripted multi-turn conversations). Judge verdicts come from the opposite
provider at temperature 0, so the system never grades its own homework.

**In production, the same loop at scale:** every conversation traced;
in-product 👍/👎/report-discrepancy feedback (both discrepancy reports filed
during this build became fixes and then eval cases within the hour); wrong-fact
reports treated as sev-1; weekly trace sampling with failure coding; recurring
failure modes promoted to rules or tools, never patched with wording alone.

**Honest known gaps:** reliability@3 (each case run three times per provider)
still leaves one flaky case per provider, so stability is measured but not yet
solved; multi-turn coverage is two scripted cases against an infinite
conversation space; judge rubrics are audited by hand-labeling, which doesn't
scale past a small team without tooling.

The short version: as testing went on, the model was given less to do, not
more to trust. Every failure the tests found moved another responsibility
(matching, counting, filtering, provenance, validation) out of the model and
into plain code anyone can read and check.
