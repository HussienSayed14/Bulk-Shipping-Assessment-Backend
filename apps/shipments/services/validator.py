"""
Validator Service

Validates shipment records and populates validation_errors field.
Runs both on upload (initial validation) and after edits (re-validation).
"""

import re
import logging

logger = logging.getLogger(__name__)


# Valid US state/territory abbreviations
VALID_STATES = {
    'AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'FL', 'GA',
    'HI', 'ID', 'IL', 'IN', 'IA', 'KS', 'KY', 'LA', 'ME', 'MD',
    'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH', 'NJ',
    'NM', 'NY', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA', 'RI', 'SC',
    'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV', 'WI', 'WY',
    'DC', 'PR', 'VI', 'GU', 'AS', 'MP',
}

# Regex for US zip codes: 5 digits or 5+4 format
ZIP_PATTERN = re.compile(r'^\d{5}(-\d{4})?$')


def validate_record(record) -> list:
    """
    Validate a ShipmentRecord model instance.
    Returns a list of error strings. Empty list = valid.

    Args:
        record: ShipmentRecord model instance (or dict with same keys)

    Returns:
        list of validation error strings
    """
    errors = []

    # Use getattr for model instances, .get() for dicts
    def get_val(key, default=''):
        if isinstance(record, dict):
            return record.get(key, default)
        return getattr(record, key, default)

    # ── Ship To validation (required) ──
    errors.extend(_validate_ship_to(get_val))

    # ── Ship From validation (required) ──
    errors.extend(_validate_ship_from(get_val))

    # ── Package validation (required) ──
    errors.extend(_validate_package(get_val))

    return errors


def _validate_ship_to(get_val) -> list:
    """Validate Ship To address fields."""
    errors = []

    if not get_val('to_first_name', '').strip():
        errors.append('Missing: Recipient first name')

    if not get_val('to_address1', '').strip():
        errors.append('Missing: Recipient address')

    if not get_val('to_city', '').strip():
        errors.append('Missing: Recipient city')

    # State validation
    to_state = get_val('to_state', '').strip().upper()
    if not to_state:
        errors.append('Missing: Recipient state')
    elif to_state not in VALID_STATES:
        errors.append(f'Invalid: Recipient state "{to_state}" is not a valid US state')

    # Zip validation
    to_zip = get_val('to_zip', '').strip()
    if not to_zip:
        errors.append('Missing: Recipient ZIP code')
    elif not ZIP_PATTERN.match(to_zip):
        errors.append(f'Invalid: Recipient ZIP code "{to_zip}" (expected 5 digits or 5+4 format)')

    return errors


def _validate_ship_from(get_val) -> list:
    """Validate Ship From address fields."""
    errors = []

    if not get_val('from_first_name', '').strip():
        errors.append('Missing: Sender name')

    if not get_val('from_address1', '').strip():
        errors.append('Missing: Sender address')

    if not get_val('from_city', '').strip():
        errors.append('Missing: Sender city')

    # State validation
    from_state = get_val('from_state', '').strip().upper()
    if not from_state:
        errors.append('Missing: Sender state')
    elif from_state not in VALID_STATES:
        errors.append(f'Invalid: Sender state "{from_state}" is not a valid US state')

    # Zip validation
    from_zip = get_val('from_zip', '').strip()
    if not from_zip:
        errors.append('Missing: Sender ZIP code')
    elif not ZIP_PATTERN.match(from_zip):
        errors.append(f'Invalid: Sender ZIP code "{from_zip}" (expected 5 digits or 5+4 format)')

    return errors


def _validate_package(get_val) -> list:
    """Validate package weight and dimensions."""
    errors = []

    # Weight - at least one must be > 0
    weight_lb = get_val('weight_lb', None)
    weight_oz = get_val('weight_oz', None)

    has_weight = False
    if weight_lb is not None and weight_lb > 0:
        has_weight = True
    if weight_oz is not None and weight_oz > 0:
        has_weight = True

    if not has_weight:
        errors.append('Missing: Package weight (lbs or oz required)')

    # Negative weight check
    if weight_lb is not None and weight_lb < 0:
        errors.append('Invalid: Weight (lbs) cannot be negative')
    if weight_oz is not None and weight_oz < 0:
        errors.append('Invalid: Weight (oz) cannot be negative')

    # Dimensions - all three required
    length = get_val('length', None)
    width = get_val('width', None)
    height = get_val('height', None)

    missing_dims = []
    if length is None or length <= 0:
        missing_dims.append('length')
    if width is None or width <= 0:
        missing_dims.append('width')
    if height is None or height <= 0:
        missing_dims.append('height')

    if len(missing_dims) == 3:
        errors.append('Missing: Package dimensions (length, width, height)')
    elif missing_dims:
        errors.append(f'Missing: Package {", ".join(missing_dims)}')

    return errors


def validate_and_update_record(record) -> None:
    """
    Validate a ShipmentRecord model instance and update its
    validation_errors and is_valid fields. Does NOT save.

    Args:
        record: ShipmentRecord model instance
    """
    errors = validate_record(record)
    record.validation_errors = errors
    record.is_valid = len(errors) == 0


def validate_records_bulk(records) -> dict:
    """
    Validate multiple ShipmentRecord instances.
    Updates each record's validation_errors and is_valid fields in place.
    Does NOT save.

    Args:
        records: queryset or list of ShipmentRecord instances

    Returns:
        dict with counts: {'total', 'valid', 'invalid'}
    """
    valid_count = 0
    invalid_count = 0

    for record in records:
        validate_and_update_record(record)
        if record.is_valid:
            valid_count += 1
        else:
            invalid_count += 1

    total = valid_count + invalid_count
    logger.info(f"Bulk validation complete: {valid_count}/{total} valid, {invalid_count}/{total} invalid")

    return {
        'total': total,
        'valid': valid_count,
        'invalid': invalid_count,
    }