"""
Address Verifier Service — 3-tier verification

Priority:
  1. USPS Address API (new REST API — free, apis.usps.com)
  2. Smarty (formerly SmartyStreets — 250 free/month)
  3. Static validation (format checks, ZIP-state cross-check)

If a tier fails (timeout, auth, rate limit), the next tier runs.
"""

import re
import logging
import time
import requests
from django.conf import settings

logger = logging.getLogger('apps.shipments.services.address_verifier')

VALID_STATES = {
    'AL','AK','AZ','AR','CA','CO','CT','DE','FL','GA','HI','ID','IL','IN',
    'IA','KS','KY','LA','ME','MD','MA','MI','MN','MS','MO','MT','NE','NV',
    'NH','NJ','NM','NY','NC','ND','OH','OK','OR','PA','RI','SC','SD','TN',
    'TX','UT','VT','VA','WA','WV','WI','WY','DC','PR','VI','GU','AS','MP',
}

ZIP_STATE_MAP = {
    range(100,150):['NY','NJ','CT','PA'], range(150,200):['PA','DE','MD','DC'],
    range(200,270):['VA','WV','DC','MD'], range(270,290):['NC'], range(290,300):['SC'],
    range(300,320):['GA'], range(320,350):['FL'], range(350,370):['AL'],
    range(370,386):['TN'], range(386,398):['MS'], range(400,428):['KY'],
    range(430,459):['OH'], range(460,480):['IN'], range(480,500):['MI'],
    range(500,529):['IA'], range(530,550):['WI'], range(550,568):['MN'],
    range(570,578):['SD'], range(580,589):['ND'], range(590,600):['MT'],
    range(600,630):['IL'], range(630,659):['MO'], range(660,680):['KS'],
    range(680,694):['NE'], range(700,715):['LA'], range(716,730):['AR'],
    range(730,750):['OK'], range(750,800):['TX'], range(800,816):['CO'],
    range(820,832):['WY'], range(832,839):['ID'], range(840,848):['UT'],
    range(850,866):['AZ'], range(870,885):['NM'], range(889,899):['NV'],
    range(900,935):['CA'], range(935,966):['CA','HI'], range(967,969):['HI'],
    range(970,980):['OR'], range(980,995):['WA'], range(995,1000):['AK'],
}

ZIP_PATTERN = re.compile(r'^\d{5}(-\d{4})?$')
ADDRESS_NUMBER_PATTERN = re.compile(r'^\d+\s')
PO_BOX_PATTERN = re.compile(r'^P\.?O\.?\s*BOX', re.IGNORECASE)
API_TIMEOUT = 8


def _result(verified, errors=None, warnings=None, suggestions=None, provider='static'):
    return {
        'verified': verified, 'errors': errors or [], 'warnings': warnings or [],
        'suggestions': suggestions or {}, 'provider': provider,
    }


# =============================================================================
# TIER 1: USPS REST API (apis.usps.com)
# =============================================================================

_usps_cache = {'token': None, 'expires': 0}


def _get_usps_token():
    cid = getattr(settings, 'USPS_CLIENT_ID', '')
    csec = getattr(settings, 'USPS_CLIENT_SECRET', '')
    if not cid or not csec:
        return None
    if _usps_cache['token'] and time.time() < _usps_cache['expires']:
        return _usps_cache['token']
    try:
        r = requests.post('https://apis.usps.com/oauth2/v3/token',
            json={'client_id': cid, 'client_secret': csec, 'grant_type': 'client_credentials'},
            headers={'Content-Type': 'application/json'}, timeout=API_TIMEOUT)
        r.raise_for_status()
        d = r.json()
        _usps_cache['token'] = d['access_token']
        _usps_cache['expires'] = time.time() + int(d.get('expires_in', 3600)) - 60
        logger.info('USPS OAuth token acquired')
        return _usps_cache['token']
    except Exception as e:
        logger.warning(f'USPS token failed: {e}')
        return None


