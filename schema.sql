-- Reset table for idempotent runs
DROP TABLE IF EXISTS inventory_batches CASCADE;

-- Inventory table with OCC and hard allocation guards
CREATE TABLE inventory_batches (
    id SERIAL PRIMARY KEY,
    sku VARCHAR(50) NOT NULL UNIQUE,
    tenant_id VARCHAR(50) NOT NULL,
    quantity_on_hand INT NOT NULL CHECK (quantity_on_hand >= 0),
    allocated_quantity INT NOT NULL DEFAULT 0 CHECK (allocated_quantity <= quantity_on_hand),
    version INT NOT NULL DEFAULT 1,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Enable Row-Level Security
ALTER TABLE inventory_batches ENABLE ROW LEVEL SECURITY;

-- Tenant isolation policy driven by application session variable
CREATE POLICY tenant_isolation_policy ON inventory_batches
    FOR ALL
    USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), ''));

-- Seed initial test record: 10 units available for allocation
INSERT INTO inventory_batches (sku, tenant_id, quantity_on_hand, allocated_quantity)
VALUES ('SKU-ELEC-1001', 'tenant_alpha', 10, 0);