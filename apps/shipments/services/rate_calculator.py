"""
Rate Calculator Service

Calculates shipping costs based on package weight and selected service.
Uses simple pricing model that can be swapped for real API later.
"""

import logging
from decimal import Decimal, ROUND_HALF_UP

logger = logging.getLogger(__name__)


# Pricing table
RATES = {
    'priority': {
        'name': 'Priority Mail',
        'base_price': Decimal('5.00'),
        'per_oz_rate': Decimal('0.10'),
    },
    'ground': {
        'name': 'Ground Shipping',
        'base_price': Decimal('2.50'),
        'per_oz_rate': Decimal('0.05'),
    },
}


def get_available_services() -> list:
    """Return list of available shipping services with pricing info."""
    return [
        {
            'key': key,
            'name': rate['name'],
            'base_price': float(rate['base_price']),
            'per_oz_rate': float(rate['per_oz_rate']),
        }
        for key, rate in RATES.items()
    ]


def calculate_cost(weight_lb: int, weight_oz: int, service: str) -> Decimal:
    """
    Calculate shipping cost for a single shipment.

    Args:
        weight_lb: Weight in pounds
        weight_oz: Weight in ounces (additional)
        service: Service key ('priority' or 'ground')

    Returns:
        Decimal cost rounded to 2 decimal places
    """
    if service not in RATES:
        logger.warning(f"Unknown shipping service: {service}")
        return Decimal('0.00')

    rate = RATES[service]

    # Convert to total ounces
    total_oz = ((weight_lb or 0) * 16) + (weight_oz or 0)

    if total_oz <= 0:
        # Minimum charge = base price
        return rate['base_price']

    cost = rate['base_price'] + (Decimal(str(total_oz)) * rate['per_oz_rate'])
    return cost.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def calculate_cost_for_record(record) -> Decimal:
    """
    Calculate shipping cost for a ShipmentRecord instance.

    Args:
        record: ShipmentRecord model instance

    Returns:
        Decimal cost
    """
    if not record.shipping_service:
        return Decimal('0.00')

    return calculate_cost(
        weight_lb=record.weight_lb or 0,
        weight_oz=record.weight_oz or 0,
        service=record.shipping_service,
    )


def get_cheapest_service(weight_lb: int, weight_oz: int) -> dict:
    """
    Find the cheapest shipping service for given weight.

    Returns:
        dict with 'service' key and 'cost'
    """
    cheapest = None
    cheapest_cost = None

    for key in RATES:
        cost = calculate_cost(weight_lb, weight_oz, key)
        if cheapest_cost is None or cost < cheapest_cost:
            cheapest = key
            cheapest_cost = cost

    return {
        'service': cheapest,
        'cost': cheapest_cost,
    }


def get_rates_for_record(record) -> list:
    """
    Get all available rates for a shipment record.

    Args:
        record: ShipmentRecord instance

    Returns:
        list of dicts with service info and calculated cost
    """
    weight_lb = record.weight_lb or 0
    weight_oz = record.weight_oz or 0

    rates = []
    for key, rate_info in RATES.items():
        cost = calculate_cost(weight_lb, weight_oz, key)
        rates.append({
            'key': key,
            'name': rate_info['name'],
            'cost': float(cost),
        })

    return rates