"""Local FAISS + Amazon Bedrock pipeline for NorthStar retention offers."""

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re
from typing import Optional

import boto3
import faiss
import numpy as np


DEFAULT_EMBEDDING_MODEL_ID = "amazon.titan-embed-text-v2:0"
DEFAULT_GENERATION_MODEL_ID = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
DEFAULT_PROMPT_PATH = Path(__file__).parent / "prompt_templates" / "offer_generation_prompts.md"
DEFAULT_CHUNK_SIZE = 1200
DEFAULT_CHUNK_OVERLAP = 180
EMBEDDING_DIMENSIONS = 1024


@dataclass(frozen=True)
class PolicyChunk:
    """A text fragment with enough source metadata to audit retrieval."""

    chunk_id: str
    doc_id: str
    section: str
    text: str


@dataclass(frozen=True)
class RetrievalRequest:
    query: str
    allowed_doc_ids: Optional[set[str]] = None


def _split_markdown_sections(text: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, list[str]]] = []
    heading = "Document overview"
    body: list[str] = []

    def flush():
        content = "\n".join(body).strip()
        if content:
            sections.append((heading, [content]))

    for line in text.splitlines():
        if line.startswith("#"):
            flush()
            heading = line.lstrip("#").strip() or "Document overview"
            body = []
        else:
            body.append(line)
    flush()
    return [(title, parts[0]) for title, parts in sections]


def _text_windows(text: str, chunk_size: int, overlap: int) -> list[str]:
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    windows = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        if end < len(text):
            boundary = text.rfind(" ", start + int(chunk_size * 0.6), end)
            if boundary > start:
                end = boundary
        fragment = text[start:end].strip()
        if fragment:
            windows.append(fragment)
        if end >= len(text):
            break
        next_start = max(start + 1, end - overlap)
        while next_start < len(text) and not text[next_start - 1].isspace():
            next_start += 1
        start = next_start
    return windows


