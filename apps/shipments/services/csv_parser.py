"""
CSV Parser Service

Handles parsing the uploaded CSV file, mapping columns to model fields,
and cleaning up messy data (e.g., full names in first_name field).
"""

import csv
import io
import re
import logging

logger = logging.getLogger(__name__)


# Column index mapping from the CSV template
COLUMN_MAP = {
    0: 'from_first_name',
    1: 'from_last_name',
    2: 'from_address1',
    3: 'from_address2',
    4: 'from_city',
    5: 'from_zip',
    6: 'from_state',
    7: 'to_first_name',
    8: 'to_last_name',
    9: 'to_address1',
    10: 'to_address2',
    11: 'to_city',
    12: 'to_zip',
    13: 'to_state',
    14: 'weight_lb',
    15: 'weight_oz',
    16: 'length',
    17: 'width',
    18: 'height',
    19: 'from_phone',
    20: 'to_phone',
    21: 'order_number',
    22: 'item_sku',
}

# Number of header rows to skip in the template
HEADER_ROWS = 2


def parse_csv(file) -> dict:
    """
    Parse an uploaded CSV file and return structured shipment data.

    Args:
        file: Django UploadedFile or file-like object

    Returns:
        dict with 'records' (list of dicts) and 'errors' (list of parse-level errors)
    """
    records = []
    parse_errors = []

    try:
        # Read the file content
        if hasattr(file, 'read'):
            content = file.read()
            if isinstance(content, bytes):
                content = content.decode('utf-8-sig')  # Handle BOM
        else:
            content = str(file)

        reader = csv.reader(io.StringIO(content))
        all_rows = list(reader)

        logger.info(f"CSV loaded: {len(all_rows)} total rows (including {HEADER_ROWS} header rows)")

        if len(all_rows) <= HEADER_ROWS:
            parse_errors.append('CSV file has no data rows (only headers found).')
            return {'records': [], 'errors': parse_errors}

        # Skip header rows
        data_rows = all_rows[HEADER_ROWS:]

        for row_idx, row in enumerate(data_rows):
            row_number = row_idx + HEADER_ROWS + 1  # 1-based, accounting for headers

            # Skip completely empty rows
            if not any(cell.strip() for cell in row):
                continue

            try:
                record = _parse_row(row, row_number)
                records.append(record)
            except Exception as e:
                parse_errors.append(f"Row {row_number}: Failed to parse - {str(e)}")
                logger.error(f"Failed to parse row {row_number}: {e}")

        logger.info(f"Successfully parsed {len(records)} records, {len(parse_errors)} parse errors")

    except UnicodeDecodeError:
        parse_errors.append('File encoding not supported. Please save as UTF-8 CSV.')
        logger.error("CSV encoding error")
    except csv.Error as e:
        parse_errors.append(f'Invalid CSV format: {str(e)}')
        logger.error(f"CSV format error: {e}")
    except Exception as e:
        parse_errors.append(f'Unexpected error reading file: {str(e)}')
        logger.error(f"Unexpected CSV parse error: {e}")

    return {'records': records, 'errors': parse_errors}


