"""
Two-stage OpenAI integration:

Stage 1 — web discovery (run_web_research):
  Calls the Responses API with the hosted web_search tool.
  Returns the discovery text and raw response dict for source parsing and audit.

Stage 2 — structured extraction (extract_evidence_bundle):
  Sends the discovery text back to the Responses API with structured output
  (EvidenceBundle Pydantic schema). Returns a validated EvidenceBundle.
"""

import json
from typing import Any

from app.config import get_settings
from app.openai_client import client
from app.prompts import EXTRACTION_INSTRUCTIONS, RESEARCH_INSTRUCTIONS
from app.schemas import EvidenceBundle


settings = get_settings()


def run_web_research(research_input: str, instructions: str) -> tuple[str, dict[str, Any]]:
    """
    Stage 1: Call the Responses API with web_search to gather public evidence.

    Returns:
        discovery_text: The model's narrative research brief.
        raw_response: Full response payload serialised as a dict (for source
                      parsing and audit trail storage).
    """
    response = client.responses.create(
        model=settings.openai_research_model,
        instructions=instructions,
        tools=[
            {
                "type": "web_search_preview",
                "search_context_size": settings.research_search_context_size,
            }
        ],
        input=research_input,
    )

    raw_response = response.model_dump(mode="json")

    return response.output_text, raw_response


def extract_evidence_bundle(
    *,
    organisation_name: str,
    discovery_text: str,
    sources: list[dict],
    instructions: str,
) -> EvidenceBundle:
    """
    Stage 2: Convert the discovery brief into a validated EvidenceBundle.

    The model is constrained to the EvidenceBundle Pydantic schema via
    structured output. Scoring weights are applied by application code, not
    by the model.
    """
    source_summary = [
        {
            "title": source.get("title"),
            "url": source["url"],
            "domain": source.get("domain"),
        }
        for source in sources[: settings.max_research_sources]
    ]

    input_text = f"""
Organisation: {organisation_name}

Research brief:
{discovery_text}

Discovered source list:
{json.dumps(source_summary, indent=2)}

Create the structured evidence assessment.
"""

    response = client.responses.parse(
        model=settings.openai_extraction_model,
        instructions=instructions,
        input=input_text,
        text_format=EvidenceBundle,
    )

    if response.output_parsed is None:
        raise RuntimeError("The extraction response did not contain parsed output")

    return response.output_parsed
