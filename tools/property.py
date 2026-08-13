import json
import requests
from typing import Optional

from core.config import (
    TOOL_TIMEOUT,
    _COOK_ADDR_URL,
    _COOK_RES_URL,
    _COOK_COMMERCIAL_URL,
    _COOK_ASSESSED_URL,
)
from core.utils import _parse_address

_CAPACITY_REGS = {
    "IL": {"sqft_per_child": 35, "regulation": "IL DCFS Title 89, Part 407"},
    "MN": {"sqft_per_child": 35, "regulation": "MN Rules 9503.0155"},
}

def calculate_max_capacity(building_sqft: float, state: str = "IL", usable_ratio: float = 0.65) -> str:
    """Calculate the maximum legal childcare capacity for a building based on state building code requirements.

    Shows the full calculation so findings can be verified.

    Args:
        building_sqft: Total building square footage
        state: State abbreviation (IL or MN)
        usable_ratio: Estimated ratio of usable childcare space to total sqft (default 0.65)
    """
    state_key = state.upper()
    reg = _CAPACITY_REGS.get(state_key)
    if not reg:
        return json.dumps({"status": "error", "error": f"State {state} not supported. Use IL or MN."})
    if not building_sqft or building_sqft <= 0:
        return json.dumps({"status": "error", "error": "building_sqft must be greater than 0"})

    sqft_per_child = reg["sqft_per_child"]
    usable_sqft = float(building_sqft) * float(usable_ratio)
    max_legal = int(usable_sqft // sqft_per_child)

    return json.dumps({
        "status": "ok",
        "building_sqft": float(building_sqft),
        "usable_ratio": usable_ratio,
        "usable_sqft": round(usable_sqft, 1),
        "sqft_per_child_required": sqft_per_child,
        "max_legal_capacity": max_legal,
        "state": state_key,
        "regulation": reg["regulation"],
        "calculation": f"{building_sqft} sqft × {usable_ratio} usable ratio = {usable_sqft:.0f} usable sqft ÷ {sqft_per_child} sqft/child = {max_legal} children max",
    })

def get_property_data(address: str, county: str = "Cook", state: str = "IL") -> str:
    """Get building and parcel data for a specific address from county GIS records.

    Returns building square footage, lot size, zoning, property class, and year built.

    Args:
        address: Full street address
        county: County name (default: Cook for Chicago/IL)
        state: State abbreviation (default: IL)
    """
    if not address:
        return json.dumps({"status": "error", "error": "address is required"})

    try:
        parsed = _parse_address(address)
        if "house" not in parsed or "street" not in parsed:
            return json.dumps({"status": "error", "error": f"Could not parse address: {address}"})

        parts = [parsed["house"]]
        if parsed.get("direction"):
            parts.append(parsed["direction"])
        parts.append(parsed["street"])
        if parsed.get("suffix"):
            parts.append(parsed["suffix"])
        addr_prefix = " ".join(parts)
        # Escape single quotes to prevent SoQL injection
        safe_prefix = addr_prefix.replace("'", "''")

        # Step 1: Resolve to PIN via Cook County address dataset
        pin: Optional[str] = None
        for query_pattern in [
            f"prop_address_full='{safe_prefix}'",
            f"starts_with(prop_address_full, '{safe_prefix}')",
        ]:
            params = {
                "$where": query_pattern,
                "$select": "pin",
                "$order": "year DESC",
                "$limit": "1",
            }
            r = requests.get(_COOK_ADDR_URL, params=params, timeout=TOOL_TIMEOUT)
            r.raise_for_status()
            rows = r.json()
            if rows:
                pin = rows[0].get("pin")
                break

        if not pin:
            return json.dumps({
                "status": "not_found",
                "address": address,
                "building_sqft": 0.0,
                "county": county,
                "state": state,
                "error": "No parcel PIN found for this address in Cook County dataset",
            })

        # Step 2: Try residential characteristics
        r = requests.get(_COOK_RES_URL, params={
            "pin": pin,
            "$select": "char_bldg_sf,char_land_sf,char_yrblt,class",
            "$order": "year DESC",
            "$limit": "1",
        }, timeout=TOOL_TIMEOUT)
        r.raise_for_status()
        rows = r.json()
        if rows and rows[0]:
            row = rows[0]
            sqft = float(row.get("char_bldg_sf") or 0)
            if sqft > 0:
                return json.dumps({
                    "status": "ok",
                    "address": address,
                    "building_sqft": sqft,
                    "lot_size": str(int(float(row.get("char_land_sf") or 0))),
                    "zoning": "",
                    "property_class": row.get("class", ""),
                    "year_built": int(float(row.get("char_yrblt") or 0)),
                    "county": "Cook",
                    "state": state,
                    "pin": pin,
                    "source": "Cook County Residential Characteristics (Socrata)",
                })

        # Step 3: Try commercial valuation (Cook County PINs are 14 digits)
        dashed = f"{pin[:2]}-{pin[2:4]}-{pin[4:7]}-{pin[7:10]}-{pin[10:]}" if len(pin) == 14 else pin
        r = requests.get(_COOK_COMMERCIAL_URL, params={
            "keypin": dashed,
            "$select": "bldgsf,landsf,yearbuilt,property_type_use",
            "$order": "year DESC",
            "$limit": "1",
        }, timeout=TOOL_TIMEOUT)
        r.raise_for_status()
        rows = r.json()
        if rows and rows[0]:
            row = rows[0]
            sqft = float(row.get("bldgsf") or 0)
            if sqft > 0:
                return json.dumps({
                    "status": "ok",
                    "address": address,
                    "building_sqft": sqft,
                    "lot_size": str(int(float(row.get("landsf") or 0))),
                    "zoning": "",
                    "property_class": row.get("property_type_use", ""),
                    "year_built": int(float(row.get("yearbuilt") or 0)),
                    "county": "Cook",
                    "state": state,
                    "pin": pin,
                    "source": "Cook County Commercial Valuation (Socrata)",
                })

        # Step 4: Assessed values fallback (no sqft)
        r = requests.get(_COOK_ASSESSED_URL, params={
            "pin": pin,
            "$select": "class,mailed_bldg,mailed_tot",
            "$order": "year DESC",
            "$limit": "1",
        }, timeout=TOOL_TIMEOUT)
        r.raise_for_status()
        rows = r.json()
        row = rows[0] if rows else {}
        return json.dumps({
            "status": "ok",
            "address": address,
            "building_sqft": 0.0,
            "lot_size": "",
            "zoning": "",
            "property_class": row.get("class", ""),
            "year_built": 0,
            "county": "Cook",
            "state": state,
            "pin": pin,
            "assessed_building_value": float(row.get("mailed_bldg") or 0),
            "assessed_total_value": float(row.get("mailed_tot") or 0),
            "source": "Cook County Assessed Values (Socrata)",
            "note": "No building sqft found; assessed value may help estimate size ($100-150/sqft rule of thumb)",
        })

    except Exception as exc:
        return json.dumps({"status": "error", "address": address, "error": str(exc)})
