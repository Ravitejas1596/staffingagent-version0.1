-- Migration 014: Combined field expansion (007-013)
-- Adds all new columns across billable_charges, bill_masters, bill_master_transactions,
-- payable_charges, pay_masters, pay_master_transactions, client_corporations,
-- job_orders, and placements.
-- Safe to run on Aurora — all ADD COLUMN statements use IF NOT EXISTS.

BEGIN;

-- ============================================================
-- billable_charges: GL segments, billing contact, currency, etc.
-- ============================================================
ALTER TABLE billable_charges
    ADD COLUMN IF NOT EXISTS billing_client_contact_id       INTEGER,
    ADD COLUMN IF NOT EXISTS billing_client_contact_first    TEXT,
    ADD COLUMN IF NOT EXISTS billing_client_contact_last     TEXT,
    ADD COLUMN IF NOT EXISTS billing_client_corporation_id   INTEGER,
    ADD COLUMN IF NOT EXISTS billing_client_corporation_name TEXT,
    ADD COLUMN IF NOT EXISTS currency_unit                   TEXT,
    ADD COLUMN IF NOT EXISTS entry_type                      TEXT,
    ADD COLUMN IF NOT EXISTS external_id                     TEXT,
    ADD COLUMN IF NOT EXISTS description                     TEXT,
    ADD COLUMN IF NOT EXISTS gl_segment1_number              TEXT,
    ADD COLUMN IF NOT EXISTS gl_segment1_name                TEXT,
    ADD COLUMN IF NOT EXISTS gl_segment2_number              TEXT,
    ADD COLUMN IF NOT EXISTS gl_segment2_name                TEXT,
    ADD COLUMN IF NOT EXISTS gl_segment3_number              TEXT,
    ADD COLUMN IF NOT EXISTS gl_segment3_name                TEXT,
    ADD COLUMN IF NOT EXISTS gl_segment4_number              TEXT,
    ADD COLUMN IF NOT EXISTS gl_segment4_name                TEXT,
    ADD COLUMN IF NOT EXISTS gl_segment5_number              TEXT,
    ADD COLUMN IF NOT EXISTS gl_segment5_name                TEXT,
    ADD COLUMN IF NOT EXISTS gl_service_code                 TEXT,
    ADD COLUMN IF NOT EXISTS has_rebill                      BOOLEAN,
    ADD COLUMN IF NOT EXISTS invoice_term_id                 INTEGER,
    ADD COLUMN IF NOT EXISTS transaction_type                TEXT,
    ADD COLUMN IF NOT EXISTS has_adjustment                  BOOLEAN,
    ADD COLUMN IF NOT EXISTS billing_profile_id              INTEGER,
    ADD COLUMN IF NOT EXISTS billing_profile_title           TEXT;

-- ============================================================
-- bill_masters: sync batch, invoiceable flag, external ID
-- ============================================================
ALTER TABLE bill_masters
    ADD COLUMN IF NOT EXISTS billing_sync_batch_id INTEGER,
    ADD COLUMN IF NOT EXISTS can_invoice           BOOLEAN,
    ADD COLUMN IF NOT EXISTS external_id           TEXT;

-- ============================================================
-- bill_master_transactions: accounting period, custom rate
-- ============================================================
ALTER TABLE bill_master_transactions
    ADD COLUMN IF NOT EXISTS accounting_period_id   INTEGER,
    ADD COLUMN IF NOT EXISTS accounting_period_date DATE,
    ADD COLUMN IF NOT EXISTS is_custom_rate         BOOLEAN,
    ADD COLUMN IF NOT EXISTS was_unbilled           BOOLEAN;

