"""
assistant — a grounded natural-language query layer.

This is deliberately NOT a large language model and makes no external calls.
It maps an investigator's question to one of a fixed set of intents and answers
it entirely from the structured evidence already in the case: entities, FIRs,
the timeline, leads, anomalies and the graph. Every answer cites its source
records, so it cannot hallucinate — the same guarantee the rest of PRAHARI
gives. An on-premise LLM that summarises this same structured layer is the
documented Phase 2 upgrade; it would summarise, never invent.
"""
from backend.assistant.ask import answer, EXAMPLES

__all__ = ["answer", "EXAMPLES"]