def _verify_usps(address1, address2, city, state, zip_code):
    token = _get_usps_token()
    if not token:
        return None
    try:
        params = {'streetAddress': address1.strip(), 'city': city.strip(),
                  'state': state.strip().upper()}
        if address2 and address2.strip():
            params['secondaryAddress'] = address2.strip()
        if zip_code and zip_code.strip():
            params['ZIPCode'] = zip_code.strip()[:5]

        r = requests.get('https://apis.usps.com/addresses/v3/address', params=params,
            headers={'Authorization': f'Bearer {token}', 'Accept': 'application/json'},
            timeout=API_TIMEOUT)

        if r.status_code == 200:
            addr = r.json().get('address', {})
            suggestions = {}
            warnings = []

            std_street = addr.get('streetAddress', '')
            std_city = addr.get('city', '')
            std_state = addr.get('state', '')
            std_zip = addr.get('ZIPCode', '')
            std_zip4 = addr.get('ZIPPlus4', '')

            if std_street and std_street.upper() != address1.strip().upper():
                suggestions['address1'] = std_street
            if std_city and std_city.upper() != city.strip().upper():
                suggestions['city'] = std_city
            if std_state and std_state != state.strip().upper():
                suggestions['state'] = std_state
            if std_zip and std_zip != zip_code.strip()[:5]:
                suggestions['zip'] = std_zip
            if std_zip4:
                suggestions['zip_plus4'] = f'{std_zip}-{std_zip4}'

            if suggestions:
                warnings.append('USPS suggested corrections — review the suggested fields.')

            logger.info(f'USPS verified: {std_street}, {std_city}, {std_state} {std_zip}')
            return _result(True, warnings=warnings, suggestions=suggestions, provider='usps')

        elif r.status_code in (400, 404):
            err = r.json() if r.text else {}
            msg = (err.get('error', {}).get('message', '')
                   or err.get('message', 'Address not found in USPS database.'))
            logger.info(f'USPS not found: {msg}')
            return _result(False, errors=[f'USPS: {msg}'], provider='usps')
        else:
            logger.warning(f'USPS status {r.status_code}')
            return None

    except (requests.Timeout, requests.ConnectionError) as e:
        logger.warning(f'USPS connection issue: {e}')
        return None
    except Exception as e:
        logger.warning(f'USPS error: {e}')
        return None


# =============================================================================
# TIER 2: SMARTY (formerly SmartyStreets)
# =============================================================================

def _verify_smarty(address1, address2, city, state, zip_code):
    auth_id = getattr(settings, 'SMARTY_AUTH_ID', '')
    auth_token = getattr(settings, 'SMARTY_AUTH_TOKEN', '')
    if not auth_id or not auth_token:
        return None

    try:
        params = {
            'auth-id': auth_id, 'auth-token': auth_token,
            'street': address1.strip(), 'city': city.strip(),
            'state': state.strip().upper(),
            'zipcode': zip_code.strip()[:5] if zip_code else '',
            'candidates': 1, 'match': 'enhanced',
        }
        if address2 and address2.strip():
            params['secondary'] = address2.strip()

        r = requests.get('https://us-street.api.smarty.com/street-address',
                         params=params, timeout=API_TIMEOUT)

        if r.status_code == 200:
            results = r.json()
            if not results:
                logger.info(f'Smarty: not found — {address1}, {city}, {state}')
                return _result(False,
                    errors=['Address not found — may not be a deliverable US address.'],
                    provider='smarty')

            c = results[0]
            comp = c.get('components', {})
            analysis = c.get('analysis', {})
            meta = c.get('metadata', {})

            dpv = analysis.get('dpv_match_code', '')
            dpv_fn = analysis.get('dpv_footnotes', '')

            suggestions = {}
            warnings = []
            errors = []

            dl1 = c.get('delivery_line_1', '')
            if dl1 and dl1.upper() != address1.strip().upper():
                suggestions['address1'] = dl1
            if comp.get('city_name', '').upper() != city.strip().upper():
                suggestions['city'] = comp.get('city_name', '')
            if comp.get('state_abbreviation', '') != state.strip().upper():
                suggestions['state'] = comp.get('state_abbreviation', '')

            zc = comp.get('zipcode', '')
            p4 = comp.get('plus4_code', '')
            if zc and zc != zip_code.strip()[:5]:
                suggestions['zip'] = zc
            if p4:
                suggestions['zip_plus4'] = f'{zc}-{p4}'

            if dpv == 'Y':
                verified = True
                if suggestions:
                    warnings.append('Smarty corrected the address — see suggestions.')
            elif dpv == 'S':
                verified = True
                warnings.append('Address valid but may need a unit/suite number.')
            elif dpv == 'D':
                verified = False
                errors.append('Street matched but the specific number could not be confirmed.')
            else:
                verified = False
                errors.append('Address could not be verified as deliverable.')

            if 'BB' in dpv_fn:
                warnings.append('The street number is not valid for this route.')
            if 'CC' in dpv_fn:
                warnings.append('Secondary info (apt/suite) does not match.')
            if 'N1' in dpv_fn:
                warnings.append('A secondary designator (apt, suite) is required.')

            rdi = meta.get('rdi', '')
            if rdi == 'Commercial':
                warnings.append('This is a commercial address.')
            if analysis.get('dpv_vacant', '') == 'Y':
                warnings.append('Address is flagged as vacant by USPS.')

            logger.info(f'Smarty verified={verified} dpv={dpv}: {dl1}')
            return _result(verified, errors=errors, warnings=warnings,
                           suggestions=suggestions, provider='smarty')

        elif r.status_code in (401, 402):
            logger.warning(f'Smarty auth/billing error: {r.status_code}')
            return None
        else:
            logger.warning(f'Smarty status {r.status_code}')
            return None

    except (requests.Timeout, requests.ConnectionError) as e:
        logger.warning(f'Smarty connection issue: {e}')
        return None
    except Exception as e:
        logger.warning(f'Smarty error: {e}')
        return None


