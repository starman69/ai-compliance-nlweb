"""Shared core for AI Compliance NLWeb — profile-aware, RAG-only.

Pure modules (router, models, embedding_text, prompts, pricing, token_ledger,
corpus, security) carry no heavy SDK imports so they are unit-testable with
plain pytest. Client/vector-store SDKs are lazy-imported inside the factories.
"""
