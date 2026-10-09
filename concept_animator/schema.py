"""Data model for concept explanation trees.

The tree is the persisted product of an LLM-driven concept decomposition.
Each node may carry:
- a short explanation (a few sentences),
- child concepts that were found in the explanation,
- set-theory relationships among the concept and its children,
- temporal relationships (with special edge rendering),
- spatial relationships (optional),
- contrast concepts rendered as solid orange boxes in the HTML animation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from typing import Any, Optional


# Set-theory relation names we support in rendering.
SET_RELATIONS = {
    "subset_of",
    "superset_of",
    "element_of",
    "intersects",
    "disjoint_from",
    "equal_to",
    "union_of",
    "complement_of",
}

# Temporal relation kinds; all are rendered with a special edge.
TEMPORAL_RELATIONS = {
    "before",
    "after",
    "during",
    "starts",
    "finishes",
    "overlaps",
    "meets",
}

# Primitive kinds that terminate traversal.
PRIMITIVE_KINDS = {"physical", "math"}

# Typed expression blocks that enrich how a node is explained.
# Each block is a free-form dict that MUST carry a "type" from this set.
BLOCK_TYPES = {
    "formula",   # {text, caption?}               styled formula display
    "analogy",    # {text}                         everyday-life analogy
    "example",    # {title?, text}                 concrete worked example
    "quote",      # {text, source?}                verbatim excerpt from the source doc
    "callout",    # {text, tone: warn|key}         emphasis / pitfall box
    "steps",      # {items: [str, ...]}            numbered animated timeline
    "table",      # {columns: [...], rows: [[...]]} comparison table
    "chart",      # {chart: bar|line, title?, unit?, data: [{label, value}]}
    "quiz",       # {question, answer, hint?}      click-to-reveal self check
    "video",      # {src (file path), caption?}      embedded animation (mp4, base64-inlined)
}


@dataclass
class SetRelation:
    subject: str
    relation: str
    object: str
    note: str = ""

    def validate(self) -> None:
        if self.relation not in SET_RELATIONS:
            raise ValueError(f"Unknown set relation: {self.relation}")


@dataclass
class TemporalRelation:
    before: str
    after: str
    kind: str = "before"
    note: str = ""

    def validate(self) -> None:
        if self.kind not in TEMPORAL_RELATIONS:
            raise ValueError(f"Unknown temporal relation: {self.kind}")


@dataclass
class SpatialRelation:
    subject: str
    relation: str
    object: str
    note: str = ""

    def validate(self) -> None:
        # Spatial relations are free-form (contains, near, inside, surrounds, ...)
        if not self.relation:
            raise ValueError("Spatial relation must not be empty")


@dataclass
class ConceptNode:
    id: str
    name: str
    summary: str = ""
    explanation: list[str] = field(default_factory=list)
    is_primitive: bool = False
    primitive_kind: Optional[str] = None
    contrast: list[str] = field(default_factory=list)
    blocks: list[dict[str, Any]] = field(default_factory=list)
    children: list["ConceptNode"] = field(default_factory=list)
    set_relations: list[SetRelation] = field(default_factory=list)
    temporal_relations: list[TemporalRelation] = field(default_factory=list)
    spatial_relations: list[SpatialRelation] = field(default_factory=list)

    def validate(self) -> None:
        if self.is_primitive and self.primitive_kind not in PRIMITIVE_KINDS:
            raise ValueError(
                f"Primitive node {self.name} must have primitive_kind in {PRIMITIVE_KINDS}"
            )
        for rel in self.set_relations:
            rel.validate()
        for rel in self.temporal_relations:
            rel.validate()
        for rel in self.spatial_relations:
            rel.validate()
        for block in self.blocks:
            if not isinstance(block, dict) or block.get("type") not in BLOCK_TYPES:
                raise ValueError(f"Invalid expression block: {block!r}")
        for child in self.children:
            child.validate()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "summary": self.summary,
            "explanation": self.explanation,
            "is_primitive": self.is_primitive,
            "primitive_kind": self.primitive_kind,
            "contrast": self.contrast,
            "blocks": self.blocks,
            "set_relations": [asdict(r) for r in self.set_relations],
            "temporal_relations": [asdict(r) for r in self.temporal_relations],
            "spatial_relations": [asdict(r) for r in self.spatial_relations],
            "children": [child.to_dict() for child in self.children],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ConceptNode":
        return cls(
            id=data["id"],
            name=data["name"],
            summary=data.get("summary", ""),
            explanation=data.get("explanation", []),
            is_primitive=data.get("is_primitive", False),
            primitive_kind=data.get("primitive_kind"),
            contrast=data.get("contrast", []),
            blocks=data.get("blocks", []),
            set_relations=[
                SetRelation(**r) for r in data.get("set_relations", [])
            ],
            temporal_relations=[
                TemporalRelation(**r) for r in data.get("temporal_relations", [])
            ],
            spatial_relations=[
                SpatialRelation(**r) for r in data.get("spatial_relations", [])
            ],
            children=[cls.from_dict(c) for c in data.get("children", [])],
        )

    def walk(self):
        """Yield (depth, node) in depth-first order."""
        stack = [(0, self)]
        while stack:
            depth, node = stack.pop()
            yield depth, node
            for child in reversed(node.children):
                stack.append((depth + 1, child))


def save_tree(node: ConceptNode, path: str) -> None:
    node.validate()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(node.to_dict(), f, ensure_ascii=False, indent=2)


def load_tree(path: str) -> ConceptNode:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    node = ConceptNode.from_dict(data)
    node.validate()
    return node