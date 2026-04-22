"""
VMS Matching Agent — 3-node pipeline:
  1. fast_match_node  : alias lookup + exact + Levenshtein fuzzy (no LLM)
  2. llm_match_node   : Claude handles what fast_match couldn't resolve
  3. persist_node     : combines all matches, sets confidence tiers

Human-in-the-loop happens at the API layer after persist_node writes to DB.
"""
import json
import re
from typing import Any

from langgraph.graph import END, StateGraph

from src.agents.vms_matching.prompts import VMS_MATCHING_SYSTEM
import asyncio

from src.shared.llm import invoke_claude, invoke_llm, usage_update
from src.shared.state import VMSMatchingState, as_dict

# Confidence thresholds
AUTO_ACCEPT = 0.95   # write as approved, no review needed
NEEDS_REVIEW = 0.70  # write as pending
# below NEEDS_REVIEW → pending with low confidence flag


# ---------------------------------------------------------------------------
# Levenshtein distance (no external deps)
# ---------------------------------------------------------------------------

def _levenshtein(a: str, b: str) -> int:
    a, b = a.lower(), b.lower()
    if a == b:
        return 0
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a):
        curr = [i + 1]
        for j, cb in enumerate(b):
            curr.append(min(prev[j + 1] + 1, curr[j] + 1, prev[j] + (0 if ca == cb else 1)))
        prev = curr
    return prev[-1]


def _name_similarity(vms_name: str, first: str, last: str) -> float:
    """Return 0.0–1.0 similarity between a VMS name string and a canonical first+last."""
    if not vms_name or not first or not last:
        return 0.0

    canonical = f"{first} {last}".lower().strip()
    vms = vms_name.lower().strip()

    if vms == canonical:
        return 1.0

    # Try common formats
    variants = [
        f"{first} {last}",
        f"{last} {first}",
        f"{last}, {first}",
        f"{first[0]}. {last}",
        f"{first[0]} {last}",
        f"{last} {first[0]}.",
    ]
    for v in variants:
        if vms == v.lower():
            return 0.97

    # Levenshtein over full name
    max_len = max(len(canonical), len(vms), 1)
    dist = _levenshtein(canonical, vms)
    similarity = 1.0 - (dist / max_len)
    return round(max(0.0, similarity), 3)


def _normalize(name: str) -> str:
    return " ".join(name.lower().split())


# ---------------------------------------------------------------------------
# Node 1: Fast matching (alias + exact + fuzzy)
# ---------------------------------------------------------------------------

def fast_match_node(state: dict[str, Any]) -> dict[str, Any]:
    state = as_dict(state)
    vms_records: list[dict] = state.get("vms_records") or []
    placements: list[dict] = state.get("placements") or []
    aliases: dict = state.get("aliases") or {}

    resolved = []
    unresolved = []

    for rec in vms_records:
        vms_name = (rec.get("candidate_name") or "").strip()
        vms_rate = float(rec.get("bill_rate") or 0)
        best_match = None
        best_score = 0.0

        # --- Step 1: alias lookup (exact string match on learned corrections)
        alias = aliases.get(_normalize(vms_name))
        if alias:
            # find the placement matching this alias
            for p in placements:
                if p.get("bullhorn_id") == alias.get("bullhorn_id"):
                    sim = _name_similarity(vms_name, alias["canonical_first"], alias["canonical_last"])
                    rate_delta = round(vms_rate - float(p.get("bill_rate") or 0), 2)
                    resolved.append({
                        **rec,
                        "matched_placement_id": p.get("placement_id"),
                        "matched_bullhorn_id": p.get("bullhorn_id"),
                        "confidence": 0.98,
                        "match_method": "alias",
                        "name_similarity": sim,
                        "rate_delta": rate_delta,
                        "hours_delta": 0.0,
                        "explanation": f"Matched via learned alias: '{vms_name}' → {alias['canonical_first']} {alias['canonical_last']}",
                    })
                    best_match = "found"
                    break
            if best_match:
                continue

        # --- Step 2: exact + fuzzy name match
        for p in placements:
            sim = _name_similarity(
                vms_name,
                p.get("candidate_first") or "",
                p.get("candidate_last") or "",
            )
            if sim > best_score:
                best_score = sim
                best_placement = p

        if best_score >= 0.85:
            rate_delta = round(vms_rate - float(best_placement.get("bill_rate") or 0), 2)
            method = "exact" if best_score >= 0.999 else "fuzzy"
            resolved.append({
                **rec,
                "matched_placement_id": best_placement.get("placement_id"),
                "matched_bullhorn_id": best_placement.get("bullhorn_id"),
                "confidence": round(best_score * 0.97, 3),  # slight discount vs alias
                "match_method": method,
                "name_similarity": best_score,
                "rate_delta": rate_delta,
                "hours_delta": 0.0,
                "explanation": f"Name similarity {best_score:.2f} ({method})",
            })
        else:
            unresolved.append(rec)

    return {
        "resolved": resolved,
        "unresolved": unresolved,
    }


# ---------------------------------------------------------------------------
# Node 2: LLM matching for unresolved records
# ---------------------------------------------------------------------------