-- ============================================================
-- payable_charges: GL segments, currency, entry type
-- ============================================================
ALTER TABLE payable_charges
    ADD COLUMN IF NOT EXISTS transaction_type   TEXT,
    ADD COLUMN IF NOT EXISTS currency_unit      TEXT,
    ADD COLUMN IF NOT EXISTS entry_type         TEXT,
    ADD COLUMN IF NOT EXISTS external_id        TEXT,
    ADD COLUMN IF NOT EXISTS description        TEXT,
    ADD COLUMN IF NOT EXISTS gl_segment1_number TEXT,
    ADD COLUMN IF NOT EXISTS gl_segment1_name   TEXT,
    ADD COLUMN IF NOT EXISTS gl_segment2_number TEXT,
    ADD COLUMN IF NOT EXISTS gl_segment2_name   TEXT,
    ADD COLUMN IF NOT EXISTS gl_segment3_number TEXT,
    ADD COLUMN IF NOT EXISTS gl_segment3_name   TEXT,
    ADD COLUMN IF NOT EXISTS gl_segment4_number TEXT,
    ADD COLUMN IF NOT EXISTS gl_segment4_name   TEXT,
    ADD COLUMN IF NOT EXISTS gl_segment5_number TEXT,
    ADD COLUMN IF NOT EXISTS gl_segment5_name   TEXT,
    ADD COLUMN IF NOT EXISTS gl_service_code    TEXT,
    ADD COLUMN IF NOT EXISTS has_adjustment     BOOLEAN;

-- ============================================================
-- pay_masters: date fields, status, external ID
-- ============================================================
ALTER TABLE pay_masters
    ADD COLUMN IF NOT EXISTS date_added         DATE,
    ADD COLUMN IF NOT EXISTS date_last_modified DATE,
    ADD COLUMN IF NOT EXISTS charge_type        TEXT,
    ADD COLUMN IF NOT EXISTS transaction_status TEXT,
    ADD COLUMN IF NOT EXISTS pay_sync_batch_id  INTEGER,
    ADD COLUMN IF NOT EXISTS can_pay            BOOLEAN,
    ADD COLUMN IF NOT EXISTS external_id        TEXT;

-- ============================================================
-- pay_master_transactions: accounting period, review flags
-- ============================================================
ALTER TABLE pay_master_transactions
    ADD COLUMN IF NOT EXISTS is_unbillable          BOOLEAN,
    ADD COLUMN IF NOT EXISTS needs_review           BOOLEAN,
    ADD COLUMN IF NOT EXISTS accounting_period_id   INTEGER,
    ADD COLUMN IF NOT EXISTS accounting_period_date DATE,
    ADD COLUMN IF NOT EXISTS is_custom_rate         BOOLEAN,
    ADD COLUMN IF NOT EXISTS was_unbilled           BOOLEAN;

