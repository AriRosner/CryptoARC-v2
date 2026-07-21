"""Verify that BotSettings fields stay aligned across backend and frontend sources."""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path


FIELD_NAME = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*")


def extract_braced_block(source: str, start: int) -> str:
    """Return the first balanced brace-delimited block at or after ``start``.

    Braces inside quoted strings and JavaScript-style comments do not affect the
    balance, so the helper is suitable for the TypeScript declaration and object
    literal forms checked by this script.
    """

    opening = source.find("{", start)
    if opening < 0:
        raise ValueError("opening brace not found")

    depth = 0
    index = opening
    quote: str | None = None
    line_comment = False
    block_comment = False
    while index < len(source):
        character = source[index]
        next_character = source[index + 1] if index + 1 < len(source) else ""

        if line_comment:
            if character in "\r\n":
                line_comment = False
            index += 1
            continue
        if block_comment:
            if character == "*" and next_character == "/":
                block_comment = False
                index += 2
                continue
            index += 1
            continue
        if quote:
            if character == "\\":
                index += 2
                continue
            if character == quote:
                quote = None
            index += 1
            continue
        if character == "/" and next_character == "/":
            line_comment = True
            index += 2
            continue
        if character == "/" and next_character == "*":
            block_comment = True
            index += 2
            continue
        if character in "'\"`":
            quote = character
            index += 1
            continue
        if character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                return source[opening : index + 1]
        index += 1

    raise ValueError("unterminated brace-delimited block")


def extract_python_dataclass_fields(source: str, class_name: str) -> set[str]:
    """Extract direct annotated fields from a Python dataclass without importing it."""

    module = ast.parse(source)
    for node in module.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return {
                field.target.id
                for field in node.body
                if isinstance(field, ast.AnnAssign) and isinstance(field.target, ast.Name)
            }
    raise ValueError(f"class {class_name} not found")


def extract_top_level_fields(block: str) -> set[str]:
    """Extract identifier keys whose colon appears at the block's top level."""

    fields: set[str] = set()
    depth = 0
    index = 0
    quote: str | None = None
    line_comment = False
    block_comment = False
    while index < len(block):
        character = block[index]
        next_character = block[index + 1] if index + 1 < len(block) else ""

        if line_comment:
            if character in "\r\n":
                line_comment = False
            index += 1
            continue
        if block_comment:
            if character == "*" and next_character == "/":
                block_comment = False
                index += 2
                continue
            index += 1
            continue
        if quote:
            if character == "\\":
                index += 2
                continue
            if character == quote:
                quote = None
            index += 1
            continue
        if character == "/" and next_character == "/":
            line_comment = True
            index += 2
            continue
        if character == "/" and next_character == "*":
            block_comment = True
            index += 2
            continue
        if character in "'\"`":
            quote = character
            index += 1
            continue
        if character == "{":
            depth += 1
            index += 1
            continue
        if character == "}":
            depth -= 1
            index += 1
            continue
        if depth == 1:
            match = FIELD_NAME.match(block, index)
            if match:
                cursor = match.end()
                while cursor < len(block) and block[cursor].isspace():
                    cursor += 1
                if cursor < len(block) and block[cursor] == "?":
                    cursor += 1
                    while cursor < len(block) and block[cursor].isspace():
                        cursor += 1
                if cursor < len(block) and block[cursor] == ":":
                    fields.add(match.group())
                index = match.end()
                continue
        index += 1
    return fields


def find_top_level_property(block: str, name: str) -> int | None:
    """Return the cursor after a direct ``name:`` property, if present."""

    depth = 0
    index = 0
    quote: str | None = None
    line_comment = False
    block_comment = False
    while index < len(block):
        character = block[index]
        next_character = block[index + 1] if index + 1 < len(block) else ""

        if line_comment:
            if character in "\r\n":
                line_comment = False
            index += 1
            continue
        if block_comment:
            if character == "*" and next_character == "/":
                block_comment = False
                index += 2
                continue
            index += 1
            continue
        if quote:
            if character == "\\":
                index += 2
                continue
            if character == quote:
                quote = None
            index += 1
            continue
        if character == "/" and next_character == "/":
            line_comment = True
            index += 2
            continue
        if character == "/" and next_character == "*":
            block_comment = True
            index += 2
            continue
        if character in "'\"`":
            quote = character
            index += 1
            continue
        if character == "{":
            depth += 1
            index += 1
            continue
        if character == "}":
            depth -= 1
            index += 1
            continue
        if depth == 1:
            match = FIELD_NAME.match(block, index)
            if match:
                cursor = match.end()
                while cursor < len(block) and block[cursor].isspace():
                    cursor += 1
                if match.group() == name and cursor < len(block) and block[cursor] == ":":
                    return cursor + 1
                index = match.end()
                continue
        index += 1
    return None


def extract_frontend_interface_fields(source: str) -> set[str]:
    marker = re.search(r"\bexport\s+interface\s+BotSettings\b", source)
    if not marker:
        raise ValueError("export interface BotSettings not found")
    return extract_top_level_fields(extract_braced_block(source, marker.end()))


def extract_fallback_settings_fields(source: str) -> set[str]:
    marker = re.search(r"\bconst\s+fallbackSnapshot\s*:\s*BotSnapshot\s*=", source)
    if not marker:
        raise ValueError("const fallbackSnapshot: BotSnapshot not found")
    snapshot_block = extract_braced_block(source, marker.end())
    settings_start = find_top_level_property(snapshot_block, "settings")
    if settings_start is None:
        raise ValueError("fallbackSnapshot settings object not found")
    return extract_top_level_fields(extract_braced_block(snapshot_block, settings_start))


def compare_field_sets(expected: set[str], actual: set[str], label: str) -> list[str]:
    """Return deterministic, actionable parity messages for one contract surface."""

    messages: list[str] = []
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing:
        messages.append(f"{label}: missing fields: {', '.join(missing)}")
    if extra:
        messages.append(f"{label}: extra fields: {', '.join(extra)}")
    return messages


def load_contract_fields(root: Path) -> tuple[set[str], set[str], set[str]]:
    """Load the three settings field sets from the repository rooted at ``root``."""

    backend = (root / "backend" / "app" / "core" / "models.py").read_text(encoding="utf-8")
    frontend = (root / "frontend" / "src" / "types.ts").read_text(encoding="utf-8")
    app = (root / "frontend" / "src" / "App.tsx").read_text(encoding="utf-8")
    return (
        extract_python_dataclass_fields(backend, "BotSettings"),
        extract_frontend_interface_fields(frontend),
        extract_fallback_settings_fields(app),
    )


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    backend_fields, frontend_fields, fallback_fields = load_contract_fields(root)
    messages = compare_field_sets(backend_fields, frontend_fields, "frontend interface")
    messages.extend(compare_field_sets(backend_fields, fallback_fields, "fallback snapshot"))
    if messages:
        print("Settings contract drift detected:", file=sys.stderr)
        for message in messages:
            print(f"- {message}", file=sys.stderr)
        return 1

    print(f"Settings contract passed: {len(backend_fields)} fields in all 3 surfaces.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
