"""
StaffingAgent API entrypoint. Exposes agent invocations and (optional) gateway endpoints.
Run: uvicorn src.api.main:app --reload
Requires: pip install uvicorn fastapi
"""
import os
from typing import Any, Literal

import asyncpg

# Optional FastAPI — only load if uvicorn runs this module
try:
    from fastapi import FastAPI, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    from pydantic import BaseModel
except ImportError:
    FastAPI = None  # type: ignore
    BaseModel = None  # type: ignore

from src.sync._db import parse_db_url
from src.agents.vms_matching import get_graph as get_vms_matching_graph

if FastAPI is not None:
    app = FastAPI(title="StaffingAgent.ai API", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    async def _get_conn() -> asyncpg.Connection:
        db_url = os.environ["DATABASE_URL"]
        return await asyncpg.connect(**parse_db_url(db_url))

    # ------------------------------------------------------------------ #
    # VMS endpoints                                                        #
    # ------------------------------------------------------------------ #

    @app.get("/vms/records")
    async def list_vms_records(tenant_id: str, limit: int = 200, offset: int = 0) -> dict[str, Any]:
        conn = await _get_conn()
        try:
            rows = await conn.fetch(
                """
                SELECT id, upload_id, vms_platform, placement_ref, candidate_name,
                       week_ending, regular_hours, ot_hours, bill_rate, ot_rate,
                       per_diem, total_amount, status, source_type, created_at
                FROM vms_records
                WHERE tenant_id = $1::uuid
                ORDER BY created_at DESC
                LIMIT $2 OFFSET $3
                """,
                tenant_id, limit, offset,
            )
            total = await conn.fetchval(
                "SELECT COUNT(*) FROM vms_records WHERE tenant_id = $1::uuid", tenant_id
            )
        finally:
            await conn.close()
        return {
            "total": total,
            "records": [dict(r) for r in rows],
        }

    @app.get("/vms/matches")
    async def list_vms_matches(tenant_id: str, status: str | None = None, limit: int = 200, offset: int = 0) -> dict[str, Any]:
        conn = await _get_conn()
        try:
            where = "m.tenant_id = $1::uuid"
            params: list[Any] = [tenant_id]
            if status:
                params.append(status)
                where += f" AND m.status = ${len(params)}"

            rows = await conn.fetch(
                f"""
                SELECT
                    m.id, m.vms_record_id, m.placement_id, m.bullhorn_id,
                    m.confidence, m.match_method, m.name_similarity,
                    m.rate_delta, m.hours_delta, m.financial_impact,
                    m.llm_explanation, m.status, m.review_notes,
                    r.candidate_name, r.week_ending, r.regular_hours,
                    r.ot_hours, r.bill_rate, r.vms_platform, r.placement_ref
                FROM vms_matches m
                JOIN vms_records r ON r.id = m.vms_record_id
                WHERE {where}
                ORDER BY m.confidence ASC NULLS FIRST
                LIMIT ${len(params)+1} OFFSET ${len(params)+2}
                """,
                *params, limit, offset,
            )
            total = await conn.fetchval(
                f"SELECT COUNT(*) FROM vms_matches m WHERE {where}", *params
            )
        finally:
            await conn.close()

        def serialize(r: asyncpg.Record) -> dict[str, Any]:
            d = dict(r)
            for k, v in d.items():
                if hasattr(v, "isoformat"):
                    d[k] = v.isoformat()
                elif hasattr(v, "__str__") and type(v).__name__ in ("UUID", "Decimal"):
                    d[k] = str(v)
            return d

        return {
            "total": total,
            "matches": [serialize(r) for r in rows],
        }

    class MatchReviewBody(BaseModel):
        action: Literal["approved", "rejected", "dismissed"]
        review_notes: str | None = None
        reviewed_by: str | None = None

    @app.patch("/vms/matches/{match_id}")
    async def review_vms_match(match_id: str, body: MatchReviewBody) -> dict[str, Any]:
        conn = await _get_conn()
        try:
            row = await conn.fetchrow(
                """
                UPDATE vms_matches
                SET status = $1, review_notes = $2, reviewed_at = now()
                WHERE id = $3::uuid
                RETURNING id, status, review_notes, reviewed_at
                """,
                body.action, body.review_notes, match_id,
            )
        finally:
            await conn.close()
        if not row:
            raise HTTPException(status_code=404, detail="Match not found")
        d = dict(row)
        if d.get("reviewed_at"):
            d["reviewed_at"] = d["reviewed_at"].isoformat()
        return d

    # ------------------------------------------------------------------ #
    # VMS run matching agent                                               #
    # ------------------------------------------------------------------ #

    @app.post("/vms/run-matching")
    async def run_vms_matching(tenant_id: str, upload_id: str | None = None) -> dict[str, Any]:
        conn = await _get_conn()
        try:
            # Load unmatched VMS records
            where = "tenant_id = $1::uuid AND status = 'pending'"
            params: list[Any] = [tenant_id]
            if upload_id:
                params.append(upload_id)
                where += f" AND upload_id = ${len(params)}::uuid"
            vms_rows = await conn.fetch(
                f"SELECT * FROM vms_records WHERE {where} LIMIT 500", *params
            )
            if not vms_rows:
                return {"message": "No pending VMS records found", "matched": 0}

            # Load placements for name matching
            placement_rows = await conn.fetch(
                """
                SELECT id::text AS placement_id, bullhorn_id,
                       candidate_first,
                       candidate_last,
                       client_name, bill_rate, date_begin AS start_date, date_end AS end_date
                FROM placements
                WHERE tenant_id = $1::uuid AND date_end >= now() - interval '1 year'
                LIMIT 1000
                """,
                tenant_id,
            )

            # Load name aliases
            alias_rows = await conn.fetch(
                "SELECT vms_name, canonical_first, canonical_last, bullhorn_id FROM vms_name_aliases WHERE tenant_id = $1::uuid",
                tenant_id,
            )
        finally:
            await conn.close()

        def row_to_dict(r: asyncpg.Record) -> dict[str, Any]:
            d = dict(r)
            for k, v in d.items():
                if hasattr(v, "isoformat"):
                    d[k] = v.isoformat()
                elif type(v).__name__ in ("UUID", "Decimal"):
                    d[k] = str(v)
            return d

        vms_records = [row_to_dict(r) for r in vms_rows]
        placements = [row_to_dict(r) for r in placement_rows]
        aliases = {r["vms_name"]: dict(r) for r in alias_rows}

        # Run the matching agent
        graph = get_vms_matching_graph()
        result = graph.invoke({
            "tenant_id": tenant_id,
            "vms_records": vms_records,
            "placements": placements,
            "aliases": aliases,
        })

        matches: list[dict] = result.get("matches") or []

        # Persist matches to vms_matches
        conn = await _get_conn()
        try:
            inserted = 0
            for m in matches:
                vms_record_id = m.get("id")
                if not vms_record_id:
                    continue
                await conn.execute(
                    """
                    INSERT INTO vms_matches (
                        tenant_id, vms_record_id, placement_id, bullhorn_id,
                        confidence, match_method, name_similarity,
                        rate_delta, hours_delta, financial_impact,
                        llm_explanation, status
                    ) VALUES (
                        $1::uuid, $2::uuid,
                        $3::uuid,
                        $4, $5, $6, $7, $8, $9, $10, $11,
                        CASE WHEN $5 >= 0.95 THEN 'approved' ELSE 'pending' END
                    )
                    ON CONFLICT DO NOTHING
                    """,
                    tenant_id,
                    str(vms_record_id),
                    m.get("matched_placement_id"),
                    m.get("matched_bullhorn_id"),
                    float(m.get("confidence") or 0),
                    m.get("match_method") or "unmatched",
                    float(m.get("name_similarity") or 0),
                    float(m.get("rate_delta") or 0) if m.get("rate_delta") is not None else None,
                    float(m.get("hours_delta") or 0) if m.get("hours_delta") is not None else None,
                    abs(float(m.get("rate_delta") or 0)) * float(m.get("regular_hours") or 40) if m.get("rate_delta") else None,
                    m.get("explanation"),
                )
                inserted += 1
        finally:
            await conn.close()

        summary = result.get("result") or {}
        return {
            "message": f"Matching complete. {inserted} matches persisted.",
            "matched": inserted,
            **summary,
        }

    # ------------------------------------------------------------------ #
    # VMS uploads                                                          #
    # ------------------------------------------------------------------ #

    @app.get("/vms/uploads")
    async def list_vms_uploads(tenant_id: str) -> dict[str, Any]:
        conn = await _get_conn()
        try:
            rows = await conn.fetch(
                """
                SELECT id, filename, vms_platform, record_count, status,
                       error_message, created_at, completed_at
                FROM vms_uploads
                WHERE tenant_id = $1::uuid
                ORDER BY created_at DESC
                LIMIT 50
                """,
                tenant_id,
            )
        finally:
            await conn.close()

        def serialize(r: asyncpg.Record) -> dict[str, Any]:
            d = dict(r)
            for k, v in d.items():
                if hasattr(v, "isoformat"):
                    d[k] = v.isoformat()
                elif type(v).__name__ in ("UUID",):
                    d[k] = str(v)
            return d

        return {"uploads": [serialize(r) for r in rows]}

    # ------------------------------------------------------------------ #
    # Health                                                               #
    # ------------------------------------------------------------------ #

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

else:
    app = None  # type: ignore


