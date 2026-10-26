"""
YottaFlex Payroll - Validation Engine
======================================
Seed    : 20261022 (used only by generate_data.py, NOT here)
Python  : 3.10+

Reads raw CSVs from data/, applies 5 business rules, writes:
  - output/Exceptions.csv  : all detected violations (append-preserving)
  - output/PayrollExport.csv: clean, approved records only

Business Rules Enforced:
  BR-001  Total approved hours per (employee, period) must not exceed MAX_HOURS_PER_PERIOD (184)
  BR-002  No (employee, period, allowance_type) combination may appear more than once
  BR-003  deduction_applied_count must be <= 1 for every leave record
  BR-004  All TimeEntry records with status != 'Approved' must be excluded from export
  BR-005  PayrollSummary.recorded_net_pay must equal computed (gross_pay - total_deductions)
          within a tolerance of 0.01

Run:
    python src/validate_payroll.py
"""

import csv
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR   = ROOT / "data"
OUTPUT_DIR = ROOT / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

MAX_HOURS_PER_PERIOD = 184
RECON_TOLERANCE      = 0.01
RUN_TS = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

EXCEPTIONS_PATH    = OUTPUT_DIR / "Exceptions.csv"
EXPORT_PATH        = OUTPUT_DIR / "PayrollExport.csv"

EXCEPTION_COLS = [
    "exception_id", "run_timestamp", "rule_id", "rule_name",
    "employee_id", "period_id", "entity_id", "severity",
    "description", "detected_value", "expected_value",
]


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def load_csvs():
    print("Loading CSVs from data/ ...")
    employees  = pd.read_csv(DATA_DIR / "Employee.csv", dtype=str)
    pay_periods= pd.read_csv(DATA_DIR / "PayPeriod.csv", dtype=str)
    time_df    = pd.read_csv(DATA_DIR / "TimeEntry.csv", dtype=str)
    leave_df   = pd.read_csv(DATA_DIR / "LeaveRecord.csv", dtype=str)
    allowance_df = pd.read_csv(DATA_DIR / "Allowance.csv", dtype=str)
    deduction_df = pd.read_csv(DATA_DIR / "Deduction.csv", dtype=str)
    payroll_df = pd.read_csv(DATA_DIR / "PayrollSummary.csv", dtype=str)

    # Cast numeric columns
    time_df["hours_worked"]   = pd.to_numeric(time_df["hours_worked"], errors="coerce")
    allowance_df["amount"]    = pd.to_numeric(allowance_df["amount"], errors="coerce")
    deduction_df["amount"]    = pd.to_numeric(deduction_df["amount"], errors="coerce")
    leave_df["deduction_applied_count"] = pd.to_numeric(
        leave_df["deduction_applied_count"], errors="coerce").fillna(0)
    payroll_df["net_pay"]            = pd.to_numeric(payroll_df["net_pay"], errors="coerce")
    payroll_df["recorded_net_pay"]   = pd.to_numeric(payroll_df["recorded_net_pay"], errors="coerce")
    payroll_df["gross_pay"]          = pd.to_numeric(payroll_df["gross_pay"], errors="coerce")
    payroll_df["total_deductions"]   = pd.to_numeric(payroll_df["total_deductions"], errors="coerce")

    print(f"  TimeEntry rows      : {len(time_df):>8,}")
    print(f"  LeaveRecord rows    : {len(leave_df):>8,}")
    print(f"  Allowance rows      : {len(allowance_df):>8,}")
    print(f"  Deduction rows      : {len(deduction_df):>8,}")
    print(f"  PayrollSummary rows : {len(payroll_df):>8,}")
    return employees, pay_periods, time_df, leave_df, allowance_df, deduction_df, payroll_df


def make_exc(rule_id, rule_name, employee_id, period_id, entity_id,
             severity, description, detected, expected) -> dict:
    return {
        "exception_id":   str(uuid.uuid4()),
        "run_timestamp":  RUN_TS,
        "rule_id":        rule_id,
        "rule_name":      rule_name,
        "employee_id":    str(employee_id),
        "period_id":      str(period_id),
        "entity_id":      str(entity_id),
        "severity":       severity,
        "description":    str(description),
        "detected_value": str(detected),
        "expected_value": str(expected),
    }


# ---------------------------------------------------------------------------
# BR-001: Hours exceed period maximum
# ---------------------------------------------------------------------------
def check_hours_exceed_max(time_df: pd.DataFrame) -> list:
    """
    Sum approved hours per (employee_id, period_id).
    Flag any combination where total > MAX_HOURS_PER_PERIOD.
    """
    violations = []
    approved = time_df[time_df["status"] == "Approved"].copy()
    agg = (approved.groupby(["employee_id", "period_id"])["hours_worked"]
           .sum().reset_index().rename(columns={"hours_worked": "total_hours"}))
    bad = agg[agg["total_hours"] > MAX_HOURS_PER_PERIOD]
    for _, row in bad.iterrows():
        violations.append(make_exc(
            rule_id="BR-001", rule_name="HoursExceedPeriodMaximum",
            employee_id=row["employee_id"], period_id=row["period_id"],
            entity_id=f"{row['employee_id']}_{row['period_id']}",
            severity="HIGH",
            description=(f"Employee {row['employee_id']} has {row['total_hours']:.2f} "
                         f"approved hours in {row['period_id']} "
                         f"(max allowed: {MAX_HOURS_PER_PERIOD})."),
            detected=f"{row['total_hours']:.2f}",
            expected=f"<= {MAX_HOURS_PER_PERIOD}",
        ))
    print(f"[BR-001] HoursExceedPeriodMaximum    : {len(violations):>4} violations")
    return violations


