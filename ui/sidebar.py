"""
TRUTHFORGE AI — Streamlit Sidebar
Renders model selection and API key inputs.
Returns a LangGraph config dict.
"""
from __future__ import annotations
import os
import streamlit as st
from config import CLOUD_MODELS, LOCAL_MODELS, make_langgraph_config


def render_sidebar() -> dict:
    """
    Render model configuration controls and return the LangGraph config dict.
    Called inside an expander in main.py — no st.sidebar wrapper here.
    """
    if True:  # block retained for minimal diff
        # --- Model Selection ---
        st.caption("Select the AI model for transcript analysis.")
        model_type = st.radio(
            "Model Type",
            ["☁️ Cloud Models", "🖥️ Local Models"],
            horizontal=True,
        )
        lm_studio_model_name = ""
        if model_type == "☁️ Cloud Models":
            selected_label = st.selectbox(
                "Select Cloud Model",
                list(CLOUD_MODELS.keys()),
                index=0,
            )
            provider = CLOUD_MODELS[selected_label][1]
            key_map = {
                "anthropic":    ("ANTHROPIC_API_KEY",    "Anthropic API Key"),
                "openai":       ("OPENAI_API_KEY",       "OpenAI API Key"),
                "google_genai": ("GOOGLE_API_KEY",       "Google API Key"),
            }
            if provider in key_map:
                env_key, label = key_map[provider]
                current = os.getenv(env_key, "")

                if current:
                    # Key is already set via environment — show confirmation, never expose it
                    st.success(f"✅ {label} configured", icon="🔑")
                    # Still allow override if user wants to use their own key
                    override = st.text_input(
                        f"Override {label} (optional)",
                        value="",
                        type="password",
                        placeholder="Leave blank to use server key",
                        help=f"A server-side {env_key} is already set. Only fill this to use a different key.",
                    )
                    if override:
                        os.environ[env_key] = override
                else:
                    # No env key set — user must provide one
                    api_key = st.text_input(
                        label,
                        value="",
                        type="password",
                        placeholder="sk-... or similar",
                        help=f"Set {env_key} in your .env file or enter it here.",
                    )
                    if api_key:
                        os.environ[env_key] = api_key

        else:
            selected_label = st.selectbox(
                "Select Local Model",
                list(LOCAL_MODELS.keys()),
                index=0,
            )
            if selected_label == "LM Studio (custom)":
                lm_studio_model_name = st.text_input(
                    "LM Studio Model Name",
                    value=os.getenv("LM_STUDIO_MODEL", "local-model"),
                    help="Exact model name as shown in LM Studio.",
                )
                base_url = st.text_input(
                    "LM Studio Base URL",
                    value=os.getenv("LM_STUDIO_BASE_URL", "http://localhost:1234/v1"),
                )
                os.environ["LM_STUDIO_BASE_URL"] = base_url
                os.environ["LM_STUDIO_MODEL"] = lm_studio_model_name
            else:
                ollama_url = st.text_input(
                    "Ollama Base URL",
                    value=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
                )
                os.environ["OLLAMA_BASE_URL"] = ollama_url
                st.info(
                    f"Make sure Ollama is running and the model is pulled:\n"
                    f"`ollama pull {LOCAL_MODELS.get(selected_label, ('?', ''))[0]}`"
                )

        with st.expander("🔬 Advanced Options", expanded=False):
            langsmith = st.toggle("Enable LangSmith Tracing", value=False)
            if langsmith:
                ls_key = st.text_input("LangSmith API Key", type="password")
                ls_project = st.text_input("LangSmith Project", value="truthforge-ai")
                if ls_key:
                    os.environ["LANGCHAIN_API_KEY"] = ls_key
                    os.environ["LANGCHAIN_TRACING_V2"] = "true"
                    os.environ["LANGCHAIN_PROJECT"] = ls_project

        st.caption("SWE5008 NUS · For academic use only.")

    config = make_langgraph_config(selected_label, lm_studio_model_name)
    return config
