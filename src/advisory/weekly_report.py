"""
Generate the weekly AI advisory board report.

Entrypoint: python -m src.advisory.weekly_report

For each persona (CFO, Chief of Staff, GTM Lead, Product Lead, Risk Advisor):
  1. Build a prompt: persona instructions + master context + current weekly state
  2. Call Claude API (claude-3-5-sonnet-20241022 — fast and cost-effective for structured output)
  3. Collect the response

Compile all 5 analyses into a single markdown report and deliver via GitHub Issue.
"""
from __future__ import annotations

import os
import sys
import textwrap
from datetime import datetime

import anthropic

from .deliver import create_github_issue
from .personas import Persona, load_master_context, load_personas
from .state import get_report_date, get_report_week, load_current_state

# Claude model — use Sonnet for balance of quality and cost
# Each weekly run: 5 personas × ~3,000 tokens input + ~800 tokens output ≈ 19,000 tokens
# At Sonnet pricing this is well under $1 per weekly run
MODEL = "claude-sonnet-4-5"

# Max tokens per persona response — enough for the structured output format
MAX_TOKENS_PER_PERSONA = 1200


def build_prompt(persona: Persona, master_context: str, current_state: str) -> str:
    """Assemble the full prompt for a single persona analysis."""
    return textwrap.dedent(f"""
        You are the {persona.name} for StaffingAgent.ai. Below are your role instructions,
        the full business context, and this week's business state update.

        Respond ONLY with your weekly brief in the exact format specified in your role instructions.
        Be specific. Use actual numbers from the current state where available.
        Where data is missing or not yet applicable (pre-revenue), say so clearly rather than
        fabricating numbers. Do not add preamble or explanation outside the brief format.

        ---
        ## YOUR ROLE INSTRUCTIONS
        {persona.instructions}

        ---
        ## MASTER BUSINESS CONTEXT
        {master_context}

        ---
        ## THIS WEEK'S BUSINESS STATE
        {current_state}
    """).strip()


def run_persona(
    client: anthropic.Anthropic,
    persona: Persona,
    master_context: str,
    current_state: str,
) -> str:
    """Call Claude API for a single persona and return the response text."""
    prompt = build_prompt(persona, master_context, current_state)
    print(f"  Generating {persona.name} analysis...", flush=True)

    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS_PER_PERSONA,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


def compile_report(
    persona_outputs: dict[str, str],
    report_date: str,
    report_week: str,
) -> str:
    """Combine all persona outputs into a single markdown report."""
    sections = []
    sections.append("# StaffingAgent.ai — Weekly Advisory Board Report")
    sections.append(f"**{report_date}** | {report_week}")
    sections.append(
        "> Generated automatically by the AI Management System. "
        "Each section is an independent analysis from a specialized persona "
        "hardwired to the North Star: highest EBITDA per FTE.\n"
        "> \n"
        "> **Decision filter (apply in order):**\n"
        "> 1. Does it accelerate a signed customer?\n"
        "> 2. Does it improve Assess→Transform conversion rate?\n"
        "> 3. Does it increase GP$ without adding FTE?\n"
        "> 4. Does it reduce a HIGH-severity risk?\n"
    )
    sections.append("---")

    persona_order = [
        "Chief of Staff",  # First: priorities and blockers
        "CFO",             # Second: financial health
        "GTM Lead",        # Third: pipeline
        "Product Lead",    # Fourth: build status
        "Risk Advisor",    # Fifth: risk register
    ]

    for name in persona_order:
        if name in persona_outputs:
            sections.append(f"\n## {name}\n")
            sections.append(persona_outputs[name])
            sections.append("\n---")

    sections.append(
        "\n*This report was generated automatically. "
        "Update `docs/current-state.md` each Sunday to keep analyses current.*"
    )

    return "\n".join(sections)


def main() -> None:
    """Main entrypoint: generate and deliver the weekly advisory report."""
    import os as _os
    dry_run = _os.environ.get("DRY_RUN", "false").lower() == "true"

    print("StaffingAgent AI Advisory Board — Weekly Report")
    print(f"Run time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    if dry_run:
        print("MODE: DRY RUN — report will be printed to logs, no GitHub Issue created")
    print("=" * 60)

    # Load inputs
    print("\nLoading business context and state...")
    try:
        master_context = load_master_context()
        current_state = load_current_state()
        personas = load_personas()
    except (FileNotFoundError, ValueError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Loaded {len(personas)} personas. Calling Claude API...")

    # Initialize Anthropic client
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY environment variable not set.", file=sys.stderr)
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)

    # Generate each persona analysis
    persona_outputs: dict[str, str] = {}
    errors: list[str] = []

    for persona in personas:
        try:
            output = run_persona(client, persona, master_context, current_state)
            persona_outputs[persona.name] = output
            print(f"  ✓ {persona.name} complete ({len(output)} chars)")
        except Exception as e:
            error_msg = f"Failed to generate {persona.name} analysis: {e}"
            print(f"  ✗ ERROR: {error_msg}", file=sys.stderr)
            errors.append(error_msg)
            # Continue with other personas even if one fails
            persona_outputs[persona.name] = (
                f"*{persona.name} analysis unavailable this week due to an error: {e}*"
            )

    # Compile full report
    report_date = get_report_date()
    report_week = get_report_week()
    full_report = compile_report(persona_outputs, report_date, report_week)

    print(f"\nReport compiled ({len(full_report)} chars).")

    # Dry run: print to logs only, skip GitHub Issue creation
    if dry_run:
        print("\n" + "=" * 60)
        print("DRY RUN OUTPUT:")
        print("=" * 60)
        print(full_report)
        print("\n✓ Dry run complete. No GitHub Issue created.")
        return

    print("Delivering via GitHub Issue...")

    # Deliver
    try:
        issue_url = create_github_issue(
            title=f"Weekly Advisory Board — {report_date}",
            body=full_report,
        )
        print(f"\n✓ Report delivered: {issue_url}")
    except Exception as e:
        print(f"\n✗ GitHub Issue delivery failed: {e}", file=sys.stderr)
        # Fall back: print report to stdout so GitHub Actions captures it in logs
        print("\n" + "=" * 60)
        print("REPORT OUTPUT (delivery failed — see logs):")
        print("=" * 60)
        print(full_report)
        sys.exit(1)

    if errors:
        print(f"\nWarnings: {len(errors)} persona(s) had errors (see above).")
        sys.exit(0)  # Partial success — don't fail the workflow

    print("\nAdvisory board report complete.")


if __name__ == "__main__":
    main()
