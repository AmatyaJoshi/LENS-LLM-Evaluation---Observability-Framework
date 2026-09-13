"""Versioned judge prompts (SPEC.md §5.3, CLAUDE.md).

Each prompt is a Markdown file under ``lens_core/judges/prompts/`` with YAML-ish
front matter (``name``, ``version``, ``output``) and two sections, ``## System``
and ``## User``. Variables are ``{{name}}`` placeholders. Bump ``version`` on
any edit; every Score row records the version it was produced with.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

PROMPTS_DIR = Path(__file__).parent / "prompts"
_FRONT = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_VAR = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")


@dataclass(frozen=True)
class Prompt:
    name: str
    version: str
    output: str  # json | text
    system: str
    user: str

    @property
    def variables(self) -> set[str]:
        return set(_VAR.findall(self.system)) | set(_VAR.findall(self.user))

    def render(self, variables: dict[str, Any]) -> tuple[str, str]:
        def sub(text: str) -> str:
            def repl(m: re.Match[str]) -> str:
                key = m.group(1)
                if key not in variables:
                    if key == "__retry_hint":
                        return ""
                    raise KeyError(f"prompt {self.name}@{self.version} missing variable {key!r}")
                value = variables[key]
                return value if isinstance(value, str) else str(value)

            return _VAR.sub(repl, text)

        user = sub(self.user)
        hint = variables.get("__retry_hint")
        if hint:
            user = f"{user}\n\n{hint}"
        return sub(self.system), user


def parse_prompt(text: str, fallback_name: str) -> Prompt:
    m = _FRONT.match(text)
    meta: dict[str, str] = {}
    body = text
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip().strip('"')
        body = text[m.end() :]
    parts = re.split(r"^## (System|User)\s*$", body, flags=re.MULTILINE)
    sections: dict[str, str] = {}
    for i in range(1, len(parts) - 1, 2):
        sections[parts[i]] = parts[i + 1].strip()
    if "System" not in sections or "User" not in sections:
        raise ValueError(f"prompt {fallback_name} must have '## System' and '## User' sections")
    return Prompt(
        name=meta.get("name", fallback_name),
        version=str(meta.get("version", "1")),
        output=meta.get("output", "json"),
        system=sections["System"],
        user=sections["User"],
    )


@cache
def load_prompt(name: str, directory: Path | None = None) -> Prompt:
    path = (directory or PROMPTS_DIR) / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"judge prompt not found: {path}")
    return parse_prompt(path.read_text(encoding="utf-8"), name)


def list_prompts(directory: Path | None = None) -> list[Prompt]:
    d = directory or PROMPTS_DIR
    return [load_prompt(p.stem, d) for p in sorted(d.glob("*.md"))]
