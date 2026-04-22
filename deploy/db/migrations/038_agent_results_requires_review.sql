-- Migration 038: Add requires_review column to agent_results

ALTER TABLE agent_results
    ADD COLUMN IF NOT EXISTS requires_review BOOLEAN NOT NULL DEFAULT false;
