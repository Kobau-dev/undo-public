"""H Company Holo models through the OpenAI-compatible Models API.

Docs: https://hub.hcompany.ai/models-api/overview
- base URL https://api.hcompany.ai/v1, bearer key
- models: holo4-27b (most capable), holo4-35b-a3b (fastest), holo3-1-35b-a3b (free tier)
- at most 5 images per request
- grounding returns integer coordinates normalized to [0, 1000] on the image sent
- H-specific extras: structured_outputs={"json": schema}, chat_template_kwargs={"enable_thinking": bool}
"""
from __future__ import annotations

import json
import time
from typing import Any

from openai import APIError, APITimeoutError, OpenAI, RateLimitError
from PIL import Image
from pydantic import BaseModel, Field

from undo.images import image_part, text_part
from undo.interfaces import ModelResponse, ToolCall, VisionModel
from undo.log import get_logger

log = get_logger("holo")

MAX_IMAGES_PER_REQUEST = 5


class _Point(BaseModel):
    x: int = Field(ge=0, le=1000, description="X coordinate as integer in [0, 1000]")
    y: int = Field(ge=0, le=1000, description="Y coordinate as integer in [0, 1000]")


class HoloVisionModel(VisionModel):
    name = "holo"

    def __init__(self, api_key: str, base_url: str = "https://api.hcompany.ai/v1", model: str = "holo4-35b-a3b", timeout: float = 60.0, reasoning_effort: str | None = None):
        self.model = model
        self.reasoning_effort = reasoning_effort  # holo4-27b only: low | medium | xhigh (ignored by the others)
        self.client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout, max_retries=1)

    # -- core ---------------------------------------------------------------
    def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        json_schema: dict[str, Any] | None = None,
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.0,
        thinking: bool = True,
        max_tokens: int = 2048,
    ) -> ModelResponse:
        if json_schema and tools:
            raise ValueError("Holo: do not mix structured_outputs and tools in one request")
        n_images = sum(1 for m in messages for p in (m.get("content") if isinstance(m.get("content"), list) else []) if p.get("type") == "image_url")
        if n_images > MAX_IMAGES_PER_REQUEST:
            raise ValueError(f"Holo accepts at most {MAX_IMAGES_PER_REQUEST} images per request, got {n_images}")

        extra_body: dict[str, Any] = {"chat_template_kwargs": {"enable_thinking": thinking}}
        if json_schema:
            extra_body["structured_outputs"] = {"json": json_schema}
        kwargs: dict[str, Any] = dict(model=self.model, messages=messages, temperature=temperature, max_tokens=max_tokens, extra_body=extra_body)
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "required"
        if self.reasoning_effort and thinking:
            kwargs["reasoning_effort"] = self.reasoning_effort

        last_exc: Exception | None = None
        for attempt in range(3):
            try:
                t0 = time.time()
                resp = self.client.chat.completions.create(**kwargs)
                choice = resp.choices[0]
                msg = choice.message
                calls = []
                for tc in msg.tool_calls or []:
                    try:
                        args = json.loads(tc.function.arguments or "{}")
                    except json.JSONDecodeError:
                        args = {"_raw": tc.function.arguments}
                    calls.append(ToolCall(name=tc.function.name, arguments=args))
                reasoning = getattr(msg, "reasoning", None)
                log.debug("holo %s %.1fs images=%d tools=%d", self.model, time.time() - t0, n_images, len(calls))
                return ModelResponse(content=msg.content, tool_calls=calls, reasoning=reasoning, raw=resp)
            except (RateLimitError, APITimeoutError) as exc:
                last_exc = exc
                wait = 2.0 * (attempt + 1)
                log.warning("holo %s, retry in %.0fs", type(exc).__name__, wait)
                time.sleep(wait)
            except APIError as exc:
                last_exc = exc
                if getattr(exc, "status_code", 500) and exc.status_code < 500:
                    raise
                time.sleep(1.5 * (attempt + 1))
        raise RuntimeError(f"Holo request failed after retries: {last_exc}")

    # -- grounding ----------------------------------------------------------
    def locate(self, image: Image.Image, target: str) -> tuple[int, int]:
        """Element localization, as documented at hub.hcompany.ai/models-api/element-localization."""
        schema = _Point.model_json_schema()
        prompt = (
            "Localize an element on the GUI image according to the provided target and output a click position.\n"
            f" * You must output a valid JSON following the format: {schema}\n"
            f" Your target is:\n{target}"
        )
        resp = self.complete(
            [{"role": "user", "content": [image_part(image), text_part(prompt)]}],
            json_schema=schema,
            temperature=0.0,
            thinking=False,
            max_tokens=64,
        )
        point = _Point.model_validate_json(resp.content or "{}")
        return int(point.x / 1000 * image.width), int(point.y / 1000 * image.height)

    def list_models(self) -> list[str]:
        return [m.id for m in self.client.models.list().data]
