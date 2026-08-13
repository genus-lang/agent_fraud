import csv
import io
import json
import re

import requests
from bs4 import BeautifulSoup

from core.config import _IL_DCFS_URL, DCFS_TIMEOUT, MAX_PROVIDER_CAP

def search_childcare_providers(zip_code: str, state: str = "IL") -> str:
    """Search for licensed childcare providers in a target ZIP code area.

    Args:
        zip_code: 5-digit ZIP code to search
        state: State abbreviation (currently supports IL)
    """
    if state.upper() != "IL":
        return json.dumps({"status": "error", "error": "Only Illinois (IL) is supported in this demo."})
    if not re.match(r"^\d{5}$", str(zip_code).strip()):
        return json.dumps({"status": "error", "error": f"Invalid ZIP code '{zip_code}'. Must be exactly 5 digits."})

    try:
        session = requests.Session()
        headers = {"User-Agent": "Mozilla/5.0"}

        # Step 1: GET page to extract ASP.NET ViewState tokens
        page = session.get(_IL_DCFS_URL, headers=headers, timeout=DCFS_TIMEOUT)
        page.raise_for_status()
        soup = BeautifulSoup(page.text, "html.parser")

        form_data: dict[str, str] = {}
        for el in soup.find_all("input"):
            name = el.get("name")
            if name:
                form_data[name] = el.get("value", "")

        # Step 2: Trigger the search
        form_data["__EVENTTARGET"] = "ctl00$ContentPlaceHolderContent$ASPxSearch"
        for key in list(form_data.keys()):
            if key.endswith("ASPxSearch") and key.startswith("ctl00$ContentPlaceHolderContent$"):
                form_data[key] = "Search"

        resp = session.post(_IL_DCFS_URL, data=form_data, headers=headers, timeout=DCFS_TIMEOUT)
        resp.raise_for_status()

        # Step 3: Parse CSV rows embedded in the response
        providers = []
        for row in csv.reader(io.StringIO(resp.text)):
            if len(row) < 17:
                continue
            if not re.match(r"^\d{6}$", str(row[0]).strip()):
                continue
            row_zip = str(row[5]).strip().split("-")[0][:5]
            target_zip = str(zip_code).strip()[:5]
            if target_zip and row_zip != target_zip:
                continue
            providers.append({
                "name": str(row[1]).strip(),
                "address": str(row[2]).strip(),
                "city": str(row[3]).strip(),
                "zip": row_zip,
                "capacity": int(float(str(row[14]).strip() or "0")) if str(row[14]).strip() else 0,
                "license_type": str(row[7]).strip(),
                "status": str(row[16]).strip(),
                "license_number": str(row[0]).strip(),
                "state": "IL",
            })

        # Cap for demo
        capped = providers[:MAX_PROVIDER_CAP]
        return json.dumps({
            "status": "ok",
            "zip_code": zip_code,
            "total_found": len(providers),
            "providers_returned": len(capped),
            "note": f"Showing {len(capped)} of {len(providers)} providers." if len(providers) > MAX_PROVIDER_CAP else "",
            "providers": capped,
        })

    except Exception as exc:
        return json.dumps({"status": "error", "error": str(exc)})
