-- Migration 006: BillableCharge, BillMaster, BillMasterTransaction,
--                 PayableCharge, PayMaster, PayMasterTransaction

BEGIN;

CREATE TABLE billable_charges (
    id                          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id                   UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    bullhorn_id                 INTEGER NOT NULL,
    date_added                  DATE,
    date_last_modified          DATE,
    period_end_date             DATE,
    subtotal                    NUMERIC(14, 4),
    is_invoiced                 BOOLEAN,
    status                      TEXT,
    transaction_status          TEXT,
    candidate_bullhorn_id       INTEGER,
    client_corporation_id       INTEGER,
    client_corporation_name     TEXT,
    placement_bullhorn_id       INTEGER,
    job_order_bullhorn_id       INTEGER,
    timesheet_bullhorn_id       INTEGER,
    raw_data                    JSONB NOT NULL DEFAULT '{}',
    synced_at                   TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, bullhorn_id)
);

CREATE INDEX idx_billable_charges_tenant     ON billable_charges(tenant_id);
CREATE INDEX idx_billable_charges_status     ON billable_charges(status);
CREATE INDEX idx_billable_charges_period     ON billable_charges(period_end_date);
CREATE INDEX idx_billable_charges_placement  ON billable_charges(placement_bullhorn_id);

CREATE TABLE bill_masters (
    id                          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id                   UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    bullhorn_id                 INTEGER NOT NULL,
    date_added                  DATE,
    date_last_modified          DATE,
    transaction_date            DATE,
    charge_type                 TEXT,
    transaction_status          TEXT,
    billable_charge_bullhorn_id INTEGER,
    earn_code                   TEXT,
    raw_data                    JSONB NOT NULL DEFAULT '{}',
    synced_at                   TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, bullhorn_id)
);

CREATE INDEX idx_bill_masters_tenant  ON bill_masters(tenant_id);
CREATE INDEX idx_bill_masters_charge  ON bill_masters(billable_charge_bullhorn_id);

CREATE TABLE bill_master_transactions (
    id                          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id                   UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    bullhorn_id                 INTEGER NOT NULL,
    date_added                  DATE,
    date_last_modified          DATE,
    amount                      NUMERIC(14, 4),
    quantity                    NUMERIC(10, 4),
    rate                        NUMERIC(12, 4),
    net_amount                  NUMERIC(14, 4),
    net_quantity                NUMERIC(10, 4),
    recording_date              DATE,
    pay_period_end_date         DATE,
    is_deleted                  BOOLEAN,
    is_unbillable               BOOLEAN,
    needs_review                BOOLEAN,
    transaction_type            TEXT,
    transaction_origin          TEXT,
    bill_master_bullhorn_id     INTEGER,
    unit_of_measure             TEXT,
    raw_data                    JSONB NOT NULL DEFAULT '{}',
    synced_at                   TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, bullhorn_id)
);

CREATE INDEX idx_bmt_tenant       ON bill_master_transactions(tenant_id);
CREATE INDEX idx_bmt_bill_master  ON bill_master_transactions(bill_master_bullhorn_id);
CREATE INDEX idx_bmt_period       ON bill_master_transactions(pay_period_end_date);

CREATE TABLE payable_charges (
    id                          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id                   UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    bullhorn_id                 INTEGER NOT NULL,
    date_added                  DATE,
    date_last_modified          DATE,
    period_end_date             DATE,
    subtotal                    NUMERIC(14, 4),
    status                      TEXT,
    transaction_status          TEXT,
    candidate_bullhorn_id       INTEGER,
    client_corporation_id       INTEGER,
    client_corporation_name     TEXT,
    placement_bullhorn_id       INTEGER,
    job_order_bullhorn_id       INTEGER,
    timesheet_bullhorn_id       INTEGER,
    raw_data                    JSONB NOT NULL DEFAULT '{}',
    synced_at                   TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, bullhorn_id)
);

CREATE INDEX idx_payable_charges_tenant     ON payable_charges(tenant_id);
CREATE INDEX idx_payable_charges_status     ON payable_charges(status);
CREATE INDEX idx_payable_charges_period     ON payable_charges(period_end_date);
CREATE INDEX idx_payable_charges_placement  ON payable_charges(placement_bullhorn_id);

CREATE TABLE pay_masters (
    id                          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id                   UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    bullhorn_id                 INTEGER NOT NULL,
    transaction_date            DATE,
    payable_charge_bullhorn_id  INTEGER,
    earn_code                   TEXT,
    raw_data                    JSONB NOT NULL DEFAULT '{}',
    synced_at                   TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, bullhorn_id)
);

CREATE INDEX idx_pay_masters_tenant  ON pay_masters(tenant_id);
CREATE INDEX idx_pay_masters_charge  ON pay_masters(payable_charge_bullhorn_id);

CREATE TABLE pay_master_transactions (
    id                          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id                   UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    bullhorn_id                 INTEGER NOT NULL,
    date_added                  DATE,
    date_last_modified          DATE,
    amount                      NUMERIC(14, 4),
    quantity                    NUMERIC(10, 4),
    rate                        NUMERIC(12, 4),
    net_amount                  NUMERIC(14, 4),
    net_quantity                NUMERIC(10, 4),
    recording_date              DATE,
    pay_period_end_date         DATE,
    is_deleted                  BOOLEAN,
    transaction_type            TEXT,
    transaction_origin          TEXT,
    pay_master_bullhorn_id      INTEGER,
    unit_of_measure             TEXT,
    raw_data                    JSONB NOT NULL DEFAULT '{}',
    synced_at                   TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, bullhorn_id)
);

CREATE INDEX idx_pmt_tenant      ON pay_master_transactions(tenant_id);
CREATE INDEX idx_pmt_pay_master  ON pay_master_transactions(pay_master_bullhorn_id);
CREATE INDEX idx_pmt_period      ON pay_master_transactions(pay_period_end_date);

GRANT SELECT, INSERT, UPDATE, DELETE ON billable_charges TO app_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON bill_masters TO app_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON bill_master_transactions TO app_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON payable_charges TO app_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON pay_masters TO app_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON pay_master_transactions TO app_user;

COMMIT;
