"""Cassette judge: records and replays judge responses so tests never call an LLM.

A cassette is a JSON file ``{"entries": {key: [responses...]}}`` where ``key`` is
``"<prompt_name>@<version>:<sha1(system+user)[:12]>"``. In *replay* mode a missing
key falls back to the next unconsumed response registered under the bare prompt
name (``"<prompt_name>"``), which lets tests script sequences per prompt without
hashing. In *record* mode calls are forwarded to an inner judge and saved.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

from lens_core.judges.base import Judge, JudgeError, JudgeResponse
from lens_core.judges.prompts import Prompt


def _key(prompt_name: str, version: str, system: str, user: str) -> str:
    digest = hashlib.sha1((system + "\n---\n" + user).encode("utf-8")).hexdigest()[:12]
    return f"{prompt_name}@{version}:{digest}"


class CassetteJudge(Judge):
    name = "cassette"
    tier = "cassette"

    def __init__(
        self,
        path: Path | None = None,
        *,
        entries: dict[str, list[str | dict[str, Any]]] | None = None,
        inner: Judge | None = None,
        model: str = "cassette",
        embeddings: dict[str, list[float]] | None = None,
    ) -> None:
        super().__init__()
        self.path = path
        self.inner = inner
        self.model = inner.model if inner else model
        self._entries: dict[str, list[str | dict[str, Any]]] = defaultdict(list)
        self._cursor: dict[str, int] = defaultdict(int)
        self._embeddings = embeddings
        self._current_prompt: tuple[str, str] | None = None
        if path and path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            for k, v in data.get("entries", {}).items():
                self._entries[k] = list(v)
        for k, v in (entries or {}).items():
            self._entries[k].extend(v)

    # -- recording helpers --------------------------------------------------------------------
    def save(self) -> None:
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps({"entries": dict(self._entries)}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def script(self, prompt_name: str, *responses: str | dict[str, Any]) -> CassetteJudge:
        """Register canned responses for a prompt name (in order)."""
        self._entries[prompt_name].extend(responses)
        return self

    # -- Judge API ----------------------------------------------------------------------------
    async def complete(
        self,
        prompt: Prompt,
        variables: dict[str, Any],
        *,
        temperature: float = 0.0,
        max_tokens: int = 1024,
    ) -> JudgeResponse:
        self._current_prompt = (prompt.name, prompt.version)
        return await super().complete(
            prompt, variables, temperature=temperature, max_tokens=max_tokens
        )

    async def _complete(
        self, system: str, user: str, *, temperature: float, max_tokens: int
    ) -> JudgeResponse:
        name, version = self._current_prompt or ("unknown", "0")
        exact = _key(name, version, system, user)
        t0 = time.perf_counter()
        for key in (exact, name):
            responses = self._entries.get(key)
            if responses:
                idx = self._cursor[key]
                if idx < len(responses):
                    self._cursor[key] += 1
                    raw = responses[idx]
                    text = raw if isinstance(raw, str) else json.dumps(raw)
                    return JudgeResponse(
                        text=text,
                        model=self.model,
                        prompt_name=name,
                        prompt_version=version,
                        tokens_in=len(system + user) // 4,
                        tokens_out=len(text) // 4,
                        cost_usd=0.0,
                        latency_ms=(time.perf_counter() - t0) * 1000,
                        cached=True,
                    )
        if self.inner is not None:
            resp = await self.inner._complete(
                system, user, temperature=temperature, max_tokens=max_tokens
            )
            self._entries[exact].append(resp.text)
            self.save()
            return resp
        raise JudgeError(f"cassette has no response for {exact} (prompt {name})")

    async def embed(self, texts: list[str]) -> list[list[float]] | None:
        if self._embeddings is None:
            return None if self.inner is None else await self.inner.embed(texts)
        return [self._embeddings.get(t, [0.0]) for t in texts]
