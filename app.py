"""AI Fraud Investigation Agent — Surelock Homes Demo

Autonomous childcare provider fraud investigation using public records,
property GIS data, Google Maps, and Claude via OpenRouter.

Usage:
    streamlit run app.py
"""

from __future__ import annotations

import streamlit as st
from agno.agent import Agent
from agno.models.openrouter import OpenRouter

from core.prompts import _build_system_prompt
from tools.providers import search_childcare_providers
from tools.property import get_property_data, calculate_max_capacity
from tools.google import geocode_address, get_street_view, get_places_info
from tools.business import check_business_registration

# ── Streamlit App ─────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Surelock Homes — AI Fraud Investigation Agent",
    page_icon="🔍",
    layout="wide",
)

st.title("🔍 AI Fraud Investigation Agent")
st.caption(
    "Autonomous childcare provider fraud investigation using public licensing records, "
    "Cook County property data, Google Maps, and Claude via OpenRouter."
)

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Configuration")

    openrouter_key = st.text_input(
        "OpenRouter API Key",
        type="password",
        help="Get one at openrouter.ai — free tier available",
    )
    google_key = st.text_input(
        "Google Maps API Key",
        type="password",
        help="Needs Geocoding, Places, and Street View APIs enabled. Optional — skips visual analysis if omitted.",
    )
    model_id = st.selectbox(
        "Model",
        options=[
            "anthropic/claude-sonnet-4.6",
            "anthropic/claude-opus-4.6",
            "google/gemini-3.1-flash-lite-preview",
            "openai/gpt-5.4",
            "openai/gpt-4o",
        ],
        index=0,
        help="Claude Sonnet is a good balance of speed and quality",
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

    investigate_btn = st.button(
        "🔍 Start Investigation",
        type="primary",
        disabled=not openrouter_key,
        use_container_width=True,
    )

    st.divider()
    st.markdown(
        "**About:** This is a demo of [Surelock Homes](https://github.com/oso95/Surelock-Homes), "
        "an open-source autonomous fraud investigation system for subsidized childcare."
    )
    st.markdown(
        "**Scope:** Illinois only. Detects physical impossibility and anomalies in licensing records. "
        "Does **not** detect attendance fraud (requires non-public CCAP billing data)."
    )

# ── Main Investigation Area ───────────────────────────────────────────────────
if not investigate_btn:
    st.info(
        "Enter your OpenRouter API key in the sidebar and click **Start Investigation** to begin. "
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

elif investigate_btn and openrouter_key:
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

    st.markdown(f"### Investigation: ZIP {zip_code}")
    st.markdown(f"*Model: `{model_id}`*")
    st.divider()

    # Build agent
    try:
        agent = Agent(
            model=OpenRouter(id=model_id, api_key=openrouter_key, max_tokens=16384),
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
                "For each Day Care Center with high capacity: deep investigation — property data, capacity calc, street view, places info.",
                "For Day Care Homes (small capacity): quick triage — note capacity vs legal limit.",
                "Cross-reference business registrations when owner names appear across multiple providers.",
                "Narrate your thinking as you investigate. The narration IS the product.",
                "Never say 'fraud' — use 'anomaly', 'requires further investigation', 'flags'.",
                "End with a summary of flagged providers and pattern findings.",
            ],
            markdown=True,
            compress_tool_results=True,  # Auto-compresses large tool responses to prevent context overflow
        )
    except Exception as exc:
        st.error(f"Failed to initialize agent: {exc}")
        st.stop()

    # Stream the investigation
    narration_area = st.empty()
    parts: list = []

    try:
        with st.spinner("Investigation in progress..."):
            for chunk in agent.run(query, stream=True):
                content = getattr(chunk, "content", None)
                if content:
                    parts.append(content)
                    narration_area.markdown("".join(parts))
        full_text = "".join(parts)

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
