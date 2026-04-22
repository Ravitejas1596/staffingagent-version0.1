"""
Bullhorn pay/bill data sync.

Fetches Placements, Timesheets, and TimesheetEntries from Bullhorn
and upserts them into the StaffingAgent database.

Usage:
    python -m src.sync.bullhorn_sync                             # uses STAFFINGAGENT_TENANT env
    python -m src.sync.bullhorn_sync --tenant-id <slug>          # specific tenant
    python -m src.sync.bullhorn_sync --entity placements         # single entity only

Required env vars: BULLHORN_* (see bullhorn_auth.py), DATABASE_URL
"""
from __future__ import annotations

import argparse
import asyncio
import datetime
import logging
import os
from typing import Any

import asyncpg

from src.sync._db import parse_db_url
from src.sync.bullhorn_auth import BullhornSession, bullhorn_query, bullhorn_search, get_session

log = logging.getLogger("bullhorn_sync")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(levelname)s %(name)s %(message)s")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Used to find all fields...
# https://github.com/bullhorn/sdk-rest/tree/master/src/main/java/com/bullhornsdk/data/model/entity

PAGE_SIZE = 500

BILLABLE_CHARGE_FIELDS = (
    "id,dateAdded,dateLastModified,periodEndDate,subtotal,isInvoiced,"
    "status(id,label),"
    "transactionStatus(id,name),"
    "transactionType(id,name),"
    "candidate(id,firstName,lastName),"
    "clientCorporation(id,name),"
    "placement(id),"
    "jobOrder(id,title),"
    "timesheet(id),"
    "billingClientContact(id,firstName,lastName),"
    "billingClientCorporation(id,name),"
    "currencyUnit,"
    "entryTypeLookup(id,label),"
    "externalID,"
    "description,"
    "generalLedgerSegment1(id,externalSegmentNumber,externalSegmentName),"
    "generalLedgerSegment2(id,externalSegmentNumber,externalSegmentName),"
    "generalLedgerSegment3(id,externalSegmentNumber,externalSegmentName),"
    "generalLedgerSegment4(id,externalSegmentNumber,externalSegmentName),"
    "generalLedgerSegment5(id,externalSegmentNumber,externalSegmentName),"
    "generalLedgerServiceCode,"
    "hasRebill,"
    "invoiceTerm(id),"
    "hasAdjustment,"
    "billingProfile(id,title)"
)

BILL_MASTER_FIELDS = (
    "id,dateAdded,dateLastModified,transactionDate,"
    "chargeTypeLookup(id,label),"
    "transactionStatus(id,name),"
    "billableCharge(id),"
    "earnCode(id,externalID,title),"
    "billingSyncBatch(id),"
    "canInvoice,"
    "externalID"
)

BILL_MASTER_TRANSACTION_FIELDS = (
    "id,dateAdded,dateLastModified,amount,quantity,rate,netAmount,netQuantity,"
    "recordingDate,payPeriodEndDate,isDeleted,isUnbillable,needsReview,"
    "transactionType(id,name),"
    "transactionOrigin(id,name),"
    "billMaster(id),"
    "unitOfMeasure(id,label),"
    "accountingPeriod(id,accountingPeriodDate),"
    "isCustomRate,"
    "wasUnbilled"
)

PAYABLE_CHARGE_FIELDS = (
    "id,dateAdded,dateLastModified,periodEndDate,subtotal,"
    "status(id,label),"
    "transactionStatus(id,name),"
    "transactionType(id,name),"
    "candidate(id,firstName,lastName),"
    "clientCorporation(id,name),"
    "placement(id),"
    "jobOrder(id,title),"
    "timesheet(id),"
    "currencyUnit,"
    "entryTypeLookup(id,label),"
    "externalID,"
    "description,"
    "generalLedgerSegment1(id,externalSegmentNumber,externalSegmentName),"
    "generalLedgerSegment2(id,externalSegmentNumber,externalSegmentName),"
    "generalLedgerSegment3(id,externalSegmentNumber,externalSegmentName),"
    "generalLedgerSegment4(id,externalSegmentNumber,externalSegmentName),"
    "generalLedgerSegment5(id,externalSegmentNumber,externalSegmentName),"
    "generalLedgerServiceCode,"
    "hasAdjustment"
)

PAY_MASTER_FIELDS = (
    "id,dateAdded,dateLastModified,transactionDate,"
    "chargeTypeLookup(id,label),"
    "transactionStatus(id,name),"
    "payableCharge(id),"
    "earnCode(id,externalID,title),"
    "externalID"
)

PAY_MASTER_TRANSACTION_FIELDS = (
    "id,dateAdded,dateLastModified,amount,quantity,rate,netAmount,netQuantity,"
    "recordingDate,payPeriodEndDate,isDeleted,"
    "transactionType(id,name),"
    "transactionOrigin(id,name),"
    "payMaster(id),"
    "unitOfMeasure(id,label),"
    "accountingPeriod(id,accountingPeriodDate),"
    "isCustomRate"
)

CANDIDATE_FIELDS = (
    "id,firstName,lastName,name,email,mobile,phone,status,dateAdded,"
    "owner(id,firstName,lastName)"
)

CLIENT_CORPORATION_FIELDS = (
    "id,name,companyURL,dateAdded,dateLastModified,status,"
    "phone,fax,billingPhone,externalID,"
    "numEmployees,revenue,annualRevenue,feeArrangement,taxRate,workWeekStart,"
    "billingFrequency,invoiceFormat,ownership,tickerSymbol,dateFounded,"
    "twitterHandle,linkedinProfileName,facebookProfileName,"
    "address(address1,address2,city,state,zip),"
    "billingAddress(address1,address2,city,state,zip),"
    "parentClientCorporation(id,name),"
    "department(id,name),"
    "branch(id,name),"
    "customFloat1,customFloat2,customFloat3,"
    "customDate1,customDate2,customDate3,"
    "customInt1,customInt2,customInt3,"
    "customText1,customText2,customText3,customText4,customText5,customText6,customText7,customText8,customText9,customText10,"
    "customText11,customText12,customText13,customText14,customText15,customText16,customText17,customText18,customText19,customText20,"
    "customTextBlock1,customTextBlock2,customTextBlock3,customTextBlock4,customTextBlock5"
)

JOB_ORDER_FIELDS = (
    "id,title,status,numOpenings,isOpen,isDeleted,isWorkFromHome,willRelocate,willSponsor,"
    "dateAdded,dateLastModified,dateLastPublished,dateClosed,dateEnd,startDate,"
    "employmentType,type,source,onSite,travelRequirements,yearsRequired,"
    "payRate,clientBillRate,salary,salaryUnit,durationWeeks,hoursPerWeek,taxStatus,"
    "description,publicDescription,externalID,reportTo,"
    "address(address1,address2,city,state,zip),"
    "clientCorporation(id,name),"
    "clientContact(id,firstName,lastName),"
    "owner(id,firstName,lastName),"
    "branch(id,name),"
    "customDate1,customDate2,customDate3,"
    "customFloat1,customFloat2,customFloat3,"
    "customInt1,customInt2,customInt3,"
    "customText1,customText2,customText3,customText4,customText5,"
    "customText6,customText7,customText8,customText9,customText10,"
    "customText11,customText12,customText13,customText14,customText15,"
    "customText16,customText17,customText18,customText19,customText20,"
    "customTextBlock1,customTextBlock2,customTextBlock3,customTextBlock4,customTextBlock5"
)

PLACEMENT_FIELDS = (
    "id,dateAdded,dateLastModified,status,employmentType,employeeType,isWorkFromHome,"
    "payRate,clientBillRate,overtimeRate,clientOvertimeRate,salary,salaryUnit,"
    "fee,flatFee,markUpPercentage,overtimeMarkUpPercentage,otExemption,"
    "dateBegin,dateEnd,dateClientEffective,dateEffective,estimatedEndDate,employmentStartDate,"
    "durationWeeks,hoursPerDay,hoursOfOperation,workWeekStart,timesheetCycle,"
    "billingFrequency,taxRate,taxState,costCenter,positionCode,reportTo,comments,"
    "terminationReason,quitJob,payrollEmployeeType,payGroup,"
    "generalLedgerSegment1(id,externalSegmentNumber,externalSegmentName),"
    "generalLedgerSegment2(id,externalSegmentNumber,externalSegmentName),"
    "generalLedgerSegment3(id,externalSegmentNumber,externalSegmentName),"
    "generalLedgerSegment4(id,externalSegmentNumber,externalSegmentName),"
    "generalLedgerSegment5(id,externalSegmentNumber,externalSegmentName),"
    "candidate(id,firstName,lastName),"
    "jobOrder(id,title),"
    "clientContact(id,firstName,lastName),"
    "clientCorporation(id,name),"
    "owner(id,firstName,lastName),"
    "branch(id,name),"
    "vendorClientCorporation(id,name),"
    "customDate1,customDate2,customDate3,"
    "customFloat1,customFloat2,customFloat3,"
    "customInt1,customInt2,customInt3,"
    "customText1,customText2,customText3,customText4,customText5,"
    "customText6,customText7,customText8,customText9,customText10,"
    "customText11,customText12,customText13,customText14,customText15,"
    "customText16,customText17,customText18,customText19,customText20,"
    "customTextBlock1,customTextBlock2,customTextBlock3,customTextBlock4,customTextBlock5"
)

TIMESHEET_FIELDS = (
    "id,dateAdded,dateLastModified,hoursWorked,additionalBillAmount,additionalPayAmount,"
    "approvedDate,endDate,evaluationState,processingStatus,"
    "timesheetEntryApprovalStatusLookup,"
    "candidate(id,firstName,lastName),"
    "placement(id),"
    "jobOrder(id,title),"
    "clientCorporation(id,name)"
)

TIMESHEET_ENTRY_FIELDS = (
    "id,dateAdded,dateLastModified,applicableFrom,applicableTo,"
    "quantity,billRate,payRate,comment,"
    "timesheetEntryApprovalStatusLookup,"
    "timesheet(id),"
    "earnCode(id,code)"
)


