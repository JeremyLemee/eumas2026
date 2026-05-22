import os
from pathlib import Path
from typing import Any

from langchain.chat_models import BaseChatModel
from langchain_openai.data._profiles import _PROFILES as OPENAI_MODEL_PROFILES
from langchain_openai import ChatOpenAI

from langchain_ollama import ChatOllama
from pydantic import SecretStr


def _normalize_openai_model_name(name: str) -> str:
    return name.strip().lower().replace(".", "-")


def _openai_model_supports_reasoning(name: str) -> bool:
    normalized_name = _normalize_openai_model_name(name)
    profile = OPENAI_MODEL_PROFILES.get(normalized_name)
    if profile is not None:
        return bool(profile.get("reasoning_output"))

    return normalized_name.startswith(("o1", "o3", "o4", "gpt-5"))


def load_llm(
    provider: str,
    name: str,
    temperature: float | None = None,
    reasoning: bool | str | None = None,
    thinking: bool | str | None = None,
) -> BaseChatModel:
    model_kwargs: dict[str, Any] = {}
    if temperature is not None:
        model_kwargs["temperature"] = temperature

    provider_key = provider.lower()
    if provider_key == "openai":
        if reasoning is False and _openai_model_supports_reasoning(name):
            model_kwargs["reasoning"] = {"effort": "none"}

        if os.getenv("OPENAI_API_KEY"):
            return ChatOpenAI(model=name, **model_kwargs)
        key_path = Path(__file__).resolve().parent / "API_KEY.txt"
        api_key = None
        if key_path.exists():
            api_key = key_path.read_text().strip() or None
        if api_key:
            return ChatOpenAI(model=name, api_key=SecretStr(api_key), **model_kwargs)
        return ChatOpenAI(model=name, **model_kwargs)
    if provider_key == "ollama":
        ollama_reasoning = reasoning if reasoning is not None else thinking
        if ollama_reasoning is not None:
            model_kwargs["reasoning"] = ollama_reasoning
        return ChatOllama(model=name, **model_kwargs)

    raise ValueError("Only 'openai' and 'ollama' providers are supported")
