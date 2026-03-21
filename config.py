"""
TRUTHFORGE AI — Model Provider Configuration
Supports cloud (Anthropic, OpenAI, Google) and local (Ollama, LM Studio) models.
"""

from __future__ import annotations
import os
from dotenv import load_dotenv

load_dotenv()

# --- Provider registry ---

CLOUD_MODELS: dict[str, tuple[str, str]] = {
    "Claude Sonnet 4.6 (Anthropic)": ("claude-sonnet-4-6", "anthropic"),
    "GPT-4o (OpenAI)":               ("gpt-4o", "openai"),
    "GPT-4o Mini (OpenAI)":          ("gpt-4o-mini", "openai"),
    "Gemini 2.0 Flash (Google)":     ("gemini-2.0-flash", "google_genai"),
}

LOCAL_MODELS: dict[str, tuple[str, str] | None] = {
    "Llama 3.1 8B (Ollama)":  ("llama3.1:8b", "ollama"),
    "Mistral 7B (Ollama)":    ("mistral:7b", "ollama"),
    "Phi-3 Mini (Ollama)":    ("phi3:mini", "ollama"),
    "LM Studio (custom)":     None,  # handled separately via base_url
}

ALL_MODELS: dict[str, tuple[str, str] | None] = {**CLOUD_MODELS, **LOCAL_MODELS}

# Default model used when no config is provided
DEFAULT_MODEL_NAME = "claude-sonnet-4-6"
DEFAULT_MODEL_PROVIDER = "anthropic"


def get_llm(model_name: str, model_provider: str, temperature: float = 0):
    """
    Return a LangChain chat model for the given provider.
    Supports cloud providers via init_chat_model and local providers via
    Ollama or LM Studio (OpenAI-compatible endpoint).
    """
    if model_provider == "lmstudio":
        from langchain_openai import ChatOpenAI
        base_url = os.getenv("LM_STUDIO_BASE_URL", "http://localhost:1234/v1")
        return ChatOpenAI(
            base_url=base_url,
            api_key="lm-studio",
            model=model_name,
            temperature=temperature,
        )

    if model_provider == "ollama":
        from langchain_ollama import ChatOllama
        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        return ChatOllama(
            model=model_name,
            base_url=base_url,
            temperature=temperature,
        )

    # Cloud providers: anthropic, openai, google_genai
    from langchain.chat_models import init_chat_model
    return init_chat_model(
        model=model_name,
        model_provider=model_provider,
        temperature=temperature,
    )


def get_llm_from_config(config: dict) -> object:
    """Extract model settings from a LangGraph config dict and return LLM."""
    cfg = config.get("configurable", {})
    model_name = cfg.get("model", DEFAULT_MODEL_NAME)
    model_provider = cfg.get("model_provider", DEFAULT_MODEL_PROVIDER)
    return get_llm(model_name, model_provider)


def make_langgraph_config(model_label: str, lm_studio_model: str = "") -> dict:
    """
    Convert a display label from ALL_MODELS into a LangGraph config dict.
    Used by the Streamlit sidebar to pass model choice into the pipeline.
    """
    entry = ALL_MODELS.get(model_label)
    if entry is None:
        # LM Studio custom path
        model_name = lm_studio_model or os.getenv("LM_STUDIO_MODEL", "local-model")
        return {"configurable": {"model": model_name, "model_provider": "lmstudio"}}
    model_name, model_provider = entry
    return {"configurable": {"model": model_name, "model_provider": model_provider}}
