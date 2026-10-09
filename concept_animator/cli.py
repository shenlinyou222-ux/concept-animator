"""Command-line interface for the concept explainer tool.

All paths are resolved from the current working directory, so run from the
repository root.

Examples
--------
python -m concept_animator.cli demo --output output/demo.html
python -m concept_animator.cli verify --input data/sample_tree.json
python -m concept_animator.cli render --input data/sample_tree.json --output output/demo.html
OPENAI_API_KEY=... python -m concept_animator.cli build --topic "机器学习是什么" --output output/my_tree.json
OPENAI_API_KEY=... python -m concept_animator.cli build --topic "光合作用" --output output/photosynthesis.json --render output/photosynthesis.html
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .builder import ConceptBuilder
from .inference import infer_tree
from .llm_client import LLMClient
from .render import render_to_file
from .schema import load_tree, save_tree, ConceptNode

# This module lives at <repo-root>/concept_animator/cli.py, so the repository
# root that owns data/ output/ media/ is exactly one level above the package.
PACKAGE_DIR = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_DIR.parent
DATA_DIR = REPO_ROOT / "data"


def _demo_tree() -> ConceptNode:
    sample = DATA_DIR / "sample_tree.json"
    if not sample.is_file():
        raise FileNotFoundError(
            f"Bundled sample tree not found at {sample}. "
            "Run the CLI from a full checkout of the repository."
        )
    return load_tree(str(sample))


def cmd_demo(args: argparse.Namespace) -> int:
    tree = _demo_tree()
    output = args.output
    render_to_file(tree, output)
    return 0


def cmd_render(args: argparse.Namespace) -> int:
    tree = load_tree(args.input)
    render_to_file(tree, args.output)
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    tree = load_tree(args.input)
    tree.validate()
    count = sum(1 for _, _ in tree.walk())
    leaves = sum(1 for _, n in tree.walk() if not n.children)
    print(f"OK: {tree.name}, nodes={count}, leaves={leaves}")
    return 0


def cmd_infer(args: argparse.Namespace) -> int:
    tree = load_tree(args.input)
    infer_tree(tree)
    save_tree(tree, args.output)
    print(f"Saved inferred tree: {args.output}")
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    try:
        llm = LLMClient(timeout=args.timeout)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    doc_context = ""
    if args.doc:
        doc_path = Path(args.doc)
        if not doc_path.exists():
            print(f"ERROR: document not found: {args.doc}", file=sys.stderr)
            return 2
        raw = doc_path.read_bytes()
        for enc in ("utf-8", "utf-8-sig", "gb18030"):
            try:
                doc_context = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        print(f"Loaded source document: {args.doc} ({len(doc_context)} chars)")
    builder = ConceptBuilder(
        llm,
        max_depth=args.max_depth,
        max_children_per_node=args.max_children,
        doc_context=doc_context,
    )
    tree = builder.build(args.topic)
    save_tree(tree, args.output)
    print(f"Saved tree: {args.output}")
    if args.render:
        render_to_file(tree, args.render)
    return 0


def _configure_stdio() -> None:
    """Keep CJK output printable when stdout is not an interactive console.

    On Windows, Python falls back to the locale encoding (cp1252 on a US/EU
    install) whenever stdout is redirected or piped, and the shipped trees have
    Chinese names, so ``print(f"OK: {tree.name}, ...")`` used to die with
    UnicodeEncodeError. Pinning the CLI's own output streams to UTF-8 (and never
    failing on a character the terminal cannot draw) makes
    ``python -m concept_animator.cli verify ... > log.txt`` safe everywhere.
    Nothing about the tool's data handling changes.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue  # stream replaced by the caller, or Python < 3.7
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            pass


def main(argv: list[str] | None = None) -> int:
    _configure_stdio()
    parser = argparse.ArgumentParser(
        prog="concept-animator",
        description="Build and render concept explanation trees as HTML animations.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_demo = sub.add_parser("demo", help="Render the bundled sample tree to an HTML viewer")
    p_demo.add_argument("--output", default=str(Path("output/demo.html")))
    p_demo.set_defaults(func=cmd_demo)

    p_render = sub.add_parser("render", help="Render an existing concept tree JSON to HTML")
    p_render.add_argument("--input", required=True)
    p_render.add_argument("--output", required=True)
    p_render.set_defaults(func=cmd_render)

    p_verify = sub.add_parser("verify", help="Validate a concept tree JSON")
    p_verify.add_argument("--input", required=True)
    p_verify.set_defaults(func=cmd_verify)

    p_infer = sub.add_parser("infer", help="Add derived set/temporal closure relations")
    p_infer.add_argument("--input", required=True)
    p_infer.add_argument("--output", required=True)
    p_infer.set_defaults(func=cmd_infer)

    p_build = sub.add_parser("build", help="Build a tree by LLM traversal")
    p_build.add_argument("--topic", required=True)
    p_build.add_argument("--doc", default="", help="Optional source document (.txt/.md) to ground the explanation")
    p_build.add_argument("--output", required=True)
    p_build.add_argument("--max-depth", type=int, default=6)
    p_build.add_argument("--max-children", type=int, default=8)
    p_build.add_argument("--timeout", type=float, default=120.0)
    p_build.add_argument("--render", default="", help="Also render HTML to this path")
    p_build.set_defaults(func=cmd_build)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())