INVOICE_FIELDS = (
    "id,dateAdded,dateLastModified,invoiceStatementNumber,subtotal,total,status,"
    "invoiceStatementDate,isFinalized,"
    "clientCorporation(id,name),"
    "invoiceTerm(id)"
)


def _ms_to_date(val: int | str | None) -> datetime.date | None:
    """Convert a Bullhorn date value to a Python date.
    Bullhorn returns either millisecond timestamps (int) or ISO strings (str)."""
    if val is None:
        return None
    if isinstance(val, str):
        try:
            return datetime.date.fromisoformat(val[:10])
        except ValueError:
            return None
    try:
        return datetime.datetime.fromtimestamp(val / 1000, tz=datetime.timezone.utc).date()
    except (OSError, ValueError, OverflowError, TypeError):
        return None


def _lookup(val: Any) -> str | None:
    """Extract label from a Bullhorn lookup object like {'id': 5, 'label': 'Failed'}, or return as-is if string."""
    if val is None:
        return None
    if isinstance(val, dict):
        return val.get("label") or val.get("name")
    return str(val)


def _nested(obj: Any, *keys: str, default: Any = None) -> Any:
    """Safely traverse nested dicts: _nested(row, 'candidate', 'firstName')."""
    for key in keys:
        if not isinstance(obj, dict):
            return default
        obj = obj.get(key, default)
    return obj


async def _search_all(session: BullhornSession, entity: str, fields: str, query: str = "id:[1 TO *]") -> list[dict]:
    """Page through all records using the /search endpoint (for indexed entities like Candidate)."""
    records: list[dict] = []
    start = 0
    while True:
        page = await bullhorn_search(session, entity, fields, query=query, count=PAGE_SIZE, start=start)
        batch = page.get("data", [])
        records.extend(batch)
        log.info("  %s: fetched %d records (total so far: %d)", entity, len(batch), len(records))
        if len(batch) < PAGE_SIZE:
            break
        start += PAGE_SIZE
    return records


async def _get_last_synced(conn: asyncpg.Connection, tenant_id: str, entity: str) -> datetime.datetime | None:
    row = await conn.fetchrow(
        "SELECT last_synced_at FROM sync_state WHERE tenant_id=$1::uuid AND entity=$2",
        tenant_id, entity,
    )
    return row["last_synced_at"] if row else None


async def _record_sync(conn: asyncpg.Connection, tenant_id: str, entity: str, count: int) -> None:
    now = datetime.datetime.now(datetime.timezone.utc)
    await conn.execute(
        """
        INSERT INTO sync_state (tenant_id, entity, last_synced_at)
        VALUES ($1::uuid, $2, $3)
        ON CONFLICT (tenant_id, entity) DO UPDATE SET last_synced_at = EXCLUDED.last_synced_at
        """,
        tenant_id, entity, now,
    )
    await conn.execute(
        """
        INSERT INTO sync_history (tenant_id, entity, sync_date, record_count, synced_at)
        VALUES ($1::uuid, $2, $3, $4, $5)
        """,
        tenant_id, entity, now.date(), count, now,
    )


async def _fetch_all(session: BullhornSession, entity: str, fields: str, where: str = "id>0") -> list[dict]:
    """Page through all records for an entity."""
    records: list[dict] = []
    start = 0
    while True:
        page = await bullhorn_query(session, entity, fields, where=where, count=PAGE_SIZE, start=start)
        batch = page.get("data", [])
        records.extend(batch)
        log.info("  %s: fetched %d records (total so far: %d)", entity, len(batch), len(records))
        if len(batch) < PAGE_SIZE:
            break
        start += PAGE_SIZE
    return records


# ---------------------------------------------------------------------------
# Upsert functions
# ---------------------------------------------------------------------------

