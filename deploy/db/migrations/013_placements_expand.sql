-- Migration 013: Expand placements with full field set from Bullhorn SDK

BEGIN;

-- Rename existing columns to match new naming convention
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

-- Add all new columns
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

-- Migrate data from old columns to new ones
UPDATE placements SET
    candidate_first     = candidate_first_old,
    candidate_last      = candidate_last_old,
    job_title           = job_title_old,
    client_corporation_name = client_name_old,
    pay_rate            = pay_rate_old,
    bill_rate           = bill_rate_old,
    ot_pay_rate         = ot_pay_rate_old,
    ot_bill_rate        = ot_bill_rate_old,
    start_date          = start_date_old,
    end_date            = end_date_old;

-- Drop old columns
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