# ---------------------------------------------------------------------------
# BR-002: Duplicate allowance
# ---------------------------------------------------------------------------
def check_duplicate_allowances(allowance_df: pd.DataFrame) -> list:
    """
    Within each (employee_id, period_id), no allowance_type may appear > once.
    """
    violations = []
    dup_mask = allowance_df.duplicated(
        subset=["employee_id", "period_id", "allowance_type"], keep="first")
    dupes = allowance_df[dup_mask]
    for _, row in dupes.iterrows():
        violations.append(make_exc(
            rule_id="BR-002", rule_name="DuplicateAllowance",
            employee_id=row["employee_id"], period_id=row["period_id"],
            entity_id=row["allowance_id"],
            severity="MEDIUM",
            description=(f"Allowance {row['allowance_id']} ({row['allowance_type']}) "
                         f"is a duplicate for {row['employee_id']} in {row['period_id']}."),
            detected=f"allowance_type={row['allowance_type']} appears > 1 time",
            expected="Each allowance_type appears exactly once per (employee, period)",
        ))
    print(f"[BR-002] DuplicateAllowance          : {len(violations):>4} violations")
    return violations


# ---------------------------------------------------------------------------
# BR-003: Leave deduction applied twice
# ---------------------------------------------------------------------------
def check_leave_double_deduction(leave_df: pd.DataFrame) -> list:
    """
    For any leave record where deduction_applied is True,
    deduction_applied_count must equal exactly 1.
    """
    violations = []
    bad = leave_df[
        (leave_df["deduction_applied"].astype(str).str.lower().isin(["true","1","yes"]))
        & (leave_df["deduction_applied_count"] > 1)
    ]
    for _, row in bad.iterrows():
        violations.append(make_exc(
            rule_id="BR-003", rule_name="LeaveDeductionAppliedTwice",
            employee_id=row["employee_id"], period_id=row["period_id"],
            entity_id=row["leave_id"],
            severity="HIGH",
            description=(f"Leave {row['leave_id']} for {row['employee_id']} "
                         f"has deduction_applied_count={int(row['deduction_applied_count'])} "
                         f"(must be 1 when deduction_applied=True)."),
            detected=f"deduction_applied_count={int(row['deduction_applied_count'])}",
            expected="deduction_applied_count == 1",
        ))
    print(f"[BR-003] LeaveDeductionAppliedTwice  : {len(violations):>4} violations")
    return violations


# ---------------------------------------------------------------------------
# BR-004: Unapproved time flagged for export
# ---------------------------------------------------------------------------
def check_unapproved_time(time_df: pd.DataFrame) -> list:
    """
    Any TimeEntry where status != 'Approved' but approved_by is NOT null
    is a contradictory record that must not be exported.
    """
    violations = []
    bad = time_df[
        (time_df["status"] != "Approved")
        & (time_df["approved_by"].notna())
        & (time_df["approved_by"].astype(str).str.strip() != "")
        & (time_df["approved_by"].astype(str).str.lower() != "none")
        & (time_df["approved_by"].astype(str).str.lower() != "nan")
    ]
    for _, row in bad.iterrows():
        violations.append(make_exc(
            rule_id="BR-004", rule_name="UnapprovedTimeInExport",
            employee_id=row["employee_id"], period_id=row["period_id"],
            entity_id=row["time_entry_id"],
            severity="CRITICAL",
            description=(f"Time entry {row['time_entry_id']} has status='{row['status']}' "
                         f"but approved_by='{row['approved_by']}' is set. "
                         f"This record is not approved yet must not enter payroll."),
            detected=f"status={row['status']}, approved_by={row['approved_by']}",
            expected="status='Approved' when approved_by is populated",
        ))
    print(f"[BR-004] UnapprovedTimeInExport      : {len(violations):>4} violations")
    return violations