async def sync_placements(conn: asyncpg.Connection, tenant_id: str, records: list[dict]) -> int:
    def _num(val):
        if val is None or val == "":
            return None
        return val

    def _text(val):
        if isinstance(val, list):
            return ", ".join(str(v) for v in val) if val else None
        return val

    def _gl(r: dict, key: str, field: str):
        seg = r.get(key)
        if isinstance(seg, dict):
            return seg.get(field)
        return None

    rows = []
    for r in records:
        rows.append((
            tenant_id, r["id"],
            r.get("status"),
            r.get("employmentType"),
            r.get("employeeType"),
            r.get("isWorkFromHome"),
            _ms_to_date(r.get("dateAdded")),
            _ms_to_date(r.get("dateLastModified")),
            _ms_to_date(r.get("dateBegin")),
            _ms_to_date(r.get("dateEnd")),
            _ms_to_date(r.get("dateClientEffective")),
            _ms_to_date(r.get("dateEffective")),
            _ms_to_date(r.get("estimatedEndDate")),
            _ms_to_date(r.get("employmentStartDate")),
            _num(r.get("payRate")),
            _num(r.get("clientBillRate")),
            _num(r.get("overtimeRate")),
            _num(r.get("clientOvertimeRate")),
            _num(r.get("salary")),
            r.get("salaryUnit"),
            _num(r.get("fee")),
            _num(r.get("flatFee")),
            _num(r.get("markUpPercentage")),
            _num(r.get("overtimeMarkUpPercentage")),
            str(r["otExemption"]) if r.get("otExemption") is not None else None,
            _num(r.get("durationWeeks")),
            _num(r.get("hoursPerDay")),
            r.get("hoursOfOperation"),
            r.get("workWeekStart"),
            _lookup(r.get("timesheetCycle")),
            r.get("billingFrequency"),
            _num(r.get("taxRate")),
            r.get("taxState"),
            r.get("costCenter"),
            r.get("positionCode"),
            r.get("reportTo"),
            r.get("comments"),
            r.get("terminationReason"),
            r.get("quitJob"),
            r.get("payrollEmployeeType"),
            r.get("payGroup"),
            _gl(r, "generalLedgerSegment1", "externalSegmentNumber"),
            _gl(r, "generalLedgerSegment1", "externalSegmentName"),
            _gl(r, "generalLedgerSegment2", "externalSegmentNumber"),
            _gl(r, "generalLedgerSegment2", "externalSegmentName"),
            _gl(r, "generalLedgerSegment3", "externalSegmentNumber"),
            _gl(r, "generalLedgerSegment3", "externalSegmentName"),
            _gl(r, "generalLedgerSegment4", "externalSegmentNumber"),
            _gl(r, "generalLedgerSegment4", "externalSegmentName"),
            _gl(r, "generalLedgerSegment5", "externalSegmentNumber"),
            _gl(r, "generalLedgerSegment5", "externalSegmentName"),
            _nested(r, "candidate", "id"),
            _nested(r, "candidate", "firstName"),
            _nested(r, "candidate", "lastName"),
            _nested(r, "jobOrder", "id"),
            _nested(r, "jobOrder", "title"),
            _nested(r, "clientContact", "id"),
            _nested(r, "clientContact", "firstName"),
            _nested(r, "clientContact", "lastName"),
            _nested(r, "clientCorporation", "id"),
            _nested(r, "clientCorporation", "name"),
            _nested(r, "owner", "id"),
            _nested(r, "owner", "firstName"),
            _nested(r, "owner", "lastName"),
            _nested(r, "branch", "id"),
            _nested(r, "branch", "name"),
            _nested(r, "vendorClientCorporation", "id"),
            _nested(r, "vendorClientCorporation", "name"),
            _ms_to_date(r.get("customDate1")), _ms_to_date(r.get("customDate2")), _ms_to_date(r.get("customDate3")),
            _num(r.get("customFloat1")), _num(r.get("customFloat2")), _num(r.get("customFloat3")),
            _num(r.get("customInt1")), _num(r.get("customInt2")), _num(r.get("customInt3")),
            _text(r.get("customText1")), _text(r.get("customText2")), _text(r.get("customText3")),
            _text(r.get("customText4")), _text(r.get("customText5")), _text(r.get("customText6")),
            _text(r.get("customText7")), _text(r.get("customText8")), _text(r.get("customText9")),
            _text(r.get("customText10")), _text(r.get("customText11")), _text(r.get("customText12")),
            _text(r.get("customText13")), _text(r.get("customText14")), _text(r.get("customText15")),
            _text(r.get("customText16")), _text(r.get("customText17")), _text(r.get("customText18")),
            _text(r.get("customText19")), _text(r.get("customText20")),
            _text(r.get("customTextBlock1")), _text(r.get("customTextBlock2")), _text(r.get("customTextBlock3")),
            _text(r.get("customTextBlock4")), _text(r.get("customTextBlock5")),
        ))

    await conn.executemany(
        """
        INSERT INTO placements (
            tenant_id, bullhorn_id,
            status, employment_type, employee_type, is_work_from_home,
            date_added, date_last_modified, start_date, end_date,
            date_client_effective, date_effective, estimated_end_date, employment_start_date,
            pay_rate, bill_rate, ot_pay_rate, ot_bill_rate,
            salary, salary_unit, fee, flat_fee,
            mark_up_percentage, overtime_mark_up_percentage, ot_exemption,
            duration_weeks, hours_per_day, hours_of_operation, work_week_start, timesheet_cycle,
            billing_frequency, tax_rate, tax_state, cost_center, position_code,
            report_to, comments, termination_reason, quit_job, payroll_employee_type, pay_group,
            gl_segment1_number, gl_segment1_name,
            gl_segment2_number, gl_segment2_name,
            gl_segment3_number, gl_segment3_name,
            gl_segment4_number, gl_segment4_name,
            gl_segment5_number, gl_segment5_name,
            candidate_bullhorn_id, candidate_first, candidate_last,
            job_order_bullhorn_id, job_title,
            client_contact_id, client_contact_first, client_contact_last,
            client_corporation_id, client_corporation_name,
            owner_bullhorn_id, owner_first, owner_last,
            branch_id, branch_name,
            vendor_client_corporation_id, vendor_client_corporation_name,
            custom_date1, custom_date2, custom_date3,
            custom_float1, custom_float2, custom_float3,
            custom_int1, custom_int2, custom_int3,
            custom_text1, custom_text2, custom_text3, custom_text4, custom_text5,
            custom_text6, custom_text7, custom_text8, custom_text9, custom_text10,
            custom_text11, custom_text12, custom_text13, custom_text14, custom_text15,
            custom_text16, custom_text17, custom_text18, custom_text19, custom_text20,
            custom_text_block1, custom_text_block2, custom_text_block3,
            custom_text_block4, custom_text_block5,
            raw_data, synced_at, updated_at
        )
        SELECT
            $1::uuid,$2,$3,$4,$5,$6,$7,$8,$9,$10,
            $11,$12,$13,$14,$15,$16,$17,$18,$19,$20,
            $21,$22,$23,$24,$25,$26,$27,$28,$29,$30,
            $31,$32,$33,$34,$35,$36,$37,$38,$39,$40,$41,
            $42,$43,$44,$45,$46,$47,$48,$49,$50,$51,
            $52,$53,$54,$55,$56,$57,$58,$59,$60,$61,
            $62,$63,$64,$65,$66,$67,$68,
            $69,$70,$71,$72,$73,$74,$75,$76,$77,
            $78,$79,$80,$81,$82,$83,$84,$85,$86,$87,
            $88,$89,$90,$91,$92,$93,$94,$95,$96,$97,
            $98,$99,$100,$101,$102,
            '{}'::jsonb, now(), now()
        ON CONFLICT (tenant_id, bullhorn_id) DO UPDATE SET
            status                          = EXCLUDED.status,
            employment_type                 = EXCLUDED.employment_type,
            employee_type                   = EXCLUDED.employee_type,
            is_work_from_home               = EXCLUDED.is_work_from_home,
            date_last_modified              = EXCLUDED.date_last_modified,
            start_date                      = EXCLUDED.start_date,
            end_date                        = EXCLUDED.end_date,
            date_client_effective           = EXCLUDED.date_client_effective,
            date_effective                  = EXCLUDED.date_effective,
            estimated_end_date              = EXCLUDED.estimated_end_date,
            employment_start_date           = EXCLUDED.employment_start_date,
            pay_rate                        = EXCLUDED.pay_rate,
            bill_rate                       = EXCLUDED.bill_rate,
            ot_pay_rate                     = EXCLUDED.ot_pay_rate,
            ot_bill_rate                    = EXCLUDED.ot_bill_rate,
            salary                          = EXCLUDED.salary,
            salary_unit                     = EXCLUDED.salary_unit,
            fee                             = EXCLUDED.fee,
            flat_fee                        = EXCLUDED.flat_fee,
            mark_up_percentage              = EXCLUDED.mark_up_percentage,
            overtime_mark_up_percentage     = EXCLUDED.overtime_mark_up_percentage,
            ot_exemption                    = EXCLUDED.ot_exemption,
            duration_weeks                  = EXCLUDED.duration_weeks,
            hours_per_day                   = EXCLUDED.hours_per_day,
            hours_of_operation              = EXCLUDED.hours_of_operation,
            work_week_start                 = EXCLUDED.work_week_start,
            timesheet_cycle                 = EXCLUDED.timesheet_cycle,
            billing_frequency               = EXCLUDED.billing_frequency,
            tax_rate                        = EXCLUDED.tax_rate,
            tax_state                       = EXCLUDED.tax_state,
            cost_center                     = EXCLUDED.cost_center,
            position_code                   = EXCLUDED.position_code,
            report_to                       = EXCLUDED.report_to,
            comments                        = EXCLUDED.comments,
            termination_reason              = EXCLUDED.termination_reason,
            quit_job                        = EXCLUDED.quit_job,
            payroll_employee_type           = EXCLUDED.payroll_employee_type,
            pay_group                       = EXCLUDED.pay_group,
            gl_segment1_number              = EXCLUDED.gl_segment1_number,
            gl_segment1_name                = EXCLUDED.gl_segment1_name,
            gl_segment2_number              = EXCLUDED.gl_segment2_number,
            gl_segment2_name                = EXCLUDED.gl_segment2_name,
            gl_segment3_number              = EXCLUDED.gl_segment3_number,
            gl_segment3_name                = EXCLUDED.gl_segment3_name,
            gl_segment4_number              = EXCLUDED.gl_segment4_number,
            gl_segment4_name                = EXCLUDED.gl_segment4_name,
            gl_segment5_number              = EXCLUDED.gl_segment5_number,
            gl_segment5_name                = EXCLUDED.gl_segment5_name,
            candidate_bullhorn_id           = EXCLUDED.candidate_bullhorn_id,
            candidate_first                 = EXCLUDED.candidate_first,
            candidate_last                  = EXCLUDED.candidate_last,
            job_order_bullhorn_id           = EXCLUDED.job_order_bullhorn_id,
            job_title                       = EXCLUDED.job_title,
            client_contact_id               = EXCLUDED.client_contact_id,
            client_contact_first            = EXCLUDED.client_contact_first,
            client_contact_last             = EXCLUDED.client_contact_last,
            client_corporation_id           = EXCLUDED.client_corporation_id,
            client_corporation_name         = EXCLUDED.client_corporation_name,
            owner_bullhorn_id               = EXCLUDED.owner_bullhorn_id,
            owner_first                     = EXCLUDED.owner_first,
            owner_last                      = EXCLUDED.owner_last,
            branch_id                       = EXCLUDED.branch_id,
            branch_name                     = EXCLUDED.branch_name,
            vendor_client_corporation_id    = EXCLUDED.vendor_client_corporation_id,
            vendor_client_corporation_name  = EXCLUDED.vendor_client_corporation_name,
            custom_date1                    = EXCLUDED.custom_date1,
            custom_date2                    = EXCLUDED.custom_date2,
            custom_date3                    = EXCLUDED.custom_date3,
            custom_float1                   = EXCLUDED.custom_float1,
            custom_float2                   = EXCLUDED.custom_float2,
            custom_float3                   = EXCLUDED.custom_float3,
            custom_int1                     = EXCLUDED.custom_int1,
            custom_int2                     = EXCLUDED.custom_int2,
            custom_int3                     = EXCLUDED.custom_int3,
            custom_text1                    = EXCLUDED.custom_text1,
            custom_text2                    = EXCLUDED.custom_text2,
            custom_text3                    = EXCLUDED.custom_text3,
            custom_text4                    = EXCLUDED.custom_text4,
            custom_text5                    = EXCLUDED.custom_text5,
            custom_text6                    = EXCLUDED.custom_text6,
            custom_text7                    = EXCLUDED.custom_text7,
            custom_text8                    = EXCLUDED.custom_text8,
            custom_text9                    = EXCLUDED.custom_text9,
            custom_text10                   = EXCLUDED.custom_text10,
            custom_text11                   = EXCLUDED.custom_text11,
            custom_text12                   = EXCLUDED.custom_text12,
            custom_text13                   = EXCLUDED.custom_text13,
            custom_text14                   = EXCLUDED.custom_text14,
            custom_text15                   = EXCLUDED.custom_text15,
            custom_text16                   = EXCLUDED.custom_text16,
            custom_text17                   = EXCLUDED.custom_text17,
            custom_text18                   = EXCLUDED.custom_text18,
            custom_text19                   = EXCLUDED.custom_text19,
            custom_text20                   = EXCLUDED.custom_text20,
            custom_text_block1              = EXCLUDED.custom_text_block1,
            custom_text_block2              = EXCLUDED.custom_text_block2,
            custom_text_block3              = EXCLUDED.custom_text_block3,
            custom_text_block4              = EXCLUDED.custom_text_block4,
            custom_text_block5              = EXCLUDED.custom_text_block5,
            synced_at                       = now(),
            updated_at                      = now()
        """,
        rows,
    )
    return len(rows)


async def sync_timesheets(conn: asyncpg.Connection, tenant_id: str, records: list[dict]) -> int:
    rows = []
    for r in records:
        rows.append((
            tenant_id,
            r["id"],
            _nested(r, "placement", "id"),
            _nested(r, "candidate", "firstName"),
            _nested(r, "candidate", "lastName"),
            _nested(r, "clientCorporation", "name"),
            _nested(r, "jobOrder", "title"),
            _ms_to_date(r.get("endDate")),
            float(r.get("hoursWorked") or 0),
            float(r.get("additionalBillAmount") or 0),
            float(r.get("additionalPayAmount") or 0),
            _lookup(r.get("evaluationState")),
            _lookup(r.get("processingStatus")),
            _lookup(r.get("timesheetEntryApprovalStatusLookup")),
        ))

    await conn.executemany(
        """
        INSERT INTO timesheets (
            tenant_id, bullhorn_id, placement_bullhorn_id,
            candidate_first, candidate_last, client_name, job_title,
            week_ending, hours_worked,
            additional_bill_amount, additional_pay_amount,
            evaluation_state, processing_status, approval_status,
            raw_data, synced_at
        )
        SELECT
            $1::uuid, $2, $3,
            $4, $5, $6, $7,
            $8, $9,
            $10, $11,
            $12, $13, $14,
            '{}'::jsonb, now()
        ON CONFLICT (tenant_id, bullhorn_id) DO UPDATE SET
            placement_bullhorn_id  = EXCLUDED.placement_bullhorn_id,
            candidate_first        = EXCLUDED.candidate_first,
            candidate_last         = EXCLUDED.candidate_last,
            client_name            = EXCLUDED.client_name,
            job_title              = EXCLUDED.job_title,
            week_ending            = EXCLUDED.week_ending,
            hours_worked           = EXCLUDED.hours_worked,
            additional_bill_amount = EXCLUDED.additional_bill_amount,
            additional_pay_amount  = EXCLUDED.additional_pay_amount,
            evaluation_state       = EXCLUDED.evaluation_state,
            processing_status      = EXCLUDED.processing_status,
            approval_status        = EXCLUDED.approval_status,
            synced_at              = now()
        """,
        rows,
    )
    return len(rows)


