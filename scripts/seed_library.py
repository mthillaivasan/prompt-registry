#!/usr/bin/env python3
"""
Seed the prompt_library table from a YAML fixture.

Usage:
  python -m scripts.seed_library fixtures/library_seed.yaml

Idempotent on `title`: existing entries are left alone unless
--update is passed. Entries missing any of prompt_type, input_type,
output_type, summary, topic_coverage are classified by Haiku
(claude-haiku-4-5-20251001), which also returns a one-sentence
rationale stored in classification_notes.

Entries with empty full_text are skipped with an 'awaiting content'
message — useful for Lombard placeholders that need manual paste
before seeding.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models import PromptLibrary
from app.schemas import PromptType

# ── Topic IDs from docs/CHECKLIST_DESIGN.md — Extraction topics ──────────────
# Haiku uses these as the allowed values for topic_coverage tagging. Expand
# once other prompt_types get their topic lists (classification, summarisation…)
_KNOWN_TOPICS = [
    "topic_1_prompt_type",
    "topic_2_source_doc",
    "topic_3_output",
    "topic_4_target_system",
    "topic_4b_ai_platform",
    "topic_5_risk_tier",
    "topic_6_data_points",
    "topic_7_field_format",
    "topic_8_null_handling",
    "topic_9_confidence_traceability",
    "topic_10_error_modes",
]

_PROMPT_TYPES = list(PromptType.__args__)

_CLASSIFICATION_SYSTEM = """You classify prompt-library entries for a registry.

For the provided prompt, return a single JSON object (and nothing else) with these keys:

- prompt_type: one of {prompt_types}
- input_type: short phrase describing the kind of input the prompt consumes (e.g. "PDF document", "email thread", "data table", "free text"). Null if not applicable.
- output_type: short phrase describing the shape of the output (e.g. "JSON object", "markdown report", "classification label + rationale", "plain text"). Null if not applicable.
- summary: one-sentence description of what the prompt does.
- topic_coverage: a JSON array of topic_ids this prompt meaningfully addresses, chosen ONLY from this list: {topics}. Use [] if none apply.
- classification_notes: one sentence explaining WHY you picked the above values. Reference specific wording from the prompt that led you to each choice.

