# 📦 Bulk Shipping Label Platform — Backend API

A Django REST API for bulk shipping label creation. Upload a CSV of shipment records, review and edit them, verify addresses against real USPS/Smarty APIs, select shipping services, and purchase labels — all through a clean REST interface.

---

## Overview

This platform streamlines the process of creating shipping labels in bulk. Instead of entering addresses one by one, users upload a CSV file containing up to hundreds of shipment records, then use the wizard-style workflow to clean, validate, and purchase labels.

**Core workflow:**

```
Upload CSV → Review & Edit → Verify Addresses → Select Shipping → Purchase Labels
```

**Key capabilities:**

- CSV parsing with intelligent name splitting (handles "Salina Dixon", "C/O Simoneau" formats)
- Real-time record validation with detailed error messages
- Bulk operations — apply a saved address or package preset to hundreds of records at once
- 3-tier address verification: USPS REST API → Smarty (SmartyStreets) → static fallback
- Shipping rate calculation with Ground and Priority Mail options
- Balance-based purchasing with transaction history
- Interactive API documentation via Swagger UI

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Framework** | Django 5.x + Django REST Framework |
| **Auth** | JWT via `djangorestframework-simplejwt` |
| **Database** | SQLite (development) — swap to PostgreSQL for production |
| **API Docs** | `drf-spectacular` (OpenAPI 3.0 / Swagger UI / ReDoc) |
| **Address Verification** | USPS REST API, Smarty (SmartyStreets), static fallback |
| **Filtering** | `django-filter` with search and ordering |
| **Config** | `python-decouple` for environment variables |
| **HTTP Client** | `requests` (for external API calls) |
| **CORS** | `django-cors-headers` |

---

## Project Structure

```
backend/
├── config/
│   ├── settings.py          # Main settings (DRF, JWT, CORS, logging, API keys)
│   ├── urls.py              # Root URL configuration
│   ├── wsgi.py
│   └── asgi.py
├── apps/
│   ├── users/               # Auth, login, user profile, balance
│   │   ├── models.py        # UserProfile (extends User with balance + company)
│   │   ├── serializers.py
│   │   ├── views.py         # login, token refresh, /me endpoint
│   │   └── urls.py
│   ├── addresses/            # Saved ship-from addresses (CRUD)
│   │   ├── models.py        # SavedAddress
│   │   ├── serializers.py
│   │   ├── views.py
│   │   └── urls.py
│   ├── packages/             # Saved package presets (CRUD)
│   │   ├── models.py        # SavedPackage (dimensions + weight)
│   │   ├── serializers.py
│   │   ├── views.py
│   │   └── urls.py
│   ├── shipments/            # Core — batches, records, bulk actions
│   │   ├── models.py        # ShipmentBatch, ShipmentRecord
│   │   ├── serializers.py
│   │   ├── views.py         # Upload, CRUD, bulk ops, verify, rates, purchase
│   │   ├── urls.py
│   │   └── services/
│   │       ├── csv_parser.py        # CSV parsing + name splitting
│   │       ├── validator.py         # Record validation engine
│   │       ├── rate_calculator.py   # Shipping cost calculation
│   │       └── address_verifier.py  # 3-tier address verification
│   └── billing/              # Transaction records
│       ├── models.py        # Transaction (purchase, top-up, refund)
│       └── urls.py
├── logs/                     # Rotating log files (auto-created)
├── manage.py
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
└── .env                      # Environment variables (not committed)
```

---

## API Documentation (Swagger)

Once the server is running, interactive API docs are available at:

| URL | Description |
|-----|-------------|
| **`http://127.0.0.1:8000/api/docs/`** | **Swagger UI** — interactive, test endpoints directly in the browser |
| `http://127.0.0.1:8000/api/redoc/` | ReDoc — clean read-only documentation |
| `http://127.0.0.1:8000/api/schema/` | Raw OpenAPI 3.0 JSON schema |
| `http://127.0.0.1:8000/admin/` | Django admin panel |

