"""AI Fraud Investigation Agent — Agent Fraud Demo

Autonomous childcare provider fraud investigation using public records,
property GIS data, Google Maps, and Claude via OpenRouter.

Usage:
    streamlit run app.py
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st
from agno.agent import Agent
from agno.models.openrouter import OpenRouter
from agno.models.google import Gemini
from agno.models.groq import Groq
from agno.models.openai import OpenAILike

from core.prompts import _build_system_prompt
from tools.providers import search_childcare_providers
from tools.property import get_property_data, calculate_max_capacity
from tools.google import geocode_address, get_street_view, get_places_info
from tools.business import check_business_registration

# ── Streamlit App ─────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Agent Fraud — AI Fraud Investigation Agent",
    page_icon="🔍",
    layout="wide",
)

def load_css():
    css_path = Path("core/styles.css")
    if css_path.exists():
        with open(css_path) as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

load_css()

def _render_report(text: str):
    """Render the investigation output. Simple and reliable — never drops content."""
    import re

    if not text or not text.strip():
        st.warning("The investigation returned no results.")
        return

    # Convert HTML from ChatGPT's innerHTML to Markdown
    try:
        from markdownify import markdownify as md_convert
        if "<" in text and ">" in text:
            text = md_convert(
                text,
                heading_style="ATX",
                strip=['img', 'svg', 'picture', 'button', 'form'],
                escape_asterisks=False,
                escape_underscores=False,
            ).strip()
    except Exception:
        pass  # fallback: render as-is

    # Strip markdown images
    text = re.sub(r'!\[.*?\]\(.*?\)', '', text)

    # Strip ChatGPT "Give feedback" footer and everything after it
    for marker in ["Give feedback", "Was this response", "Report content"]:
        if marker in text:
            text = text.split(marker, 1)[0].strip()

    # Clean up excessive blank lines
    text = re.sub(r'\n{3,}', '\n\n', text).strip()

    if not text:
        st.warning("Response received but contained no displayable text after processing.")
        return

    # Debug expander so you can always see what came back
    with st.expander("🔍 Raw response (debug)", expanded=False):
        st.text(text[:3000] + ("…" if len(text) > 3000 else ""))

    # Render the markdown directly — no complex sectioning that can silently drop content
    st.markdown(text)


st.markdown('<div class="gradient-text">🔍 Agent Fraud</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="subtitle">'
    'Autonomous AI-powered childcare provider fraud investigation using public licensing records, '
    'Cook County property GIS data, and live business intelligence.'
    '</div>', 
    unsafe_allow_html=True
)

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Configuration")

    openrouter_key = st.text_input(
        "OpenRouter API Key (Optional)",
        type="password",
        help="Get one at openrouter.ai",
    )
    
    google_key = st.text_input(
        "Google Maps API Key",
        type="password",
        help="Needs Geocoding, Places, and Street View APIs enabled. Optional — skips visual analysis if omitted.",
    )
    
    model_id = st.selectbox(
        "AI Model",
        options=[
            "ai-bridge/free",
            "openai/gpt-4o",
            "openai/gpt-4o-mini",
            "anthropic/claude-3.5-sonnet",
            "meta-llama/llama-3.1-70b-instruct",
        ],
        index=0,
        help="Select the AI model. OpenRouter models require an OpenRouter API Key.",
    )
    _COOK_COUNTY_ZIPS = [
        "60623",  # Little Village / North Lawndale
        "60629",  # Chicago Lawn
        "60644",  # Austin
        "60621",  # Englewood
        "60628",  # Roseland
        "60619",  # Chatham / Auburn Gresham
        "60636",  # West Englewood
        "60612",  # Near West Side
        "60620",  # Auburn Gresham
        "60624",  # Garfield Park
    ]
    zip_code = st.selectbox(
        "ZIP Code (Cook County, IL)",
        options=_COOK_COUNTY_ZIPS,
        index=_COOK_COUNTY_ZIPS.index("60623"),
        help="Property data is available for Cook County ZIPs only",
    )

    is_extension = "bridge" in model_id.lower() or "extension" in model_id.lower()
    investigate_btn = st.button(
        "🔍 Start Investigation",
        type="primary",
        disabled=not (openrouter_key or is_extension),
        use_container_width=True,
    )

    st.divider()
    st.markdown(
        "**About:** This is a demo of [Agent Fraud](https://github.com/genus-lang/agent_fraud), "
        "an open-source autonomous fraud investigation system for subsidized childcare."
    )
    st.markdown(
        "**Scope:** Illinois only. Detects physical impossibility and anomalies in licensing records. "
        "Does **not** detect attendance fraud (requires non-public CCAP billing data)."
    )

# ── Main Investigation Area ───────────────────────────────────────────────────
if not investigate_btn:
    st.info(
        "Click **Start Investigation** to begin. "
        "The agent will search for licensed childcare providers in the ZIP code, "
        "cross-reference property records, and narrate its findings in real time."
    )
    with st.expander("How it works"):
        st.markdown("""
