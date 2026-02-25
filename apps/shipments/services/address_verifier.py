"""
Address Verifier Service — 3-tier verification

Priority:
  1. USPS Address API (new REST API — apis.usps.com)
  2. Smarty (formerly SmartyStreets)
  3. Static validation (format checks, ZIP-state cross-check)

Logging goals:
- Trace a single verification end-to-end via trace_id
- Log timing, status codes, and short response snippets
- Never leak secrets (client_secret, auth-token, bearer token)
"""

import re
import uuid
import logging
import time
import requests
from django.conf import settings

logger = logging.getLogger("apps.shipments.services.address_verifier")

VALID_STATES = {
    "AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID","IL","IN",
    "IA","KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV",
    "NH","NJ","NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN",
    "TX","UT","VT","VA","WA","WV","WI","WY","DC","PR","VI","GU","AS","MP",
}

ZIP_STATE_MAP = {
    range(100,150):["NY","NJ","CT","PA"], range(150,200):["PA","DE","MD","DC"],
    range(200,270):["VA","WV","DC","MD"], range(270,290):["NC"], range(290,300):["SC"],
    range(300,320):["GA"], range(320,350):["FL"], range(350,370):["AL"],
    range(370,386):["TN"], range(386,398):["MS"], range(400,428):["KY"],
    range(430,459):["OH"], range(460,480):["IN"], range(480,500):["MI"],
    range(500,529):["IA"], range(530,550):["WI"], range(550,568):["MN"],
    range(570,578):["SD"], range(580,589):["ND"], range(590,600):["MT"],
    range(600,630):["IL"], range(630,659):["MO"], range(660,680):["KS"],
    range(680,694):["NE"], range(700,715):["LA"], range(716,730):["AR"],
    range(730,750):["OK"], range(750,800):["TX"], range(800,816):["CO"],
    range(820,832):["WY"], range(832,839):["ID"], range(840,848):["UT"],
    range(850,866):["AZ"], range(870,885):["NM"], range(889,899):["NV"],
    range(900,935):["CA"], range(935,966):["CA","HI"], range(967,969):["HI"],
    range(970,980):["OR"], range(980,995):["WA"], range(995,1000):["AK"],
}

ZIP_PATTERN = re.compile(r"^\d{5}(-\d{4})?$")
ADDRESS_NUMBER_PATTERN = re.compile(r"^\d+\s")
PO_BOX_PATTERN = re.compile(r"^P\.?O\.?\s*BOX", re.IGNORECASE)

API_TIMEOUT = 8
RESP_SNIPPET_LEN = 700

USPS_TOKEN_URL = "https://apis.usps.com/oauth2/v3/token"
USPS_VERIFY_URL = "https://apis.usps.com/addresses/v3/address"
SMARTY_URL = "https://us-street.api.smarty.com/street-address"

_usps_cache = {"token": None, "expires": 0}


def _result(verified, errors=None, warnings=None, suggestions=None, provider="static"):
    return {
        "verified": verified,
        "errors": errors or [],
        "warnings": warnings or [],
        "suggestions": suggestions or {},
        "provider": provider,
    }


def _mask(s: str, keep: int = 4) -> str:
    """Mask secrets for logs."""
    if not s:
        return ""
    if len(s) <= keep:
        return "*" * len(s)
    return s[:keep] + "*" * (len(s) - keep)


def _safe_snippet(text: str) -> str:
    if not text:
        return ""
    return text[:RESP_SNIPPET_LEN]


def _safe_params_for_log(params: dict) -> dict:
    """Avoid logging long / sensitive fields."""
    safe = dict(params or {})
    if "secondaryAddress" in safe and safe["secondaryAddress"]:
        safe["secondaryAddress"] = str(safe["secondaryAddress"])[:40]
    if "streetAddress" in safe and safe["streetAddress"]:
        safe["streetAddress"] = str(safe["streetAddress"])[:60]
    return safe


# =============================================================================
# TIER 1: USPS REST API (apis.usps.com)
# =============================================================================

