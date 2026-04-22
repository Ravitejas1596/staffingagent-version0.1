resource "aws_sqs_queue" "bullhorn_events_dlq" {
  name                      = "${local.name}-bullhorn-events-dlq"
  message_retention_seconds = 1209600 # 14 days
}

resource "aws_sqs_queue" "bullhorn_events" {
  name                       = "${local.name}-bullhorn-events"
  visibility_timeout_seconds = 300   # consumer has 5 min to process a batch
  message_retention_seconds  = 86400 # 1 day — events go stale fast
  receive_wait_time_seconds  = 20    # long polling

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.bullhorn_events_dlq.arn
    maxReceiveCount     = 3
  })
}

resource "aws_sqs_queue" "agent_jobs_dlq" {
  name                      = "${local.name}-agent-jobs-dlq"
  message_retention_seconds = 1209600 # 14 days
}

resource "aws_sqs_queue" "agent_jobs" {
  name                       = "${local.name}-agent-jobs"
  visibility_timeout_seconds = 300 # 5 minutes — agent runs can be long
  message_retention_seconds  = 1209600 # 14 days
  receive_wait_time_seconds  = 20 # long polling

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.agent_jobs_dlq.arn
    maxReceiveCount     = 3
  })
}

# ── Time Anomaly Agent — SLA timer queue ─────────────────────────────
# outreach_node enqueues a delayed message per alert with DelaySeconds
# set to the first-reminder or escalation window from TimeAnomalyConfig.
# The sla_timer_worker consumes these and resumes the LangGraph thread
# so wait_recheck can re-poll Bullhorn.
#
# Max delay SQS supports is 15 minutes per SendMessage call; longer SLA
# bands (up to 24h) are handled by the worker re-enqueuing a fresh
# delayed message with the remaining time. Keeps the architecture
# uniform across severity bands.

resource "aws_sqs_queue" "time_anomaly_sla_timers_dlq" {
  name                      = "${local.name}-time-anomaly-sla-timers-dlq"
  message_retention_seconds = 1209600 # 14 days
}

resource "aws_sqs_queue" "time_anomaly_sla_timers" {
  name                       = "${local.name}-time-anomaly-sla-timers"
  visibility_timeout_seconds = 120   # worker has 2 min to resume the graph
  message_retention_seconds  = 1209600 # 14 days
  receive_wait_time_seconds  = 20    # long polling
  delay_seconds              = 0     # per-message DelaySeconds is what matters here

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.time_anomaly_sla_timers_dlq.arn
    maxReceiveCount     = 3
  })
}
