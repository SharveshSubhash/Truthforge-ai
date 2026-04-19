"""
TRUTHFORGE AI — Transcript Processing Agent
================================================================
Converts raw legal transcript text into structured data.

Steps
-----
1. spaCy NER with custom EntityRuler patterns for legal entities
   (JUDGE, COURT, STATUTE, CASE_CITATION, WITNESS, DEFENDANT, DATE_LEGAL)
2. LLM structured-output call to extract events and key statements
3. Returns entities + structured_facts ready for the Timeline Agent

Standalone usage
----------------
    from agents.transcript_processing_agent import TranscriptProcessingAgent
    from config import get_llm
    agent = TranscriptProcessingAgent()
    result = agent.run(transcript_text, llm=get_llm("claude-sonnet-4-6", "anthropic"))
    print(result)
"""

from __future__ import annotations
from langchain_core.runnables import RunnableConfig
import json
import re
from typing import Optional

from pydantic import BaseModel, Field

from core.state import Entity
from core.logger import audit, get_logger

logger = get_logger("transcript_processing_agent")

# ---------------------------------------------------------------------------
# spaCy setup with legal EntityRuler
# ---------------------------------------------------------------------------

_NLP = None


def _get_nlp():
    global _NLP
    if _NLP is not None:
        return _NLP
    try:
        import spacy
        try:
            nlp = spacy.load("en_core_web_trf")
        except OSError:
            try:
                nlp = spacy.load("en_core_web_sm")
            except OSError:
                nlp = spacy.blank("en")
                logger.warning("no_spacy_model_found_using_blank")

        # Add legal EntityRuler before the NER component
        ruler_name = "entity_ruler"
        if ruler_name not in nlp.pipe_names:
            ruler = nlp.add_pipe("entity_ruler", before="ner") if "ner" in nlp.pipe_names \
                     else nlp.add_pipe("entity_ruler")
            _add_legal_patterns(ruler)

        _NLP = nlp
    except ImportError:
        logger.warning("spacy_not_installed_ner_disabled")
        _NLP = None
    return _NLP


def _add_legal_patterns(ruler) -> None:
    patterns = [
        # Judges
        {"label": "JUDGE", "pattern": [{"LOWER": {"IN": ["justice", "judge", "hon.", "honourable", "honorable"]}},
                                        {"IS_TITLE": True, "OP": "+"}]},
        # Courts
        {"label": "COURT", "pattern": [{"LOWER": {"IN": ["supreme", "high", "district", "subordinate", "state"]}},
                                        {"LOWER": "court"}]},
        {"label": "COURT", "pattern": [{"TEXT": {"REGEX": r"[A-Z]"}, "OP": "+"}, {"LOWER": "court"}]},
        # Case citations like "[2024] SGCA 1"
        {"label": "CASE_CITATION", "pattern": [{"TEXT": "["}, {"IS_DIGIT": True},
                                                {"TEXT": "]"}, {"IS_UPPER": True}, {"IS_DIGIT": True}]},
        # Statutes
        {"label": "STATUTE", "pattern": [{"TEXT": {"REGEX": r"[A-Z][a-z]+"}},
                                          {"LOWER": {"IN": ["act", "ordinance", "code", "regulations?"]}}]},
        # Legal roles
        {"label": "DEFENDANT", "pattern": [{"LOWER": {"IN": ["defendant", "accused", "appellant", "respondent"]}}]},
        {"label": "PLAINTIFF",  "pattern": [{"LOWER": {"IN": ["plaintiff", "claimant", "petitioner", "prosecution"]}}]},
        {"label": "WITNESS",    "pattern": [{"LOWER": {"IN": ["witness", "pw1", "pw2", "dw1", "dw2",
                                                               "complainant", "testifier"]}}]},
        {"label": "COUNSEL",    "pattern": [{"LOWER": {"IN": ["counsel", "advocate", "solicitor", "barrister",
                                                               "dpp", "dac", "mr", "ms", "mrs"]}}]},
    ]
    ruler.add_patterns(patterns)


def extract_entities_spacy(text: str) -> list[Entity]:
    """Run spaCy NER on text, return list of Entity dicts."""
    nlp = _get_nlp()
    if nlp is None:
        return []
    doc = nlp(text)
    entities: list[Entity] = []
    seen: set[tuple] = set()
    for ent in doc.ents:
        key = (ent.text, ent.label_, ent.start_char)
        if key in seen:
            continue
        seen.add(key)
        entities.append(Entity(
            text=ent.text,
            label=ent.label_,
            start=ent.start_char,
            end=ent.end_char,
            confidence=1.0,
        ))
    return entities


# ---------------------------------------------------------------------------
# Pydantic schema for LLM structured output
# ---------------------------------------------------------------------------

class EventModel(BaseModel):
    event_id: str = Field(description="Unique ID, e.g. 'E001'")
    description: str = Field(description="One-sentence description of what happened")
    timestamp: Optional[str] = Field(None, description="Timestamp as mentioned in transcript")
    actors: list[str] = Field(default_factory=list, description="Names/roles involved")
    location: Optional[str] = Field(None, description="Location if mentioned")
    source_excerpt: str = Field(description="Verbatim quote from transcript (max 100 chars)")