### How to authenticate in Swagger

1. Open `/api/docs/`
2. Find **POST `/api/auth/login/`** → click "Try it out"
3. Enter your credentials and execute
4. Copy the `access` token from the response
5. Click the **🔒 Authorize** button at the top of the page
6. Paste: `Bearer <your_token>` and click Authorize
7. All endpoints are now authenticated — test freely

---

## Setup — Local (Python)

### Prerequisites

- Python 3.10+
- pip

### 1. Clone the repository

```bash
git clone https://github.com/HussienSayed14/Bulk-Shipping-Assessment-Backend.git
cd Bulk-Shipping-Assessment-Backend
```

### 2. Create a virtual environment

```bash
python -m venv venv
source venv/bin/activate        # macOS / Linux
venv\Scripts\activate           # Windows
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Create the `.env` file

Create a `.env` file in the `backend/` root:

```env
# Django
SECRET_KEY=your-secret-key-change-this-in-production
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

# CORS — frontend URLs
CORS_ALLOWED_ORIGINS=http://localhost:5173,http://localhost:3000

# Address Verification APIs (optional — falls back to static checks)
# USPS REST API (free): https://developers.usps.com
USPS_CLIENT_ID=
USPS_CLIENT_SECRET=

# Smarty / SmartyStreets (250 free/month): https://www.smarty.com/pricing
SMARTY_AUTH_ID=
SMARTY_AUTH_TOKEN=
```

> **Tip:** Generate a secret key with: `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"`

### 5. Run migrations

```bash
python manage.py migrate
```

### 6. Create a superuser

```bash
python manage.py createsuperuser
```

### 7. (Optional) Set up test data

Go to `http://127.0.0.1:8000/admin/` and:

- Create a **UserProfile** for your superuser with a starting balance (e.g., $500)
- Add a few **Saved Addresses** (your ship-from locations)
- Add a few **Saved Packages** (common package sizes)

### 8. Start the development server

```bash
python manage.py runserver
```

The API is now live at `http://127.0.0.1:8000/api/` and Swagger docs at `http://127.0.0.1:8000/api/docs/`.

---

## Setup — Docker

### Prerequisites

- Docker
- Docker Compose

### 1. Clone the repository

```bash
git clone https://github.com/HussienSayed14/Bulk-Shipping-Assessment-Backend.git
cd Bulk-Shipping-Assessment-Backend
```

### 2. Create the `.env` file

Same as above — create a `.env` file in `backend/` with your settings.

### 3. Create the Dockerfile

If not already present, create `Dockerfile`:

```dockerfile
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project
COPY . .

# Create logs directory
RUN mkdir -p logs

# Collect static files
RUN python manage.py collectstatic --noinput 2>/dev/null || true

EXPOSE 8000

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
```

### 4. Create docker-compose.yml

```yaml
version: "3.8"

services:
  backend:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - .:/app
      - ./db.sqlite3:/app/db.sqlite3
    env_file:
      - .env
    environment:
      - DEBUG=True
    command: >
      sh -c "python manage.py migrate &&
             python manage.py runserver 0.0.0.0:8000"
```

### 5. Build and run

```bash
docker-compose up --build
```

### 6. Create a superuser (first time only)

In a separate terminal:

```bash
docker-compose exec backend python manage.py createsuperuser
```

### 7. Access the app

- **API:** `http://localhost:8000/api/`
- **Swagger UI:** `http://localhost:8000/api/docs/`
- **Admin:** `http://localhost:8000/admin/`

---

## API Endpoints

### Authentication

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/auth/login/` | Login with username/password, returns JWT tokens |
| POST | `/api/auth/refresh/` | Refresh an expired access token |
| GET | `/api/auth/me/` | Get current user profile and balance |

### Saved Addresses

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/saved-addresses/` | List all saved addresses |
| POST | `/api/saved-addresses/create/` | Create a new saved address |
| GET | `/api/saved-addresses/<id>/` | Get a specific address |
| PATCH | `/api/saved-addresses/<id>/update/` | Update an address |
| DELETE | `/api/saved-addresses/<id>/delete/` | Delete an address |