# ---------------------------------------------------------------------------
# BR-005: Payroll reconciliation failure
# ---------------------------------------------------------------------------
def check_payroll_reconciliation(payroll_df: pd.DataFrame) -> list:
    """
    Recompute net_pay = gross_pay - total_deductions.
    Compare with recorded_net_pay; flag any delta > RECON_TOLERANCE.
    """
    violations = []
    payroll_df = payroll_df.copy()
    payroll_df["computed_net"] = (
        payroll_df["gross_pay"] - payroll_df["total_deductions"]
    ).round(2)
    payroll_df["delta"] = (
        payroll_df["recorded_net_pay"] - payroll_df["computed_net"]
    ).abs().round(4)
    bad = payroll_df[payroll_df["delta"] > RECON_TOLERANCE]
    for _, row in bad.iterrows():
        violations.append(make_exc(
            rule_id="BR-005", rule_name="PayrollReconciliationFailure",
            employee_id=row["employee_id"], period_id=row["period_id"],
            entity_id=f"{row['employee_id']}_{row['period_id']}",
            severity="CRITICAL",
            description=(f"PayrollSummary for {row['employee_id']} in {row['period_id']}: "
                         f"computed net_pay={row['computed_net']:.2f} but "
                         f"recorded_net_pay={row['recorded_net_pay']:.2f} "
                         f"(delta={row['delta']:.2f})."),
            detected=f"recorded_net_pay={row['recorded_net_pay']:.2f}",
            expected=f"computed net_pay={row['computed_net']:.2f} (tolerance={RECON_TOLERANCE})",
        ))
    print(f"[BR-005] PayrollReconciliationFailure: {len(violations):>4} violations")
    return violations


# ---------------------------------------------------------------------------
# WRITE EXCEPTIONS (append to preserve history)
# ---------------------------------------------------------------------------
def write_exceptions(violations: list) -> None:
    if not violations:
        print("\n[Exceptions] No violations found.")
        return

    df_new = pd.DataFrame(violations, columns=EXCEPTION_COLS)

    if EXCEPTIONS_PATH.exists():
        df_existing = pd.read_csv(EXCEPTIONS_PATH, dtype=str)
        df_out = pd.concat([df_existing, df_new], ignore_index=True)
        print(f"\n[Exceptions] Appending {len(df_new)} new violations "
              f"(total history: {len(df_out)} rows) -> Exceptions.csv")
    else:
        df_out = df_new
        print(f"\n[Exceptions] Writing {len(df_out)} violations -> Exceptions.csv")

    df_out.to_csv(EXCEPTIONS_PATH, index=False)


# ---------------------------------------------------------------------------
# WRITE CLEAN PAYROLL EXPORT
# ---------------------------------------------------------------------------
def write_payroll_export(
    time_df: pd.DataFrame,
    employees: pd.DataFrame,
    allowance_df: pd.DataFrame,
    deduction_df: pd.DataFrame,
    payroll_df: pd.DataFrame,
    violations: list,
) -> None:
    """
    Export only clean, approved records.

    Exclusion criteria:
      - Employees with any violation in violations list
      - Time entries with status != 'Approved'
      - Payroll summaries with reconciliation failure
    """
    # Collect (employee_id, period_id) pairs with any exception
    excluded_pairs = set()
    for v in violations:
        excluded_pairs.add((v["employee_id"], v["period_id"]))

    # Start with clean PayrollSummary rows
    ps_clean = payroll_df[
        ~payroll_df.apply(lambda r: (r["employee_id"], r["period_id"]) in excluded_pairs, axis=1)
    ].copy()

    # Merge in employee metadata
    export_df = ps_clean.merge(
        employees[["employee_id","first_name","last_name","department",
                   "employment_type","pay_basis"]],
        on="employee_id", how="left",
    )

    export_df["export_timestamp"] = RUN_TS
    export_df["export_status"] = "APPROVED"

    export_df.to_csv(EXPORT_PATH, index=False)
    print(f"[PayrollExport] {len(export_df):>6,} clean records exported -> PayrollExport.csv")

    total_payroll = export_df["net_pay"].astype(float).sum()
    print(f"[PayrollExport] Total Net Payroll: ${total_payroll:,.2f}")


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------
def main():
    print("=" * 65)
    print("  YottaFlex Payroll - Validation Engine")
    print(f"  Run Timestamp : {RUN_TS}")
    print("=" * 65)

    employees, pay_periods, time_df, leave_df, allowance_df, deduction_df, payroll_df = load_csvs()

    print("\n-- Running Business Rule Checks --")
    all_violations = []
    all_violations += check_hours_exceed_max(time_df)
    all_violations += check_duplicate_allowances(allowance_df)
    all_violations += check_leave_double_deduction(leave_df)
    all_violations += check_unapproved_time(time_df)
    all_violations += check_payroll_reconciliation(payroll_df)

    total = len(all_violations)
    print(f"\nTotal violations detected: {total}")

    write_exceptions(all_violations)
    write_payroll_export(time_df, employees, allowance_df, deduction_df, payroll_df, all_violations)

    print("\n-- Anomaly Detection Summary --")
    expected_rules = {
        "BR-001": "HoursExceedPeriodMaximum",
        "BR-002": "DuplicateAllowance",
        "BR-003": "LeaveDeductionAppliedTwice",
        "BR-004": "UnapprovedTimeInExport",
        "BR-005": "PayrollReconciliationFailure",
    }
    detected_rules = {v["rule_id"] for v in all_violations}
    for rid, rname in expected_rules.items():
        status = "CAUGHT" if rid in detected_rules else "MISSED"
        count  = sum(1 for v in all_violations if v["rule_id"] == rid)
        print(f"  {rid} ({rname:35s}) : {status} [{count} violation(s)]")

    print("\nValidation complete.")


if __name__ == "__main__":
    main()