def _get_usps_token(trace_id: str | None = None) -> str | None:
    cid = getattr(settings, "USPS_CLIENT_ID", "") or ""
    csec = getattr(settings, "USPS_CLIENT_SECRET", "") or ""

    if not cid or not csec:
        logger.warning("[%s] USPS creds missing (USPS_CLIENT_ID/USPS_CLIENT_SECRET)", trace_id)
        return None

    # Cache hit
    if _usps_cache["token"] and time.time() < _usps_cache["expires"]:
        logger.debug("[%s] USPS token cache hit (ttl=%ds)", trace_id, int(_usps_cache["expires"] - time.time()))
        return _usps_cache["token"]

    payload = {"client_id": cid, "client_secret": csec, "grant_type": "client_credentials"}
    headers = {"Content-Type": "application/json"}

    logger.debug("[%s] USPS token request url=%s client_id=%s", trace_id, USPS_TOKEN_URL, _mask(cid, 6))

    try:
        t0 = time.time()
        r = requests.post(USPS_TOKEN_URL, json=payload, headers=headers, timeout=API_TIMEOUT)
        took_ms = int((time.time() - t0) * 1000)

        logger.info("[%s] USPS token response status=%s took_ms=%d", trace_id, r.status_code, took_ms)

        if r.status_code >= 400:
            logger.warning("[%s] USPS token failed status=%s body=%s",
                           trace_id, r.status_code, _safe_snippet(r.text))
            return None

        d = r.json() if r.text else {}
        token = d.get("access_token")
        if not token:
            logger.warning("[%s] USPS token missing access_token body=%s", trace_id, str(d)[:RESP_SNIPPET_LEN])
            return None

        expires_in = int(d.get("expires_in", 3600))
        _usps_cache["token"] = token
        _usps_cache["expires"] = time.time() + expires_in - 60

        logger.info("[%s] USPS token acquired expires_in=%ds", trace_id, expires_in)
        return token

    except (requests.Timeout, requests.ConnectionError) as e:
        logger.warning("[%s] USPS token connection issue: %s", trace_id, repr(e))
        return None
    except Exception:
        logger.exception("[%s] USPS token unexpected error", trace_id)
        return None


def _verify_usps(address1, address2, city, state, zip_code, trace_id: str | None = None):
    token = _get_usps_token(trace_id=trace_id)
    if not token:
        logger.info("[%s] USPS skipped (no token)", trace_id)
        return None

    params = {
        "streetAddress": (address1 or "").strip(),
        "city": (city or "").strip(),
        "state": (state or "").strip().upper(),
    }
    if address2 and address2.strip():
        params["secondaryAddress"] = address2.strip()
    if zip_code and zip_code.strip():
        params["ZIPCode"] = zip_code.strip()[:5]

    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

    logger.debug("[%s] USPS verify request url=%s params=%s", trace_id, USPS_VERIFY_URL, _safe_params_for_log(params))

    try:
        t0 = time.time()
        r = requests.get(USPS_VERIFY_URL, params=params, headers=headers, timeout=API_TIMEOUT)
        took_ms = int((time.time() - t0) * 1000)

        logger.info("[%s] USPS verify response status=%s took_ms=%d", trace_id, r.status_code, took_ms)

        if r.status_code != 200:
            logger.warning("[%s] USPS verify non-200 status=%s body=%s",
                           trace_id, r.status_code, _safe_snippet(r.text))

            # Treat as "real result" (no fallback) when USPS says not found / bad request
            if r.status_code in (400, 404):
                err = r.json() if r.text else {}
                msg = (
                    (err.get("error", {}) or {}).get("message", "")
                    or err.get("message", "")
                    or "Address not found in USPS database."
                )
                return _result(False, errors=[f"USPS: {msg}"], provider="usps")

            # Auth/rate-limit/server errors => fallback to next tier
            return None

        data = r.json() if r.text else {}
        addr = data.get("address", {}) if isinstance(data, dict) else {}

        suggestions = {}
        warnings = []

        std_street = addr.get("streetAddress", "") or ""
        std_city = addr.get("city", "") or ""
        std_state = addr.get("state", "") or ""
        std_zip = addr.get("ZIPCode", "") or ""
        std_zip4 = addr.get("ZIPPlus4", "") or ""

        # Compare & suggest standardized values
        if std_street and std_street.upper() != (address1 or "").strip().upper():
            suggestions["address1"] = std_street
        if std_city and std_city.upper() != (city or "").strip().upper():
            suggestions["city"] = std_city
        if std_state and std_state != (state or "").strip().upper():
            suggestions["state"] = std_state
        if std_zip and std_zip != (zip_code or "").strip()[:5]:
            suggestions["zip"] = std_zip
        if std_zip4 and std_zip:
            suggestions["zip_plus4"] = f"{std_zip}-{std_zip4}"

        if suggestions:
            warnings.append("USPS suggested corrections — review the suggested fields.")

        logger.info("[%s] USPS verified ok standardized=%s", trace_id, {
            "street": std_street[:60],
            "city": std_city,
            "state": std_state,
            "zip": std_zip,
        })

        return _result(True, warnings=warnings, suggestions=suggestions, provider="usps")

    except (requests.Timeout, requests.ConnectionError) as e:
        logger.warning("[%s] USPS verify connection issue: %s", trace_id, repr(e))
        return None
    except Exception:
        logger.exception("[%s] USPS verify unexpected error", trace_id)
        return None