### Saved Packages

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/saved-packages/` | List all saved packages |
| POST | `/api/saved-packages/create/` | Create a new package preset |
| GET | `/api/saved-packages/<id>/` | Get a specific package |
| PATCH | `/api/saved-packages/<id>/update/` | Update a package |
| DELETE | `/api/saved-packages/<id>/delete/` | Delete a package |

### Batches

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/batches/` | List all batches |
| POST | `/api/batches/upload/` | Upload a CSV file to create a batch |
| GET | `/api/batches/<id>/` | Get batch details |
| DELETE | `/api/batches/<id>/delete/` | Delete a batch (draft only) |
| POST | `/api/batches/<id>/calculate-rates/` | Calculate shipping rates for a batch |
| POST | `/api/batches/<id>/purchase/` | Purchase labels for a batch |

### Shipment Records

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/batches/<id>/shipments/` | List records (supports `?filter=`, `?search=`, `?verification=`) |
| GET | `/api/shipments/<id>/` | Get a single record |
| PATCH | `/api/shipments/<id>/update/` | Update a record |
| DELETE | `/api/shipments/<id>/delete/` | Delete a record |

### Bulk Actions

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/batches/<id>/shipments/bulk-update-from/` | Apply a saved address as Ship From |
| POST | `/api/batches/<id>/shipments/bulk-update-package/` | Apply a saved package preset |
| POST | `/api/batches/<id>/shipments/bulk-update-shipping/` | Change shipping service |
| POST | `/api/batches/<id>/shipments/bulk-delete/` | Delete multiple records |
| POST | `/api/batches/<id>/shipments/bulk-verify/` | Verify addresses in bulk |

### Address Verification

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/shipments/<id>/verify/<from\|to>/` | Verify a single address |
| POST | `/api/batches/<id>/shipments/bulk-verify/` | Bulk verify (body: `address_type`: from/to/both) |

### Shipping Rates

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/shipping-rates/` | List available shipping services and pricing |

---

## Address Verification

The system uses a 3-tier fallback chain for address verification:

```
Request → USPS REST API → Smarty (SmartyStreets) → Static Validation
             ✓ return        ✗ timeout/error           ✗ both failed
                                  ✓ return               ✓ always returns
```

**Tier 1 — USPS REST API** (Primary, free, unlimited)
- Standardizes addresses against the official USPS database
- Returns corrected street, city, state, and ZIP+4
- Register at [developers.usps.com](https://developers.usps.com)

**Tier 2 — Smarty** (Fallback, 250 free/month)
- DPV-level validation (confirms deliverability)
- Detects vacant addresses, commercial vs residential, missing unit numbers
- Register at [smarty.com/pricing](https://www.smarty.com/pricing)

**Tier 3 — Static Validation** (Final fallback)
- Format checks: required fields, valid state abbreviation, ZIP format
- ZIP-to-state cross-check (flags mismatches)
- Always returns a result, even when external APIs are unavailable

Every verification response includes a `provider` field indicating which tier was used.

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `SECRET_KEY` | Yes | Django secret key |
| `DEBUG` | No | `True` for development (default: `False`) |
| `ALLOWED_HOSTS` | No | Comma-separated hostnames |
| `CORS_ALLOWED_ORIGINS` | No | Comma-separated frontend URLs |
| `USPS_CLIENT_ID` | No | USPS REST API client ID |
| `USPS_CLIENT_SECRET` | No | USPS REST API client secret |
| `SMARTY_AUTH_ID` | No | Smarty auth ID |
| `SMARTY_AUTH_TOKEN` | No | Smarty auth token |

---

## Logging

Logs are written to the `logs/` directory with automatic rotation:

| Log File | Contents |
|----------|----------|
| `app.log` | General application logs |
| `error.log` | Error-level events only |
| `api.log` | API request/response logs |
| `address_verification.log` | All address verification activity |

---