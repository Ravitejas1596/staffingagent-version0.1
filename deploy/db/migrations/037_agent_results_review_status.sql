-- Migration 037: Add review_status column to agent_results

ALTER TABLE agent_results
    ADD COLUMN IF NOT EXISTS review_status TEXT NOT NULL DEFAULT 'pending';