def llm_match_node(state: dict[str, Any]) -> dict[str, Any]:
    state = as_dict(state)
    unresolved: list[dict] = state.get("unresolved") or []
    placements: list[dict] = state.get("placements") or []
    prior_usage = state.get("token_usage") or []

    if not unresolved:
        return {"llm_matches": [], **usage_update(None, prior_usage)}

    # Trim placements payload to keep token count manageable
    slim_placements = [
        {
            "placement_id": p.get("placement_id"),
            "bullhorn_id": p.get("bullhorn_id"),
            "candidate_first": p.get("candidate_first"),
            "candidate_last": p.get("candidate_last"),
            "client_name": p.get("client_name"),
            "bill_rate": p.get("bill_rate"),
            "start_date": str(p.get("start_date") or ""),
            "end_date": str(p.get("end_date") or ""),
        }
        for p in placements[:200]
    ]

    slim_unresolved = [
        {
            "vms_id": str(r.get("id")),
            "vms_name": r.get("candidate_name"),
            "week_ending": str(r.get("week_ending") or ""),
            "regular_hours": r.get("regular_hours"),
            "ot_hours": r.get("ot_hours"),
            "bill_rate": r.get("bill_rate"),
            "placement_ref": r.get("placement_ref"),
            "vms_platform": r.get("vms_platform"),
        }
        for r in unresolved
    ]

    user_content = (
        f"Match these {len(slim_unresolved)} unresolved VMS records to Bullhorn placements.\n\n"
        f"Unresolved VMS records:\n{json.dumps(slim_unresolved, default=str)}\n\n"
        f"Available placements:\n{json.dumps(slim_placements, default=str)}\n\n"
        "Return one JSON object with keys: matches, unmatched, summary."
    )

    try:
        content, usage = asyncio.get_event_loop().run_until_complete(invoke_llm(
            [{"role": "user", "content": user_content}],
            task_type="structured_matching",
            system=VMS_MATCHING_SYSTEM,
            tenant_id=state.get("tenant_id"),
        ))
    except Exception as e:
        # Fallback: try direct Claude call if router fails entirely
        try:
            content, usage = invoke_claude(
                [{"role": "user", "content": user_content}],
                system=VMS_MATCHING_SYSTEM,
            )
        except Exception as e2:
            return {"error": str(e2), "llm_matches": [], **usage_update(None, prior_usage)}

    text = content.strip()
    for pattern in [r"```json\s*(.*?)\s*```", r"```\s*(.*?)\s*```", r"(\{.*\})"]:
        m = re.search(pattern, text, re.DOTALL)
        if m:
            text = m.group(1).strip()
            break

    try:
        out = json.loads(text)
    except json.JSONDecodeError:
        out = {"matches": [], "unmatched": [], "summary": content}

    # Enrich LLM matches with method tag and map vms_id back to original record
    id_to_record = {str(r.get("id")): r for r in unresolved}
    llm_matches = []
    for m in out.get("matches", []):
        orig = id_to_record.get(str(m.get("vms_id"))) or {}
        llm_matches.append({
            **orig,
            "matched_placement_id": m.get("placement_id"),
            "matched_bullhorn_id": m.get("bullhorn_id"),
            "confidence": float(m.get("confidence", 0.0)),
            "match_method": "llm",
            "name_similarity": float(m.get("name_similarity", 0.0)),
            "rate_delta": float(m.get("rate_delta", 0.0)),
            "hours_delta": 0.0,
            "explanation": m.get("explanation", ""),
        })

    # Records LLM couldn't match
    unmatched_ids = set(str(x) for x in out.get("unmatched", []))
    for r in unresolved:
        if str(r.get("id")) in unmatched_ids:
            llm_matches.append({
                **r,
                "matched_placement_id": None,
                "matched_bullhorn_id": None,
                "confidence": 0.0,
                "match_method": "unmatched",
                "name_similarity": 0.0,
                "rate_delta": None,
                "hours_delta": None,
                "explanation": "No match found by LLM",
            })

    return {
        "llm_matches": llm_matches,
        **usage_update(usage, prior_usage),
    }


# ---------------------------------------------------------------------------
# Node 3: Combine all matches
# ---------------------------------------------------------------------------

def combine_node(state: dict[str, Any]) -> dict[str, Any]:
    state = as_dict(state)
    resolved: list[dict] = state.get("resolved") or []
    llm_matches: list[dict] = state.get("llm_matches") or []
    all_matches = resolved + llm_matches

    # Flag any that need human review
    needs_review = any(
        m.get("match_method") != "unmatched" and float(m.get("confidence") or 0) < AUTO_ACCEPT
        for m in all_matches
    )

    return {
        "matches": all_matches,
        "human_review_required": needs_review,
        "result": {
            "total": len(all_matches),
            "auto_accepted": sum(1 for m in all_matches if float(m.get("confidence") or 0) >= AUTO_ACCEPT),
            "needs_review": sum(1 for m in all_matches if NEEDS_REVIEW <= float(m.get("confidence") or 0) < AUTO_ACCEPT),
            "low_confidence": sum(1 for m in all_matches if 0 < float(m.get("confidence") or 0) < NEEDS_REVIEW),
            "unmatched": sum(1 for m in all_matches if m.get("match_method") == "unmatched"),
        },
    }


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------

def _should_run_llm(state: dict[str, Any]) -> str:
    s = as_dict(state)
    return "llm_match" if s.get("unresolved") else "combine"


def get_graph():
    graph = StateGraph(VMSMatchingState)
    graph.add_node("fast_match", fast_match_node)
    graph.add_node("llm_match", llm_match_node)
    graph.add_node("combine", combine_node)
    graph.set_entry_point("fast_match")
    graph.add_conditional_edges("fast_match", _should_run_llm, ["llm_match", "combine"])
    graph.add_edge("llm_match", "combine")
    graph.add_edge("combine", END)
    return graph.compile()
