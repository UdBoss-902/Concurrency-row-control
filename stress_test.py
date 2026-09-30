import time
import random
import concurrent.futures
from inventory_service import allocate_pessimistic, allocate_optimistic, get_connection

SKU_SINGLE = "SKU-STRESS-001"
TENANT = "tenant_alpha"

def seed_stress_db():
    """Seeds database with stock for both single-SKU and multi-SKU scenarios."""
    conn = get_connection()
    with conn.cursor() as cur:
        # Clear existing stress data
        cur.execute("DELETE FROM inventory_batches WHERE sku LIKE 'SKU-STRESS-%';")
        
        # 1. Single SKU with 50 items for ultra-high contention test
        cur.execute("""
            INSERT INTO inventory_batches (sku, tenant_id, quantity_on_hand, allocated_quantity, version)
            VALUES (%s, %s, 50, 0, 1);
        """, (SKU_SINGLE, TENANT))

        # 2. 50 distinct SKUs with 10 items each for low contention test
        for i in range(1, 51):
            sku_name = f"SKU-STRESS-{i:03d}"
            if sku_name != SKU_SINGLE:
                cur.execute("""
                    INSERT INTO inventory_batches (sku, tenant_id, quantity_on_hand, allocated_quantity, version)
                    VALUES (%s, %s, 10, 0, 1);
                """, (sku_name, TENANT))

        conn.commit()
    conn.close()

def allocate_optimistic_with_retry(sku: str, tenant_id: str, qty: int, max_retries=5) -> dict:
    """Executes OCC with exponential backoff and random jitter."""
    for attempt in range(max_retries):
        res = allocate_optimistic(sku, tenant_id, qty)
        if res["status"] != "CONFLICT":
            return res
        # Exponential backoff: 5ms, 10ms, 20ms... + random jitter
        sleep_time = (0.005 * (2 ** attempt)) + random.uniform(0.001, 0.005)
        time.sleep(sleep_time)
    return {"status": "MAX_RETRIES_EXCEEDED", "message": "Failed after max backoff attempts"}

# --- BENCHMARK RUNNERS ---

def run_high_contention_pessimistic(threads=500):
    print(f"\n[1/4] Running High-Contention Pessimistic Test ({threads} threads -> 1 SKU with 50 stock)...")
    seed_stress_db()
    
    start_time = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=threads) as executor:
        futures = [executor.submit(allocate_pessimistic, SKU_SINGLE, TENANT, 1) for _ in range(threads)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]
    elapsed = time.perf_counter() - start_time

    successes = sum(1 for r in results if r["status"] == "SUCCESS")
    failures = sum(1 for r in results if r["status"] == "FAILED")

    print(f"  ➜ Duration:           {elapsed:.3f} seconds")
    print(f"  ➜ Successful Stock:   {successes}/50 allocated")
    print(f"  ➜ Graceful Rejections:{failures} (out of stock)")

def run_high_contention_occ_no_retry(threads=500):
    print(f"\n[2/4] Running High-Contention OCC (No Retry) ({threads} threads -> 1 SKU with 50 stock)...")
    seed_stress_db()

    start_time = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=threads) as executor:
        futures = [executor.submit(allocate_optimistic, SKU_SINGLE, TENANT, 1) for _ in range(threads)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]
    elapsed = time.perf_counter() - start_time

    successes = sum(1 for r in results if r["status"] == "SUCCESS")
    conflicts = sum(1 for r in results if r["status"] == "CONFLICT")

    print(f"  ➜ Duration:           {elapsed:.3f} seconds")
    print(f"  ➜ Successful Stock:   {successes}")
    print(f"  ➜ Stale Conflicts:    {conflicts} (rejected due to version collision)")

def run_high_contention_occ_with_retry(threads=500):
    print(f"\n[3/4] Running High-Contention OCC (With Exponential Backoff Retry) ({threads} threads)...")
    seed_stress_db()

    start_time = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=threads) as executor:
        futures = [executor.submit(allocate_optimistic_with_retry, SKU_SINGLE, TENANT, 1) for _ in range(threads)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]
    elapsed = time.perf_counter() - start_time

    successes = sum(1 for r in results if r["status"] == "SUCCESS")
    retries_exceeded = sum(1 for r in results if r["status"] == "MAX_RETRIES_EXCEEDED")

    print(f"  ➜ Duration:           {elapsed:.3f} seconds")
    print(f"  ➜ Successful Stock:   {successes}/50 allocated after retries")
    print(f"  ➜ Exhausted Retries:  {retries_exceeded}")

def run_low_contention_occ(threads=500):
    print(f"\n[4/4] Running Low-Contention OCC Test ({threads} threads distributed over 50 SKUs)...")
    seed_stress_db()

    # Evenly assign 500 threads across 50 different SKUs (10 workers per SKU)
    sku_list = [f"SKU-STRESS-{((i % 50) + 1):03d}" for i in range(threads)]

    start_time = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=threads) as executor:
        futures = [executor.submit(allocate_optimistic, sku_list[i], TENANT, 1) for i in range(threads)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]
    elapsed = time.perf_counter() - start_time

    successes = sum(1 for r in results if r["status"] == "SUCCESS")
    conflicts = sum(1 for r in results if r["status"] == "CONFLICT")

    print(f"  ➜ Duration:           {elapsed:.3f} seconds")
    print(f"  ➜ Total Allocated:    {successes}")
    print(f"  ➜ Conflicts Encountered: {conflicts}")

if __name__ == "__main__":
    print("=========================================================")
    print("      CONCURRENCY ENGINE: 500-THREAD STRESS TEST         ")
    print("=========================================================")
    
    run_high_contention_pessimistic(threads=500)
    run_high_contention_occ_no_retry(threads=500)
    run_high_contention_occ_with_retry(threads=500)
    run_low_contention_occ(threads=500)
    
    print("\n=========================================================")
    print("              STRESS SIMULATION COMPLETE                 ")
    print("=========================================================")