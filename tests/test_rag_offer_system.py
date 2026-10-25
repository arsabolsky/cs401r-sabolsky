import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

import rag_offer_system as rag
from rag_offer_system import (
    PolicyChunk,
    RAGOfferSystem,
    build_retrieval_request,
    chunk_policy_document,
    interpret_customer_profile,
    rank_policy_chunks,
)


class PolicyChunkingTests(unittest.TestCase):
    def test_chunks_keep_document_section_and_overlapping_text(self):
        source = "## Return Window\n\n" + "policy words " * 20

        chunks = chunk_policy_document(
            source, doc_id="POL-RET-004", chunk_size=80, overlap=20
        )

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(c.doc_id == "POL-RET-004" for c in chunks))
        self.assertTrue(all(c.section == "Return Window" for c in chunks))
        self.assertEqual(len({c.chunk_id for c in chunks}), len(chunks))
        self.assertTrue(any(set(chunks[0].text.split()) & set(chunks[1].text.split())))

    def test_invalid_overlap_is_rejected(self):
        with self.assertRaises(ValueError):
            chunk_policy_document("some policy", "POL-RET-004", chunk_size=20, overlap=20)


class RetrievalStrategyTests(unittest.TestCase):
    def setUp(self):
        self.profile = {
            "loyalty_tier": "Gold",
            "online_to_store_ratio": 0.75,
            "top_categories": ["Outdoor"],
        }

    def test_strategies_build_distinct_queries_and_option_c_filter(self):
        option_a = build_retrieval_request("A", self.profile, "Make an offer")
        option_b = build_retrieval_request("B", self.profile, "Make an offer")
        option_c = build_retrieval_request("C", self.profile, "Make an offer")

        self.assertIn("Gold", option_a.query)
        self.assertIn("final sale", option_b.query.lower())
        self.assertIn("online", option_c.query.lower())
        self.assertEqual(option_c.allowed_doc_ids, {"POL-LOY-011", "POL-SHP-007"})
        self.assertIsNone(option_a.allowed_doc_ids)
        self.assertIsNone(option_b.allowed_doc_ids)

    def test_faiss_ranking_applies_option_c_source_filter(self):
        chunks = [
            PolicyChunk("a", "POL-RET-004", "Returns", "return window"),
            PolicyChunk("b", "POL-LOY-011", "Points", "Gold points"),
            PolicyChunk("c", "POL-SHP-007", "Shipping", "Gold shipping"),
        ]
        vectors = np.asarray([[0.99, 0.0], [0.9, 0.1], [0.8, 0.2]], dtype=np.float32)
        ranked = rank_policy_chunks(
            query_vector=np.asarray([1.0, 0.0], dtype=np.float32),
            chunk_vectors=vectors,
            chunks=chunks,
            top_k=2,
            allowed_doc_ids={"POL-LOY-011", "POL-SHP-007"},
        )

        self.assertEqual([chunk.chunk_id for chunk in ranked], ["b", "c"])

    def test_profile_signals_are_interpreted_and_missing_values_are_safe(self):
        signals = interpret_customer_profile({
            "category_diversity_score": 0.125,
            "online_to_store_ratio": 0.20,
        })
        missing_profile_query = build_retrieval_request("C", {}, "Make an offer")

        self.assertTrue(any("narrow" in item.lower() and "1 of 8" in item for item in signals))
        self.assertTrue(any("in-store" in item.lower() for item in signals))
        self.assertIn("unknown tier", missing_profile_query.query)


class FakeBody:
    def __init__(self, value):
        self.value = json.dumps(value).encode("utf-8")

    def read(self):
        return self.value


class FakeBedrockRuntime:
    def __init__(self, answer_text="A grounded offer. Shop Outdoor today."):
        self.converse_request = None
        self.embedding_calls = 0
        self.answer_text = answer_text

    def invoke_model(self, *, modelId, body, contentType, accept):
        self.embedding_calls += 1
        request = json.loads(body)
        self.asserted_model_id = modelId
        # The same fixed direction keeps these contract tests deterministic.
        return {"body": FakeBody({"embedding": [1.0] + [0.0] * 1023})}

    def converse(self, **kwargs):
        self.converse_request = kwargs
        return {"output": {"message": {"content": [{"text": self.answer_text}]}}}


