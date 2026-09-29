import os
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()

def get_connection():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME", "udboss_ledger"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", "postgres")
    )

def set_tenant_context(cursor, tenant_id):
    """Enforces PostgreSQL Row-Level Security (RLS) context for the transaction."""
    cursor.execute("SELECT set_config('app.current_tenant_id', %s, true);", (tenant_id,))

# --- 1. PESSIMISTIC LOCKING (SELECT ... FOR UPDATE) ---
def allocate_pessimistic(sku: str, tenant_id: str, qty_to_allocate: int) -> dict:
    """
    Locks the row at read time using FOR UPDATE to prevent race conditions.
    Other transactions trying to access this row will wait until this commits.
    """
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            set_tenant_context(cur, tenant_id)

            # Lock the target row exclusively
            cur.execute("""
                SELECT id, sku, quantity_on_hand, allocated_quantity
                FROM inventory_batches
                WHERE sku = %s
                FOR UPDATE;
            """, (sku,))
            batch = cur.fetchone()

            if not batch:
                return {"status": "ERROR", "message": f"SKU {sku} not found for tenant"}

            available = batch['quantity_on_hand'] - batch['allocated_quantity']
            if available < qty_to_allocate:
                return {"status": "FAILED", "message": f"Insufficient stock. Requested: {qty_to_allocate}, Available: {available}"}

            # Update allocation within locked transaction
            cur.execute("""
                UPDATE inventory_batches
                SET allocated_quantity = allocated_quantity + %s
                WHERE sku = %s;
            """, (qty_to_allocate, sku))

            conn.commit()
            return {"status": "SUCCESS", "allocated": qty_to_allocate, "method": "PESSIMISTIC"}
    except Exception as e:
        conn.rollback()
        return {"status": "ERROR", "message": str(e)}
    finally:
        conn.close()

# --- 2. OPTIMISTIC CONCURRENCY CONTROL (OCC) ---
def allocate_optimistic(sku: str, tenant_id: str, qty_to_allocate: int) -> dict:
    """
    Does NOT lock the row on read. Uses version counters to detect conflicts on write.
    If another transaction updated the row in the meantime, the version check fails.
    """
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            set_tenant_context(cur, tenant_id)

            # Read record without locking
            cur.execute("""
                SELECT id, sku, quantity_on_hand, allocated_quantity, version
                FROM inventory_batches
                WHERE sku = %s;
            """, (sku,))
            batch = cur.fetchone()

            if not batch:
                return {"status": "ERROR", "message": f"SKU {sku} not found for tenant"}

            available = batch['quantity_on_hand'] - batch['allocated_quantity']
            if available < qty_to_allocate:
                return {"status": "FAILED", "message": f"Insufficient stock. Requested: {qty_to_allocate}, Available: {available}"}

            current_version = batch['version']

            # Conditional update: only succeeds if version matches current state
            cur.execute("""
                UPDATE inventory_batches
                SET allocated_quantity = allocated_quantity + %s,
                    version = version + 1
                WHERE sku = %s AND version = %s;
            """, (qty_to_allocate, sku, current_version))

            if cur.rowcount == 0:
                conn.rollback()
                return {"status": "CONFLICT", "message": "Concurrency conflict! Row was updated by another transaction."}

            conn.commit()
            return {"status": "SUCCESS", "allocated": qty_to_allocate, "new_version": current_version + 1, "method": "OPTIMISTIC"}
    except Exception as e:
        conn.rollback()
        return {"status": "ERROR", "message": str(e)}
    finally:
        conn.close()