Return only the JSON object. No prose, no code fences, no commentary.
""".strip()


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def classify_entry(full_text: str, known: dict[str, Any], client=None) -> dict[str, Any]:
    """Call Haiku to fill in missing classification fields.

    `known` holds fields already set on the entry so Haiku can honour them.
    Returns a dict with prompt_type, input_type, output_type, summary,
    topic_coverage, classification_notes. Raises on Haiku failure — the
    caller decides whether to abort or skip.
    """
    import anthropic

    if client is None:
        client = anthropic.Anthropic()

    system = _CLASSIFICATION_SYSTEM.format(
        prompt_types=", ".join(f'"{t}"' for t in _PROMPT_TYPES),
        topics=", ".join(f'"{t}"' for t in _KNOWN_TOPICS),
    )

    user_content = "PROMPT TEXT:\n" + full_text.strip()
    if known:
        user_content += "\n\nKNOWN FIELDS (preserve these unless clearly wrong):\n"
        user_content += json.dumps(known, indent=2)

    response = client.messages.create(
        model=os.getenv("LIBRARY_CLASSIFIER_MODEL", "claude-haiku-4-5-20251001"),
        max_tokens=1024,
        system=system,
        messages=[{"role": "user", "content": user_content}],
    )
    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```", 2)[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    parsed = json.loads(raw)

    topics = parsed.get("topic_coverage") or []
    topics = [t for t in topics if t in _KNOWN_TOPICS]

    return {
        "prompt_type": parsed.get("prompt_type"),
        "input_type": parsed.get("input_type"),
        "output_type": parsed.get("output_type"),
        "summary": parsed.get("summary"),
        "topic_coverage": topics,
        "classification_notes": parsed.get("classification_notes"),
    }


def _needs_classification(entry: dict[str, Any]) -> bool:
    """True if any classification field is missing on a fixture entry."""
    return not all(
        entry.get(k) for k in ("prompt_type", "input_type", "output_type", "summary")
    ) or not isinstance(entry.get("topic_coverage"), list) or not entry.get("classification_notes")


def upsert_entry(
    db, entry: dict[str, Any], *, client=None, update_existing: bool = False
) -> tuple[str, dict[str, Any]]:
    """Upsert a library entry by title. Returns (action, merged_entry).

    Actions:
      - 'skipped_empty'   : full_text missing → skipped
      - 'skipped_exists'  : entry with this title already exists, update_existing=False
      - 'created'         : new row inserted (may have involved classification)
      - 'updated'         : existing row updated (only when update_existing=True)
    """
    title = entry.get("title")
    if not title:
        raise ValueError("entry missing 'title'")

    full_text = (entry.get("full_text") or "").strip()
    if not full_text:
        return "skipped_empty", entry

    existing = db.query(PromptLibrary).filter(PromptLibrary.title == title).first()
    if existing and not update_existing:
        return "skipped_exists", entry

    known = {k: v for k, v in entry.items() if k not in ("title", "full_text", "domain", "source_provenance") and v}
    if _needs_classification(entry):
        classified = classify_entry(full_text, known, client=client)
        for k, v in classified.items():
            if entry.get(k) in (None, "", []):
                entry[k] = v
        if not entry.get("classification_notes") and classified.get("classification_notes"):
            entry["classification_notes"] = classified["classification_notes"]

    topic_coverage = entry.get("topic_coverage") or []
    if not isinstance(topic_coverage, list):
        topic_coverage = []

    now = _utcnow()
    if existing:
        existing.full_text = full_text
        existing.summary = entry.get("summary")
        existing.prompt_type = entry.get("prompt_type")
        existing.input_type = entry.get("input_type")
        existing.output_type = entry.get("output_type")
        existing.domain = entry.get("domain") or "general"
        existing.source_provenance = entry.get("source_provenance")
        existing.topic_coverage = json.dumps(topic_coverage)
        existing.classification_notes = entry.get("classification_notes")
        existing.updated_at = now
        db.commit()
        return "updated", entry

    row = PromptLibrary(
        title=title,
        full_text=full_text,
        summary=entry.get("summary"),
        prompt_type=entry.get("prompt_type"),
        input_type=entry.get("input_type"),
        output_type=entry.get("output_type"),
        domain=entry.get("domain") or "general",
        source_provenance=entry.get("source_provenance"),
        topic_coverage=json.dumps(topic_coverage),
        classification_notes=entry.get("classification_notes"),
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.commit()
    return "created", entry


def load_entries(
    db, entries: list[dict[str, Any]], *, client=None, update_existing: bool = False
) -> list[tuple[str, str]]:
    """Seed an iterable of entries. Returns list of (action, title)."""
    results = []
    for entry in entries:
        try:
            action, merged = upsert_entry(
                db, dict(entry), client=client, update_existing=update_existing,
            )
        except Exception as e:
            results.append(("error: " + str(e), entry.get("title", "<unknown>")))
            continue
        results.append((action, merged.get("title", "<unknown>")))
    return results


def _load_yaml(path: str) -> list[dict[str, Any]]:
    import yaml

    with open(path) as f:
        data = yaml.safe_load(f)
    if isinstance(data, dict) and "entries" in data:
        return data["entries"]
    if isinstance(data, list):
        return data
    raise ValueError(f"YAML fixture {path} must be a list or a dict with an 'entries' key")


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed prompt_library from a YAML fixture")
    parser.add_argument("fixture", help="Path to YAML fixture file")
    parser.add_argument("--update", action="store_true", help="Update existing entries by title")
    args = parser.parse_args()

    entries = _load_yaml(args.fixture)
    db = SessionLocal()
    try:
        results = load_entries(db, entries, update_existing=args.update)
    finally:
        db.close()

    print(f"\nSeed complete — {len(results)} entr{'y' if len(results) == 1 else 'ies'} processed:\n")
    for action, title in results:
        print(f"  [{action:<16}] {title}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
