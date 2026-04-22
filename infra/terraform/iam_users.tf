locals {
  account_id = data.aws_caller_identity.current.account_id
  aws_region = "us-east-1"
}

# ── Chris Scowden — ops/monitoring access ─────────────────────────────────────

resource "aws_iam_user" "chris" {
  name = "chris.scowden"
  tags = { Name = "Chris Scowden", Team = "StaffingAgent" }
}

resource "aws_iam_policy" "chris_ops" {
  name        = "staffingagent-ops-access"
  description = "Scoped ops access for Chris Scowden — ECS, ECR, logs, RDS Data API, S3, Secrets Manager"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [

      # ── ECS — view + force new deployments ───────────────────────────────
      {
        Sid    = "ECSReadAndDeploy"
        Effect = "Allow"
        Action = [
          "ecs:DescribeClusters",
          "ecs:DescribeServices",
          "ecs:DescribeTasks",
          "ecs:DescribeTaskDefinition",
          "ecs:ListClusters",
          "ecs:ListServices",
          "ecs:ListTasks",
          "ecs:ListTaskDefinitions",
          "ecs:UpdateService",   # force new deployment
          "ecs:RunTask",
          "ecs:StopTask",
        ]
        Resource = "*"
        Condition = {
          StringEquals = {
            "ecs:cluster" = "arn:aws:ecs:${local.aws_region}:${local.account_id}:cluster/staffingagent-prod-cluster"
          }
        }
      },
      # DescribeClusters/ListClusters/ListTaskDefinitions don't support cluster condition — allow separately
      {
        Sid    = "ECSGlobalDescribe"
        Effect = "Allow"
        Action = [
          "ecs:DescribeClusters",
          "ecs:ListClusters",
          "ecs:ListTaskDefinitions",
          "ecs:DescribeTaskDefinition",
        ]
        Resource = "*"
      },

      # ── ECR — read-only ───────────────────────────────────────────────────
      {
        Sid    = "ECRRead"
        Effect = "Allow"
        Action = [
          "ecr:GetAuthorizationToken",
          "ecr:DescribeRepositories",
          "ecr:ListImages",
          "ecr:DescribeImages",
          "ecr:BatchGetImage",
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchCheckLayerAvailability",
        ]
        Resource = "*"
      },

      # ── CloudWatch Logs — read for staffingagent ECS log groups ──────────
      {
        Sid    = "CloudWatchLogsRead"
        Effect = "Allow"
        Action = [
          "logs:DescribeLogGroups",
          "logs:DescribeLogStreams",
          "logs:GetLogEvents",
          "logs:FilterLogEvents",
          "logs:GetLogGroupFields",
          "logs:StartQuery",
          "logs:StopQuery",
          "logs:GetQueryResults",
        ]
        Resource = [
          "arn:aws:logs:${local.aws_region}:${local.account_id}:log-group:/ecs/staffingagent*",
          "arn:aws:logs:${local.aws_region}:${local.account_id}:log-group:/ecs/staffingagent*:*",
        ]
      },
      # DescribeLogGroups on root resource (required by console)
      {
        Sid      = "CloudWatchLogsDescribe"
        Effect   = "Allow"
        Action   = ["logs:DescribeLogGroups"]
        Resource = "*"
      },

      # ── RDS / Aurora — Query Editor via Data API ──────────────────────────
      {
        Sid    = "RDSDataAPI"
        Effect = "Allow"
        Action = [
          "rds-data:ExecuteStatement",
          "rds-data:BatchExecuteStatement",
          "rds-data:BeginTransaction",
          "rds-data:CommitTransaction",
          "rds-data:RollbackTransaction",
        ]
        Resource = "arn:aws:rds:${local.aws_region}:${local.account_id}:cluster:staffingagent-prod-db"
      },
      {
        Sid    = "RDSDescribe"
        Effect = "Allow"
        Action = [
          "rds:DescribeDBClusters",
          "rds:DescribeDBInstances",
          "rds:DescribeDBClusterParameters",
        ]
        Resource = "*"
      },

      # ── S3 — read/write on staffingagent buckets ──────────────────────────
      {
        Sid    = "S3BucketList"
        Effect = "Allow"
        Action = ["s3:ListBucket", "s3:GetBucketLocation"]
        Resource = [
          "arn:aws:s3:::staffingagent-frontend-prod",
          "arn:aws:s3:::staffingagent-uploads-prod",
        ]
      },
      {
        Sid    = "S3Objects"
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:GetObjectVersion",
        ]
        Resource = [
          "arn:aws:s3:::staffingagent-frontend-prod/*",
          "arn:aws:s3:::staffingagent-uploads-prod/*",
        ]
      },
      {
        Sid    = "S3ListAll"  # needed for S3 console to show buckets
        Effect = "Allow"
        Action = ["s3:ListAllMyBuckets"]
        Resource = "*"
      },

      # ── Secrets Manager — read + update staffingagent secrets ─────────────
      {
        Sid    = "SecretsManagerAccess"
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue",
          "secretsmanager:PutSecretValue",
          "secretsmanager:UpdateSecret",
          "secretsmanager:DescribeSecret",
          "secretsmanager:ListSecretVersionIds",
        ]
        Resource = "arn:aws:secretsmanager:${local.aws_region}:${local.account_id}:secret:staffingagent/*"
      },
      {
        Sid      = "SecretsManagerList"
        Effect   = "Allow"
        Action   = ["secretsmanager:ListSecrets"]
        Resource = "*"
      },
    ]
  })
}

