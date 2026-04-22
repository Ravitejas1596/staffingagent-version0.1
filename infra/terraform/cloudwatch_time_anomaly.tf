# CloudWatch dashboard + alarms for the Time Anomaly agent.
#
# Why this file exists
# --------------------
# The agent runs as an SQS-triggered worker + FastAPI handlers in the
# main ECS service. When pilots start exercising it we need a single
# place to see:
#
#   - Is the SLA-timer queue backing up? (scheduler failure)
#   - Is the DLQ growing? (poison messages)
#   - How many alerts are firing per hour across all tenants?
#   - How deep is the HITL backlog right now? (customer-facing SLA risk)
#   - Are worker errors elevated?
#
# The ApplicationMetrics/* metrics below are emitted by the worker and
# the API layer via boto3 PutMetricData. Keeping them under a single
# Namespace keeps the dashboard tidy and alarmable.

locals {
  ta_metrics_namespace = "StaffingAgent/TimeAnomaly"
}

resource "aws_cloudwatch_dashboard" "time_anomaly" {
  dashboard_name = "${local.name}-time-anomaly"

  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "metric"
        x      = 0
        y      = 0
        width  = 12
        height = 6
        properties = {
          title   = "SLA timer queue — depth"
          region  = var.aws_region
          stacked = false
          view    = "timeSeries"
          metrics = [
            [
              "AWS/SQS",
              "ApproximateNumberOfMessagesVisible",
              "QueueName",
              aws_sqs_queue.time_anomaly_sla_timers.name,
            ],
            [
              "AWS/SQS",
              "ApproximateNumberOfMessagesDelayed",
              "QueueName",
              aws_sqs_queue.time_anomaly_sla_timers.name,
            ],
          ]
          period = 60
          stat   = "Maximum"
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 0
        width  = 12
        height = 6
        properties = {
          title   = "SLA timer DLQ — depth (should stay at 0)"
          region  = var.aws_region
          stacked = false
          view    = "timeSeries"
          metrics = [
            [
              "AWS/SQS",
              "ApproximateNumberOfMessagesVisible",
              "QueueName",
              aws_sqs_queue.time_anomaly_sla_timers_dlq.name,
            ],
          ]
          period = 60
          stat   = "Maximum"
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 6
        width  = 8
        height = 6
        properties = {
          title   = "Alerts detected (all tenants, /hour)"
          region  = var.aws_region
          stacked = true
          view    = "timeSeries"
          metrics = [
            [
              local.ta_metrics_namespace,
              "AlertDetected",
              "AlertGroup",
              "group_a1_first_miss",
            ],
            [
              "...",
              "AlertGroup",
              "group_a2_consecutive_miss",
            ],
            [
              "...",
              "AlertGroup",
              "group_b_ot_over_limit",
            ],
            [
              "...",
              "AlertGroup",
              "group_b_total_over_limit",
            ],
            [
              "...",
              "AlertGroup",
              "group_c_variance",
            ],
          ]
          period = 3600
          stat   = "Sum"
        }
      },
      {
        type   = "metric"
        x      = 8
        y      = 6
        width  = 8
        height = 6
        properties = {
          title   = "HITL backlog (alerts in escalated_hitl state)"
          region  = var.aws_region
          stacked = false
          view    = "timeSeries"
          metrics = [
            [
              local.ta_metrics_namespace,
              "HitlBacklog",
            ],
          ]
          period = 300
          stat   = "Maximum"
        }
      },
      {
        type   = "metric"
        x      = 16
        y      = 6
        width  = 8
        height = 6
        properties = {
          title   = "Agent errors (node failures per minute)"
          region  = var.aws_region
          stacked = true
          view    = "timeSeries"
          metrics = [
            [
              local.ta_metrics_namespace,
              "NodeError",
              "Node",
              "detect",
            ],
            [
              "...",
              "Node",
              "outreach",
            ],
            [
              "...",
              "Node",
              "wait_recheck",
            ],
            [
              "...",
              "Node",
              "escalate_hitl",
            ],
            [
              "...",
              "Node",
              "close",
            ],
          ]
          period = 60
          stat   = "Sum"
        }
      },
    ]
  })
}

# ── Alarms ───────────────────────────────────────────────────────────
# These are the "wake me up in the middle of the night" alarms. Each is
# intentionally conservative on thresholds for pilot launch — we expect
# Chris to tighten them after the first week of production signal.

resource "aws_cloudwatch_metric_alarm" "sla_timer_dlq" {
  alarm_name          = "${local.name}-time-anomaly-sla-timer-dlq-nonzero"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 300
  statistic           = "Maximum"
  threshold           = 0
  alarm_description   = "Any message in the SLA timer DLQ means a poison message dropped from the worker — investigate."
  treat_missing_data  = "notBreaching"

  dimensions = {
    QueueName = aws_sqs_queue.time_anomaly_sla_timers_dlq.name
  }
}

resource "aws_cloudwatch_metric_alarm" "sla_timer_queue_depth" {
  alarm_name          = "${local.name}-time-anomaly-sla-timer-queue-backlogged"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 300
  statistic           = "Maximum"
  threshold           = 500
  alarm_description   = "Visible messages are timers past their due time that haven't been consumed — scheduler is lagging."
  treat_missing_data  = "notBreaching"

  dimensions = {
    QueueName = aws_sqs_queue.time_anomaly_sla_timers.name
  }
}

resource "aws_cloudwatch_metric_alarm" "time_anomaly_node_errors" {
  alarm_name          = "${local.name}-time-anomaly-node-errors-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  metric_name         = "NodeError"
  namespace           = local.ta_metrics_namespace
  period              = 60
  statistic           = "Sum"
  threshold           = 10
  alarm_description   = "More than 10 node errors/minute for 3 consecutive minutes — likely bad Bullhorn config, expired token, or a gateway outage."
  treat_missing_data  = "notBreaching"
}

resource "aws_cloudwatch_metric_alarm" "time_anomaly_hitl_backlog" {
  alarm_name          = "${local.name}-time-anomaly-hitl-backlog-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "HitlBacklog"
  namespace           = local.ta_metrics_namespace
  period              = 1800
  statistic           = "Maximum"
  threshold           = 100
  alarm_description   = "More than 100 alerts are sitting in HITL state for over 30 minutes — customer SLA risk."
  treat_missing_data  = "notBreaching"
}

output "time_anomaly_dashboard_url" {
  description = "Direct link to the CloudWatch dashboard."
  value = format(
    "https://%s.console.aws.amazon.com/cloudwatch/home?region=%s#dashboards:name=%s",
    var.aws_region,
    var.aws_region,
    aws_cloudwatch_dashboard.time_anomaly.dashboard_name,
  )
}
