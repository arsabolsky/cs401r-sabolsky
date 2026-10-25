# Track B examples and failure analysis

The five examples below are actual final responses from `RAGOfferSystem.generate_offer` after its policy guardrail. In each case the model proposed unsupported wording and the guardrail substituted a conditional benefit found in the policy corpus. These are successful guarded outputs, not claims that the raw model was compliant. The exact raw response, final answer, contexts, and chunk IDs for these five calls are retained in `track-b-example-runs.json`.

## Guarded example 1: EX-GOLD-ONLINE

**Input profile:** Gold; churn probability 81%; channel ratio 0.72; categories: Outdoor, Footwear.
**Input request:** “Write a brief retention offer using one existing policy benefit and a category in this profile. Do not invent a promotion.”
**Final output:** If your Gold tier is confirmed under the current trailing-12-month spend rules, the policy lists free standard shipping on any order. Explore the Outdoor category and visit NorthStar to consider your next purchase.
**Retrieved policy chunk IDs:** POL-LOY-011-s10-c01, POL-SHP-007-s03-c01, POL-LOY-011-s04-c01, POL-LOY-011-s06-c01
**Relevant policy rule:** POL-LOY-011 lists free standard shipping at any order amount for Gold. The output states tier entitlement conditionally because policy tier uses trailing-12-month spend, while the profile provides a lifetime-value-derived tier.
**Guardrail fallback used:** True.

## Guarded example 2: EX-BRONZE-APPAREL

**Input profile:** Bronze; churn probability 74%; channel ratio 0.20; categories: Apparel.
**Input request:** “Write a brief retention offer using one existing policy benefit and a category in this profile. Do not invent a promotion.”
**Final output:** If your Bronze tier is confirmed under the current trailing-12-month spend rules, the policy lists free standard shipping on orders of $75 or more. Explore the Apparel category and visit NorthStar to consider your next purchase.
**Retrieved policy chunk IDs:** POL-LOY-011-s10-c01, POL-SHP-007-s03-c01, POL-LOY-011-s03-c01, POL-LOY-011-s07-c01
**Relevant policy rule:** POL-LOY-011 lists free standard shipping for Bronze on orders of $75 or more. The output states tier entitlement conditionally because policy tier uses trailing-12-month spend, while the profile provides a lifetime-value-derived tier.
**Guardrail fallback used:** True.

## Guarded example 3: EX-PLATINUM-OUTDOOR

**Input profile:** Platinum; churn probability 66%; channel ratio 0.55; categories: Outdoor, Home.
**Input request:** “Write a brief retention offer using one existing policy benefit and a category in this profile. Do not invent a promotion.”
**Final output:** If your Platinum tier is confirmed under the current trailing-12-month spend rules, the policy lists 48-hour early access to sales. Explore the Outdoor category and visit NorthStar to consider your next purchase.
**Retrieved policy chunk IDs:** POL-SHP-007-s03-c01, POL-LOY-011-s10-c01, POL-LOY-011-s06-c01, POL-LOY-011-s03-c01
**Relevant policy rule:** POL-LOY-011 lists 48 hours of early access to sales for Platinum. The output states tier entitlement conditionally because policy tier uses trailing-12-month spend, while the profile provides a lifetime-value-derived tier.
**Guardrail fallback used:** True.

## Guarded example 4: EX-SILVER-HOME

**Input profile:** Silver; churn probability 70%; channel ratio 0.61; categories: Home, Beauty.
**Input request:** “Write a brief retention offer using one existing policy benefit and a category in this profile. Do not invent a promotion.”
**Final output:** If your Silver tier is confirmed under the current trailing-12-month spend rules, the policy lists 12-hour early access to sales. Explore the Home category and visit NorthStar to consider your next purchase.
**Retrieved policy chunk IDs:** POL-LOY-011-s10-c01, POL-SHP-007-s03-c01, POL-LOY-011-s03-c01, POL-LOY-011-s13-c01
**Relevant policy rule:** POL-LOY-011 lists 12 hours of early access to sales for Silver. The output states tier entitlement conditionally because policy tier uses trailing-12-month spend, while the profile provides a lifetime-value-derived tier.
**Guardrail fallback used:** True.

## Guarded example 5: EX-GOLD-FOOTWEAR

**Input profile:** Gold; churn probability 69%; channel ratio 0.48; categories: Footwear.
**Input request:** “Write a brief retention offer using one existing policy benefit and a category in this profile. Do not invent a promotion.”
**Final output:** If your Gold tier is confirmed under the current trailing-12-month spend rules, the policy lists free standard shipping on any order. Explore the Footwear category and visit NorthStar to consider your next purchase.
**Retrieved policy chunk IDs:** POL-LOY-011-s10-c01, POL-SHP-007-s03-c01, POL-LOY-011-s04-c01, POL-LOY-011-s03-c01
**Relevant policy rule:** POL-LOY-011 lists free standard shipping at any order amount for Gold. The output states tier entitlement conditionally because policy tier uses trailing-12-month spend, while the profile provides a lifetime-value-derived tier.
**Guardrail fallback used:** True.

## Failure 1: unsupported percentage discount

**Observed input:** `CUST-10000904`, Bronze, Apparel; retrieval strategy A, run `strategy-A-nova-pro-judge`.

**Raw model output:** “Dear Valued Customer, we hope you're doing well. We'd like to offer you 15% off your next purchase of apparel to welcome you back. Enjoy your discount when you shop online or in-store.”

**Retrieved policy chunk IDs:** `POL-LOY-011-s10-c01`, `KB-FAQ-022-s03-c01`, `POL-RET-004-s03-c01`, `POL-SHP-007-s03-c01`.

**Failure:** No retrieved policy offers a 15% discount. The customer also shops mostly in store, so the copy did not use that profile signal.

**Concrete fix:** Prohibit new discounts and promo codes unless the exact offer is retrieved. The final implementation detects percentage discounts and replaces them with a benefit verified in the loyalty policy; it records the fallback in `guardrail_fallback`.

## Failure 2: invented discount and offer terms

**Observed input:** `CUST-10000317`, Gold, Outdoor/Footwear; retrieval strategy B, run `strategy-B-nova-pro-judge`.

**Raw model output:** “Enjoy 20% off your next purchase of outdoor gear or footwear, exclusively for our Gold members. Plus, take advantage of free return shipping on all orders. Shop now and experience the NorthStar difference.”

**Retrieved policy chunk IDs:** `POL-LOY-011-s13-c01`, `POL-LOY-011-s12-c01`, `KB-FAQ-022-s03-c02`, `POL-RET-004-s07-c01`.

**Failure:** The 20% discount and exclusive-promotion framing are not present in policy. Free return shipping is a valid Gold benefit, but it does not authorize the invented discount. Strategy B also retrieved less entitlement context overall.

**Concrete fix:** Prefer strategy C for tier and shipping facts, tighten the prompt to reject new promotions, and run the response through the policy-bound fallback. The fallback adds the exact tier-benefit chunk to returned contexts so the answer remains auditable.

## Evidence interpretation

The failure outputs are preserved as observed; the fixes are implemented in `rag_offer_system.py` and tested with a mocked Bedrock response. The final evaluation scores and run-to-run comparisons are in `track-b-metric-summary.md` and `rag_eval.csv`. The guardrail fallback is intentionally conservative and reduces offer relevance scores, as reported there.
