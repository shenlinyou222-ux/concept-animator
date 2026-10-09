"""Set-theory and temporal inference for concept trees.

The LLM provides explicit relationships; this module derives additional
relationships that follow from transitive closure, so the rendered diagram can
show the mathematically implied structure (e.g. A subset B and B subset C
implies A subset C; A before B and B before C implies A before C).
"""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Iterable

from .schema import ConceptNode, SetRelation, TemporalRelation

VALID_SET = {
    "subset_of",
    "superset_of",
    "element_of",
    "intersects",
    "disjoint_from",
    "equal_to",
    "union_of",
    "complement_of",
}


def _names_in_relations(node: ConceptNode) -> set[str]:
    names = {node.name}
    for child in node.children:
        names.add(child.name)
    for rel in node.set_relations:
        names.add(rel.subject)
        names.add(rel.object)
    for rel in node.temporal_relations:
        names.add(rel.before)
        names.add(rel.after)
    for rel in node.spatial_relations:
        names.add(rel.subject)
        names.add(rel.object)
    return {n for n in names if n}


def _transitive_closure(pairs: Iterable[tuple[str, str]]) -> list[tuple[str, str]]:
    graph: dict[str, set[str]] = defaultdict(set)
    for a, b in pairs:
        if a and b and a != b:
            graph[a].add(b)
    # BFS over each source for transitive reachability.
    seen_pairs: set[tuple[str, str]] = set()
    for source in list(graph):
        queue = deque([source])
        visited = {source}
        while queue:
            cur = queue.popleft()
            for nxt in graph[cur]:
                if nxt not in visited:
                    visited.add(nxt)
                    queue.append(nxt)
                    if source != nxt:
                        seen_pairs.add((source, nxt))
    return list(seen_pairs)


def infer_node_relations(node: ConceptNode) -> None:
    """Add derived set/temporal relations directly to one node in-place."""
    names = _names_in_relations(node)

    # Set-theory transitive closure for subset_of and superset_of.
    subset_pairs = [
        (rel.subject, rel.object)
        for rel in node.set_relations
        if rel.relation == "subset_of" and rel.subject in names and rel.object in names
    ]
    superset_pairs = [
        (rel.subject, rel.object)
        for rel in node.set_relations
        if rel.relation == "superset_of" and rel.subject in names and rel.object in names
    ]
    existing = {
        (r.subject, r.relation, r.object)
        for r in node.set_relations
    }

    for a, b in _transitive_closure(subset_pairs):
        if (a, "subset_of", b) not in existing:
            node.set_relations.append(
                SetRelation(
                    subject=a,
                    relation="subset_of",
                    object=b,
                    note="由集合论传递闭包推导",
                )
            )
            existing.add((a, "subset_of", b))

    # A superset_of B is the same as B subset_of A; derive the mirror too.
    reverse_subset = [(b, a) for a, b in superset_pairs]
    for a, b in _transitive_closure(reverse_subset):
        if (a, "subset_of", b) not in existing:
            node.set_relations.append(
                SetRelation(
                    subject=a,
                    relation="subset_of",
                    object=b,
                    note="由 superset_of 反向后传递推导",
                )
            )
            existing.add((a, "subset_of", b))

    # Temporal transitive closure.
    temporal_pairs = [
        (rel.before, rel.after)
        for rel in node.temporal_relations
        if rel.before in names and rel.after in names
    ]
    existing_temporal = {
        (r.before, r.after)
        for r in node.temporal_relations
    }
    for a, b in _transitive_closure(temporal_pairs):
        if (a, b) not in existing_temporal:
            node.temporal_relations.append(
                TemporalRelation(
                    before=a,
                    after=b,
                    kind="before",
                    note="由时间先后关系传递推导",
                )
            )
            existing_temporal.add((a, b))


def infer_tree(root: ConceptNode) -> ConceptNode:
    """Apply inference to every node in the tree."""
    for _, node in root.walk():
        infer_node_relations(node)
    root.validate()
    return root