-- ============================================================
-- client_corporations: full field expansion + custom fields
-- ============================================================
ALTER TABLE client_corporations
    ADD COLUMN IF NOT EXISTS date_last_modified             DATE,
    ADD COLUMN IF NOT EXISTS phone                          TEXT,
    ADD COLUMN IF NOT EXISTS fax                            TEXT,
    ADD COLUMN IF NOT EXISTS billing_phone                  TEXT,
    ADD COLUMN IF NOT EXISTS external_id                    TEXT,
    ADD COLUMN IF NOT EXISTS num_employees                  INTEGER,
    ADD COLUMN IF NOT EXISTS revenue                        NUMERIC(18,2),
    ADD COLUMN IF NOT EXISTS annual_revenue                 NUMERIC(18,2),
    ADD COLUMN IF NOT EXISTS fee_arrangement                NUMERIC(8,4),
    ADD COLUMN IF NOT EXISTS tax_rate                       NUMERIC(8,4),
    ADD COLUMN IF NOT EXISTS work_week_start                INTEGER,
    ADD COLUMN IF NOT EXISTS billing_frequency              TEXT,
    ADD COLUMN IF NOT EXISTS invoice_format                 TEXT,
    ADD COLUMN IF NOT EXISTS ownership                      TEXT,
    ADD COLUMN IF NOT EXISTS ticker_symbol                  TEXT,
    ADD COLUMN IF NOT EXISTS date_founded                   DATE,
    ADD COLUMN IF NOT EXISTS twitter_handle                 TEXT,
    ADD COLUMN IF NOT EXISTS linkedin_profile_name          TEXT,
    ADD COLUMN IF NOT EXISTS facebook_profile_name          TEXT,
    ADD COLUMN IF NOT EXISTS address1                       TEXT,
    ADD COLUMN IF NOT EXISTS address2                       TEXT,
    ADD COLUMN IF NOT EXISTS city                           TEXT,
    ADD COLUMN IF NOT EXISTS state                          TEXT,
    ADD COLUMN IF NOT EXISTS zip                            TEXT,
    ADD COLUMN IF NOT EXISTS billing_address1               TEXT,
    ADD COLUMN IF NOT EXISTS billing_address2               TEXT,
    ADD COLUMN IF NOT EXISTS billing_city                   TEXT,
    ADD COLUMN IF NOT EXISTS billing_state                  TEXT,
    ADD COLUMN IF NOT EXISTS billing_zip                    TEXT,
    ADD COLUMN IF NOT EXISTS parent_client_corporation_id   INTEGER,
    ADD COLUMN IF NOT EXISTS parent_client_corporation_name TEXT,
    ADD COLUMN IF NOT EXISTS department_id                  INTEGER,
    ADD COLUMN IF NOT EXISTS department_name                TEXT,
    ADD COLUMN IF NOT EXISTS branch_id                      INTEGER,
    ADD COLUMN IF NOT EXISTS branch_name                    TEXT,
    ADD COLUMN IF NOT EXISTS billing_contact_id             INTEGER,
    ADD COLUMN IF NOT EXISTS billing_contact_first          TEXT,
    ADD COLUMN IF NOT EXISTS billing_contact_last           TEXT,
    ADD COLUMN IF NOT EXISTS custom_float1                  NUMERIC(18,4),
    ADD COLUMN IF NOT EXISTS custom_float2                  NUMERIC(18,4),
    ADD COLUMN IF NOT EXISTS custom_float3                  NUMERIC(18,4),
    ADD COLUMN IF NOT EXISTS custom_date1                   DATE,
    ADD COLUMN IF NOT EXISTS custom_date2                   DATE,
    ADD COLUMN IF NOT EXISTS custom_date3                   DATE,
    ADD COLUMN IF NOT EXISTS custom_int1                    INTEGER,
    ADD COLUMN IF NOT EXISTS custom_int2                    INTEGER,
    ADD COLUMN IF NOT EXISTS custom_int3                    INTEGER,
    ADD COLUMN IF NOT EXISTS custom_text1                   TEXT,
    ADD COLUMN IF NOT EXISTS custom_text2                   TEXT,
    ADD COLUMN IF NOT EXISTS custom_text3                   TEXT,
    ADD COLUMN IF NOT EXISTS custom_text4                   TEXT,
    ADD COLUMN IF NOT EXISTS custom_text5                   TEXT,
    ADD COLUMN IF NOT EXISTS custom_text6                   TEXT,
    ADD COLUMN IF NOT EXISTS custom_text7                   TEXT,
    ADD COLUMN IF NOT EXISTS custom_text8                   TEXT,
    ADD COLUMN IF NOT EXISTS custom_text9                   TEXT,
    ADD COLUMN IF NOT EXISTS custom_text10                  TEXT,
    ADD COLUMN IF NOT EXISTS custom_text11                  TEXT,
    ADD COLUMN IF NOT EXISTS custom_text12                  TEXT,
    ADD COLUMN IF NOT EXISTS custom_text13                  TEXT,
    ADD COLUMN IF NOT EXISTS custom_text14                  TEXT,
    ADD COLUMN IF NOT EXISTS custom_text15                  TEXT,
    ADD COLUMN IF NOT EXISTS custom_text16                  TEXT,
    ADD COLUMN IF NOT EXISTS custom_text17                  TEXT,
    ADD COLUMN IF NOT EXISTS custom_text18                  TEXT,
    ADD COLUMN IF NOT EXISTS custom_text19                  TEXT,
    ADD COLUMN IF NOT EXISTS custom_text20                  TEXT,
    ADD COLUMN IF NOT EXISTS custom_text_block1             TEXT,
    ADD COLUMN IF NOT EXISTS custom_text_block2             TEXT,
    ADD COLUMN IF NOT EXISTS custom_text_block3             TEXT,
    ADD COLUMN IF NOT EXISTS custom_text_block4             TEXT,
    ADD COLUMN IF NOT EXISTS custom_text_block5             TEXT;