def chunk_policy_document(text: str, doc_id: str,
                          chunk_size: int = DEFAULT_CHUNK_SIZE,
                          overlap: int = DEFAULT_CHUNK_OVERLAP) -> list[PolicyChunk]:
    """Split Markdown by heading, then into overlapping character windows.

    Heading boundaries remain intact; each window repeats its section name so
    retrieval can identify a rule without depending on neighboring chunks.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap must be non-negative and smaller than chunk_size")

    chunks = []
    section_number = 0
    for section, body in _split_markdown_sections(text):
        section_number += 1
        for chunk_number, window in enumerate(
                _text_windows(body, chunk_size, overlap), start=1):
            chunks.append(PolicyChunk(
                chunk_id=f"{doc_id}-s{section_number:02d}-c{chunk_number:02d}",
                doc_id=doc_id,
                section=section,
                text=f"{section}\n{window}",
            ))
    return chunks


def load_policy_chunks(corpus_dir: str | Path,
                       chunk_size: int = DEFAULT_CHUNK_SIZE,
                       overlap: int = DEFAULT_CHUNK_OVERLAP) -> list[PolicyChunk]:
    """Load every Markdown policy file and require its declared document ID."""
    paths = sorted(Path(corpus_dir).glob("*.md"))
    if not paths:
        raise FileNotFoundError(f"No Markdown policy files found in {corpus_dir}")
    all_chunks = []
    for path in paths:
        text = path.read_text(encoding="utf-8")
        match = re.search(r"^\*\*Document ID:\*\*\s*(\S+)", text, re.MULTILINE)
        if not match:
            raise ValueError(f"Policy document is missing its Document ID: {path}")
        all_chunks.extend(chunk_policy_document(
            text, match.group(1), chunk_size=chunk_size, overlap=overlap))
    if not all_chunks:
        raise ValueError(f"Policy corpus contains no text chunks: {corpus_dir}")
    return all_chunks


def build_retrieval_request(strategy: str, customer_context: dict,
                            question: str) -> RetrievalRequest:
    """Build one of the three prompt-template retrieval strategies."""
    strategy = strategy.upper()
    tier = customer_context.get("loyalty_tier") or "unknown tier"
    ratio = customer_context.get("online_to_store_ratio")
    try:
        numeric_ratio = float(ratio) if ratio is not None else None
        if numeric_ratio is None:
            channel = "channel not specified"
        elif numeric_ratio >= 0.6:
            channel = "primarily online"
        elif numeric_ratio <= 0.4:
            channel = "primarily in store"
        else:
            channel = "mixed online and in store"
    except (TypeError, ValueError):
        channel = "in store"
    if strategy == "A":
        query = (
            f"loyalty tier {tier} benefits points earn rate free shipping threshold "
            f"return window birthday reward. {question}"
        )
        return RetrievalRequest(query)
    if strategy == "B":
        query = (
            "final sale non-returnable exclusions expired offers cannot be reinstated "
            f"retention offer validity single use combinability. {question}"
        )
        return RetrievalRequest(query)
    if strategy == "C":
        query = (
            f"tier {tier} entitlements and shipping thresholds for a customer who shops "
            f"{channel}. {question}"
        )
        return RetrievalRequest(query, {"POL-LOY-011", "POL-SHP-007"})
    raise ValueError("retrieval strategy must be A, B, or C")


def rank_policy_chunks(query_vector: np.ndarray, chunk_vectors: np.ndarray,
                       chunks: list[PolicyChunk], top_k: int = 4,
                       allowed_doc_ids: Optional[set[str]] = None,
                       index=None,
                       ) -> list[PolicyChunk]:
    """Return the top FAISS inner-product matches, optionally source-filtered."""
    if top_k <= 0:
        raise ValueError("top_k must be positive")
    if len(chunks) == 0:
        return []
    vectors = np.asarray(chunk_vectors, dtype=np.float32)
    if vectors.ndim != 2 or vectors.shape[0] != len(chunks):
        raise ValueError("chunk_vectors must have one vector per policy chunk")
    query = np.asarray(query_vector, dtype=np.float32).reshape(1, -1)
    if query.shape[1] != vectors.shape[1]:
        raise ValueError("query and chunk embedding dimensions must match")
    if index is None:
        index = faiss.IndexFlatIP(vectors.shape[1])
        index.add(np.ascontiguousarray(vectors))
    scores, indices = index.search(np.ascontiguousarray(query), len(chunks))
    ranked = []
    for index_value in indices[0]:
        if index_value < 0:
            continue
        chunk = chunks[int(index_value)]
        if allowed_doc_ids is None or chunk.doc_id in allowed_doc_ids:
            ranked.append(chunk)
            if len(ranked) == top_k:
                break
    return ranked


def serialize_customer_profile(customer_context: dict) -> str:
    """Produce a compact, stable profile string without passing an ID to the judge."""
    preferred = (
        "loyalty_tier", "churn_probability", "days_since_last_purchase",
        "total_lifetime_value", "avg_order_value", "category_diversity_score",
        "online_to_store_ratio", "top_categories",
    )
    lines = []
    for key in preferred:
        if key not in customer_context or customer_context[key] is None:
            continue
        value = customer_context[key]
        if key == "top_categories":
            if isinstance(value, str):
                value = value or "not provided"
            else:
                value = ", ".join(map(str, value)) if value else "not provided"
        elif key == "churn_probability":
            value = f"{float(value):.0%}"
        elif key in {"total_lifetime_value", "avg_order_value"}:
            value = f"${float(value):,.2f}"
        elif key in {"category_diversity_score", "online_to_store_ratio"}:
            value = f"{float(value):.2f}"
        lines.append(f"{key}={value}")
    serialized = "Customer profile: " + ("; ".join(lines) if lines else "no profile fields provided")
    interpretations = interpret_customer_profile(customer_context)
    if interpretations:
        serialized += "\nProfile interpretation: " + "; ".join(interpretations)
    return serialized


def interpret_customer_profile(customer_context: dict) -> list[str]:
    interpretations = []
    diversity = customer_context.get("category_diversity_score")
    if diversity is not None:
        try:
            category_count = max(0, min(8, round(float(diversity) * 8)))
            if category_count <= 2:
                breadth = "narrow"
            elif category_count <= 5:
                breadth = "moderate"
            else:
                breadth = "broad"
            interpretations.append(
                f"{breadth} category variety (about {category_count} of 8 categories)"
            )
        except (TypeError, ValueError):
            pass
    ratio = customer_context.get("online_to_store_ratio")
    if ratio is not None:
        try:
            ratio = float(ratio)
            if ratio >= 0.6:
                channel = "primarily online"
            elif ratio <= 0.4:
                channel = "primarily in-store"
            else:
                channel = "mixed online and in-store"
            interpretations.append(channel)
        except (TypeError, ValueError):
            pass
    return interpretations


def _extract_prompt_block(markdown: str, heading_prefix: str) -> str:
    lines = markdown.splitlines()
    heading_index = next((i for i, line in enumerate(lines)
                          if line.startswith(heading_prefix)), None)
    if heading_index is None:
        raise ValueError(f"Prompt template heading not found: {heading_prefix}")
    opening = next((i for i in range(heading_index + 1, len(lines))
                    if lines[i].strip() == "```"), None)
    if opening is None:
        raise ValueError(f"Fenced prompt block not found after {heading_prefix}")
    closing = next((i for i in range(opening + 1, len(lines))
                    if lines[i].strip() == "```"), None)
    if closing is None:
        raise ValueError(f"Unclosed prompt block after {heading_prefix}")
    return "\n".join(lines[opening + 1:closing])


def _user_prompt(prompt_markdown: str, customer_context: dict, question: str) -> str:
    diversity = customer_context.get("category_diversity_score")
    ratio = customer_context.get("online_to_store_ratio")
    probability = customer_context.get("churn_probability")
    categories = customer_context.get("top_categories") or []
    if isinstance(categories, str):
        categories = [categories]
    values = {
        "customer_id": "omitted for privacy",
        "loyalty_tier": customer_context.get("loyalty_tier", "Unknown"),
        "churn_probability": f"{float(probability):.0%}" if probability is not None else "unknown",
        "days_since_last_purchase": customer_context.get("days_since_last_purchase", "unknown"),
        "total_lifetime_value": (f"${float(customer_context['total_lifetime_value']):,.2f}"
                                 if customer_context.get("total_lifetime_value") is not None else "unknown"),
        "avg_order_value": (f"${float(customer_context['avg_order_value']):,.2f}"
                            if customer_context.get("avg_order_value") is not None else "unknown"),
        "category_diversity_score": f"{float(diversity):.2f}" if diversity is not None else "unknown",
        "online_to_store_ratio": f"{float(ratio):.2f}" if ratio is not None else "unknown",
        "top_categories": ", ".join(map(str, categories)) or "not provided",
        "question": question,
    }
    template = _extract_prompt_block(
        prompt_markdown, "## Template 2: User Turn")
    rendered = template.format(**values)
    interpretations = interpret_customer_profile(customer_context)
    if interpretations:
        rendered += "\n\nProfile interpretation: " + "; ".join(interpretations)
    return rendered


def _answer_needs_policy_fallback(answer: str, customer_context: dict) -> bool:
    """Catch common unsupported promotion, catalog, and eligibility claims."""
    text = answer.lower()
    unsupported_patterns = (
        r"\b(?:latest|new arrivals?|new collections?|our selection|in stock|inventory)\b",
        r"\b(?:upcoming|next) sale\b",
        r"\b\d+(?:\.\d+)?\s*%\s*(?:off|discount)",
        r"\b(?:promo|discount) code\b",
        r"\b(?:valid for|expires? in|within)\s+\d+\s+(?:days?|weeks?)\b",
        r"\bexclusive (?:offer|sale|discount)\b",
    )
    if any(re.search(pattern, text) for pattern in unsupported_patterns):
        return True

    if "birthday" in text and not customer_context.get("birthday_eligible"):
        return True
    if "unused" in text and not customer_context.get("annual_gear_credit_unused"):
        return True

    tier = str(customer_context.get("loyalty_tier") or "").strip()
    if tier and tier.lower() in text and not re.search(
            r"\b(?:if|when)\b.{0,55}\b(?:confirmed|current policy|trailing 12-month)\b",
            text):
        return True
    return False


def _policy_bound_fallback(customer_context: dict,
                           all_chunks: list[PolicyChunk]) -> tuple[str, Optional[PolicyChunk]]:
    """Build a conditional offer from an exact tier benefit present in policy."""
    tier = str(customer_context.get("loyalty_tier") or "").strip().title()
    category_value = customer_context.get("top_categories") or []
    if isinstance(category_value, str):
        categories = [category_value] if category_value else []
    else:
        categories = list(category_value)
    category = str(categories[0]) if categories else None

    choices = {
        "Bronze": (
            "free standard shipping on orders of $75 or more",
            ("free standard shipping", "$75"),
        ),
        "Silver": (
            "12-hour early access to sales",
            ("early access", "12 hour"),
        ),
        "Gold": (
            "free standard shipping on any order",
            ("free standard shipping", "always"),
        ),
        "Platinum": (
            "48-hour early access to sales",
            ("early access", "48 hour"),
        ),
    }
    benefit, needles = choices.get(tier, (None, ()))
    supporting_chunk = next((
        chunk for chunk in all_chunks
        if chunk.doc_id == "POL-LOY-011"
        and all(needle in chunk.text.lower() for needle in needles)
    ), None) if benefit else None

    if not category or not supporting_chunk:
        return (
            "I cannot confirm a specific tier benefit from the policy passages "
            "retrieved for this profile. Review the current loyalty terms before "
            "making an offer.",
            supporting_chunk,
        )
    return (
        f"If your {tier} tier is confirmed under the current trailing-12-month "
        f"spend rules, the policy lists {benefit}. Explore the {category} category "
        "and visit NorthStar to consider your next purchase.",
        supporting_chunk,
    )


class RAGOfferSystem:
    """Embed policy text once, retrieve with FAISS, and generate through Bedrock."""

    def __init__(self, corpus_dir="northstar-policy-docs", region="us-east-1",
                 embedding_model_id=DEFAULT_EMBEDDING_MODEL_ID,
                 generation_model_id=DEFAULT_GENERATION_MODEL_ID,
                 top_k=4, retrieval_strategy="C", return_profile_context=True,
                 bedrock_client=None, chunk_size=DEFAULT_CHUNK_SIZE,
                 chunk_overlap=DEFAULT_CHUNK_OVERLAP,
                 prompt_path=DEFAULT_PROMPT_PATH):
        self.embedding_model_id = embedding_model_id
        self.generation_model_id = generation_model_id
        self.top_k = top_k
        self.retrieval_strategy = retrieval_strategy.upper()
        if self.retrieval_strategy not in {"A", "B", "C"}:
            raise ValueError("retrieval_strategy must be A, B, or C")
        self.return_profile_context = return_profile_context
        self.bedrock = bedrock_client or boto3.client("bedrock-runtime", region_name=region)
        self.chunks = load_policy_chunks(corpus_dir, chunk_size, chunk_overlap)
        self.prompt_markdown = Path(prompt_path).read_text(encoding="utf-8")
        vectors = [self._embed(chunk.text) for chunk in self.chunks]
        self.chunk_vectors = np.ascontiguousarray(np.vstack(vectors), dtype=np.float32)
        faiss.normalize_L2(self.chunk_vectors)
        self.index = faiss.IndexFlatIP(EMBEDDING_DIMENSIONS)
        self.index.add(self.chunk_vectors)

    def _embed(self, text: str) -> np.ndarray:
        response = self.bedrock.invoke_model(
            modelId=self.embedding_model_id,
            contentType="application/json",
            accept="application/json",
            body=json.dumps({"inputText": text, "dimensions": EMBEDDING_DIMENSIONS,
                             "normalize": True}),
        )
        body = response["body"].read()
        vector = np.asarray(json.loads(body)["embedding"], dtype=np.float32)
        if vector.shape != (EMBEDDING_DIMENSIONS,):
            raise ValueError(
                f"Titan returned {vector.size} dimensions; expected {EMBEDDING_DIMENSIONS}"
            )
        return vector

    def retrieve(self, customer_context: dict, question: str) -> tuple[RetrievalRequest, list[PolicyChunk]]:
        request = build_retrieval_request(
            self.retrieval_strategy, customer_context, question)
        query_vector = self._embed(request.query)
        faiss.normalize_L2(query_vector.reshape(1, -1))
        chunks = rank_policy_chunks(
            query_vector, self.chunk_vectors, self.chunks, self.top_k,
            request.allowed_doc_ids, index=self.index,
        )
        return request, chunks

    def _system_prompt(self, policy_context: str, profile_context: str) -> str:
        base = _extract_prompt_block(
            self.prompt_markdown, "## Template 1: System Prompt")
        tier_guidelines = _extract_prompt_block(
            self.prompt_markdown, "## Template 3: Tier-Aware Offer Guidelines")
        safety = _extract_prompt_block(
            self.prompt_markdown, "## Template 5: Guardrail Prompt")
        return base.format(
            retrieved_context=policy_context,
            customer_profile=profile_context,
            tier_guidelines=tier_guidelines,
        ) + "\n\n## Non-negotiable safety constraints\n" + safety

    def generate_offer(self, customer_context: dict, question: str) -> dict:
        """Return the two-field contract consumed by the assignment harness."""
        detailed = self.generate_offer_with_metadata(customer_context, question)
        return {"answer": detailed["answer"], "contexts": detailed["contexts"]}

    def generate_offer_with_metadata(self, customer_context: dict,
                                     question: str) -> dict:
        """Return the offer plus chunk IDs and guardrail details for auditing."""
        request, chunks = self.retrieve(customer_context, question)
        profile_context = serialize_customer_profile(customer_context)
        policy_context = "\n\n".join(
            f"[{c.doc_id} | {c.section} | {c.chunk_id}]\n{c.text}" for c in chunks)
        if not chunks:
            answer = (
                "I cannot verify a policy-backed incentive from the available guidance, "
                "so I will not make a specific benefit claim. Please check the current "
                "loyalty terms before contacting the customer."
            )
            contexts = [profile_context] if self.return_profile_context else []
            return {"answer": answer, "contexts": contexts, "chunk_ids": [],
                    "retrieved_chunks": [], "retrieval_query": request.query,
                    "guardrail_fallback": False}

        system_prompt = self._system_prompt(policy_context, profile_context)
        response = self.bedrock.converse(
            modelId=self.generation_model_id,
            system=[{"text": system_prompt}],
            messages=[{"role": "user", "content": [{
                "text": _user_prompt(self.prompt_markdown, customer_context, question)
            }]}],
            inferenceConfig={"maxTokens": 256, "temperature": 0.2},
        )
        try:
            answer = response["output"]["message"]["content"][0]["text"].strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError("Bedrock Converse returned no text response") from exc
        guardrail_fallback = _answer_needs_policy_fallback(answer, customer_context)
        if guardrail_fallback:
            answer, supporting_chunk = _policy_bound_fallback(
                customer_context, self.chunks)
            if supporting_chunk and supporting_chunk.chunk_id not in {
                    chunk.chunk_id for chunk in chunks}:
                chunks.append(supporting_chunk)
        policy_contexts = [chunk.text for chunk in chunks]
        contexts = policy_contexts + ([profile_context] if self.return_profile_context else [])
        return {
            "answer": answer,
            "contexts": contexts,
            "chunk_ids": [chunk.chunk_id for chunk in chunks],
            "retrieved_chunks": [asdict(chunk) for chunk in chunks],
            "retrieval_query": request.query,
            "guardrail_fallback": guardrail_fallback,
        }