async def sync_timesheet_entries(conn: asyncpg.Connection, tenant_id: str, records: list[dict]) -> int:
    rows = []
    for r in records:
        rows.append((
            tenant_id,
            r["id"],
            _nested(r, "timesheet", "id"),
            _ms_to_date(r.get("applicableFrom")),
            _ms_to_date(r.get("applicableTo")),
            float(r.get("quantity") or 0),
            r.get("billRate"),
            r.get("payRate"),
            r.get("comment"),
            _nested(r, "earnCode", "code"),
            _lookup(r.get("timesheetEntryApprovalStatusLookup")),
        ))

    await conn.executemany(
        """
        INSERT INTO timesheet_entries (
            tenant_id, bullhorn_id, timesheet_bullhorn_id,
            applicable_from, applicable_to,
            quantity, bill_rate, pay_rate, comment,
            earn_code, approval_status,
            raw_data, synced_at
        )
        SELECT
            $1::uuid, $2, $3,
            $4, $5,
            $6, $7, $8, $9,
            $10, $11,
            '{}'::jsonb, now()
        ON CONFLICT (tenant_id, bullhorn_id) DO UPDATE SET
            timesheet_bullhorn_id = EXCLUDED.timesheet_bullhorn_id,
            applicable_from       = EXCLUDED.applicable_from,
            applicable_to         = EXCLUDED.applicable_to,
            quantity              = EXCLUDED.quantity,
            bill_rate             = EXCLUDED.bill_rate,
            pay_rate              = EXCLUDED.pay_rate,
            comment               = EXCLUDED.comment,
            earn_code             = EXCLUDED.earn_code,
            approval_status       = EXCLUDED.approval_status,
            synced_at             = now()
        """,
        rows,
    )
    return len(rows)


async def sync_invoices(conn: asyncpg.Connection, tenant_id: str, records: list[dict]) -> int:
    today = datetime.date.today()
    rows = []
    for r in records:
        invoice_date = _ms_to_date(r.get("invoiceStatementDate"))
        days_to_pay = 30  # default Net 30; BH invoiceTerm nested fields not queryable
        due = (invoice_date + datetime.timedelta(days=int(days_to_pay))) if invoice_date else None
        is_finalized = r.get("isFinalized") or False
        status = _lookup(r.get("status")) or r.get("status") or ""
        if isinstance(status, dict):
            status = status.get("label") or status.get("name") or ""
        is_paid = is_finalized or str(status).lower() in ("paid", "voided", "finalized")
        days_out = max(0, (today - due).days) if due and not is_paid else 0
        rows.append((
            tenant_id,
            r["id"],
            r.get("invoiceStatementNumber"),
            _nested(r, "clientCorporation", "name"),
            float(r.get("subtotal") or 0),
            float(r.get("total") or 0),
            status,
            invoice_date,
            due,
            None,   # paid_date not directly available from BH InvoiceStatement
            days_out,
            is_finalized,
        ))

    await conn.executemany(
        """
        INSERT INTO invoices (
            tenant_id, bullhorn_id, invoice_number, client_name,
            amount, balance, status, invoice_date, due_date, paid_date,
            days_outstanding, is_finalized, synced_at
        )
        SELECT
            $1::uuid, $2, $3, $4,
            $5, $6, $7, $8, $9, $10,
            $11, $12, now()
        ON CONFLICT (tenant_id, bullhorn_id) DO UPDATE SET
            invoice_number   = EXCLUDED.invoice_number,
            client_name      = EXCLUDED.client_name,
            amount           = EXCLUDED.amount,
            balance          = EXCLUDED.balance,
            status           = EXCLUDED.status,
            invoice_date     = EXCLUDED.invoice_date,
            due_date         = EXCLUDED.due_date,
            paid_date        = EXCLUDED.paid_date,
            days_outstanding = EXCLUDED.days_outstanding,
            is_finalized     = EXCLUDED.is_finalized,
            synced_at        = now()
        """,
        rows,
    )
    return len(rows)


async def sync_billable_charges(conn: asyncpg.Connection, tenant_id: str, records: list[dict]) -> int:
    def _gl(r: dict, key: str, field: str) -> str | None:
        seg = r.get(key)
        if isinstance(seg, dict):
            return seg.get(field)
        return None

    rows = []
    for r in records:
        rows.append((
            tenant_id, r["id"],
            _ms_to_date(r.get("dateAdded")),
            _ms_to_date(r.get("dateLastModified")),
            _ms_to_date(r.get("periodEndDate")),
            r.get("subtotal"),
            r.get("isInvoiced"),
            _lookup(r.get("status")),
            _lookup(r.get("transactionStatus")),
            _nested(r, "candidate", "id"),
            _nested(r, "clientCorporation", "id"),
            _nested(r, "clientCorporation", "name"),
            _nested(r, "placement", "id"),
            _nested(r, "jobOrder", "id"),
            _nested(r, "timesheet", "id"),
            # new fields
            _nested(r, "billingClientContact", "id"),
            _nested(r, "billingClientContact", "firstName"),
            _nested(r, "billingClientContact", "lastName"),
            _nested(r, "billingClientCorporation", "id"),
            _nested(r, "billingClientCorporation", "name"),
            (r.get("currencyUnit") or {}).get("alphabeticCode") or (r.get("currencyUnit") or {}).get("name"),
            _lookup(r.get("entryTypeLookup")),
            r.get("externalID"),
            r.get("description"),
            _gl(r, "generalLedgerSegment1", "externalSegmentNumber"),
            _gl(r, "generalLedgerSegment1", "externalSegmentName"),
            _gl(r, "generalLedgerSegment2", "externalSegmentNumber"),
            _gl(r, "generalLedgerSegment2", "externalSegmentName"),
            _gl(r, "generalLedgerSegment3", "externalSegmentNumber"),
            _gl(r, "generalLedgerSegment3", "externalSegmentName"),
            _gl(r, "generalLedgerSegment4", "externalSegmentNumber"),
            _gl(r, "generalLedgerSegment4", "externalSegmentName"),
            _gl(r, "generalLedgerSegment5", "externalSegmentNumber"),
            _gl(r, "generalLedgerSegment5", "externalSegmentName"),
            r.get("generalLedgerServiceCode"),
            r.get("hasRebill"),
            _nested(r, "invoiceTerm", "id"),
            _nested(r, "transactionType", "name"),
            r.get("hasAdjustment"),
            _nested(r, "billingProfile", "id"),
            _nested(r, "billingProfile", "title"),
        ))
    await conn.executemany(
        """
        INSERT INTO billable_charges (
            tenant_id, bullhorn_id, date_added, date_last_modified, period_end_date,
            subtotal, is_invoiced, status, transaction_status,
            candidate_bullhorn_id, client_corporation_id, client_corporation_name,
            placement_bullhorn_id, job_order_bullhorn_id, timesheet_bullhorn_id,
            billing_client_contact_id, billing_client_contact_first, billing_client_contact_last,
            billing_client_corporation_id, billing_client_corporation_name,
            currency_unit, entry_type, external_id, description,
            gl_segment1_number, gl_segment1_name,
            gl_segment2_number, gl_segment2_name,
            gl_segment3_number, gl_segment3_name,
            gl_segment4_number, gl_segment4_name,
            gl_segment5_number, gl_segment5_name,
            gl_service_code, has_rebill, invoice_term_id, transaction_type,
            has_adjustment, billing_profile_id, billing_profile_title,
            raw_data, synced_at
        )
        SELECT
            $1::uuid,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,
            $16,$17,$18,$19,$20,$21,$22,$23,$24,
            $25,$26,$27,$28,$29,$30,$31,$32,$33,$34,
            $35,$36,$37,$38,$39,$40,$41,
            '{}'::jsonb,now()
        ON CONFLICT (tenant_id, bullhorn_id) DO UPDATE SET
            date_last_modified              = EXCLUDED.date_last_modified,
            period_end_date                 = EXCLUDED.period_end_date,
            subtotal                        = EXCLUDED.subtotal,
            is_invoiced                     = EXCLUDED.is_invoiced,
            status                          = EXCLUDED.status,
            transaction_status              = EXCLUDED.transaction_status,
            billing_client_contact_id       = EXCLUDED.billing_client_contact_id,
            billing_client_contact_first    = EXCLUDED.billing_client_contact_first,
            billing_client_contact_last     = EXCLUDED.billing_client_contact_last,
            billing_client_corporation_id   = EXCLUDED.billing_client_corporation_id,
            billing_client_corporation_name = EXCLUDED.billing_client_corporation_name,
            currency_unit                   = EXCLUDED.currency_unit,
            entry_type                      = EXCLUDED.entry_type,
            external_id                     = EXCLUDED.external_id,
            description                     = EXCLUDED.description,
            gl_segment1_number              = EXCLUDED.gl_segment1_number,
            gl_segment1_name                = EXCLUDED.gl_segment1_name,
            gl_segment2_number              = EXCLUDED.gl_segment2_number,
            gl_segment2_name                = EXCLUDED.gl_segment2_name,
            gl_segment3_number              = EXCLUDED.gl_segment3_number,
            gl_segment3_name                = EXCLUDED.gl_segment3_name,
            gl_segment4_number              = EXCLUDED.gl_segment4_number,
            gl_segment4_name                = EXCLUDED.gl_segment4_name,
            gl_segment5_number              = EXCLUDED.gl_segment5_number,
            gl_segment5_name                = EXCLUDED.gl_segment5_name,
            gl_service_code                 = EXCLUDED.gl_service_code,
            has_rebill                      = EXCLUDED.has_rebill,
            invoice_term_id                 = EXCLUDED.invoice_term_id,
            transaction_type                = EXCLUDED.transaction_type,
            has_adjustment                  = EXCLUDED.has_adjustment,
            billing_profile_id              = EXCLUDED.billing_profile_id,
            billing_profile_title           = EXCLUDED.billing_profile_title,
            synced_at                       = now()
        """, rows)
    return len(rows)


