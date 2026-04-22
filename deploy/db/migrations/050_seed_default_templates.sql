-- Migration 050: seed DRAFT platform-default message templates.
--
-- These are placeholder templates so the Time Anomaly agent has something to
-- render end-to-end during the April 23 sprint start. Cortney's Apr 24
-- deliverable replaces every row here with production copy before pilot
-- go-live (May 30).
--
-- Every row is marked with [DRAFT] in the body so an accidental pilot send
-- is visually obvious in the recipient's inbox.
--
-- Allowed variables (enforced by message_templates.py Jinja2 environment):
--   {{ employee_first_name }}
--   {{ week_ending_date }}
--   {{ bte_link }}
--   {{ recruiter_name }}
--   {{ company_short_name }}
--   {{ pay_period_start }}
--   {{ pay_period_end }}

BEGIN;

-- Run with bypass_rls so NULL tenant_id inserts succeed under RLS policy.
SET LOCAL app.bypass_rls = 'on';

INSERT INTO message_templates (tenant_id, template_key, channel, language, body)
VALUES
    (NULL, 'time_anomaly.group_a1.sms', 'sms', 'en',
     '[DRAFT] Hi {{ employee_first_name }}, this is {{ company_short_name }}. '
     'Your timesheet for week ending {{ week_ending_date }} has not been received. '
     'Please submit it here: {{ bte_link }}. Reply STOP to opt out.'),

    (NULL, 'time_anomaly.group_a2.sms', 'sms', 'en',
     '[DRAFT] Hi {{ employee_first_name }}, your timesheet for week ending '
     '{{ week_ending_date }} is still missing — this is the second week in a row. '
     'Please submit immediately: {{ bte_link }}. Your recruiter {{ recruiter_name }} '
     'will follow up by end of day.'),

    (NULL, 'time_anomaly.group_a2.email_subject', 'email_subject', 'en',
     '[DRAFT] Consecutive missing timesheet — {{ employee_first_name }} — '
     'week ending {{ week_ending_date }}'),

    (NULL, 'time_anomaly.group_a2.email_body', 'email_body', 'en',
     '[DRAFT]\n\n'
     'Hello {{ recruiter_name }},\n\n'
     '{{ employee_first_name }} has now missed two consecutive timesheets '
     '(most recent week ending {{ week_ending_date }}). An SMS reminder has '
     'been sent. Please reach out to confirm the placement status.\n\n'
     'Company policy requires recruiter follow-up after two consecutive missed '
     'weeks. Training link and policy reference will be added by Cortney '
     'before pilot.\n\n'
     '— StaffingAgent'),

    (NULL, 'time_anomaly.group_b.sms', 'sms', 'en',
     '[DRAFT] Hi {{ employee_first_name }}, your hours submitted for week '
     'ending {{ week_ending_date }} appear to be over the limit permitted for '
     'your placement. Billing is on hold pending review. Please confirm or '
     'correct here: {{ bte_link }}. Reply STOP to opt out.'),

    (NULL, 'time_anomaly.group_c.sms', 'sms', 'en',
     '[DRAFT] Hi {{ employee_first_name }}, your hours for week ending '
     '{{ week_ending_date }} are significantly different from your typical '
     'pattern. Billing is on hold pending review. Please confirm or correct '
     'here: {{ bte_link }}. Reply STOP to opt out.');

COMMIT;