# =============================================================================
# TIER 3: STATIC VALIDATION
# =============================================================================

def _verify_static(first_name, address1, address2, city, state, zip_code):
    errors = []
    warnings = []
    suggestions = {}

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

    if errors:
        return _result(False, errors, warnings, suggestions, 'static')

    state = state.upper().strip()
    zip_code = zip_code.strip()

    if not ZIP_PATTERN.match(zip_code):
        errors.append(f'ZIP code "{zip_code}" is not valid format.')
    else:
        pfx = int(zip_code[:3])
        exp = _get_states_for_zip(pfx)
        if exp and state not in exp:
            warnings.append(f'ZIP {zip_code} typically belongs to {", ".join(exp)}, not {state}.')

    addr = address1.strip()
    if not ADDRESS_NUMBER_PATTERN.match(addr) and not PO_BOX_PATTERN.match(addr):
        warnings.append('Address may be missing a street number.')
    if any(c.isdigit() for c in city):
        warnings.append('City name contains numbers — please verify.')

    warnings.append('Verified by format checks only (external APIs unavailable).')
    return _result(len(errors) == 0, errors, warnings, suggestions, 'static')


def _get_states_for_zip(pfx):
    for r, states in ZIP_STATE_MAP.items():
        if pfx in r:
            return states
    return []


# =============================================================================
# MAIN ENTRY POINTS
# =============================================================================

def verify_address(first_name, last_name, address1, address2,
                   city, state, zip_code):
    """
    Verify a US address: USPS → Smarty → Static.
    Returns dict: verified, errors, warnings, suggestions, provider
    """
    # Pre-check required fields
    if not address1 or not address1.strip():
        return _result(False, ['Address is required.'])
    if not city or not city.strip():
        return _result(False, ['City is required.'])
    if not state or not state.strip():
        return _result(False, ['State is required.'])
    if not zip_code or not zip_code.strip():
        return _result(False, ['ZIP code is required.'])

    # Tier 1: USPS
    logger.debug(f'Trying USPS: {address1}, {city}, {state} {zip_code}')
    res = _verify_usps(address1, address2, city, state, zip_code)
    if res is not None:
        logger.info(f'USPS result: verified={res["verified"]}')
        return res

    # Tier 2: Smarty
    logger.debug(f'Trying Smarty: {address1}, {city}, {state} {zip_code}')
    res = _verify_smarty(address1, address2, city, state, zip_code)
    if res is not None:
        logger.info(f'Smarty result: verified={res["verified"]}')
        return res

    # Tier 3: Static
    logger.debug(f'Falling back to static: {address1}, {city}, {state}')
    res = _verify_static(first_name or '', address1, address2 or '', city, state, zip_code)
    logger.info(f'Static result: verified={res["verified"]}')
    return res


def verify_record_address(record, address_type):
    """Verify Ship From or Ship To address of a ShipmentRecord."""
    if address_type == 'from':
        return verify_address(
            record.from_first_name, record.from_last_name,
            record.from_address1, record.from_address2,
            record.from_city, record.from_state, record.from_zip)
    elif address_type == 'to':
        return verify_address(
            record.to_first_name, record.to_last_name,
            record.to_address1, record.to_address2,
            record.to_city, record.to_state, record.to_zip)
    else:
        return _result(False, [f'Invalid address_type: {address_type}. Use "from" or "to".'])