def _parse_row(row: list, row_number: int) -> dict:
    """
    Parse a single CSV row into a shipment record dict.
    Handles name splitting and data cleaning.
    """
    record = {'row_number': row_number}

    for col_idx, field_name in COLUMN_MAP.items():
        value = ''
        if col_idx < len(row):
            value = row[col_idx].strip()
        record[field_name] = value# type: ignore

    # ── Clean up names ──
    # The CSV often has full names in the first_name field with last_name empty.
    # e.g., "Salina Dixon" in first_name, "" in last_name
    # e.g., "John Fradley C|O Simoneau" in first_name

    record['from_first_name'], record['from_last_name'] = _split_name(
        record.get('from_first_name', ''),# type: ignore
        record.get('from_last_name', ''),# type: ignore
    )

    record['to_first_name'], record['to_last_name'] = _split_name(
        record.get('to_first_name', ''),# type: ignore
        record.get('to_last_name', ''),# type: ignore
    )

    # ── Clean up care-of (C/O, C|O) notations ──
    # Move "C/O Name" or "C|O Name" to address2 if address2 is empty
    for prefix in ['to', 'from']:
        first_key = f'{prefix}_first_name'
        last_key = f'{prefix}_last_name'
        addr2_key = f'{prefix}_address2'

        full_name = f"{record[first_key]} {record[last_key]}".strip()
        care_of, cleaned_name = _extract_care_of(full_name)

        if care_of:
            # Put the care-of in address2 if it's empty, otherwise prepend
            if not record[addr2_key]:
                record[addr2_key] = care_of
            else:
                record[addr2_key] = f"{care_of}, {record[addr2_key]}"# type: ignore

            # Re-split the cleaned name
            parts = cleaned_name.strip().split(None, 1)
            record[first_key] = parts[0] if parts else '' # type: ignore
            record[last_key] = parts[1] if len(parts) > 1 else ''# type: ignore

    # ── Clean numeric fields ──
    record['weight_lb'] = _parse_int(record.get('weight_lb', ''))# type: ignore
    record['weight_oz'] = _parse_int(record.get('weight_oz', ''))# type: ignore
    record['length'] = _parse_decimal(record.get('length', ''))# type: ignore
    record['width'] = _parse_decimal(record.get('width', ''))# type: ignore
    record['height'] = _parse_decimal(record.get('height', ''))# type: ignore

    # ── Clean zip codes ──
    record['from_zip'] = _clean_zip(record.get('from_zip', ''))# type: ignore
    record['to_zip'] = _clean_zip(record.get('to_zip', ''))# type: ignore

    # ── Clean state abbreviations ──
    record['from_state'] = record.get('from_state', '').upper().strip()# type: ignore
    record['to_state'] = record.get('to_state', '').upper().strip()# type: ignore

    # ── Clean phone numbers ──
    record['from_phone'] = _clean_phone(record.get('from_phone', ''))# type: ignore
    record['to_phone'] = _clean_phone(record.get('to_phone', ''))# type: ignore

    return record


def _split_name(first_name: str, last_name: str) -> tuple:
    """
    If last_name is empty and first_name contains a full name, split them.

    Examples:
        ("Salina Dixon", "") → ("Salina", "Dixon")
        ("John Fradley C|O Simoneau", "") → ("John", "Fradley C|O Simoneau")
        ("Salina", "Dixon") → ("Salina", "Dixon")  # no change
    """
    first_name = first_name.strip()
    last_name = last_name.strip()

    # If last_name already has a value, don't touch it
    if last_name:
        return first_name, last_name

    # If first_name has multiple words, split on first space
    if ' ' in first_name:
        parts = first_name.split(None, 1)
        return parts[0], parts[1]

    return first_name, last_name


def _extract_care_of(name: str) -> tuple:
    """
    Extract C/O or C|O notation from a name string.

    Examples:
        "John Fradley C|O Simoneau" → ("C/O Simoneau", "John Fradley")
        "Jane C/O Smith" → ("C/O Smith", "Jane")
        "Regular Name" → ("", "Regular Name")

    Returns:
        (care_of_string, remaining_name)
    """
    # Match C/O, C|O, c/o, c|o followed by the rest
    pattern = r'\s+(C[/|]O\s+.+)$'
    match = re.search(pattern, name, re.IGNORECASE)

    if match:
        care_of = match.group(1).strip()
        # Normalize C|O to C/O
        care_of = re.sub(r'C\|O', 'C/O', care_of, flags=re.IGNORECASE)
        remaining = name[:match.start()].strip()
        return care_of, remaining

    return '', name


def _parse_int(value: str):
    """Parse string to integer, return None if empty or invalid."""
    if not value or not value.strip():
        return None
    try:
        return int(float(value.strip()))
    except (ValueError, TypeError):
        return None


def _parse_decimal(value: str):
    """Parse string to decimal, return None if empty or invalid."""
    if not value or not value.strip():
        return None
    try:
        return round(float(value.strip()), 2)
    except (ValueError, TypeError):
        return None


def _clean_zip(value: str) -> str:
    """
    Clean zip code formatting.
    Accepts: 28466, 28466-9087, 028466
    """
    value = value.strip()
    if not value:
        return ''

    # Remove any non-alphanumeric except hyphen
    value = re.sub(r'[^\d-]', '', value)
    return value


def _clean_phone(value: str) -> str:
    """Clean phone number - keep digits, hyphens, parentheses, plus, spaces."""
    value = value.strip()
    if not value:
        return ''

    # Remove everything except digits, hyphens, parens, plus, spaces
    value = re.sub(r'[^\d\-\(\)\+\s]', '', value)
    return value