CREATE INDEX IF NOT EXISTS idx_client_corps_city  ON client_corporations(city);
CREATE INDEX IF NOT EXISTS idx_client_corps_state ON client_corporations(state);

-- ============================================================
-- job_orders: full field expansion + custom fields
-- ============================================================
ALTER TABLE job_orders
    ADD COLUMN IF NOT EXISTS is_deleted             BOOLEAN,
    ADD COLUMN IF NOT EXISTS is_work_from_home      BOOLEAN,
    ADD COLUMN IF NOT EXISTS will_relocate          BOOLEAN,
    ADD COLUMN IF NOT EXISTS will_sponsor           BOOLEAN,
    ADD COLUMN IF NOT EXISTS date_last_modified     DATE,
    ADD COLUMN IF NOT EXISTS date_closed            DATE,
    ADD COLUMN IF NOT EXISTS date_end               DATE,
    ADD COLUMN IF NOT EXISTS start_date             DATE,
    ADD COLUMN IF NOT EXISTS employment_type        TEXT,
    ADD COLUMN IF NOT EXISTS type                   TEXT,
    ADD COLUMN IF NOT EXISTS source                 TEXT,
    ADD COLUMN IF NOT EXISTS on_site                TEXT,
    ADD COLUMN IF NOT EXISTS travel_requirements    TEXT,
    ADD COLUMN IF NOT EXISTS years_required         INTEGER,
    ADD COLUMN IF NOT EXISTS pay_rate               NUMERIC(14,4),
    ADD COLUMN IF NOT EXISTS client_bill_rate       NUMERIC(14,4),
    ADD COLUMN IF NOT EXISTS salary                 NUMERIC(14,4),
    ADD COLUMN IF NOT EXISTS salary_unit            TEXT,
    ADD COLUMN IF NOT EXISTS duration_weeks         NUMERIC(8,2),
    ADD COLUMN IF NOT EXISTS hours_per_week         NUMERIC(8,2),
    ADD COLUMN IF NOT EXISTS tax_status             TEXT,
    ADD COLUMN IF NOT EXISTS description            TEXT,
    ADD COLUMN IF NOT EXISTS public_description     TEXT,
    ADD COLUMN IF NOT EXISTS external_id            TEXT,
    ADD COLUMN IF NOT EXISTS report_to              TEXT,
    ADD COLUMN IF NOT EXISTS address1               TEXT,
    ADD COLUMN IF NOT EXISTS address2               TEXT,
    ADD COLUMN IF NOT EXISTS city                   TEXT,
    ADD COLUMN IF NOT EXISTS state                  TEXT,
    ADD COLUMN IF NOT EXISTS zip                    TEXT,
    ADD COLUMN IF NOT EXISTS client_contact_id      INTEGER,
    ADD COLUMN IF NOT EXISTS client_contact_first   TEXT,
    ADD COLUMN IF NOT EXISTS client_contact_last    TEXT,
    ADD COLUMN IF NOT EXISTS owner_first            TEXT,
    ADD COLUMN IF NOT EXISTS owner_last             TEXT,
    ADD COLUMN IF NOT EXISTS branch_id              INTEGER,
    ADD COLUMN IF NOT EXISTS branch_name            TEXT,
    ADD COLUMN IF NOT EXISTS custom_date1           DATE,
    ADD COLUMN IF NOT EXISTS custom_date2           DATE,
    ADD COLUMN IF NOT EXISTS custom_date3           DATE,
    ADD COLUMN IF NOT EXISTS custom_float1          NUMERIC(18,4),
    ADD COLUMN IF NOT EXISTS custom_float2          NUMERIC(18,4),
    ADD COLUMN IF NOT EXISTS custom_float3          NUMERIC(18,4),
    ADD COLUMN IF NOT EXISTS custom_int1            INTEGER,
    ADD COLUMN IF NOT EXISTS custom_int2            INTEGER,
    ADD COLUMN IF NOT EXISTS custom_int3            INTEGER,
    ADD COLUMN IF NOT EXISTS custom_text1           TEXT,
    ADD COLUMN IF NOT EXISTS custom_text2           TEXT,
    ADD COLUMN IF NOT EXISTS custom_text3           TEXT,
    ADD COLUMN IF NOT EXISTS custom_text4           TEXT,
    ADD COLUMN IF NOT EXISTS custom_text5           TEXT,
    ADD COLUMN IF NOT EXISTS custom_text6           TEXT,
    ADD COLUMN IF NOT EXISTS custom_text7           TEXT,
    ADD COLUMN IF NOT EXISTS custom_text8           TEXT,
    ADD COLUMN IF NOT EXISTS custom_text9           TEXT,
    ADD COLUMN IF NOT EXISTS custom_text10          TEXT,
    ADD COLUMN IF NOT EXISTS custom_text11          TEXT,
    ADD COLUMN IF NOT EXISTS custom_text12          TEXT,
    ADD COLUMN IF NOT EXISTS custom_text13          TEXT,
    ADD COLUMN IF NOT EXISTS custom_text14          TEXT,
    ADD COLUMN IF NOT EXISTS custom_text15          TEXT,
    ADD COLUMN IF NOT EXISTS custom_text16          TEXT,
    ADD COLUMN IF NOT EXISTS custom_text17          TEXT,
    ADD COLUMN IF NOT EXISTS custom_text18          TEXT,
    ADD COLUMN IF NOT EXISTS custom_text19          TEXT,
    ADD COLUMN IF NOT EXISTS custom_text20          TEXT,
    ADD COLUMN IF NOT EXISTS custom_text_block1     TEXT,
    ADD COLUMN IF NOT EXISTS custom_text_block2     TEXT,
    ADD COLUMN IF NOT EXISTS custom_text_block3     TEXT,
    ADD COLUMN IF NOT EXISTS custom_text_block4     TEXT,
    ADD COLUMN IF NOT EXISTS custom_text_block5     TEXT;

