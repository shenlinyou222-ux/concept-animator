"""Minimal OpenAI-compatible LLM client with JSON output support.

Uses only the Python standard library so the tool has zero third-party
dependencies. Configure through environment variables:

- OPENAI_API_KEY
- OPENAI_BASE_URL   (default: https://api.openai.com/v1)
- OPENAI_MODEL      (default: gpt-4o-mini)
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any, Optional


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        # Strip markdown code fences.
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to locate the outermost JSON object.
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end > start:
            return json.loads(text[start : end + 1])
        raise


class LLMClient:
    """A small OpenAI-compatible chat completions client."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: float = 120.0,
    ) -> None:
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.base_url = (
            base_url
            or os.environ.get("OPENAI_BASE_URL")
            or "https://api.openai.com/v1"
        ).rstrip("/")
        self.model = model or os.environ.get("OPENAI_MODEL") or "gpt-4o-mini"
        self.timeout = timeout
        if not self.api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is not set. Use --offline to generate the demo tree "
                "or set OPENAI_API_KEY / OPENAI_BASE_URL for LLM traversal."
            )

    def chat_json(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.2,
    ) -> dict[str, Any]:
        body = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "response_format": {"type": "json_object"},
        }
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"LLM HTTP {exc.code}: {detail}") from exc
        try:
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"Unexpected LLM response: {payload}") from exc
        return _extract_json(content)


# Human-readable list of set relation choices, used in prompts.
SET_RELATION_CHOICES = (
    "subset_of, superset_of, element_of, intersects, disjoint_from, "
    "equal_to, union_of, complement_of"
)
TEMPORAL_RELATION_CHOICES = (
    "before, after, during, starts, finishes, overlaps, meets"
)


def system_prompt() -> str:
    return (
        "You are an expert concept decomposition engine. You explain concepts in a "
        "way suitable for an HTML animation. You always respond in valid JSON only.\n\n"
        "Rules:\n"
        "1. Explain the given concept in 2-4 short sentences.\n"
        "2. Find the sub-concepts that appear in your explanation. Each sub-concept "
        "must be either a real physical object/entity or a simple mathematical abstract "
        "concept (function, set, matrix, vector, number, formula, algorithm, etc.). "
        "If every sub-concept is already a physical entity or such a simple math "
        "concept, mark each as is_primitive=true and choose primitive_kind: "
        "\"physical\" or \"math\". Otherwise mark is_primitive=false so it is queued "
        "for the next traversal round.\n"
        "3. Prefer tree-shaped decomposition. Avoid duplicating an ancestor as a child.\n"
        "4. Model relationships with mathematical set theory where possible: "
        f"relation must be one of {SET_RELATION_CHOICES}.\n"
        "5. Detect temporal order in process-like explanations. Use kind one of "
        f"{TEMPORAL_RELATION_CHOICES}; include before/after entries for sequenced steps.\n"
        "6. Detect spatial containment/position relations only when meaningful.\n"
        "7. Optionally list contrast concepts that help the viewer understand by "
        "comparison; they will be styled as solid orange boxes with black text.\n"
        "8. After the plain explanation sentences, add 0-4 typed expression blocks "
        "(key \"blocks\") chosen to best express THIS concept. Allowed block types: "
        "formula {text, caption?}; analogy {text}; example {title?, text}; "
        "quote {text, source?} (verbatim excerpt when a source document is given); "
        "callout {text, tone?: warn|key}; steps {items: [...]}; "
        "table {columns: [...], rows: [[...]]}; "
        "chart {chart: bar|line, title?, unit?, data: [{label, value}]}; "
        "quiz {question, answer, hint?}. Use formula/steps/chart for math or "
        "processes, analogy for hard ideas, quote only when a source document is "
        "provided, quiz at most occasionally.\n"
        "9. The response MUST include a non-empty \"blocks\" array (at least 1 "
        "block, at most 4) for EVERY node. Pick the block types that express the "
        "concept best: processes -> steps; quantitative facts -> chart or formula; "
        "source document excerpts -> quote (verbatim, with a source note); hard "
        "ideas -> analogy; pitfalls -> callout.\n"
        "10. Write ALL human-readable text (explanations, summaries, blocks) in "
        "the SAME LANGUAGE as the topic/source document (Chinese when the source "
        "document is Chinese).\n"
        "11. DECOMPOSITION DEPTH RULE: every non-trivial data structure must be "
        "decomposed down to its mathematical model before it may terminate. A "
        "container/library name is NEVER a primitive: e.g. a hash map terminates "
        "only at (hash function h: U -> Z_m, bucket array A: [m] -> list, load "
        "factor alpha = n/m); a dense 3D array terminates only at its index "
        "bijection sigma: [16]^3 -> [4096] plus element type. Give each such "
        "node a formula block with the formal signature (sets, functions, "
        "invariants). Plain containers (vector, queue, mutex) must be expanded "
        "to their underlying representation (contiguous array + size, ring "
        "buffer + head/tail, atomic flag + waiter queue).\n"
        "12. When explaining SOURCE CODE, ground claims in the code structure: "
        "name the owning module/function for each concept (as quote or callout "
        "source), and prefer calling out the exact invariants (loop bounds, "
        "layout constants, synchronization rules) that the code relies on.\n\n"
        "Return this JSON schema:\n"
        "{\n"
        '  "node": {\n'
        '    "name": "concept name",\n'
        '    "explanation": ["sentence 1", "sentence 2"],\n'
        '    "summary": "one-sentence summary"\n'
        '  },\n'
        '  "subconcepts": [\n'
        '    {\n'
        '      "name": "sub-concept",\n'
        '      "is_primitive": true,\n'
        '      "primitive_kind": "physical|math|null",\n'
        '      "description": "brief description"\n'
        '    }\n'
        "  ],\n"
        '  "contrast_concepts": ["contrast A"],\n'
        '  "blocks": [\n'
        '    {"type": "formula", "text": "L = ...", "caption": "loss"},\n'
        '    {"type": "steps", "items": ["step 1", "step 2"]}\n'
        '  ],\n'
        '  "set_relations": [\n'
        '    {"subject": "concept", "relation": "subset_of", "object": "sub-concept", "note": "why"}\n'
        "  ],\n"
        '  "temporal_relations": [\n'
        '    {"before": "A", "after": "B", "kind": "before", "note": "A happens before B"}\n'
        "  ],\n"
        '  "spatial_relations": [\n'
        '    {"subject": "A", "relation": "inside", "object": "B", "note": "why"}\n'
        "  ]\n"
        "}"
    )


def user_prompt(node_name: str, path: list[str], doc_context: str = "") -> str:
    path_text = " > ".join(path) if path else node_name
    doc_part = ""
    if doc_context:
        excerpt = doc_context[:6000]
        doc_part = (
            "You are explaining knowledge extracted from a source document. "
            "Base your explanation on it and quote it verbatim (with a source note) "
            "when a direct excerpt helps. Source document excerpt:\n\n---\n"
            f"{excerpt}\n---\n\n"
        )
    return (
        f"Concept to explain: \"{node_name}\"\n"
        f"Current path in the explanation tree: {path_text}\n\n"
        f"{doc_part}"
        "Decompose it according to the rules. Return the JSON object."
    )