**The agent uses 7 investigation tools:**

| Tool | Source |
|------|--------|
| `search_childcare_providers` | Illinois DCFS licensing database |
| `get_property_data` | Cook County Assessor (Socrata open data) |
| `calculate_max_capacity` | IL DCFS Part 407 building code math |
| `get_street_view` | Google Street View API |
| `get_places_info` | Google Places API |
| `geocode_address` | Google Maps Geocoding API |
| `check_business_registration` | IL Secretary of State |

**What it looks for:**
- Licensed capacity exceeding physical building size (mathematical impossibility)
- Addresses where Google shows a different business or closed building
- Multiple providers sharing one address
- Providers with no Google presence, reviews, or business registration
- Geographic clusters that seem non-random

**What it cannot detect:**
- Attendance fraud (billing for children who didn't attend)
- Any fraud requiring non-public CCAP billing records
        """)

elif investigate_btn and (openrouter_key or is_extension):
    # Thread API keys to tool functions via session state (read by _google_key())
    st.session_state["google_maps_api_key"] = google_key or ""

    query = (
        f"Investigate all licensed childcare providers "
        f"in ZIP code {zip_code} in Illinois. "
        f"For each provider: get property data, calculate max legal capacity, "
        f"check Google Places and Street View, and look for anomalies. "
        f"Cross-reference business registrations when you spot patterns. "
        f"Narrate your full investigation."
    )

    # Friendly model display name (hide internal IDs)
    model_display = "AI Bridge (Free)" if is_extension else model_id.split("/")[-1].replace("-", " ").replace(":", " ").title()
    st.markdown(f"### 🔎 Investigation: ZIP {zip_code}")
    st.caption(f"Powered by {model_display}")
    st.divider()

    # Build agent
    try:
        if is_extension:
            import httpx
            _model = OpenAILike(
                id="chatgpt-extension", 
                api_key="dummy", 
                base_url="http://127.0.0.1:5000/v1",
                http_client=httpx.Client(timeout=600.0)
            )
        elif "groq" in model_id.lower() and groq_key:
            actual_model_id = model_id.replace("groq/", "")
            _model = Groq(id=actual_model_id, api_key=groq_key)
        elif "gemini" in model_id.lower() and gemini_key:
            actual_model_id = model_id.replace("google/", "")
            _model = Gemini(id=actual_model_id, api_key=gemini_key)
        else:
            _model = OpenRouter(id=model_id, api_key=openrouter_key, max_tokens=16384)
            
        agent = Agent(
            model=_model,
            tools=[
                search_childcare_providers,
                get_property_data,
                calculate_max_capacity,
                geocode_address,
                get_street_view,
                get_places_info,
                check_business_registration,
            ],
            description=_build_system_prompt(),
            instructions=[
                f"Investigate all providers returned for ZIP {zip_code}.",
                "Use Markdown tables whenever presenting lists of providers, capacity data, or property dimensions.",
                "For each Day Care Center with high capacity: deep investigation — property data, capacity calc, street view, places info.",
                "For Day Care Homes (small capacity): quick triage — note capacity vs legal limit.",
                "Cross-reference business registrations when owner names appear across multiple providers.",
                "Narrate your thinking as you investigate, but present the hard data in clean, aligned Markdown tables.",
                "Never say 'fraud' — use 'anomaly', 'requires further investigation', 'flags'.",
                "End with an 'Executive Findings' section summarizing the flagged providers in a table.",
            ],
            markdown=True,
            compress_tool_results=True,  # Auto-compresses large tool responses to prevent context overflow
        )
    except Exception as exc:
        st.error(f"Failed to initialize agent: {exc}")
        st.stop()

    # ── Run the investigation ────────────────────────────────────────────────
    parts: list = []
    is_ext = is_extension

    try:
        if is_ext:
            # ── Bridge mode: send concise prompt directly to proxy ─────────────
            import httpx

            # Keep prompt SHORT so clipboard injection always succeeds.
            # ChatGPT already knows how to investigate fraud — just give it the task.
            short_prompt = (
                f"You are a fraud investigator specialising in subsidized childcare fraud in Illinois.\n\n"
                f"Task: Investigate ALL licensed childcare providers in ZIP code {zip_code} (Cook County, IL).\n\n"
                f"For each provider:\n"
                f"1. Note their licensed capacity.\n"
                f"2. Estimate if the licensed capacity is physically plausible for a residential or commercial property.\n"
                f"3. Flag any anomalies (e.g. extremely high capacity for a residential address, multiple providers at same address, no online presence).\n\n"
                f"Present your findings in clean Markdown tables with columns: Provider Name | Address | Licensed Capacity | Anomaly Flags.\n"
                f"End with an 'Executive Findings' section summarizing the top flagged providers and why they warrant further investigation.\n\n"
                f"Be thorough. Use your knowledge of typical building sizes and Illinois DCFS regulations (Part 407)."
            )

            payload = {
                "model": "gpt-4",
                "messages": [{"role": "user", "content": short_prompt}]
            }

            status_area = st.empty()
            status_area.info("⏳ Prompt sent to ChatGPT tab — waiting for the response (this takes ~1–2 min)…")

            with st.spinner("Investigation in progress… analysing providers…"):
                try:
                    resp = httpx.post(
                        "http://127.0.0.1:5000/v1/chat/completions",
                        json=payload,
                        timeout=360.0,
                    )
                except httpx.ConnectError:
                    status_area.empty()
                    st.error("❌ Cannot reach proxy on port 5000. Make sure `chatgpt_proxy.py` is running.")
                    st.stop()

            status_area.empty()

            if resp.status_code != 200:
                err = resp.json().get("error", {}).get("message", resp.text)
                st.error(f"Proxy error {resp.status_code}: {err}")
                st.stop()

            full_text = (
                resp.json()
                    .get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")
                or ""
            )

            if not full_text.strip():
                st.error("ChatGPT returned an empty response. Make sure the ChatGPT tab is open and the extension is active.")
                st.stop()

            _render_report(full_text)

        else:
            # Real-time streaming
            narration_area = st.empty()
            with st.spinner("Investigation in progress..."):
                for chunk in agent.run(query, stream=True):
                    content = getattr(chunk, "content", None)
                    if content:
                        parts.append(content)
                        narration_area.markdown("\n\n".join(parts))
            full_text = "\n\n".join(parts)

            if not full_text.strip():
                with st.spinner("Fetching final result..."):
                    response = agent.run(query, stream=False)
                    full_text = getattr(response, "content", None) or str(response)
            _render_report(full_text)

        st.success("Investigation complete.")

        # Display any Street View images collected during the investigation
        sv_cache: dict = st.session_state.get("street_view_cache", {})
        if sv_cache:
            st.markdown("### Street View Images")
            for addr, frames in sv_cache.items():
                st.markdown(f"**{addr}**")
                cols = st.columns(min(len(frames), 4))
                for col, frame in zip(cols, frames):
                    col.image(frame["image_bytes"], caption=f"Heading {frame['heading']}° · {frame['capture_date']}", use_container_width=True)
            st.session_state.pop("street_view_cache", None)

    except Exception as exc:
        st.error(f"Investigation error: {exc}")
        partial = "".join(parts)
        if partial:
            st.markdown("**Partial results:**")
            st.markdown(partial)