async def sync_bill_masters(conn: asyncpg.Connection, tenant_id: str, records: list[dict]) -> int:
    rows = []
    for r in records:
        rows.append((
            tenant_id, r["id"],
            _ms_to_date(r.get("dateAdded")),
            _ms_to_date(r.get("dateLastModified")),
            _ms_to_date(r.get("transactionDate")),
            _lookup(r.get("chargeTypeLookup")),
            _lookup(r.get("transactionStatus")),
            _nested(r, "billableCharge", "id"),
            _nested(r, "earnCode", "title"),
            _nested(r, "billingSyncBatch", "id"),
            r.get("canInvoice"),
            r.get("externalID"),
        ))
    await conn.executemany(
        """
        INSERT INTO bill_masters (
            tenant_id, bullhorn_id, date_added, date_last_modified, transaction_date,
            charge_type, transaction_status, billable_charge_bullhorn_id, earn_code,
            billing_sync_batch_id, can_invoice, external_id,
            raw_data, synced_at
        )
        SELECT $1::uuid,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,'{}'::jsonb,now()
        ON CONFLICT (tenant_id, bullhorn_id) DO UPDATE SET
            date_last_modified          = EXCLUDED.date_last_modified,
            transaction_status          = EXCLUDED.transaction_status,
            billing_sync_batch_id       = EXCLUDED.billing_sync_batch_id,
            can_invoice                 = EXCLUDED.can_invoice,
            external_id                 = EXCLUDED.external_id,
            synced_at                   = now()
        """, rows)
    return len(rows)


async def sync_bill_master_transactions(conn: asyncpg.Connection, tenant_id: str, records: list[dict]) -> int:
    rows = []
    for r in records:
        rows.append((
            tenant_id, r["id"],
            _ms_to_date(r.get("dateAdded")),
            _ms_to_date(r.get("dateLastModified")),
            r.get("amount"),
            r.get("quantity"),
            r.get("rate"),
            r.get("netAmount"),
            r.get("netQuantity"),
            _ms_to_date(r.get("recordingDate")),
            _ms_to_date(r.get("payPeriodEndDate")),
            r.get("isDeleted"),
            r.get("isUnbillable"),
            r.get("needsReview"),
            _lookup(r.get("transactionType")),
            _lookup(r.get("transactionOrigin")),
            _nested(r, "billMaster", "id"),
            _lookup(r.get("unitOfMeasure")),
            _nested(r, "accountingPeriod", "id"),
            _ms_to_date((r.get("accountingPeriod") or {}).get("accountingPeriodDate")),
            r.get("isCustomRate"),
            r.get("wasUnbilled"),
        ))
    await conn.executemany(
        """
        INSERT INTO bill_master_transactions (
            tenant_id, bullhorn_id, date_added, date_last_modified,
            amount, quantity, rate, net_amount, net_quantity,
            recording_date, pay_period_end_date,
            is_deleted, is_unbillable, needs_review,
            transaction_type, transaction_origin,
            bill_master_bullhorn_id, unit_of_measure,
            accounting_period_id, accounting_period_date,
            is_custom_rate, was_unbilled,
            raw_data, synced_at
        )
        SELECT $1::uuid,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21,$22,'{}'::jsonb,now()
        ON CONFLICT (tenant_id, bullhorn_id) DO UPDATE SET
            date_last_modified      = EXCLUDED.date_last_modified,
            amount                  = EXCLUDED.amount,
            net_amount              = EXCLUDED.net_amount,
            is_deleted              = EXCLUDED.is_deleted,
            is_unbillable           = EXCLUDED.is_unbillable,
            needs_review            = EXCLUDED.needs_review,
            accounting_period_id    = EXCLUDED.accounting_period_id,
            accounting_period_date  = EXCLUDED.accounting_period_date,
            is_custom_rate          = EXCLUDED.is_custom_rate,
            was_unbilled            = EXCLUDED.was_unbilled,
            synced_at               = now()
        """, rows)
    return len(rows)


async def sync_payable_charges(conn: asyncpg.Connection, tenant_id: str, records: list[dict]) -> int:
    def _gl(r: dict, key: str, field: str) -> str | None:
        seg = r.get(key)
        if isinstance(seg, dict):
            return seg.get(field)
        return None

    rows = []
    for r in records:
        rows.append((
            tenant_id, r["id"],
            _ms_to_date(r.get("dateAdded")),
            _ms_to_date(r.get("dateLastModified")),
            _ms_to_date(r.get("periodEndDate")),
            r.get("subtotal"),
            _lookup(r.get("status")),
            _lookup(r.get("transactionStatus")),
            _nested(r, "transactionType", "name"),
            _nested(r, "candidate", "id"),
            _nested(r, "clientCorporation", "id"),
            _nested(r, "clientCorporation", "name"),
            _nested(r, "placement", "id"),
            _nested(r, "jobOrder", "id"),
            _nested(r, "timesheet", "id"),
            (r.get("currencyUnit") or {}).get("alphabeticCode") or (r.get("currencyUnit") or {}).get("name"),
            _lookup(r.get("entryTypeLookup")),
            r.get("externalID"),
            r.get("description"),
            _gl(r, "generalLedgerSegment1", "externalSegmentNumber"),
            _gl(r, "generalLedgerSegment1", "externalSegmentName"),
            _gl(r, "generalLedgerSegment2", "externalSegmentNumber"),
            _gl(r, "generalLedgerSegment2", "externalSegmentName"),
            _gl(r, "generalLedgerSegment3", "externalSegmentNumber"),
            _gl(r, "generalLedgerSegment3", "externalSegmentName"),
            _gl(r, "generalLedgerSegment4", "externalSegmentNumber"),
            _gl(r, "generalLedgerSegment4", "externalSegmentName"),
            _gl(r, "generalLedgerSegment5", "externalSegmentNumber"),
            _gl(r, "generalLedgerSegment5", "externalSegmentName"),
            r.get("generalLedgerServiceCode"),
            r.get("hasAdjustment"),
        ))
    await conn.executemany(
        """
        INSERT INTO payable_charges (
            tenant_id, bullhorn_id, date_added, date_last_modified, period_end_date,
            subtotal, status, transaction_status, transaction_type,
            candidate_bullhorn_id, client_corporation_id, client_corporation_name,
            placement_bullhorn_id, job_order_bullhorn_id, timesheet_bullhorn_id,
            currency_unit, entry_type, external_id, description,
            gl_segment1_number, gl_segment1_name,
            gl_segment2_number, gl_segment2_name,
            gl_segment3_number, gl_segment3_name,
            gl_segment4_number, gl_segment4_name,
            gl_segment5_number, gl_segment5_name,
            gl_service_code, has_adjustment,
            raw_data, synced_at
        )
        SELECT
            $1::uuid,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,
            $16,$17,$18,$19,
            $20,$21,$22,$23,$24,$25,$26,$27,$28,$29,
            $30,$31,
            '{}'::jsonb,now()
        ON CONFLICT (tenant_id, bullhorn_id) DO UPDATE SET
            date_last_modified  = EXCLUDED.date_last_modified,
            period_end_date     = EXCLUDED.period_end_date,
            subtotal            = EXCLUDED.subtotal,
            status              = EXCLUDED.status,
            transaction_status  = EXCLUDED.transaction_status,
            transaction_type    = EXCLUDED.transaction_type,
            currency_unit       = EXCLUDED.currency_unit,
            entry_type          = EXCLUDED.entry_type,
            external_id         = EXCLUDED.external_id,
            description         = EXCLUDED.description,
            gl_segment1_number  = EXCLUDED.gl_segment1_number,
            gl_segment1_name    = EXCLUDED.gl_segment1_name,
            gl_segment2_number  = EXCLUDED.gl_segment2_number,
            gl_segment2_name    = EXCLUDED.gl_segment2_name,
            gl_segment3_number  = EXCLUDED.gl_segment3_number,
            gl_segment3_name    = EXCLUDED.gl_segment3_name,
            gl_segment4_number  = EXCLUDED.gl_segment4_number,
            gl_segment4_name    = EXCLUDED.gl_segment4_name,
            gl_segment5_number  = EXCLUDED.gl_segment5_number,
            gl_segment5_name    = EXCLUDED.gl_segment5_name,
            gl_service_code     = EXCLUDED.gl_service_code,
            has_adjustment      = EXCLUDED.has_adjustment,
            synced_at           = now()
        """, rows)
    return len(rows)


async def sync_pay_masters(conn: asyncpg.Connection, tenant_id: str, records: list[dict]) -> int:
    rows = []
    for r in records:
        rows.append((
            tenant_id, r["id"],
            _ms_to_date(r.get("dateAdded")),
            _ms_to_date(r.get("dateLastModified")),
            _ms_to_date(r.get("transactionDate")),
            _lookup(r.get("chargeTypeLookup")),
            _lookup(r.get("transactionStatus")),
            _nested(r, "payableCharge", "id"),
            _nested(r, "earnCode", "title"),
            r.get("externalID"),
        ))
    await conn.executemany(
        """
        INSERT INTO pay_masters (
            tenant_id, bullhorn_id, date_added, date_last_modified, transaction_date,
            charge_type, transaction_status,
            payable_charge_bullhorn_id, earn_code,
            external_id,
            raw_data, synced_at
        )
        SELECT $1::uuid,$2,$3,$4,$5,$6,$7,$8,$9,$10,'{}'::jsonb,now()
        ON CONFLICT (tenant_id, bullhorn_id) DO UPDATE SET
            date_last_modified      = EXCLUDED.date_last_modified,
            transaction_date        = EXCLUDED.transaction_date,
            transaction_status      = EXCLUDED.transaction_status,
            external_id             = EXCLUDED.external_id,
            synced_at               = now()
        """, rows)
    return len(rows)


