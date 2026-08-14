# 🔍 Surelock Homes: AI Fraud Investigation Agent

![Workflow Diagram](assets/workflow_diagram.png)

Surelock Homes is an advanced, autonomous AI agent designed to act as a digital forensic auditor for subsidized childcare providers. By orchestrating multiple public data sources, it investigates facilities to find discrepancies where the official licensing paperwork mathematically or visually contradicts physical reality.

---

## 🎯 Detailed Features & Capabilities

- **Autonomous Investigation:** You just provide a ZIP code, and the agent autonomously figures out which providers to check, what data to pull, and how deep to investigate based on the initial findings.
- **Cross-Referencing Reality:** It compares the licensed capacity (how many children a facility is allowed to hold) against the physical building's actual square footage.
- **Visual Intelligence:** Uses Google Street View to provide visual context—allowing human reviewers to see if an address points to an empty lot, a completely different business, or a tiny residential home claiming to hold 60 kids.
- **Business Verification:** Automatically looks up business entities to ensure the provider is actively registered and in good standing with the Secretary of State.
- **Live "Thought Process" Streaming:** The dashboard streams the agent's internal monologue in real-time. You can watch it say things like, *"I notice this building is 1,200 sq ft, let me check the legal limit..."*, making the AI's reasoning fully transparent.
- **Custom Premium UI:** Features a dark-mode, glassmorphism-styled Streamlit interface for a sleek, modern investigative experience.

---

## 🛠️ The Agent's Toolkit

The AI has access to 7 specialized tools to conduct its investigations:

1. **`search_childcare_providers`:** Scrapes the Illinois DCFS portal to find all active licensed providers in a target ZIP code.
2. **`get_property_data`:** Connects to the Cook County Assessor's open data (via Socrata API) to pull exact building square footage, lot size, and property class.
3. **`calculate_max_capacity`:** Applies the strict Illinois DCFS Part 407 building code math to determine the true maximum legal capacity.
4. **`geocode_address`:** Converts street addresses into geographic coordinates using Google Maps.
5. **`get_street_view`:** Captures 360-degree imagery (North, South, East, West) of the facility.
6. **`get_places_info`:** Queries Google Places to check if the address is listed as a different business type, and pulls recent reviews and operating status.
7. **`check_business_registration`:** Probes the state registry to see when the entity was incorporated and if it's currently active.

---

## 🧠 The Core Logic: Why Building Code Math?

We don't let the AI "guess" if something is fraudulent. We ground it in physics and the law.

- **The Law:** State laws dictate a minimum of 35 usable square feet per child indoors. 
- **The Rule of Thumb:** Typically, only about 65% of a building is "usable" childcare space (excluding hallways, kitchens, bathrooms).
- **The Math:** `Max Children = (Total Building Sq Ft × 0.65) ÷ 35`
- **The Result:** If a 900 sq ft building claims a licensed capacity of 50 kids, it is mathematically impossible. Relying on physical laws keeps the investigation objective, fair, and totally free of bias.

---

## 📂 Project Architecture

The codebase is structured for enterprise scalability:
- **`app.py`**: The main Streamlit dashboard and UI entry point.
- **`core/`**: 
  - `config.py`: Global constants and API endpoints.
  - `prompts.py`: The massive, highly detailed system prompt that instructs the LLM how to behave like a forensic auditor.
  - `utils.py`: Helper functions for parsing messy government address data.
  - `styles.css`: Custom CSS for the premium glassmorphism UI.
- **`tools/`**: Domain-specific API integrations (`business.py`, `google.py`, `property.py`, `providers.py`).

---

## 🚀 Comprehensive Setup Guide

### 1. Clone & Environment Setup
Clone the repository and optionally set up a virtual environment to keep your dependencies clean.
```bash
git clone https://github.com/genus-lang/agent_fraud.git
cd agent_fraud
python -m venv .venv
# On Windows: .venv\Scripts\activate
# On Mac/Linux: source .venv/bin/activate
```

### 2. Install Packages
```bash
pip install -r requirements.txt
```

### 3. Acquire Required API Keys
- **OpenRouter API Key (Required):** 
  - Sign up at [openrouter.ai](https://openrouter.ai).
  - Create a key to power the AI agent (Claude models are highly recommended for complex reasoning).
- **Google Maps API Key (Optional but Recommended):** 
  - Go to the [Google Cloud Console](https://console.cloud.google.com).
  - Enable the **Geocoding API**, **Places API**, and **Street View Static API**.
  - Generate an API key. Without this, the agent will skip visual and business profile checks.

### 4. Launch the Dashboard
Run the application locally:
```bash
streamlit run app.py
```
*Note: You do not need `.env` files! Just paste your API keys directly into the secure sidebar once the web app opens in your browser.*

---

## ⚠️ Limitations (What it CANNOT do)

- **Attendance Fraud:** It cannot tell if a provider is billing the state for children who aren't actually showing up. This requires non-public billing and attendance records.
- **Definitive Legal Proof:** All findings are investigative leads, flags, and anomalies. The agent is explicitly programmed to never use the word "fraud" definitively, as that is a legal conclusion requiring a human prosecutor. 

*Disclaimer: This is a demonstration tool utilizing strictly public data. It is intended to assist auditors, not replace human judgment.*