# =============================================================================
# TIER 2: SMARTY
# =============================================================================

def _verify_smarty(address1, address2, city, state, zip_code, trace_id: str | None = None):
    auth_id = getattr(settings, "SMARTY_AUTH_ID", "") or ""
    auth_token = getattr(settings, "SMARTY_AUTH_TOKEN", "") or ""
    if not auth_id or not auth_token:
        logger.info("[%s] Smarty skipped (missing SMARTY_AUTH_ID/SMARTY_AUTH_TOKEN)", trace_id)
        return None

    params = {
        "auth-id": auth_id,
        "auth-token": auth_token,
        "street": (address1 or "").strip(),
        "city": (city or "").strip(),
        "state": (state or "").strip().upper(),
        "zipcode": (zip_code or "").strip()[:5] if zip_code else "",
        "candidates": 1,
        "match": "enhanced",
    }
    if address2 and address2.strip():
        params["secondary"] = address2.strip()

    # Don't log auth-token; we can log auth-id masked
    safe_log = {
        "auth-id": _mask(auth_id, 6),
        "street": params["street"][:60],
        "city": params["city"],
        "state": params["state"],
        "zipcode": params["zipcode"],
        "secondary": (params.get("secondary", "") or "")[:40],
    }
    logger.debug("[%s] Smarty request url=%s params=%s", trace_id, SMARTY_URL, safe_log)

    try:
        t0 = time.time()
        r = requests.get(SMARTY_URL, params=params, timeout=API_TIMEOUT)
        took_ms = int((time.time() - t0) * 1000)

        logger.info("[%s] Smarty response status=%s took_ms=%d", trace_id, r.status_code, took_ms)

        if r.status_code == 200:
            results = r.json() if r.text else []
            if not results:
                logger.info("[%s] Smarty not found: %s, %s, %s", trace_id, address1, city, state)
                return _result(
                    False,
                    errors=["Address not found — may not be a deliverable US address."],
                    provider="smarty",
                )

            c = results[0]
            comp = c.get("components", {}) or {}
            analysis = c.get("analysis", {}) or {}
            meta = c.get("metadata", {}) or {}

            dpv = analysis.get("dpv_match_code", "") or ""
            dpv_fn = analysis.get("dpv_footnotes", "") or ""

            suggestions, warnings, errors = {}, [], []

            dl1 = c.get("delivery_line_1", "") or ""

            if dl1 and dl1.upper() != (address1 or "").strip().upper():
                suggestions["address1"] = dl1
            if (comp.get("city_name", "") or "").upper() != (city or "").strip().upper():
                suggestions["city"] = comp.get("city_name", "") or ""
            if (comp.get("state_abbreviation", "") or "") != (state or "").strip().upper():
                suggestions["state"] = comp.get("state_abbreviation", "") or ""

            zc = comp.get("zipcode", "") or ""
            p4 = comp.get("plus4_code", "") or ""
            if zc and zc != (zip_code or "").strip()[:5]:
                suggestions["zip"] = zc
            if p4 and zc:
                suggestions["zip_plus4"] = f"{zc}-{p4}"

            if dpv == "Y":
                verified = True
                if suggestions:
                    warnings.append("Smarty corrected the address — see suggestions.")
            elif dpv == "S":
                verified = True
                warnings.append("Address valid but may need a unit/suite number.")
            elif dpv == "D":
                verified = False
                errors.append("Street matched but the specific number could not be confirmed.")
            else:
                verified = False
                errors.append("Address could not be verified as deliverable.")

            if "BB" in dpv_fn:
                warnings.append("The street number is not valid for this route.")
            if "CC" in dpv_fn:
                warnings.append("Secondary info (apt/suite) does not match.")
            if "N1" in dpv_fn:
                warnings.append("A secondary designator (apt, suite) is required.")

            rdi = meta.get("rdi", "") or ""
            if rdi == "Commercial":
                warnings.append("This is a commercial address.")
            if analysis.get("dpv_vacant", "") == "Y":
                warnings.append("Address is flagged as vacant by USPS.")

            logger.info("[%s] Smarty verified=%s dpv=%s delivery_line_1=%s", trace_id, verified, dpv, dl1[:80])

            return _result(
                verified,
                errors=errors,
                warnings=warnings,
                suggestions=suggestions,
                provider="smarty",
            )

        # Auth/billing/rate limits -> fallback
        logger.warning("[%s] Smarty non-200 status=%s body=%s", trace_id, r.status_code, _safe_snippet(r.text))
        if r.status_code in (401, 402, 429):
            return None

        return None

    except (requests.Timeout, requests.ConnectionError) as e:
        logger.warning("[%s] Smarty connection issue: %s", trace_id, repr(e))
        return None
    except Exception:
        logger.exception("[%s] Smarty unexpected error", trace_id)
        return None


