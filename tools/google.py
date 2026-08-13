import json
import re
import requests
import streamlit as st
from typing import Optional

from core.config import TOOL_TIMEOUT
from core.utils import _google_key

def geocode_address(address: str) -> str:
    """Convert a street address to geographic coordinates (latitude/longitude).

    Args:
        address: Full street address to geocode
    """
    if not address:
        return json.dumps({"status": "error", "error": "address is required"})

    api_key = _google_key()
    if not api_key:
        return json.dumps({
            "status": "no_key",
            "address": address,
            "note": "No Google Maps API key configured. Geocoding unavailable.",
        })

    try:
        r = requests.get(
            "https://maps.googleapis.com/maps/api/geocode/json",
            params={"address": address, "key": api_key},
            timeout=TOOL_TIMEOUT,
        )
        r.raise_for_status()
        payload = r.json()
        status = payload.get("status", "").upper()
        if status == "REQUEST_DENIED":
            return json.dumps({"status": "error", "error": payload.get("error_message", "Request denied")})
        results = payload.get("results", [])
        if not results:
            return json.dumps({"status": "not_found", "address": address})
        loc = results[0]["geometry"]["location"]
        return json.dumps({
            "status": "ok",
            "address": address,
            "formatted_address": results[0].get("formatted_address"),
            "lat": loc.get("lat"),
            "lng": loc.get("lng"),
        })
    except Exception as exc:
        return json.dumps({"status": "error", "address": address, "error": str(exc)})


def get_street_view(address: str) -> str:
    """Capture Google Street View images of a location (4 angles: N/E/S/W).

    Returns image metadata. Images are stored in Streamlit session state and displayed after the investigation.

    Args:
        address: Street address to photograph
    """
    if not address:
        return json.dumps({"status": "error", "error": "address is required"})

    api_key = _google_key()
    if not api_key:
        return json.dumps({
            "status": "no_key",
            "address": address,
            "note": "No Google Maps API key. Street View unavailable.",
        })

    headings = [0, 90, 180, 270]
    images = []
    try:
        for heading in headings:
            params = {
                "location": address,
                "heading": heading,
                "size": "640x480",
                "key": api_key,
            }
            # Check metadata first
            meta_r = requests.get(
                "https://maps.googleapis.com/maps/api/streetview/metadata",
                params={**params, "return_error_codes": True},
                timeout=TOOL_TIMEOUT,
            )
            meta = meta_r.json()
            meta_status = meta.get("status", "").upper()
            if meta_status == "REQUEST_DENIED":
                return json.dumps({"status": "error", "error": meta.get("error_message", "Street View denied")})
            if meta_status != "OK":
                # ZERO_RESULTS = no imagery at this location; skip this heading
                continue

            img_r = requests.get(
                "https://maps.googleapis.com/maps/api/streetview",
                params=params,
                timeout=TOOL_TIMEOUT,
            )
            img_r.raise_for_status()
            images.append({
                "heading": heading,
                "capture_date": meta.get("date", "unknown"),
                "status": meta_status,
                "image_bytes": img_r.content,
            })

        if not images:
            return json.dumps({"status": "no_imagery", "address": address, "note": "No Street View imagery available for this address."})

        # Store raw image bytes in session state for Streamlit display.
        # Return only metadata to the LLM (base64 blobs are opaque text to the model
        # and would consume megabytes of context for a 10-provider investigation).
        cache = st.session_state.setdefault("street_view_cache", {})
        cache[address] = [
            {"heading": img["heading"], "capture_date": img["capture_date"], "image_bytes": img["image_bytes"]}
            for img in images
        ]

        return json.dumps({
            "status": "ok",
            "address": address,
            "images_captured": len(images),
            "capture_date": images[0].get("capture_date", "unknown"),
            "note": "Street View images captured. They will be displayed in the Surelock UI below the investigation narration.",
        })
    except Exception as exc:
        return json.dumps({"status": "error", "address": address, "error": str(exc)})


def get_places_info(address: str, name: str = "") -> str:
    """Get Google Places data for an address: business type, operating status, rating, and reviews.

    Args:
        address: Street address to look up
        name: Business or provider name to improve match accuracy (recommended)
    """
    if not address:
        return json.dumps({"status": "error", "error": "address is required"})

    api_key = _google_key()
    if not api_key:
        return json.dumps({
            "status": "no_key",
            "address": address,
            "note": "No Google Maps API key. Places lookup unavailable.",
        })

    try:
        # Build query plan — search by name first for best accuracy
        query_plan = []
        if name:
            query_plan.append((f"{name.strip()} {address}", False))
            query_plan.append((name.strip(), False))
        query_plan += [
            (f"childcare {address}", True),
            (f"day care {address}", True),
            (address, False),
        ]

        place_id: Optional[str] = None
        for query, require_childcare in query_plan:
            r = requests.get(
                "https://maps.googleapis.com/maps/api/place/findplacefromtext/json",
                params={"input": query, "inputtype": "textquery", "fields": "place_id,name,types", "key": api_key},
                timeout=TOOL_TIMEOUT,
            )
            r.raise_for_status()
            payload = r.json()
            candidates = payload.get("candidates", [])
            for c in candidates:
                if require_childcare:
                    types_str = " ".join(str(t) for t in c.get("types", []))
                    name_str = str(c.get("name", ""))
                    combined = (types_str + " " + name_str).lower()
                    if not any(t in combined for t in ("daycare", "day care", "child", "preschool", "school")):
                        continue
                place_id = c.get("place_id")
                break
            if place_id:
                break

        if not place_id:
            return json.dumps({
                "status": "no_place",
                "address": address,
                "note": "No Google Places listing found for this address.",
            })

        # Get full details
        detail_r = requests.get(
            "https://maps.googleapis.com/maps/api/place/details/json",
            params={
                "place_id": place_id,
                "fields": "name,business_status,rating,user_ratings_total,types,reviews,formatted_address",
                "key": api_key,
            },
            timeout=TOOL_TIMEOUT,
        )
        detail_r.raise_for_status()
        detail = detail_r.json().get("result", {})

        # Validate house number match
        expected_house = re.search(r"\b(\d+)\b", address or "")
        formatted = detail.get("formatted_address", "")
        if expected_house and formatted:
            if not re.search(rf"\b{re.escape(expected_house.group(1))}\b", formatted):
                return json.dumps({
                    "status": "address_mismatch",
                    "address": address,
                    "note": f"Place result address '{formatted}' doesn't match expected street number.",
                })

        reviews = [
            {"author": rv.get("author_name"), "rating": rv.get("rating"), "text": rv.get("text", "")[:200]}
            for rv in detail.get("reviews", [])[:3]
        ]

        return json.dumps({
            "status": "ok",
            "address": address,
            "place_name": detail.get("name"),
            "formatted_address": formatted,
            "business_type": ", ".join(detail.get("types", [])),
            "operating_status": detail.get("business_status"),
            "rating": detail.get("rating"),
            "review_count": detail.get("user_ratings_total", 0),
            "recent_reviews": reviews,
        })

    except Exception as exc:
        return json.dumps({"status": "error", "address": address, "error": str(exc)})
