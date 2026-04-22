"""Background workers for the StaffingAgent platform.

Each module here consumes from an SQS queue (see
``infra/terraform/messaging.tf``) and invokes the appropriate agent
graph to resume a paused LangGraph thread.
"""