# =============================================================================
# TIER 3: STATIC VALIDATION
# =============================================================================

def _get_states_for_zip(pfx: int):
    for r, states in ZIP_STATE_MAP.items():
        if pfx in r:
            return states
    return []


def _verify_static(first_name, address1, address2, city, state, zip_code):
    errors, warnings, suggestions = [], [], {}

    if not (first_name or "").strip():
        errors.append("Name is required.")
    if not (address1 or "").strip():
        errors.append("Address is required.")
    if not (city or "").strip():
        errors.append("City is required.")
    if not (state or "").strip():
        errors.append("State is required.")
    elif state.upper().strip() not in VALID_STATES:
        errors.append(f'"{state}" is not a valid US state abbreviation.')
    if not (zip_code or "").strip():
        errors.append("ZIP code is required.")

    if errors:
        return _result(False, errors, warnings, suggestions, "static")

    state = state.upper().strip()
    zip_code = zip_code.strip()

    if not ZIP_PATTERN.match(zip_code):
        errors.append(f'ZIP code "{zip_code}" is not valid format.')
    else:
        try:
            pfx = int(zip_code[:3])
            exp = _get_states_for_zip(pfx)
            if exp and state not in exp:
                warnings.append(f'ZIP {zip_code} typically belongs to {", ".join(exp)}, not {state}.')
        except Exception:
            warnings.append("ZIP prefix check failed — please verify ZIP.")

    addr = address1.strip()
    if not ADDRESS_NUMBER_PATTERN.match(addr) and not PO_BOX_PATTERN.match(addr):
        warnings.append("Address may be missing a street number.")
    if any(c.isdigit() for c in city):
        warnings.append("City name contains numbers — please verify.")

    warnings.append("Verified by format checks only (external APIs unavailable).")
    return _result(len(errors) == 0, errors, warnings, suggestions, "static")


# =============================================================================
# MAIN ENTRY POINTS
# =============================================================================

def verify_address(first_name, last_name, address1, address2, city, state, zip_code):
    """
    Verify a US address: USPS → Smarty → Static.
    Returns dict: verified, errors, warnings, suggestions, provider
    """
    trace_id = uuid.uuid4().hex[:10]
    start = time.time()

    def _finish(res):
        logger.info(
            "[%s] verify_address done provider=%s verified=%s took_ms=%d",
            trace_id,
            res.get("provider"),
            res.get("verified"),
            int((time.time() - start) * 1000),
        )
        return res

    # Pre-check required fields
    if not address1 or not address1.strip():
        return _finish(_result(False, ["Address is required."]))
    if not city or not city.strip():
        return _finish(_result(False, ["City is required."]))
    if not state or not state.strip():
        return _finish(_result(False, ["State is required."]))
    if not zip_code or not zip_code.strip():
        return _finish(_result(False, ["ZIP code is required."]))

    logger.debug("[%s] Input address city/state/zip=%s/%s/%s", trace_id, city.strip(), state.strip(), zip_code.strip()[:10])

    # Tier 1: USPS
    logger.debug("[%s] Trying USPS", trace_id)
    res = _verify_usps(address1, address2, city, state, zip_code, trace_id=trace_id)
    if res is not None:
        logger.info("[%s] USPS result verified=%s", trace_id, res.get("verified"))
        return _finish(res)

    # Tier 2: Smarty
    logger.debug("[%s] Trying Smarty", trace_id)
    res = _verify_smarty(address1, address2, city, state, zip_code, trace_id=trace_id)
    if res is not None:
        logger.info("[%s] Smarty result verified=%s", trace_id, res.get("verified"))
        return _finish(res)

    # Tier 3: Static
    logger.debug("[%s] Falling back to static", trace_id)
    res = _verify_static(first_name or "", address1, address2 or "", city, state, zip_code)
    logger.info("[%s] Static result verified=%s", trace_id, res.get("verified"))
    return _finish(res)


def verify_record_address(record, address_type):
    """Verify Ship From or Ship To address of a ShipmentRecord."""
    if address_type == "from":
        return verify_address(
            record.from_first_name,
            record.from_last_name,
            record.from_address1,
            record.from_address2,
            record.from_city,
            record.from_state,
            record.from_zip,
        )
    if address_type == "to":
        return verify_address(
            record.to_first_name,
            record.to_last_name,
            record.to_address1,
            record.to_address2,
            record.to_city,
            record.to_state,
            record.to_zip,
        )
    return _result(False, [f'Invalid address_type: {address_type}. Use "from" or "to".'])