async def sync_pay_master_transactions(conn: asyncpg.Connection, tenant_id: str, records: list[dict]) -> int:
    rows = []
    for r in records:
        rows.append((
            tenant_id, r["id"],
            _ms_to_date(r.get("dateAdded")),
            _ms_to_date(r.get("dateLastModified")),
            r.get("amount"),
            r.get("quantity"),
            r.get("rate"),
            r.get("netAmount"),
            r.get("netQuantity"),
            _ms_to_date(r.get("recordingDate")),
            _ms_to_date(r.get("payPeriodEndDate")),
            r.get("isDeleted"),
            _lookup(r.get("transactionType")),
            _lookup(r.get("transactionOrigin")),
            _nested(r, "payMaster", "id"),
            _lookup(r.get("unitOfMeasure")),
            _nested(r, "accountingPeriod", "id"),
            _ms_to_date((r.get("accountingPeriod") or {}).get("accountingPeriodDate")),
            r.get("isCustomRate"),
        ))
    await conn.executemany(
        """
        INSERT INTO pay_master_transactions (
            tenant_id, bullhorn_id, date_added, date_last_modified,
            amount, quantity, rate, net_amount, net_quantity,
            recording_date, pay_period_end_date, is_deleted,
            transaction_type, transaction_origin,
            pay_master_bullhorn_id, unit_of_measure,
            accounting_period_id, accounting_period_date,
            is_custom_rate,
            raw_data, synced_at
        )
        SELECT $1::uuid,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,'{}'::jsonb,now()
        ON CONFLICT (tenant_id, bullhorn_id) DO UPDATE SET
            date_last_modified      = EXCLUDED.date_last_modified,
            amount                  = EXCLUDED.amount,
            net_amount              = EXCLUDED.net_amount,
            is_deleted              = EXCLUDED.is_deleted,
            accounting_period_id    = EXCLUDED.accounting_period_id,
            accounting_period_date  = EXCLUDED.accounting_period_date,
            is_custom_rate          = EXCLUDED.is_custom_rate,
            synced_at               = now()
        """, rows)
    return len(rows)


async def sync_client_corporations(conn: asyncpg.Connection, tenant_id: str, records: list[dict]) -> int:
    def _addr(r: dict, key: str, field: str):
        a = r.get(key)
        if isinstance(a, dict):
            return a.get(field)
        return None

    def _num(val):
        """Return None for empty strings or None, otherwise the value."""
        if val is None or val == "":
            return None
        return val

    def _text(val):
        """Coerce lists to comma-joined string; pass scalars through."""
        if isinstance(val, list):
            return ", ".join(str(v) for v in val) if val else None
        return val

    rows = []
    for r in records:
        rows.append((
            tenant_id,
            r["id"],
            r.get("name"),
            r.get("companyURL"),
            _ms_to_date(r.get("dateAdded")),
            _ms_to_date(r.get("dateLastModified")),
            _lookup(r.get("status")),
            r.get("phone"),
            r.get("fax"),
            r.get("billingPhone"),
            r.get("externalID"),
            _num(r.get("numEmployees")),
            _num(r.get("revenue")),
            _num(r.get("annualRevenue")),
            _num(r.get("feeArrangement")),
            _num(r.get("taxRate")),
            _num(r.get("workWeekStart")),
            r.get("billingFrequency"),
            r.get("invoiceFormat"),
            r.get("ownership"),
            r.get("tickerSymbol"),
            _ms_to_date(r.get("dateFounded")),
            r.get("twitterHandle"),
            r.get("linkedinProfileName"),
            r.get("facebookProfileName"),
            _addr(r, "address", "address1"),
            _addr(r, "address", "address2"),
            _addr(r, "address", "city"),
            _addr(r, "address", "state"),
            _addr(r, "address", "zip"),
            _addr(r, "billingAddress", "address1"),
            _addr(r, "billingAddress", "address2"),
            _addr(r, "billingAddress", "city"),
            _addr(r, "billingAddress", "state"),
            _addr(r, "billingAddress", "zip"),
            _nested(r, "parentClientCorporation", "id"),
            _nested(r, "parentClientCorporation", "name"),
            _nested(r, "department", "id"),
            _nested(r, "department", "name"),
            _nested(r, "branch", "id"),
            _nested(r, "branch", "name"),
            _num(r.get("customFloat1")), _num(r.get("customFloat2")), _num(r.get("customFloat3")),
            _ms_to_date(r.get("customDate1")), _ms_to_date(r.get("customDate2")), _ms_to_date(r.get("customDate3")),
            _num(r.get("customInt1")), _num(r.get("customInt2")), _num(r.get("customInt3")),
            _text(r.get("customText1")), _text(r.get("customText2")), _text(r.get("customText3")), _text(r.get("customText4")), _text(r.get("customText5")),
            _text(r.get("customText6")), _text(r.get("customText7")), _text(r.get("customText8")), _text(r.get("customText9")), _text(r.get("customText10")),
            _text(r.get("customText11")), _text(r.get("customText12")), _text(r.get("customText13")), _text(r.get("customText14")), _text(r.get("customText15")),
            _text(r.get("customText16")), _text(r.get("customText17")), _text(r.get("customText18")), _text(r.get("customText19")), _text(r.get("customText20")),
            _text(r.get("customTextBlock1")), _text(r.get("customTextBlock2")), _text(r.get("customTextBlock3")),
            _text(r.get("customTextBlock4")), _text(r.get("customTextBlock5")),
        ))

    await conn.executemany(
        """
        INSERT INTO client_corporations (
            tenant_id, bullhorn_id, name, company_url,
            date_added, date_last_modified, status,
            phone, fax, billing_phone, external_id,
            num_employees, revenue, annual_revenue, fee_arrangement, tax_rate, work_week_start,
            billing_frequency, invoice_format, ownership, ticker_symbol, date_founded,
            twitter_handle, linkedin_profile_name, facebook_profile_name,
            address1, address2, city, state, zip,
            billing_address1, billing_address2, billing_city, billing_state, billing_zip,
            parent_client_corporation_id, parent_client_corporation_name,
            department_id, department_name,
            branch_id, branch_name,
            custom_float1, custom_float2, custom_float3,
            custom_date1, custom_date2, custom_date3,
            custom_int1, custom_int2, custom_int3,
            custom_text1, custom_text2, custom_text3, custom_text4, custom_text5,
            custom_text6, custom_text7, custom_text8, custom_text9, custom_text10,
            custom_text11, custom_text12, custom_text13, custom_text14, custom_text15,
            custom_text16, custom_text17, custom_text18, custom_text19, custom_text20,
            custom_text_block1, custom_text_block2, custom_text_block3,
            custom_text_block4, custom_text_block5,
            raw_data, synced_at
        )
        SELECT
            $1::uuid,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,
            $12,$13,$14,$15,$16,$17,$18,$19,$20,$21,$22,
            $23,$24,$25,$26,$27,$28,$29,$30,$31,$32,$33,$34,$35,
            $36,$37,$38,$39,$40,$41,
            $42,$43,$44,$45,$46,$47,$48,$49,$50,
            $51,$52,$53,$54,$55,$56,$57,$58,$59,$60,
            $61,$62,$63,$64,$65,$66,$67,$68,$69,$70,
            $71,$72,$73,$74,$75,
            '{}'::jsonb,now()
        ON CONFLICT (tenant_id, bullhorn_id) DO UPDATE SET
            name                        = EXCLUDED.name,
            company_url                 = EXCLUDED.company_url,
            date_last_modified          = EXCLUDED.date_last_modified,
            status                      = EXCLUDED.status,
            phone                       = EXCLUDED.phone,
            fax                         = EXCLUDED.fax,
            billing_phone               = EXCLUDED.billing_phone,
            external_id                 = EXCLUDED.external_id,
            num_employees               = EXCLUDED.num_employees,
            revenue                     = EXCLUDED.revenue,
            annual_revenue              = EXCLUDED.annual_revenue,
            fee_arrangement             = EXCLUDED.fee_arrangement,
            tax_rate                    = EXCLUDED.tax_rate,
            work_week_start             = EXCLUDED.work_week_start,
            billing_frequency           = EXCLUDED.billing_frequency,
            invoice_format              = EXCLUDED.invoice_format,
            ownership                   = EXCLUDED.ownership,
            ticker_symbol               = EXCLUDED.ticker_symbol,
            date_founded                = EXCLUDED.date_founded,
            twitter_handle              = EXCLUDED.twitter_handle,
            linkedin_profile_name       = EXCLUDED.linkedin_profile_name,
            facebook_profile_name       = EXCLUDED.facebook_profile_name,
            address1                    = EXCLUDED.address1,
            address2                    = EXCLUDED.address2,
            city                        = EXCLUDED.city,
            state                       = EXCLUDED.state,
            zip                         = EXCLUDED.zip,
            billing_address1            = EXCLUDED.billing_address1,
            billing_address2            = EXCLUDED.billing_address2,
            billing_city                = EXCLUDED.billing_city,
            billing_state               = EXCLUDED.billing_state,
            billing_zip                 = EXCLUDED.billing_zip,
            parent_client_corporation_id   = EXCLUDED.parent_client_corporation_id,
            parent_client_corporation_name = EXCLUDED.parent_client_corporation_name,
            department_id               = EXCLUDED.department_id,
            department_name             = EXCLUDED.department_name,
            branch_id                   = EXCLUDED.branch_id,
            branch_name                 = EXCLUDED.branch_name,
            custom_float1               = EXCLUDED.custom_float1,
            custom_float2               = EXCLUDED.custom_float2,
            custom_float3               = EXCLUDED.custom_float3,
            custom_date1                = EXCLUDED.custom_date1,
            custom_date2                = EXCLUDED.custom_date2,
            custom_date3                = EXCLUDED.custom_date3,
            custom_int1                 = EXCLUDED.custom_int1,
            custom_int2                 = EXCLUDED.custom_int2,
            custom_int3                 = EXCLUDED.custom_int3,
            custom_text1                = EXCLUDED.custom_text1,
            custom_text2                = EXCLUDED.custom_text2,
            custom_text3                = EXCLUDED.custom_text3,
            custom_text4                = EXCLUDED.custom_text4,
            custom_text5                = EXCLUDED.custom_text5,
            custom_text6                = EXCLUDED.custom_text6,
            custom_text7                = EXCLUDED.custom_text7,
            custom_text8                = EXCLUDED.custom_text8,
            custom_text9                = EXCLUDED.custom_text9,
            custom_text10               = EXCLUDED.custom_text10,
            custom_text11               = EXCLUDED.custom_text11,
            custom_text12               = EXCLUDED.custom_text12,
            custom_text13               = EXCLUDED.custom_text13,
            custom_text14               = EXCLUDED.custom_text14,
            custom_text15               = EXCLUDED.custom_text15,
            custom_text16               = EXCLUDED.custom_text16,
            custom_text17               = EXCLUDED.custom_text17,
            custom_text18               = EXCLUDED.custom_text18,
            custom_text19               = EXCLUDED.custom_text19,
            custom_text20               = EXCLUDED.custom_text20,
            custom_text_block1          = EXCLUDED.custom_text_block1,
            custom_text_block2          = EXCLUDED.custom_text_block2,
            custom_text_block3          = EXCLUDED.custom_text_block3,
            custom_text_block4          = EXCLUDED.custom_text_block4,
            custom_text_block5          = EXCLUDED.custom_text_block5,
            synced_at                   = now()
        """,
        rows,
    )
    return len(rows)


