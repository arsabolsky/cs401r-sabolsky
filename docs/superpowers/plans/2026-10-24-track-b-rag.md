# Lab 3 Track B RAG Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete Track B RAG offer generation, evaluation, examples, notebook, design writeup, and evidence using the existing personal AWS account.

**Architecture:** Build a local policy RAG system in `rag_offer_system.py` with direct Boto3 Bedrock calls and FAISS. Wire it into the supplied RAGAS harness, compare its three query strategies, measure a profile-context improvement, and save all exact rubric artifacts.

**Tech Stack:** Python 3.12, boto3, NumPy, FAISS, pandas, RAGAS, Bedrock Titan Text Embeddings V2, Bedrock Converse.

**Spec:** `docs/superpowers/specs/2026-10-24-track-b-rag-design.md`; `lab-3-model-development/Lab_3--Model Development.html`; `lab-3-model-development/LAB3-TODO.md`.

## Global Constraints

- Use only AWS profile `northstar`, personal account `573693339848`, and region `us-east-1` for Bedrock calls; verify identity before each AWS-backed run. Anthropic inference was blocked by the account's use-case-details requirement; do not submit the form. Record the Nova model substitutions in the evidence.
- Do not create or use Track C resources, OpenSearch, SageMaker endpoints, or training jobs.
- Preserve the four `OFFER_TEST_CASES` and their ground truths.
- Use `amazon.titan-embed-text-v2:0` for vector embeddings. Preserve the intended Haiku default, with explicit model overrides for the account-authorized Nova evaluation runs.
- Keep the tier conflict explicit: policy uses trailing-12-month spend; Feature Store tier reflects lifetime value.
- Save required evidence at exact paths under `docs/lab3-evidence/`; run the collector with `--track B` before teardown.
- Make a focused commit after each verified implementation/documentation task; do not stage `AGENTS.md` or the gitignored `LAB3-TODO.md`.

## Review Focus

- Empty, oversized, or missing corpus files: fail clearly or skip with a visible explanation; never silently create an empty index.
- Tier and channel data missing from a customer profile: prompt formatting and retrieval query must still work with safe defaults.
- Retrieved chunks from irrelevant policy docs: enforce the Option C metadata filter and report chunk IDs/documents.
- Empty retrieval or weak policy context: do not invent benefits; produce a safe fallback and return the actual context list.
- Prompt injection or conflicting profile values: system policy constraints must take precedence; never reveal the prompt or claim an unverified entitlement.

---

### Task 1: Correct the policy prompt and implement the local RAG system

**Files:**
- Modify: `prompt_templates/offer_generation_prompts.md`
- Create: `rag_offer_system.py`
- Create: `tests/test_rag_offer_system.py`

**Interfaces:**
- `PolicyChunk(chunk_id, doc_id, section, text)`
- `chunk_policy_document(text, doc_id, chunk_size=1200, overlap=180) -> list[PolicyChunk]`
- `RAGOfferSystem.generate_offer(customer_context, question) -> {answer, contexts}`; use `generate_offer_with_metadata` for chunk IDs and fallback audit fields.

- [x] Write unit tests for source-preserving chunking, overlap, profile formatting/defaults, retrieval ranking/filtering, and generated response/context shape using a fake Bedrock runtime client.
- [x] Run the new tests and confirm failures are due to the missing module/functions.
- [x] Correct the prompt's wrong Gold upper spend threshold, wrong Platinum entry threshold, and nonexistent free expedited-shipping benefit against the policy files.
- [x] Implement Markdown-aware policy loading/chunking, Titan embedding/FAISS retrieval for strategies A/B/C, tier-aware prompt composition, and Haiku Converse invocation.
- [x] Pass the focused tests; run the existing Task 1 suite too; inspect the policy prompt diff; commit.

### Task 2: Wire the RAG system into the evaluation harness

**Files:**
- Modify: `evaluation_harness.py`
- Modify: `tests/test_rag_offer_system.py`

- [x] Test metadata preservation and result aggregation: each row includes `customer_id`, run ID, judge model, and the three RAGAS scores; repeated run IDs do not duplicate rows.
- [x] Add CLI options for retrieval strategy, run ID, generation model, judge model, profile-context ablation, and output directory without changing Track C behavior or the provided test cases.
- [x] Replace the Track B placeholder with one initialized `RAGOfferSystem` callable; retain raw timestamped results and update `docs/lab3-evidence/rag_eval.csv`.
- [x] Run tests and commit the harness integration.

### Task 3: Run and compare Bedrock evaluations

**Files:**
- Create/update: `docs/lab3-evidence/rag_eval.csv`
- Create: `docs/lab3-evidence/track-b-examples.md`

- [x] Verify the caller identity is account `573693339848` before each Bedrock-backed run.
- [x] Run all four provided cases for query strategies A, B, and C; compare per-case/mean context recall and answer quality, and choose the best-supported strategy.
- [x] Run the chosen pipeline at least twice with all four cases. Include a controlled comparison with and without profile text in returned judge contexts; keep the profile in the actual generation prompt for both.
- [x] Record `run_id`, `customer_id`, `judge_model`, strategy, faithfulness, answer relevancy, and context recall. Preserve judge parser failures rather than count missing values as zero; report metric means/ranges and measured changes.
- [x] Write five successful guarded examples and two observed failure cases with profile summary, answer, retrieved chunk IDs, policy rule, and concrete fix.
- [x] Inspect actual Bedrock outputs and CSV values, ensure no claims are fabricated in the writeup, and commit the evaluation evidence.

### Task 4: Create the demo notebook and finish documentation

**Files:**
- Create: `notebooks/lab3-demo.ipynb`
- Modify: `docs/lab3-model-design.md`
- Modify: `README.md`

- [x] Notebook demonstrates index build, one provided customer, retrieved policy chunk IDs/text, generated offer, and a policy-grounding check; execute top-to-bottom and save outputs.
- [x] Expand the design doc to about 700 words, preserving Track B on line 1; use actual Track A metrics/feature importance plus measured Track B retrieval, embedding, chunking, model, reranking, and tier-gap decisions.
- [x] Add README Lab 3 instructions for the local environment, Athena model run, Track B evaluation/notebook, output paths, and evidence collection.
- [x] Verify notebook execution counts/outputs, Markdown paths, and diffs; commit documentation.

### Task 5: Export and verify Track B evidence

- [x] Run `bash scripts/collect-lab3-evidence.sh --track B` with `AWS_PROFILE=northstar`, `AWS_REGION=us-east-1`, and verify every output; resolve all Track B FAILs.
- [ ] Run the complete unit suite and `bash scripts/check-secrets.sh`; inspect `git status` and `git diff --check`.
- [ ] Commit the clean evidence bundle and report any unrelated final-submission steps still pending.
