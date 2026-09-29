# High-Performance Database Concurrency & Multi-Tenant Ledger

A production-grade Python and PostgreSQL backend implementation demonstrating state consistency, race condition prevention, and multi-tenant isolation under high concurrent write loads.

## 📌 Features & Architecture

- **Pessimistic Locking (`SELECT ... FOR UPDATE`)**: Guarantees zero race conditions during peak contention by acquiring explicit row-level exclusive locks at transaction start.
- **Optimistic Concurrency Control (OCC)**: High-throughput concurrency handling using version counters (`version = version + 1`) to detect stale writes without acquiring read locks.
- **Multi-Tenant Row-Level Security (RLS)**: Database-enforced isolation policy using `current_setting('app.current_tenant_id')` to ensure tenant data never leaks across queries.
- **Hard Database Constraints**: SQL-level invariants (`CHECK quantity_on_hand >= 0` and `CHECK allocated_quantity <= quantity_on_hand`) acting as the ultimate defense against inventory overselling.

---

## 🛠️ Tech Stack

- **Language**: Python 3.x
- **Database**: PostgreSQL
- **Driver**: `psycopg2-binary`
- **Configuration**: `python-dotenv`

---

## 📂 Repository Structure

```text
Concurrency-row-control/
├── schema.sql           # Database tables, RLS policies, check constraints, and seed data
├── inventory_service.py # Core transaction handlers (Pessimistic & OCC)
├── test_concurrency.py  # ThreadPoolExecutor multithreaded stress test harness
├── requirements.txt     # Python dependencies
├── .env                 # Local database connection credentials (git-ignored)
└── README.md            # Technical documentation
```

---

## 🧪 Concurrency Benchmarks

When subjecting a single inventory SKU to 10 simultaneous allocation requests via Python's `ThreadPoolExecutor`:

### 1. Pessimistic Locking Results
- **Success Rate**: `10/10` (100%)
- **Behavior**: Requests were serialized strictly at the database row level. Zero race conditions, zero missed allocations.
- **Best For**: High-contention inventory, payment ledgers, limited-edition sales.

### 2. Optimistic Concurrency Control (OCC) Results
- **Success Rate**: `1/10` (First valid write committed, 9 flagged as `OCC CONFLICT`)
- **Behavior**: Requests read data concurrently without waiting. The first commit bumped the version from `1` to `2`; all subsequent writes failed version checks cleanly.
- **Best For**: Read-heavy workloads, distributed systems, low-contention operations.

---

## 🚀 Getting Started

### 1. Prerequisites
- Python 3.10+
- PostgreSQL instance running locally

### 2. Environment Setup
Clone the repository and install dependencies inside a virtual environment:

```powershell
# Create and activate virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install requirements
pip install -r requirements.txt
```

Create a `.env` file in the root directory:

```env
DB_HOST=localhost
DB_PORT=5432
DB_NAME=udboss_ledger
DB_USER=postgres
DB_PASSWORD=your_password_here
```

### 3. Database Initialization
Create the database in PostgreSQL and run `schema.sql`:

```powershell
psql -U postgres -d udboss_ledger -f schema.sql
```

### 4. Running Concurrency Stress Tests

```powershell
python test_concurrency.py
```