async def sync_job_orders(conn: asyncpg.Connection, tenant_id: str, records: list[dict]) -> int:
    def _num(val):
        if val is None or val == "":
            return None
        return val

    def _text(val):
        if isinstance(val, list):
            return ", ".join(str(v) for v in val) if val else None
        return val

    def _addr(r: dict, field: str):
        a = r.get("address")
        if isinstance(a, dict):
            return a.get(field)
        return None

    rows = []
    for r in records:
        rows.append((
            tenant_id, r["id"],
            r.get("title"),
            _lookup(r.get("status")),
            r.get("numOpenings"),
            r.get("isOpen"),
            r.get("isDeleted"),
            r.get("isWorkFromHome"),
            r.get("willRelocate"),
            r.get("willSponsor"),
            _ms_to_date(r.get("dateAdded")),
            _ms_to_date(r.get("dateLastModified")),
            _ms_to_date(r.get("dateLastPublished")),
            _ms_to_date(r.get("dateClosed")),
            _ms_to_date(r.get("dateEnd")),
            _ms_to_date(r.get("startDate")),
            r.get("employmentType"),
            str(r["type"]) if r.get("type") is not None else None,
            r.get("source"),
            r.get("onSite"),
            r.get("travelRequirements"),
            r.get("yearsRequired"),
            _num(r.get("payRate")),
            _num(r.get("clientBillRate")),
            _num(r.get("salary")),
            r.get("salaryUnit"),
            _num(r.get("durationWeeks")),
            _num(r.get("hoursPerWeek")),
            r.get("taxStatus"),
            r.get("description"),
            r.get("publicDescription"),
            r.get("externalID"),
            r.get("reportTo"),
            _addr(r, "address1"),
            _addr(r, "address2"),
            _addr(r, "city"),
            _addr(r, "state"),
            _addr(r, "zip"),
            _nested(r, "clientCorporation", "id"),
            _nested(r, "clientCorporation", "name"),
            _nested(r, "clientContact", "id"),
            _nested(r, "clientContact", "firstName"),
            _nested(r, "clientContact", "lastName"),
            _nested(r, "owner", "id"),
            _nested(r, "owner", "firstName"),
            _nested(r, "owner", "lastName"),
            _nested(r, "branch", "id"),
            _nested(r, "branch", "name"),
            _ms_to_date(r.get("customDate1")), _ms_to_date(r.get("customDate2")), _ms_to_date(r.get("customDate3")),
            _num(r.get("customFloat1")), _num(r.get("customFloat2")), _num(r.get("customFloat3")),
            _num(r.get("customInt1")), _num(r.get("customInt2")), _num(r.get("customInt3")),
            _text(r.get("customText1")), _text(r.get("customText2")), _text(r.get("customText3")),
            _text(r.get("customText4")), _text(r.get("customText5")), _text(r.get("customText6")),
            _text(r.get("customText7")), _text(r.get("customText8")), _text(r.get("customText9")),
            _text(r.get("customText10")), _text(r.get("customText11")), _text(r.get("customText12")),
            _text(r.get("customText13")), _text(r.get("customText14")), _text(r.get("customText15")),
            _text(r.get("customText16")), _text(r.get("customText17")), _text(r.get("customText18")),
            _text(r.get("customText19")), _text(r.get("customText20")),
            _text(r.get("customTextBlock1")), _text(r.get("customTextBlock2")), _text(r.get("customTextBlock3")),
            _text(r.get("customTextBlock4")), _text(r.get("customTextBlock5")),
        ))

    await conn.executemany(
        """
        INSERT INTO job_orders (
            tenant_id, bullhorn_id, title, status,
            num_openings, is_open, is_deleted, is_work_from_home, will_relocate, will_sponsor,
            date_added, date_last_modified, date_last_published, date_closed, date_end, start_date,
            employment_type, type, source, on_site, travel_requirements, years_required,
            pay_rate, client_bill_rate, salary, salary_unit, duration_weeks, hours_per_week, tax_status,
            description, public_description, external_id, report_to,
            address1, address2, city, state, zip,
            client_corporation_id, client_corporation_name,
            client_contact_id, client_contact_first, client_contact_last,
            owner_bullhorn_id, owner_first, owner_last,
            branch_id, branch_name,
            custom_date1, custom_date2, custom_date3,
            custom_float1, custom_float2, custom_float3,
            custom_int1, custom_int2, custom_int3,
            custom_text1, custom_text2, custom_text3, custom_text4, custom_text5,
            custom_text6, custom_text7, custom_text8, custom_text9, custom_text10,
            custom_text11, custom_text12, custom_text13, custom_text14, custom_text15,
            custom_text16, custom_text17, custom_text18, custom_text19, custom_text20,
            custom_text_block1, custom_text_block2, custom_text_block3,
            custom_text_block4, custom_text_block5,
            raw_data, synced_at
        )
        SELECT
            $1::uuid,$2,$3,$4,$5,$6,$7,$8,$9,$10,
            $11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21,$22,
            $23,$24,$25,$26,$27,$28,$29,$30,$31,$32,$33,
            $34,$35,$36,$37,$38,$39,$40,$41,$42,$43,$44,$45,$46,$47,$48,
            $49,$50,$51,$52,$53,$54,$55,$56,$57,
            $58,$59,$60,$61,$62,$63,$64,$65,$66,$67,
            $68,$69,$70,$71,$72,$73,$74,$75,$76,$77,
            $78,$79,$80,$81,$82,
            '{}'::jsonb,now()
        ON CONFLICT (tenant_id, bullhorn_id) DO UPDATE SET
            title                   = EXCLUDED.title,
            status                  = EXCLUDED.status,
            num_openings            = EXCLUDED.num_openings,
            is_open                 = EXCLUDED.is_open,
            is_deleted              = EXCLUDED.is_deleted,
            is_work_from_home       = EXCLUDED.is_work_from_home,
            will_relocate           = EXCLUDED.will_relocate,
            will_sponsor            = EXCLUDED.will_sponsor,
            date_last_modified      = EXCLUDED.date_last_modified,
            date_last_published     = EXCLUDED.date_last_published,
            date_closed             = EXCLUDED.date_closed,
            date_end                = EXCLUDED.date_end,
            start_date              = EXCLUDED.start_date,
            employment_type         = EXCLUDED.employment_type,
            type                    = EXCLUDED.type,
            source                  = EXCLUDED.source,
            on_site                 = EXCLUDED.on_site,
            travel_requirements     = EXCLUDED.travel_requirements,
            years_required          = EXCLUDED.years_required,
            pay_rate                = EXCLUDED.pay_rate,
            client_bill_rate        = EXCLUDED.client_bill_rate,
            salary                  = EXCLUDED.salary,
            salary_unit             = EXCLUDED.salary_unit,
            duration_weeks          = EXCLUDED.duration_weeks,
            hours_per_week          = EXCLUDED.hours_per_week,
            tax_status              = EXCLUDED.tax_status,
            description             = EXCLUDED.description,
            public_description      = EXCLUDED.public_description,
            external_id             = EXCLUDED.external_id,
            report_to               = EXCLUDED.report_to,
            address1                = EXCLUDED.address1,
            address2                = EXCLUDED.address2,
            city                    = EXCLUDED.city,
            state                   = EXCLUDED.state,
            zip                     = EXCLUDED.zip,
            client_corporation_id   = EXCLUDED.client_corporation_id,
            client_corporation_name = EXCLUDED.client_corporation_name,
            client_contact_id       = EXCLUDED.client_contact_id,
            client_contact_first    = EXCLUDED.client_contact_first,
            client_contact_last     = EXCLUDED.client_contact_last,
            owner_bullhorn_id       = EXCLUDED.owner_bullhorn_id,
            owner_first             = EXCLUDED.owner_first,
            owner_last              = EXCLUDED.owner_last,
            branch_id               = EXCLUDED.branch_id,
            branch_name             = EXCLUDED.branch_name,
            custom_date1            = EXCLUDED.custom_date1,
            custom_date2            = EXCLUDED.custom_date2,
            custom_date3            = EXCLUDED.custom_date3,
            custom_float1           = EXCLUDED.custom_float1,
            custom_float2           = EXCLUDED.custom_float2,
            custom_float3           = EXCLUDED.custom_float3,
            custom_int1             = EXCLUDED.custom_int1,
            custom_int2             = EXCLUDED.custom_int2,
            custom_int3             = EXCLUDED.custom_int3,
            custom_text1            = EXCLUDED.custom_text1,
            custom_text2            = EXCLUDED.custom_text2,
            custom_text3            = EXCLUDED.custom_text3,
            custom_text4            = EXCLUDED.custom_text4,
            custom_text5            = EXCLUDED.custom_text5,
            custom_text6            = EXCLUDED.custom_text6,
            custom_text7            = EXCLUDED.custom_text7,
            custom_text8            = EXCLUDED.custom_text8,
            custom_text9            = EXCLUDED.custom_text9,
            custom_text10           = EXCLUDED.custom_text10,
            custom_text11           = EXCLUDED.custom_text11,
            custom_text12           = EXCLUDED.custom_text12,
            custom_text13           = EXCLUDED.custom_text13,
            custom_text14           = EXCLUDED.custom_text14,
            custom_text15           = EXCLUDED.custom_text15,
            custom_text16           = EXCLUDED.custom_text16,
            custom_text17           = EXCLUDED.custom_text17,
            custom_text18           = EXCLUDED.custom_text18,
            custom_text19           = EXCLUDED.custom_text19,
            custom_text20           = EXCLUDED.custom_text20,
            custom_text_block1      = EXCLUDED.custom_text_block1,
            custom_text_block2      = EXCLUDED.custom_text_block2,
            custom_text_block3      = EXCLUDED.custom_text_block3,
            custom_text_block4      = EXCLUDED.custom_text_block4,
            custom_text_block5      = EXCLUDED.custom_text_block5,
            synced_at               = now()
        """,
        rows,
    )
    return len(rows)


