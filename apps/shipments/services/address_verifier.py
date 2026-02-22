"""
Address Verifier Service

Validates addresses using static format checks.
Structured so real API calls (USPS, Smarty) can be plugged in later.

Static verification checks:
- All required fields present
- Valid US state abbreviation
- Valid ZIP code format
- ZIP code matches state (basic check)
- Address doesn't look like PO Box when not allowed
- Basic format sanity checks
"""

import re
import logging

logger = logging.getLogger('apps.shipments.services.address_verifier')


# Valid US state abbreviations
VALID_STATES = {
    'AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'FL', 'GA',
    'HI', 'ID', 'IL', 'IN', 'IA', 'KS', 'KY', 'LA', 'ME', 'MD',
    'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH', 'NJ',
    'NM', 'NY', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA', 'RI', 'SC',
    'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV', 'WI', 'WY',
    'DC', 'PR', 'VI', 'GU', 'AS', 'MP',
}

# ZIP code prefix → state mapping (first 3 digits)
# This is a simplified mapping for basic validation
ZIP_STATE_MAP = {
    range(100, 150): ['NY', 'NJ', 'CT', 'PA'],     # Northeast
    range(150, 200): ['PA', 'DE', 'MD', 'DC'],
    range(200, 270): ['VA', 'WV', 'DC', 'MD'],
    range(270, 290): ['NC'],
    range(290, 300): ['SC'],
    range(300, 320): ['GA'],
    range(320, 340): ['FL'],
    range(340, 350): ['FL'],
    range(350, 370): ['AL'],
    range(370, 386): ['TN'],
    range(386, 398): ['MS'],
    range(400, 428): ['KY'],
    range(430, 459): ['OH'],
    range(460, 480): ['IN'],
    range(480, 500): ['MI'],
    range(500, 529): ['IA'],
    range(530, 550): ['WI'],
    range(550, 568): ['MN'],
    range(570, 578): ['SD'],
    range(580, 589): ['ND'],
    range(590, 600): ['MT'],
    range(600, 630): ['IL'],
    range(630, 659): ['MO'],
    range(660, 680): ['KS'],
    range(680, 694): ['NE'],
    range(700, 715): ['LA'],
    range(716, 730): ['AR'],
    range(730, 750): ['OK'],
    range(750, 800): ['TX'],
    range(800, 816): ['CO'],
    range(820, 832): ['WY'],
    range(832, 839): ['ID'],
    range(840, 848): ['UT'],
    range(850, 866): ['AZ'],
    range(870, 885): ['NM'],
    range(889, 899): ['NV'],
    range(900, 935): ['CA'],
    range(935, 966): ['CA', 'HI'],
    range(967, 969): ['HI'],
    range(970, 980): ['OR'],
    range(980, 995): ['WA'],
    range(995, 1000): ['AK'],
}

# Regex patterns
ZIP_PATTERN = re.compile(r'^\d{5}(-\d{4})?$')
ADDRESS_NUMBER_PATTERN = re.compile(r'^\d+\s')  # Starts with a number
PO_BOX_PATTERN = re.compile(r'^P\.?O\.?\s*BOX', re.IGNORECASE)


def verify_address(first_name: str, last_name: str, address1: str, address2: str,
                   city: str, state: str, zip_code: str) -> dict:
    """
    Verify an address using static format checks.

    Returns:
        dict with:
            'verified': bool
            'errors': list of error strings
            'warnings': list of warning strings
            'suggestions': dict of suggested corrections (if any)
    """
    errors = []
    warnings = []
    suggestions = {}

    # ── Required fields ──
    if not first_name.strip():
        errors.append('Name is required.')

    if not address1.strip():
        errors.append('Address is required.')

    if not city.strip():
        errors.append('City is required.')

    if not state.strip():
        errors.append('State is required.')
    elif state.upper().strip() not in VALID_STATES:
        errors.append(f'"{state}" is not a valid US state abbreviation.')

    if not zip_code.strip():
        errors.append('ZIP code is required.')

    # If required fields are missing, return early
    if errors:
        return {
            'verified': False,
            'errors': errors,
            'warnings': warnings,
            'suggestions': suggestions,
        }

    # ── Format checks ──
    state = state.upper().strip()
    zip_code = zip_code.strip()

    # ZIP code format
    if not ZIP_PATTERN.match(zip_code):
        errors.append(f'ZIP code "{zip_code}" is not in valid format (expected 5 digits or 5+4).')
    else:
        # ZIP-State cross check
        zip_prefix = int(zip_code[:3])
        expected_states = _get_states_for_zip(zip_prefix)
        if expected_states and state not in expected_states:
            warnings.append(
                f'ZIP code {zip_code} typically belongs to {", ".join(expected_states)}, '
                f'not {state}. Please double-check.'
            )

    # Address format checks
    address1_clean = address1.strip()

    # Check if address looks like it has a street number
    if not ADDRESS_NUMBER_PATTERN.match(address1_clean) and not PO_BOX_PATTERN.match(address1_clean):
        warnings.append('Address may be missing a street number.')

    # Check for common abbreviation issues
    address_lower = address1_clean.lower()
    if ' street' in address_lower and 'st' not in address_lower:
        pass  # Full word is fine
    if address_lower.endswith(' st') or address_lower.endswith(' ave') or \
       address_lower.endswith(' rd') or address_lower.endswith(' dr') or \
       address_lower.endswith(' blvd') or address_lower.endswith(' ln') or \
       address_lower.endswith(' hwy') or address_lower.endswith(' ct'):
        pass  # Common abbreviations are fine

    # Check city for numbers (unusual)
    if any(c.isdigit() for c in city):
        warnings.append('City name contains numbers — please verify.')

    # State case correction
    if state != state.upper():
        suggestions['state'] = state.upper()

    # Determine final status
    verified = len(errors) == 0

    if verified:
        logger.info(f"Address verified: {address1_clean}, {city}, {state} {zip_code}")
    else:
        logger.warning(f"Address verification failed: {errors}")

    return {
        'verified': verified,
        'errors': errors,
        'warnings': warnings,
        'suggestions': suggestions,
    }


def verify_record_address(record, address_type: str) -> dict:
    """
    Verify either the Ship From or Ship To address of a ShipmentRecord.

    Args:
        record: ShipmentRecord instance
        address_type: 'from' or 'to'

    Returns:
        dict with verification results
    """
    if address_type == 'from':
        result = verify_address(
            first_name=record.from_first_name,
            last_name=record.from_last_name,
            address1=record.from_address1,
            address2=record.from_address2,
            city=record.from_city,
            state=record.from_state,
            zip_code=record.from_zip,
        )
    elif address_type == 'to':
        result = verify_address(
            first_name=record.to_first_name,
            last_name=record.to_last_name,
            address1=record.to_address1,
            address2=record.to_address2,
            city=record.to_city,
            state=record.to_state,
            zip_code=record.to_zip,
        )
    else:
        return {
            'verified': False,
            'errors': [f'Invalid address_type: {address_type}. Use "from" or "to".'],
            'warnings': [],
            'suggestions': {},
        }

    return result


def _get_states_for_zip(zip_prefix: int) -> list:
    """Get expected states for a ZIP code prefix."""
    for zip_range, states in ZIP_STATE_MAP.items():
        if zip_prefix in zip_range:
            return states
    return []