resource "aws_iam_user_policy_attachment" "chris_ops" {
  user       = aws_iam_user.chris.name
  policy_arn = aws_iam_policy.chris_ops.arn
}

resource "aws_iam_user_policy_attachment" "chris_iam_read" {
  user       = aws_iam_user.chris.name
  policy_arn = "arn:aws:iam::aws:policy/IAMReadOnlyAccess"
}

resource "aws_iam_user_policy_attachment" "chris_change_password" {
  user       = aws_iam_user.chris.name
  policy_arn = "arn:aws:iam::aws:policy/IAMUserChangePassword"
}

# ── Require MFA — deny everything except MFA self-enrollment if not authenticated with MFA ──

resource "aws_iam_user_policy" "chris_require_mfa" {
  name = "require-mfa"
  user = aws_iam_user.chris.name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      # Allow managing own MFA device (needed to enroll on first login)
      {
        Sid    = "AllowMFASelfManagement"
        Effect = "Allow"
        Action = [
          "iam:CreateVirtualMFADevice",
          "iam:EnableMFADevice",
          "iam:GetUser",
          "iam:ListMFADevices",
          "iam:ListVirtualMFADevices",
          "iam:ResyncMFADevice",
        ]
        Resource = [
          "arn:aws:iam::${local.account_id}:mfa/&{aws:username}",
          "arn:aws:iam::${local.account_id}:user/&{aws:username}",
        ]
      },
      # Allow viewing account-level MFA info (needed by console)
      {
        Sid      = "AllowListActions"
        Effect   = "Allow"
        Action   = ["iam:ListUsers", "iam:ListVirtualMFADevices"]
        Resource = "*"
      },
      # Deny everything else if MFA is not present
      {
        Sid    = "DenyWithoutMFA"
        Effect = "Deny"
        NotAction = [
          "iam:CreateVirtualMFADevice",
          "iam:EnableMFADevice",
          "iam:GetUser",
          "iam:ListMFADevices",
          "iam:ListVirtualMFADevices",
          "iam:ResyncMFADevice",
          "iam:ChangePassword",
          "sts:GetSessionToken",
        ]
        Resource = "*"
        Condition = {
          BoolIfExists = {
            "aws:MultiFactorAuthPresent" = "false"
          }
        }
      },
    ]
  })
}

output "chris_iam_arn" {
  value = aws_iam_user.chris.arn
}
