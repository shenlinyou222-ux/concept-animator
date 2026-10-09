"""Basic tests for the concept animator tool.

Run with:
    python -m unittest concept_animator.test_concept_animator
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from . import cli
from .builder import ConceptBuilder
from .inference import infer_tree
from .render import render_html
from .schema import load_tree, ConceptNode


class FakeLLM:
    """Minimal stand-in for LLMClient used to test traversal logic."""

    def __init__(self) -> None:
        self.calls = 0

    def chat_json(self, messages, temperature=0.2):
        self.calls += 1
        topic = messages[-1]["content"].split('"')[1] if '"' in messages[-1]["content"] else ""
        if topic == "A":
            return {
                "node": {"name": "A", "summary": "root", "explanation": ["A 由 B 组成，C 是数学对象。"]},
                "subconcepts": [
                    {"name": "B", "is_primitive": False, "primitive_kind": None, "description": "待展开"},
                    {"name": "C", "is_primitive": True, "primitive_kind": "math", "description": "集合"},
                ],
                "contrast_concepts": ["X"],
                "set_relations": [],
                "temporal_relations": [],
                "spatial_relations": [],
            }
        if topic == "B":
            return {
                "node": {"name": "B", "summary": "child", "explanation": ["B 由 D 和 E 描述。"]},
                "subconcepts": [
                    {"name": "D", "is_primitive": True, "primitive_kind": "physical", "description": "实体"},
                    {"name": "E", "is_primitive": True, "primitive_kind": "math", "description": "函数"},
                ],
                "contrast_concepts": [],
                "set_relations": [],
                "temporal_relations": [],
                "spatial_relations": [],
            }
        raise AssertionError(topic)


class ConceptAnimatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.sample = Path(__file__).resolve().parent / "sample_tree.json"
        self.tree = load_tree(str(self.sample))

    def test_sample_tree_is_valid(self) -> None:
        self.tree.validate()
        node_count = sum(1 for _, _ in self.tree.walk())
        self.assertEqual(node_count, 18)
        self.assertEqual(self.tree.children[0].name, "数据集")

    def test_inference_adds_derived_relations(self) -> None:
        before = len(self.tree.temporal_relations)
        infer_tree(self.tree)
        self.assertGreater(len(self.tree.temporal_relations), before)

    def test_render_contains_visual_grammar(self) -> None:
        html = render_html(self.tree)
        self.assertIn("background: var(--bg)", html)
        self.assertIn("--orange-fill: #ff8c00", html)
        self.assertIn("--temporal-edge: #ff8c00", html)
        self.assertIn("子节点 · 仅作结构提示", html)
        self.assertIn("TREE =", html)
        # Nodes are clickable pages and entity/abstract borders exist.
        self.assertIn('data-node-id="', html)
        self.assertIn("history.replaceState", html)
        self.assertIn("child-box.entity", html)
        self.assertIn("child-box.abstract", html)

    def test_llm_builder_terminates_at_primitives(self) -> None:
        fake = FakeLLM()
        tree = ConceptBuilder(fake, max_depth=3).build("A")
        self.assertEqual(fake.calls, 2)
        self.assertEqual(tree.name, "A")
        self.assertEqual([c.name for c in tree.children], ["B", "C"])
        b = tree.children[0]
        self.assertEqual([c.name for c in b.children], ["D", "E"])
        for _, node in tree.walk():
            if node.children:
                continue
            self.assertTrue(node.is_primitive)
            self.assertIn(node.primitive_kind, {"physical", "math"})

    def test_demo_cli_writes_html(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "demo.html"
            args = cli.argparse.Namespace(output=str(out))
            code = cli.cmd_demo(args)
            self.assertEqual(code, 0)
            self.assertTrue(out.exists())
            content = out.read_text(encoding="utf-8")
            self.assertIn("机器学习", content)


if __name__ == "__main__":
    unittest.main()