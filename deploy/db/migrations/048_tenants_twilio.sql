-- Migration 048: per-tenant Twilio messaging configuration.
--
-- Each tenant registers its own A2P 10DLC brand with The Campaign Registry so
-- SMS deliverability stays attributable to the correct staffing company rather
-- than a shared StaffingAgent brand. The Messaging Service SID identifies the
-- tenant's campaign; the Time Anomaly agent uses it as the `from` channel when
-- dispatching outbound SMS.
--
-- a2p_brand_status mirrors TCR's brand-approval lifecycle so the agent can
-- degrade gracefully (route to HITL via email) while registration is pending.
--
-- Reference: docs/twilio-a2p-onboarding.md, Time Anomaly build plan Week 1
-- Day 3.

BEGIN;

ALTER TABLE tenants
    ADD COLUMN IF NOT EXISTS twilio_messaging_service_sid TEXT,
    ADD COLUMN IF NOT EXISTS twilio_a2p_brand_status TEXT NOT NULL DEFAULT 'not_registered',
    ADD COLUMN IF NOT EXISTS twilio_a2p_brand_updated_at TIMESTAMPTZ;

ALTER TABLE tenants
    DROP CONSTRAINT IF EXISTS chk_tenants_twilio_a2p_brand_status;
ALTER TABLE tenants
    ADD CONSTRAINT chk_tenants_twilio_a2p_brand_status
    CHECK (twilio_a2p_brand_status IN (
        'not_registered',
        'pending_review',
        'approved',
        'rejected',
        'suspended'
    ));

COMMIT;
