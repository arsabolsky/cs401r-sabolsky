# Track B RAG evaluation summary

## Evaluation setup

The harness ran the four unchanged `OFFER_TEST_CASES` through local FAISS retrieval and Bedrock. Every CSV row records `run_id`, retrieval strategy, judge model, generation model, region, customer ID, retrieved chunk IDs, and whether the policy fallback replaced the model output. `rag_eval.csv` consolidates runs; timestamped `rag_eval_*.csv` files and per-run logs preserve individual execution evidence.

The configured Claude Haiku 4.5 inference profile was unavailable for inference because this personal AWS account requires Anthropic use-case details to be submitted. No form was submitted. To continue in the authorized personal account, the initial comparison used Nova Lite for generation and Nova Pro for judging. The strategy comparison below uses the same generation and judge models for all three strategies. An earlier Nova Lite judge run is preserved, but its answer-relevancy judge returned parser failures, so it is excluded from cross-strategy conclusions. The final guarded run used Nova Pro for generation and judging.

## Retrieval strategy comparison

All metrics are means across four customers; ranges show the minimum and maximum case score. Targets are shown for reference and are not pass/fail gates.

| Strategy | Generation / judge | Faithfulness mean (range) | Answer relevancy mean (range) | Context recall mean (range) |
|---|---|---:|---:|---:|
| A — tier-benefit query | Nova Lite / Nova Pro | 0.438 (0.000–0.750) | 0.341 (0.165–0.568) | 0.950 (0.800–1.000) |
| B — constraint query | Nova Lite / Nova Pro | 0.121 (0.000–0.286) | 0.366 (0.232–0.569) | 0.433 (0.250–0.750) |
| C — tier + shipping query, metadata filter | Nova Lite / Nova Pro | 0.545 (0.000–1.000) | 0.311 (0.130–0.414) | 1.000 (1.000–1.000) |

Strategy C retrieved all reference context for these four test cases; it had the strongest recall. Strategy A was close on recall, while the constraints-only query B missed more tier-entitlement context. None of the three unguarded strategies met all three reference targets. The four-case sample is small, and RAGAS model-based scores are sensitive to judge and generation behavior.

## Controlled profile-context comparison

This comparison holds strategy C, Nova Lite generation, Nova Pro judging, the four cases, and the pre-fallback prompt constant. The sole change is whether the serialized customer profile is included in the contexts passed to RAGAS. The profile remains in the generation prompt in both runs.

| Judge context | Faithfulness mean (range) | Answer relevancy mean (range) | Context recall mean (range) |
|---|---:|---:|---:|
| Profile included | 0.545 (0.000–1.000) | 0.311 (0.130–0.414) | 1.000 (1.000–1.000) |
| Profile omitted | 0.612 (0.200–1.000) | 0.410 (0.306–0.520) | 0.838 (0.600–1.000) |

In this run, adding profile text increased context recall by 0.162 and decreased faithfulness by 0.067 and answer relevancy by 0.099. That is a measured change, not evidence that profile context is generally harmful: it was one run over four cases, and profile details can help verify personalization while also making the judge look for profile claims.

## Final policy-guardrail run

After observing fabricated discounts, codes, expiration terms, birthday eligibility, and catalog claims, the system added a policy-bound fallback. It keeps the generator output only when basic checks find no common unsupported promotion/catalog claim. Otherwise it produces a two-sentence conditional offer using a tier benefit verified in `POL-LOY-011` and includes the supporting policy chunk in the judge context.

With strategy C, Nova Pro generation, Nova Pro judging, and the fallback enabled, the four-case mean was faithfulness **0.667**, answer relevancy **0.136**, and context recall **0.850**. The fallback activated for all four cases. Faithfulness improved over the pre-fallback C / Nova Pro-judge run (0.545 to 0.667), while answer relevancy declined (0.311 to 0.136) and recall declined (1.000 to 0.850). This is the measured safety/relevance tradeoff; the fallback is deliberately conditional because the profile's tier is derived from lifetime value while policy tier is based on trailing-12-month spend.

## Limitations

The final fallback is a lightweight deterministic claim filter, not a complete semantic verifier. It catches several observed classes of unsupported statements, but a different ungrounded claim may pass. The stronger Nova Pro judge also rated conservative fallback wording as less relevant to the offer request. A production implementation should validate structured benefit claims against policy data and test more customers, while preserving the account-level Anthropic access limitation in the evaluation record.
