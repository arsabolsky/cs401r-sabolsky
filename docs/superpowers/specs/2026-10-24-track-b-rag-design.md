# Track B RAG Design

## Intent

Complete Lab 3 Track B: turn a customer profile plus retrieved NorthStar policy into a short, personalized retention offer, then evaluate it with the provided four-case RAGAS harness. The student should be able to run and inspect the pipeline locally and in the demo notebook.

## Goals

- Read only the four Markdown policy files in `northstar-policy-docs/` and preserve source IDs for citation in examples.
- Embed policy chunks and queries with Titan Text Embeddings V2 and use local FAISS retrieval.
- Generate with Claude Haiku 4.5 through the US inference profile in `us-east-1`.
- Return the exact evaluator contract: `{"answer": str, "contexts": list[str]}`; include both policy evidence and profile context for judge grounding.
- Compare all three retrieval-query strategies described in `prompt_templates/offer_generation_prompts.md`.
- Preserve customer category/profile personalization while avoiding unsupported product, offer, shipping, return, and loyalty claims.
- Save reproducible per-case metrics, multiple evaluation runs, examples, a fully executed notebook, and design/README documentation.

## Non-goals

- No Track C work, OpenSearch Serverless, SageMaker endpoint, new AWS resources, or infrastructure changes.
- No changes to the four supplied evaluation cases or their ground truths.
- No claim that the original RAGAS target scores are pass/fail gates; report observed limits honestly.

## Architecture

Create `rag_offer_system.py` as the Track B module. It loads and chunks the policy corpus, calls Titan through `bedrock-runtime.invoke_model`, indexes normalized vectors in local FAISS, retrieves relevant policy sections, builds a guarded prompt from the retrieved text and customer profile, and calls Haiku through Bedrock Converse. The public `generate_offer(customer_context, question)` method returns the answer, judge contexts, and chunk IDs for evidence.

`evaluation_harness.py` remains the evaluator and CLI. It imports the RAG system once, runs the existing four cases, and writes both timestamped raw results and a consolidated `docs/lab3-evidence/rag_eval.csv` with run and judge metadata. Local unit tests use a fake Bedrock client; the rubric evaluation uses the real Bedrock judge and generator from the personal `northstar` account.

## Decisions and tradeoffs

- **Direct Boto3 + FAISS (selected):** fewer layers than LangChain and no managed vector-service cost. It makes embedding, retrieval, and generation calls visible and testable. LangChain-managed retrieval would shorten glue code but add abstraction and dependency behavior that is not needed for four short policy documents. OpenSearch would add infrastructure and cost without helping this local lab.
- **Titan V2, 1,024 dimensions, normalized vectors:** matches the project checklist and supports cosine-like ranking with FAISS inner product.
- **Markdown-aware character chunks:** retain document and section labels, use modest overlap, and state the chosen size/overlap with the observed chunk count in the report. This avoids cutting policy tables/sections into unlabeled fragments.
- **Local, per-process FAISS index:** simple and reproducible; no persistent AWS vector store or endpoint. Corpus is small enough to embed at startup.
- **Profile is both prompt input and returned judge context:** generation needs the profile, and RAGAS otherwise treats profile-derived claims as unsupported. This choice will be measured with a controlled before/after evaluation.
- **Tier mismatch:** the feature's tier is based on lifetime value while policy tier uses trailing-12-month spend. The system will phrase tier benefits conditionally and will not infer access to a higher tier's benefits.
- **No reranker initially:** use FAISS ranking and compare the three query strategies first; document this as a measured simplicity choice.

## Risks and mitigations

- Tier or benefit confusion: correct the planted prompt facts against POL-LOY-011 and POL-SHP-007, retrieve source text, and keep policy constraints explicit.
- Unsupported profile claims: return profile context to RAGAS as a separate context item.
- Retrieval misses or score variability: evaluate every test case multiple times, retain run identity, retry NaN judge rows, and report means/ranges and examples.
- Bedrock spend: use only four provided cases, small prompts/output caps, and the existing personal account; do not create infrastructure.