class StructuredFactsModel(BaseModel):
    events: list[EventModel] = Field(description="All discrete events extracted")
    key_statements: list[str] = Field(description="Important factual statements verbatim")
    summary: str = Field(description="2–3 sentence summary of the transcript")


# ---------------------------------------------------------------------------
# LLM extraction prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """You are a legal analysis assistant specializing in extracting structured information from court transcripts and legal testimonies.

Your task is to identify and extract:
1. All discrete events (actions, statements, occurrences) with their timestamps and actors
2. Key factual statements that could be checked for consistency
3. A brief summary

Rules:
- Extract ONLY what is explicitly stated in the transcript. Do NOT infer or add information.
- Use verbatim quotes from the transcript for source_excerpt (max 100 characters).
- Assign sequential event IDs: E001, E002, E003, ...
- For timestamps, use the exact phrasing from the transcript.
- Be comprehensive — missing events may cause missed inconsistencies.
"""


# ---------------------------------------------------------------------------
# Agent class
# ---------------------------------------------------------------------------

class TranscriptProcessingAgent:
    """Converts sanitized transcript text into structured entities and events."""

    def process_entities(self, text: str) -> list[Entity]:
        """Run spaCy NER on text and return entities."""
        return extract_entities_spacy(text)

    def extract_structured_facts(self, text: str, llm) -> dict:
        """
        Call the LLM with structured output to extract events and key statements.
        Falls back to empty structure on LLM failure.
        """
        try:
            structured_llm = llm.with_structured_output(StructuredFactsModel)
            result: StructuredFactsModel = structured_llm.invoke([
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": f"Please extract structured facts from this legal transcript:\n\n{text}"},
            ])
            return result.model_dump()
        except Exception as exc:
            logger.error("structured_facts_extraction_failed", error=str(exc))
            # Fallback: basic regex-based extraction
            return _fallback_extract(text)

    def run(self, sanitized_transcript: str, llm=None) -> dict:
        """
        Standalone entrypoint.

        Args:
            sanitized_transcript: pre-cleaned transcript text
            llm: LangChain chat model (optional; if None, only spaCy NER runs)

        Returns:
            dict with 'entities' and 'structured_facts'
        """
        log = audit("transcript_processing_agent", "start",
                    chars=len(sanitized_transcript))

        entities = self.process_entities(sanitized_transcript)

        if llm is not None:
            structured_facts = self.extract_structured_facts(sanitized_transcript, llm)
        else:
            structured_facts = _fallback_extract(sanitized_transcript)

        log2 = audit("transcript_processing_agent", "complete",
                     entities=len(entities),
                     events=len(structured_facts.get("events", [])))

        return {
            "entities": entities,
            "structured_facts": structured_facts,
            "audit_log": [log, log2],
        }


def _fallback_extract(text: str) -> dict:
    """Regex-based fallback when LLM is unavailable."""
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if len(s.strip()) > 20]
    events = [
        {
            "event_id": f"E{str(i+1).zfill(3)}",
            "description": s[:200],
            "timestamp": None,
            "actors": [],
            "location": None,
            "source_excerpt": s[:100],
        }
        for i, s in enumerate(sentences[:30])
    ]
    return {
        "events": events,
        "key_statements": sentences[:10],
        "summary": " ".join(sentences[:3]),
    }


# ---------------------------------------------------------------------------
# LangGraph node function
# ---------------------------------------------------------------------------

_agent_instance = TranscriptProcessingAgent()


def transcript_processing_node(state: dict, config: Optional[RunnableConfig] = None) -> dict:
    """LangGraph node: transcript processing."""
    if state.get("security_input_blocked"):
        return {"audit_log": [audit("transcript_processing_agent", "skipped_blocked_input")]}

    llm = None
    if config:
        try:
            from config import get_llm_from_config
            llm = get_llm_from_config(config)
        except Exception as e:
            logger.warning("llm_init_failed", error=str(e))

    result = _agent_instance.run(state["sanitized_transcript"], llm=llm)

    # Persist to memory store
    run_id = state.get("run_id")
    if run_id:
        try:
            from core.memory import memory_store
            memory_store.save_facts(run_id, result["structured_facts"])
        except Exception:
            pass

    n_events = len(result["structured_facts"].get("events", []))
    confidence = "HIGH" if llm is not None else "MEDIUM"
    from core.state import AgentStatus
    status_entry = AgentStatus(
        source_agent="transcript_processing",
        status="complete",
        confidence=confidence,
        next_action="proceed_to_timeline_reconstruction",
        notes=f"{len(result['entities'])} entities, {n_events} events extracted",
    )

    return {
        "entities": result["entities"],
        "structured_facts": result["structured_facts"],
        "audit_log": result["audit_log"],
        "agent_statuses": {
            **state.get("agent_statuses", {}),
            "transcript_processing": status_entry,
        },
    }


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    text = sys.stdin.read() if not sys.stdin.isatty() else (
        "On 15 January 2024, the defendant John Tan appeared before Justice Lee at the High Court. "
        "The plaintiff testified that she saw him at the scene at 10pm. "
        "However, a witness stated he was at Changi Airport at 9:45pm on the same date."
    )
    agent = TranscriptProcessingAgent()
    import json
    result = agent.run(text)
    print(json.dumps(result, indent=2, default=str))