async def sync_candidates(conn: asyncpg.Connection, tenant_id: str, records: list[dict]) -> int:
    rows = []
    for r in records:
        rows.append((
            tenant_id,
            r["id"],
            r.get("firstName"),
            r.get("lastName"),
            r.get("name"),
            r.get("email"),
            r.get("mobile"),
            r.get("phone"),
            _lookup(r.get("status")),
            _ms_to_date(r.get("dateAdded")),
            _nested(r, "owner", "firstName"),
            _nested(r, "owner", "lastName"),
        ))

    await conn.executemany(
        """
        INSERT INTO candidates (
            tenant_id, bullhorn_id,
            first_name, last_name, full_name,
            email, mobile, phone, status, date_added,
            owner_first, owner_last,
            raw_data, synced_at
        )
        SELECT
            $1::uuid, $2,
            $3, $4, $5,
            $6, $7, $8, $9, $10,
            $11, $12,
            '{}'::jsonb, now()
        ON CONFLICT (tenant_id, bullhorn_id) DO UPDATE SET
            first_name  = EXCLUDED.first_name,
            last_name   = EXCLUDED.last_name,
            full_name   = EXCLUDED.full_name,
            email       = EXCLUDED.email,
            mobile      = EXCLUDED.mobile,
            phone       = EXCLUDED.phone,
            status      = EXCLUDED.status,
            date_added  = EXCLUDED.date_added,
            owner_first = EXCLUDED.owner_first,
            owner_last  = EXCLUDED.owner_last,
            synced_at   = now()
        """,
        rows,
    )
    return len(rows)


# ---------------------------------------------------------------------------
# Main sync orchestrator
# ---------------------------------------------------------------------------

async def run_sync(tenant_id: str, entities: list[str]) -> None:
    db_url = os.getenv("DATABASE_URL", "")
    if not db_url:
        raise ValueError("DATABASE_URL is not set")

    log.info("Authenticating with Bullhorn...")
    session: BullhornSession = await get_session()
    log.info("Authenticated. restUrl=%s", session.rest_url)



    conn = await asyncpg.connect(**parse_db_url(db_url))
    try:
        # Resolve tenant slug → UUID (or use as-is if already a UUID)
        import uuid as _uuid
        try:
            tenant_uuid = str(_uuid.UUID(tenant_id))
        except ValueError:
            row = await conn.fetchrow(
                "SELECT id FROM tenants WHERE slug = $1 OR name = $1 LIMIT 1", tenant_id
            )
            if not row:
                # No tenant row yet — create a default one
                tenant_uuid = str(_uuid.uuid4())
                await conn.execute(
                    "INSERT INTO tenants (id, name, slug) VALUES ($1, $2, $3) ON CONFLICT DO NOTHING",
                    _uuid.UUID(tenant_uuid), tenant_id, tenant_id,
                )
                log.info("Created tenant '%s' with id=%s", tenant_id, tenant_uuid)
            else:
                tenant_uuid = str(row["id"])
                log.info("Resolved tenant '%s' → %s", tenant_id, tenant_uuid)

        def _where(last: datetime.datetime | None) -> str:
            if last:
                return f"id>0 AND dateLastModified>={int(last.timestamp() * 1000)}"
            return "id>0"

        if "placements" in entities:
            log.info("Fetching placements...")
            last = await _get_last_synced(conn, tenant_uuid, "placements")
            records = await _fetch_all(session, "Placement", PLACEMENT_FIELDS, where=_where(last))
            count = await sync_placements(conn, tenant_uuid, records)
            await _record_sync(conn, tenant_uuid, "placements", count)
            log.info("Upserted %d placements", count)

        if "billable_charges" in entities:
            log.info("Fetching billable charges...")
            last = await _get_last_synced(conn, tenant_uuid, "billable_charges")
            records = await _fetch_all(session, "BillableCharge", BILLABLE_CHARGE_FIELDS, where=_where(last))
            count = await sync_billable_charges(conn, tenant_uuid, records)
            await _record_sync(conn, tenant_uuid, "billable_charges", count)
            log.info("Upserted %d billable charges", count)

        if "bill_masters" in entities:
            log.info("Fetching bill masters...")
            last = await _get_last_synced(conn, tenant_uuid, "bill_masters")
            records = await _fetch_all(session, "BillMaster", BILL_MASTER_FIELDS, where=_where(last))
            count = await sync_bill_masters(conn, tenant_uuid, records)
            await _record_sync(conn, tenant_uuid, "bill_masters", count)
            log.info("Upserted %d bill masters", count)

        if "bill_master_transactions" in entities:
            log.info("Fetching bill master transactions...")
            last = await _get_last_synced(conn, tenant_uuid, "bill_master_transactions")
            records = await _fetch_all(session, "BillMasterTransaction", BILL_MASTER_TRANSACTION_FIELDS, where=_where(last))
            count = await sync_bill_master_transactions(conn, tenant_uuid, records)
            await _record_sync(conn, tenant_uuid, "bill_master_transactions", count)
            log.info("Upserted %d bill master transactions", count)

        if "payable_charges" in entities:
            log.info("Fetching payable charges...")
            last = await _get_last_synced(conn, tenant_uuid, "payable_charges")
            records = await _fetch_all(session, "PayableCharge", PAYABLE_CHARGE_FIELDS, where=_where(last))
            count = await sync_payable_charges(conn, tenant_uuid, records)
            await _record_sync(conn, tenant_uuid, "payable_charges", count)
            log.info("Upserted %d payable charges", count)

        if "pay_masters" in entities:
            log.info("Fetching pay masters...")
            last = await _get_last_synced(conn, tenant_uuid, "pay_masters")
            records = await _fetch_all(session, "PayMaster", PAY_MASTER_FIELDS, where=_where(last))
            count = await sync_pay_masters(conn, tenant_uuid, records)
            await _record_sync(conn, tenant_uuid, "pay_masters", count)
            log.info("Upserted %d pay masters", count)

        if "pay_master_transactions" in entities:
            log.info("Fetching pay master transactions...")
            last = await _get_last_synced(conn, tenant_uuid, "pay_master_transactions")
            records = await _fetch_all(session, "PayMasterTransaction", PAY_MASTER_TRANSACTION_FIELDS, where=_where(last))
            count = await sync_pay_master_transactions(conn, tenant_uuid, records)
            await _record_sync(conn, tenant_uuid, "pay_master_transactions", count)
            log.info("Upserted %d pay master transactions", count)

        if "client_corporations" in entities:
            log.info("Fetching client corporations...")
            last = await _get_last_synced(conn, tenant_uuid, "client_corporations")
            records = await _fetch_all(session, "ClientCorporation", CLIENT_CORPORATION_FIELDS, where=_where(last))
            count = await sync_client_corporations(conn, tenant_uuid, records)
            await _record_sync(conn, tenant_uuid, "client_corporations", count)
            log.info("Upserted %d client corporations", count)

        if "job_orders" in entities:
            log.info("Fetching job orders...")
            last = await _get_last_synced(conn, tenant_uuid, "job_orders")
            records = await _fetch_all(session, "JobOrder", JOB_ORDER_FIELDS, where=_where(last))
            count = await sync_job_orders(conn, tenant_uuid, records)
            await _record_sync(conn, tenant_uuid, "job_orders", count)
            log.info("Upserted %d job orders", count)

        if "candidates" in entities:
            log.info("Fetching candidates...")
            records = await _search_all(session, "Candidate", CANDIDATE_FIELDS)
            count = await sync_candidates(conn, tenant_uuid, records)
            await _record_sync(conn, tenant_uuid, "candidates", count)
            log.info("Upserted %d candidates", count)

        if "timesheets" in entities:
            log.info("Fetching timesheets...")
            last = await _get_last_synced(conn, tenant_uuid, "timesheets")
            records = await _fetch_all(session, "Timesheet", TIMESHEET_FIELDS, where=_where(last))
            count = await sync_timesheets(conn, tenant_uuid, records)
            await _record_sync(conn, tenant_uuid, "timesheets", count)
            log.info("Upserted %d timesheets", count)

        if "timesheet_entries" in entities:
            log.info("Fetching timesheet entries...")
            last = await _get_last_synced(conn, tenant_uuid, "timesheet_entries")
            records = await _fetch_all(session, "TimesheetEntry", TIMESHEET_ENTRY_FIELDS, where=_where(last))
            count = await sync_timesheet_entries(conn, tenant_uuid, records)
            await _record_sync(conn, tenant_uuid, "timesheet_entries", count)
            log.info("Upserted %d timesheet entries", count)

        if "invoices" in entities:
            log.info("Fetching invoices...")
            last = await _get_last_synced(conn, tenant_uuid, "invoices")
            records = await _fetch_all(session, "InvoiceStatement", INVOICE_FIELDS, where=_where(last))
            count = await sync_invoices(conn, tenant_uuid, records)
            await _record_sync(conn, tenant_uuid, "invoices", count)
            log.info("Upserted %d invoices", count)

    finally:
        await conn.close()

    log.info("Sync complete.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync Bullhorn pay/bill data to the database")
    parser.add_argument("--tenant-id", default=os.getenv("STAFFINGAGENT_TENANT", "default"))
    all_entities = [
        "billable_charges", "bill_masters", "bill_master_transactions",
        "payable_charges", "pay_masters", "pay_master_transactions",
        "client_corporations", "candidates", "job_orders",
        "placements", "timesheets", "timesheet_entries", "invoices",
    ]
    parser.add_argument(
        "--entity",
        choices=all_entities,
        action="append",
        dest="entities",
        help="Entity to sync (repeatable, default: all). E.g. --entity placements --entity candidates",
    )
    args = parser.parse_args()
    entities = args.entities if args.entities else all_entities
    asyncio.run(run_sync(args.tenant_id, entities))


if __name__ == "__main__":
    main()
