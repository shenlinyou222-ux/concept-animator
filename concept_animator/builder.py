"""LLM-driven traversal that builds a concept explanation tree.

The traversal follows the objective:

1. Ask the LLM to explain the current concept in a few sentences.
2. Extract sub-concepts from those sentences and queue non-primitive ones.
3. Terminate when all extracted sub-concepts are physical entities or simple
   mathematical abstractions (sets, functions, matrices, vectors, formulas, ...).
4. Persist the result as a tree, with set/temporal/spatial relations attached.
"""

from __future__ import annotations

import uuid
from collections import deque
from typing import Any, Optional

from .llm_client import LLMClient, system_prompt, user_prompt
from .schema import (
    BLOCK_TYPES,
    ConceptNode,
    PRIMITIVE_KINDS,
    SetRelation,
    SpatialRelation,
    TemporalRelation,
)


def _new_id(name: str) -> str:
    return f"{name.strip()[:24]}-{uuid.uuid4().hex[:8]}" if name.strip() else uuid.uuid4().hex[:8]


def _pick(payload: dict[str, Any], key: str, default: Any = None) -> Any:
    return payload.get(key, default)


class ConceptBuilder:
    """Expand a root concept using an LLM until all frontier nodes are primitive."""

    def __init__(
        self,
        llm: LLMClient,
        max_depth: int = 6,
        max_children_per_node: int = 8,
        doc_context: str = "",
    ) -> None:
        self.llm = llm
        self.max_depth = max_depth
        self.max_children_per_node = max_children_per_node
        self.doc_context = (doc_context or "").strip()

    def build(self, root_topic: str) -> ConceptNode:
        root = ConceptNode(id=_new_id(root_topic), name=root_topic.strip())
        root.summary = f"正在展开：{root_topic.strip()}"
        pending: deque[tuple[ConceptNode, int, list[str]]] = deque()
        pending.append((root, 0, []))
        seen = {root.name}

        while pending:
            node, depth, ancestors = pending.popleft()
            if node.is_primitive:
                continue
            if depth >= self.max_depth:
                # Force termination by treating every newly found sub-concept as terminal
                # mathematical/physical primitive when we reach the depth budget.
                self._expand_with_budget_fallback(node, depth, ancestors)
                continue

            result = self._ask_llm(node, ancestors)
            self._apply_result(node, result, depth, ancestors, pending, seen)

        root.validate()
        return root

    def _ask_llm(self, node: ConceptNode, ancestors: list[str]) -> dict[str, Any]:
        messages = [
            {"role": "system", "content": system_prompt()},
            {"role": "user", "content": user_prompt(node.name, ancestors, self.doc_context)},
        ]
        data = self.llm.chat_json(messages)
        # Accept either:
        #   {"node": {...}, "subconcepts": [...], ...}
        # or a flat LLM object with all fields at the same level.
        if "node" in data and isinstance(data["node"], dict):
            node_data = dict(data["node"])
            # Outer fields are also accepted and merged into the node payload.
            for key in (
                "subconcepts",
                "contrast_concepts",
                "blocks",
                "set_relations",
                "temporal_relations",
                "spatial_relations",
            ):
                if key in data:
                    node_data[key] = data[key]
        else:
            node_data = data
        if not isinstance(node_data, dict):
            raise RuntimeError("LLM response did not contain a JSON object.")
        return node_data

    def _apply_result(
        self,
        node: ConceptNode,
        result: dict[str, Any],
        depth: int,
        ancestors: list[str],
        pending: deque[tuple[ConceptNode, int, list[str]]],
        seen: set[str],
    ) -> None:
        name = _pick(result, "name")
        if name:
            node.name = name
        node.summary = _pick(result, "summary", node.summary) or ""
        node.explanation = [
            str(s).strip() for s in _pick(result, "explanation", []) if str(s).strip()
        ]
        node.contrast = [
            str(c).strip() for c in _pick(result, "contrast_concepts", []) if str(c).strip()
        ]

        blocks = _pick(result, "blocks", [])
        node.blocks = [
            b for b in blocks
            if isinstance(b, dict) and b.get("type") in BLOCK_TYPES
        ][:6]

        subconcepts = _pick(result, "subconcepts", [])
        if not isinstance(subconcepts, list):
            subconcepts = []
        for i, sub in enumerate(subconcepts[: self.max_children_per_node]):
            if not isinstance(sub, dict):
                continue
            child_name = str(_pick(sub, "name", "")).strip()
            if not child_name:
                continue
            is_primitive = bool(_pick(sub, "is_primitive", False))
            primitive_kind = _pick(sub, "primitive_kind")
            if primitive_kind not in PRIMITIVE_KINDS:
                primitive_kind = None

            child = ConceptNode(
                id=_new_id(child_name),
                name=child_name,
                summary=str(_pick(sub, "description", "") or ""),
                is_primitive=is_primitive,
                primitive_kind=primitive_kind,
            )
            node.children.append(child)

            # Avoid revisiting the same concept twice: treat repeats as a terminal
            # reference to keep the persisted structure a tree.
            if child_name in seen:
                child.is_primitive = True
                child.primitive_kind = child.primitive_kind or "math"
                child.summary = (child.summary or "") + "（已在上文出现，作为引用节点终止）"
                continue
            seen.add(child_name)

            if not child.is_primitive:
                pending.append((child, depth + 1, ancestors + [node.name]))

        node.set_relations = self._parse_relations(
            _pick(result, "set_relations", []),
            SetRelation,
            ["subject", "relation", "object", "note"],
        )
        node.temporal_relations = self._parse_relations(
            _pick(result, "temporal_relations", []),
            TemporalRelation,
            ["before", "after", "kind", "note"],
        )
        node.spatial_relations = self._parse_relations(
            _pick(result, "spatial_relations", []),
            SpatialRelation,
            ["subject", "relation", "object", "note"],
        )

    def _parse_relations(self, items: Any, cls, fields: list[str]) -> list[Any]:
        if not isinstance(items, list):
            return []
        out = []
        for item in items:
            if not isinstance(item, dict):
                continue
            kwargs = {}
            for field in fields:
                value = item.get(field, "")
                if field == "kind" and not value:
                    value = "before"
                kwargs[field] = value
            try:
                rel = cls(**kwargs)
                rel.validate()
                out.append(rel)
            except (ValueError, TypeError):
                # Skip malformed relation entries rather than crashing the whole build.
                continue
        return out

    def _expand_with_budget_fallback(
        self,
        node: ConceptNode,
        depth: int,
        ancestors: list[str],
    ) -> None:
        """When depth budget is reached without a clean LLM leaf, ask again with
        a stronger instruction to terminate at primitives, then mark all children
        as primitive if they still cannot be expanded."""
        node_data = self._ask_llm(node, ancestors)
        self._apply_result(node, node_data, depth, ancestors, deque(), set())
        for child in node.children:
            if not child.is_primitive:
                child.is_primitive = True
                child.primitive_kind = child.primitive_kind or "math"
                child.summary = (child.summary or "") + "（达到深度上限，按终止原语处理）"