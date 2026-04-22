-- Migration 047: cache timesheet-cycle metadata on placements.
--
-- Source of truth for pay-period computation is the placement's timesheet-cycle
-- field on Bullhorn. These columns cache the synced value so the Time Anomaly
-- agent's detect stage doesn't re-query Bullhorn for every placement on every
-- cycle.
--
-- Frequency values mirror Bullhorn's timesheet-cycle enumeration. anchor_day is
-- the day-of-week the cycle rolls over (text form, lowercase). Both are
-- nullable because historical placements synced before this migration won't
-- have the field populated until the next full sync.
--
-- Reference: Time Anomaly build plan, Week 1 Day 2-3, pay-period model decision.

BEGIN;

ALTER TABLE placements
    ADD COLUMN IF NOT EXISTS timesheet_cycle_frequency TEXT,
    ADD COLUMN IF NOT EXISTS timesheet_cycle_anchor_day TEXT,
    ADD COLUMN IF NOT EXISTS timesheet_cycle_synced_at TIMESTAMPTZ;

ALTER TABLE placements
    DROP CONSTRAINT IF EXISTS chk_placements_timesheet_cycle_frequency;
ALTER TABLE placements
    ADD CONSTRAINT chk_placements_timesheet_cycle_frequency
    CHECK (
        timesheet_cycle_frequency IS NULL
        OR timesheet_cycle_frequency IN ('weekly', 'biweekly', 'semimonthly', 'monthly')
    );

ALTER TABLE placements
    DROP CONSTRAINT IF EXISTS chk_placements_timesheet_cycle_anchor_day;
ALTER TABLE placements
    ADD CONSTRAINT chk_placements_timesheet_cycle_anchor_day
    CHECK (
        timesheet_cycle_anchor_day IS NULL
        OR timesheet_cycle_anchor_day IN (
            'sunday', 'monday', 'tuesday', 'wednesday',
            'thursday', 'friday', 'saturday'
        )
    );

CREATE INDEX IF NOT EXISTS idx_placements_timesheet_cycle
    ON placements (tenant_id, timesheet_cycle_frequency)
    WHERE timesheet_cycle_frequency IS NOT NULL;

COMMIT;
