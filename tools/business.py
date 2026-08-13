import json
import requests
from urllib.parse import urlencode

from core.config import TOOL_TIMEOUT

def check_business_registration(name: str, state: str = "IL") -> str:
    """Look up business entity registration with the Secretary of State.

    Returns incorporation date, registered agent, entity type, and status.

    Args:
        name: Business name to search
        state: State abbreviation (IL supported)
    """
    if not name:
        return json.dumps({"status": "error", "error": "name is required"})

    state_key = state.upper()
    if state_key != "IL":
        return json.dumps({"status": "error", "error": "Only Illinois (IL) is supported in this demo."})

    try:
        # IL Secretary of State API (may return 403 behind CDN firewall)
        endpoint = "https://www.cyberdriveillinois.com/corpservices/api/entitysearch?" + urlencode({
            "searchstring": name.strip().lower()
        })
        r = requests.get(endpoint, timeout=TOOL_TIMEOUT)

        if r.status_code == 403:
            return json.dumps({
                "status": "blocked",
                "query": name,
                "state": state_key,
                "note": (
                    "IL SOS API returned 403 (CDN firewall). Direct access is unavailable. "
                    "Recommend manual lookup at: https://apps.ilsos.gov/corporatellc/"
                ),
            })

        if 200 <= r.status_code < 400:
            data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
            if data:
                return json.dumps({
                    "status": "ok",
                    "query": name,
                    "state": state_key,
                    "results": data,
                })
            return json.dumps({
                "status": "reachable_no_data",
                "query": name,
                "state": state_key,
                "note": "IL SOS endpoint reachable but returned no parseable data.",
            })

        return json.dumps({
            "status": "error",
            "query": name,
            "state": state_key,
            "error": f"IL SOS returned HTTP {r.status_code}",
        })

    except requests.exceptions.ConnectionError:
        return json.dumps({
            "status": "unavailable",
            "query": name,
            "state": state_key,
            "note": "IL SOS API unreachable. Manual lookup: https://apps.ilsos.gov/corporatellc/",
        })
    except Exception as exc:
        return json.dumps({"status": "error", "query": name, "state": state_key, "error": str(exc)})