CREATE INDEX IF NOT EXISTS idx_job_orders_city  ON job_orders(city);
CREATE INDEX IF NOT EXISTS idx_job_orders_state ON job_orders(state);

-- ============================================================
-- placements: full rebuild — rename old cols, add new, migrate, drop old
-- ============================================================
ALTER TABLE placements RENAME COLUMN candidate_first TO candidate_first_old;
ALTER TABLE placements RENAME COLUMN candidate_last  TO candidate_last_old;
ALTER TABLE placements RENAME COLUMN job_title       TO job_title_old;
ALTER TABLE placements RENAME COLUMN client_name     TO client_name_old;
ALTER TABLE placements RENAME COLUMN pay_rate        TO pay_rate_old;
ALTER TABLE placements RENAME COLUMN bill_rate       TO bill_rate_old;
ALTER TABLE placements RENAME COLUMN ot_pay_rate     TO ot_pay_rate_old;
ALTER TABLE placements RENAME COLUMN ot_bill_rate    TO ot_bill_rate_old;
ALTER TABLE placements RENAME COLUMN start_date      TO start_date_old;
ALTER TABLE placements RENAME COLUMN end_date        TO end_date_old;

ALTER TABLE placements
    ADD COLUMN IF NOT EXISTS employee_type                  TEXT,
    ADD COLUMN IF NOT EXISTS is_work_from_home              BOOLEAN,
    ADD COLUMN IF NOT EXISTS date_added                     DATE,
    ADD COLUMN IF NOT EXISTS date_last_modified             DATE,
    ADD COLUMN IF NOT EXISTS start_date                     DATE,
    ADD COLUMN IF NOT EXISTS end_date                       DATE,
    ADD COLUMN IF NOT EXISTS date_client_effective          DATE,
    ADD COLUMN IF NOT EXISTS date_effective                 DATE,
    ADD COLUMN IF NOT EXISTS estimated_end_date             DATE,
    ADD COLUMN IF NOT EXISTS employment_start_date          DATE,
    ADD COLUMN IF NOT EXISTS pay_rate                       NUMERIC(14,4),
    ADD COLUMN IF NOT EXISTS bill_rate                      NUMERIC(14,4),
    ADD COLUMN IF NOT EXISTS ot_pay_rate                    NUMERIC(14,4),
    ADD COLUMN IF NOT EXISTS ot_bill_rate                   NUMERIC(14,4),
    ADD COLUMN IF NOT EXISTS salary                         NUMERIC(14,4),
    ADD COLUMN IF NOT EXISTS salary_unit                    TEXT,
    ADD COLUMN IF NOT EXISTS fee                            NUMERIC(10,4),
    ADD COLUMN IF NOT EXISTS flat_fee                       NUMERIC(14,4),
    ADD COLUMN IF NOT EXISTS mark_up_percentage             NUMERIC(8,4),
    ADD COLUMN IF NOT EXISTS overtime_mark_up_percentage    NUMERIC(8,4),
    ADD COLUMN IF NOT EXISTS ot_exemption                   TEXT,
    ADD COLUMN IF NOT EXISTS duration_weeks                 NUMERIC(8,2),
    ADD COLUMN IF NOT EXISTS hours_per_day                  NUMERIC(6,2),
    ADD COLUMN IF NOT EXISTS hours_of_operation             TEXT,
    ADD COLUMN IF NOT EXISTS work_week_start                INTEGER,
    ADD COLUMN IF NOT EXISTS timesheet_cycle                TEXT,
    ADD COLUMN IF NOT EXISTS billing_frequency              TEXT,
    ADD COLUMN IF NOT EXISTS tax_rate                       NUMERIC(8,4),
    ADD COLUMN IF NOT EXISTS tax_state                      TEXT,
    ADD COLUMN IF NOT EXISTS cost_center                    TEXT,
    ADD COLUMN IF NOT EXISTS position_code                  TEXT,
    ADD COLUMN IF NOT EXISTS report_to                      TEXT,
    ADD COLUMN IF NOT EXISTS comments                       TEXT,
    ADD COLUMN IF NOT EXISTS termination_reason             TEXT,
    ADD COLUMN IF NOT EXISTS quit_job                       BOOLEAN,
    ADD COLUMN IF NOT EXISTS payroll_employee_type          TEXT,
    ADD COLUMN IF NOT EXISTS pay_group                      TEXT,
    ADD COLUMN IF NOT EXISTS gl_segment1_number             TEXT,
    ADD COLUMN IF NOT EXISTS gl_segment1_name               TEXT,
    ADD COLUMN IF NOT EXISTS gl_segment2_number             TEXT,
    ADD COLUMN IF NOT EXISTS gl_segment2_name               TEXT,
    ADD COLUMN IF NOT EXISTS gl_segment3_number             TEXT,
    ADD COLUMN IF NOT EXISTS gl_segment3_name               TEXT,
    ADD COLUMN IF NOT EXISTS gl_segment4_number             TEXT,
    ADD COLUMN IF NOT EXISTS gl_segment4_name               TEXT,
    ADD COLUMN IF NOT EXISTS gl_segment5_number             TEXT,
    ADD COLUMN IF NOT EXISTS gl_segment5_name               TEXT,
    ADD COLUMN IF NOT EXISTS candidate_bullhorn_id          INTEGER,
    ADD COLUMN IF NOT EXISTS candidate_first                TEXT,
    ADD COLUMN IF NOT EXISTS candidate_last                 TEXT,
    ADD COLUMN IF NOT EXISTS job_order_bullhorn_id          INTEGER,
    ADD COLUMN IF NOT EXISTS job_title                      TEXT,
    ADD COLUMN IF NOT EXISTS client_contact_id              INTEGER,
    ADD COLUMN IF NOT EXISTS client_contact_first           TEXT,
    ADD COLUMN IF NOT EXISTS client_contact_last            TEXT,
    ADD COLUMN IF NOT EXISTS client_corporation_id          INTEGER,
    ADD COLUMN IF NOT EXISTS client_corporation_name        TEXT,
    ADD COLUMN IF NOT EXISTS owner_bullhorn_id              INTEGER,
    ADD COLUMN IF NOT EXISTS owner_first                    TEXT,
    ADD COLUMN IF NOT EXISTS owner_last                     TEXT,
    ADD COLUMN IF NOT EXISTS branch_id                      INTEGER,
    ADD COLUMN IF NOT EXISTS branch_name                    TEXT,
    ADD COLUMN IF NOT EXISTS vendor_client_corporation_id   INTEGER,
    ADD COLUMN IF NOT EXISTS vendor_client_corporation_name TEXT,
    ADD COLUMN IF NOT EXISTS custom_date1                   DATE,
    ADD COLUMN IF NOT EXISTS custom_date2                   DATE,
    ADD COLUMN IF NOT EXISTS custom_date3                   DATE,
    ADD COLUMN IF NOT EXISTS custom_float1                  NUMERIC(18,4),
    ADD COLUMN IF NOT EXISTS custom_float2                  NUMERIC(18,4),
    ADD COLUMN IF NOT EXISTS custom_float3                  NUMERIC(18,4),
    ADD COLUMN IF NOT EXISTS custom_int1                    INTEGER,
    ADD COLUMN IF NOT EXISTS custom_int2                    INTEGER,
    ADD COLUMN IF NOT EXISTS custom_int3                    INTEGER,
    ADD COLUMN IF NOT EXISTS custom_text1                   TEXT,
    ADD COLUMN IF NOT EXISTS custom_text2                   TEXT,
    ADD COLUMN IF NOT EXISTS custom_text3                   TEXT,
    ADD COLUMN IF NOT EXISTS custom_text4                   TEXT,
    ADD COLUMN IF NOT EXISTS custom_text5                   TEXT,
    ADD COLUMN IF NOT EXISTS custom_text6                   TEXT,
    ADD COLUMN IF NOT EXISTS custom_text7                   TEXT,
    ADD COLUMN IF NOT EXISTS custom_text8                   TEXT,
    ADD COLUMN IF NOT EXISTS custom_text9                   TEXT,
    ADD COLUMN IF NOT EXISTS custom_text10                  TEXT,
    ADD COLUMN IF NOT EXISTS custom_text11                  TEXT,
    ADD COLUMN IF NOT EXISTS custom_text12                  TEXT,
    ADD COLUMN IF NOT EXISTS custom_text13                  TEXT,
    ADD COLUMN IF NOT EXISTS custom_text14                  TEXT,
    ADD COLUMN IF NOT EXISTS custom_text15                  TEXT,
    ADD COLUMN IF NOT EXISTS custom_text16                  TEXT,
    ADD COLUMN IF NOT EXISTS custom_text17                  TEXT,
    ADD COLUMN IF NOT EXISTS custom_text18                  TEXT,
    ADD COLUMN IF NOT EXISTS custom_text19                  TEXT,
    ADD COLUMN IF NOT EXISTS custom_text20                  TEXT,
    ADD COLUMN IF NOT EXISTS custom_text_block1             TEXT,
    ADD COLUMN IF NOT EXISTS custom_text_block2             TEXT,
    ADD COLUMN IF NOT EXISTS custom_text_block3             TEXT,
    ADD COLUMN IF NOT EXISTS custom_text_block4             TEXT,
    ADD COLUMN IF NOT EXISTS custom_text_block5             TEXT;

UPDATE placements SET
    candidate_first         = candidate_first_old,
    candidate_last          = candidate_last_old,
    job_title               = job_title_old,
    client_corporation_name = client_name_old,
    pay_rate                = pay_rate_old,
    bill_rate               = bill_rate_old,
    ot_pay_rate             = ot_pay_rate_old,
    ot_bill_rate            = ot_bill_rate_old,
    start_date              = start_date_old,
    end_date                = end_date_old;

ALTER TABLE placements
    DROP COLUMN candidate_first_old,
    DROP COLUMN candidate_last_old,
    DROP COLUMN job_title_old,
    DROP COLUMN client_name_old,
    DROP COLUMN pay_rate_old,
    DROP COLUMN bill_rate_old,
    DROP COLUMN ot_pay_rate_old,
    DROP COLUMN ot_bill_rate_old,
    DROP COLUMN start_date_old,
    DROP COLUMN end_date_old;

CREATE INDEX IF NOT EXISTS idx_placements_candidate   ON placements(candidate_bullhorn_id);
CREATE INDEX IF NOT EXISTS idx_placements_job_order   ON placements(job_order_bullhorn_id);
CREATE INDEX IF NOT EXISTS idx_placements_client_corp ON placements(client_corporation_id);

COMMIT;