class RAGOfferContractTests(unittest.TestCase):
    def test_public_generate_offer_returns_exactly_answer_and_contexts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            Path(temp_dir, "loyalty-program-terms.md").write_text(
                "**Document ID:** POL-LOY-011\n\n## Points\n\nGold earns 1.5x points."
            )
            system = RAGOfferSystem(
                corpus_dir=temp_dir,
                bedrock_client=FakeBedrockRuntime(),
                top_k=10,
            )
            result = system.generate_offer(
                {"loyalty_tier": "Gold", "top_categories": ["Outdoor"]},
                "Create a retention offer.",
            )

        self.assertEqual(set(result), {"answer", "contexts"})

    def test_unsupported_promotion_and_catalog_claims_use_policy_bound_fallback(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            Path(temp_dir, "loyalty-program-terms.md").write_text(
                "**Document ID:** POL-LOY-011\n\n## Gold Benefits\n\n"
                "Gold members receive free standard shipping at any order amount (Always)."
            )
            bedrock = FakeBedrockRuntime(
                "As a Gold member, get 20% off with code GOLD20 on our latest Outdoor arrivals."
            )
            system = RAGOfferSystem(
                corpus_dir=temp_dir,
                bedrock_client=bedrock,
                top_k=10,
            )

            result = system.generate_offer_with_metadata(
                {"loyalty_tier": "Gold", "top_categories": ["Outdoor"]},
                "Create a retention offer.",
            )

        self.assertTrue(result["guardrail_fallback"])
        self.assertNotIn("20%", result["answer"])
        self.assertNotIn("latest", result["answer"].lower())
        self.assertIn("if your gold tier is confirmed", result["answer"].lower())
        self.assertIn("free standard shipping", result["answer"])
        self.assertTrue(any("free standard shipping" in c for c in result["contexts"]))

    def test_retrieval_reuses_the_faiss_index_built_by_the_system(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            Path(temp_dir, "loyalty-program-terms.md").write_text(
                "**Document ID:** POL-LOY-011\n\n## Points\n\nGold earns 1.5x points."
            )
            system = RAGOfferSystem(
                corpus_dir=temp_dir,
                bedrock_client=FakeBedrockRuntime(),
            )

            with mock.patch.object(
                    rag.faiss, "IndexFlatIP", wraps=rag.faiss.IndexFlatIP) as factory:
                system.retrieve({"loyalty_tier": "Gold"}, "Make an offer")

        factory.assert_not_called()

    def test_generate_offer_returns_answer_policy_context_profile_context_and_chunk_ids(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            Path(temp_dir, "loyalty-program-terms.md").write_text(
                "**Document ID:** POL-LOY-011\n\n## Points\n\nGold earns 1.5x points."
            )
            Path(temp_dir, "shipping-policy.md").write_text(
                "**Document ID:** POL-SHP-007\n\n## Shipping\n\nGold gets free standard shipping."
            )
            bedrock = FakeBedrockRuntime()
            system = RAGOfferSystem(
                corpus_dir=temp_dir,
                bedrock_client=bedrock,
                top_k=10,
            )

            result = system.generate_offer_with_metadata(
                {"loyalty_tier": "Gold", "top_categories": ["Outdoor"]},
                "Create a retention offer.",
            )

        self.assertIn("grounded offer", result["answer"].lower())
        self.assertTrue(any("Gold earns 1.5x points" in c for c in result["contexts"]))
        self.assertTrue(any("loyalty_tier=Gold" in c for c in result["contexts"]))
        self.assertTrue(result["chunk_ids"])
        self.assertEqual(bedrock.asserted_model_id, system.embedding_model_id)
        self.assertEqual(bedrock.converse_request["modelId"], system.generation_model_id)

    def test_profile_can_be_removed_from_judge_context_but_remains_in_prompt(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            Path(temp_dir, "loyalty-program-terms.md").write_text(
                "**Document ID:** POL-LOY-011\n\n## Points\n\nGold earns 1.5x points."
            )
            bedrock = FakeBedrockRuntime()
            system = RAGOfferSystem(
                corpus_dir=temp_dir,
                bedrock_client=bedrock,
                top_k=10,
                return_profile_context=False,
            )

            result = system.generate_offer_with_metadata(
                {"loyalty_tier": "Gold", "top_categories": ["Outdoor"]},
                "Create a retention offer.",
            )

        self.assertFalse(any("loyalty_tier=Gold" in c for c in result["contexts"]))
        self.assertIsNotNone(bedrock.converse_request)
        self.assertIn("loyalty_tier=Gold", bedrock.converse_request["system"][0]["text"])


class PromptPolicyFactTests(unittest.TestCase):
    def test_tier_guidelines_match_policy_thresholds_and_shipping_rules(self):
        markdown = Path("prompt_templates/offer_generation_prompts.md").read_text()
        tier_block = markdown.split("## Template 3:", 1)[1].split("## Template 4:", 1)[0]

        self.assertIn("Gold ($2,000 - $4,999.99)", tier_block)
        self.assertIn("Platinum ($5,000+)", tier_block)
        self.assertIn("Gold and Platinum do NOT receive free expedited shipping", tier_block)
        self.assertNotIn("Gold ($2,000 - $9,999.99)", tier_block)
        self.assertNotIn("Platinum ($10,000+)", tier_block)

    def test_prompt_blocks_unretrieved_promotion_terms(self):
        markdown = Path("prompt_templates/offer_generation_prompts.md").read_text()
        system_block = markdown.split("## Template 1:", 1)[1].split("## Template 2:", 1)[0]
        guardrail_block = markdown.split("## Template 5:", 1)[1]

        self.assertIn("Never create a discount", system_block)
        self.assertIn("expiration date", system_block)
        self.assertIn("minimum purchase", system_block)
        self.assertIn("birthday eligibility", system_block)
        self.assertIn("annual credit unused", system_block)
        self.assertIn("Do not claim products, collections, or\n  inventory", system_block)
        self.assertIn("retrieved policy\n  explicitly states", guardrail_block)


if __name__ == "__main__":
    unittest.main()
