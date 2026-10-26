"""
YottaFlex Payroll - Synthetic Data Generator
=============================================
Seed    : 20261022
Python  : 3.10+

Generates:
  - 3,000 Employee records
  - 3 payroll periods (PP-2026-01 to PP-2026-03)
  - TimeEntry.csv, LeaveRecord.csv, Allowance.csv, Deduction.csv,
    Employee.csv, PayPeriod.csv, PayrollSummary.csv
  - Injects exactly 5 anomalies; logs ground truth to data/ground_truth.json

Run:
    python src/generate_data.py
"""

import json
import random
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from faker import Faker

# ---------------------------------------------------------------------------
# 0. GLOBAL SEED
# ---------------------------------------------------------------------------
GLOBAL_SEED = 20261022
random.seed(GLOBAL_SEED)
np.random.seed(GLOBAL_SEED)
fake = Faker("en_US")
Faker.seed(GLOBAL_SEED)

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

NUM_EMPLOYEES = 3_000
MAX_HOURS_PER_PERIOD = 184

PAY_PERIODS = [
    {"period_id": "PP-2026-01", "start": date(2026, 1, 1), "end": date(2026, 1, 31)},
    {"period_id": "PP-2026-02", "start": date(2026, 2, 1), "end": date(2026, 2, 28)},
    {"period_id": "PP-2026-03", "start": date(2026, 3, 1), "end": date(2026, 3, 31)},
]

DEPARTMENTS = ["Engineering","Finance","HR","Marketing","Operations","Legal","Sales","IT Support"]
EMPLOYMENT_TYPES = ["Full-Time", "Part-Time", "Contractor"]
ALLOWANCE_TYPES = ["Housing", "Transport", "Medical", "Meal", "Communication"]
DEDUCTION_TYPES = ["Tax", "Pension", "Health Insurance", "Loan Repayment", "Union Fee"]
LEAVE_TYPES = ["Annual", "Sick", "Unpaid", "Maternity", "Paternity"]
LEAVE_STATUSES = ["Approved", "Pending", "Rejected"]
TIME_STATUSES = ["Approved", "Pending", "Rejected"]


def working_days(start: date, end: date) -> list:
    days, cur = [], start
    while cur <= end:
        if cur.weekday() < 5:
            days.append(cur)
        cur += timedelta(days=1)
    return days


fmt_emp    = lambda n: f"EMP-{n:06d}"
fmt_time   = lambda s, d: f"TIME-{s:07d}-{d.strftime('%Y%m%d')}"
fmt_leave  = lambda s: f"LVE-{s:07d}"
fmt_allow  = lambda s: f"ALW-{s:07d}"
fmt_deduct = lambda s: f"DED-{s:07d}"


# ---------------------------------------------------------------------------
# EMPLOYEE
# ---------------------------------------------------------------------------
def generate_employees() -> pd.DataFrame:
    rng = np.random.default_rng(GLOBAL_SEED)
    rows = []
    for i in range(1, NUM_EMPLOYEES + 1):
        etype = rng.choice(EMPLOYMENT_TYPES)
        basis = "Salary" if etype == "Contractor" else rng.choice(["Hourly", "Salary"])
        hr = round(float(rng.uniform(15.0, 80.0)), 2) if basis == "Hourly" else None
        sal = round(float(rng.integers(40_000, 250_001)), 2) if basis == "Salary" else None
        hire = fake.date_between(start_date=date(2015, 1, 1), end_date=date(2025, 12, 31))
        rows.append({
            "employee_id": fmt_emp(i), "first_name": fake.first_name(),
            "last_name": fake.last_name(), "department": rng.choice(DEPARTMENTS),
            "employment_type": etype, "pay_basis": basis,
            "hourly_rate": hr, "annual_salary": sal,
            "hire_date": hire.isoformat(), "is_active": True,
        })
    df = pd.DataFrame(rows)
    df.to_csv(DATA_DIR / "Employee.csv", index=False)
    print(f"[Employee]       {len(df):>7,} rows")
    return df


# ---------------------------------------------------------------------------
# PAY PERIOD
# ---------------------------------------------------------------------------
def generate_pay_periods() -> pd.DataFrame:
    rows = [{"period_id": pp["period_id"], "period_start": pp["start"].isoformat(),
              "period_end": pp["end"].isoformat(),
              "working_days": len(working_days(pp["start"], pp["end"])),
              "max_regular_hours": MAX_HOURS_PER_PERIOD, "status": "Closed"}
             for pp in PAY_PERIODS]
    df = pd.DataFrame(rows)
    df.to_csv(DATA_DIR / "PayPeriod.csv", index=False)
    print(f"[PayPeriod]      {len(df):>7,} rows")
    return df


# ---------------------------------------------------------------------------
# TIME ENTRY
# ---------------------------------------------------------------------------
def generate_time_entries(employees: pd.DataFrame) -> pd.DataFrame:
    rng = np.random.default_rng(GLOBAL_SEED + 1)
    emp_ids = employees["employee_id"].tolist()
    rows, seq = [], 1
    for pp in PAY_PERIODS:
        wdays = working_days(pp["start"], pp["end"])
        for eid in emp_ids:
            statuses = rng.choice(TIME_STATUSES, p=[0.95, 0.03, 0.02], size=len(wdays))
            hours = (np.round(rng.uniform(4, 10, size=len(wdays)) * 2) / 2).tolist()
            for d, h, s in zip(wdays, hours, statuses):
                rows.append({
                    "time_entry_id": fmt_time(seq, d), "employee_id": eid,
                    "period_id": pp["period_id"], "entry_date": d.isoformat(),
                    "hours_worked": h, "status": s,
                    "submitted_by": eid, "approved_by": eid if s == "Approved" else None,
                })
                seq += 1
    df = pd.DataFrame(rows)
    df.to_csv(DATA_DIR / "TimeEntry.csv", index=False)
    print(f"[TimeEntry]      {len(df):>7,} rows")
    return df


# ---------------------------------------------------------------------------
# LEAVE RECORD
# ---------------------------------------------------------------------------
def generate_leave_records(employees: pd.DataFrame) -> pd.DataFrame:
    rng = np.random.default_rng(GLOBAL_SEED + 2)
    emp_ids = employees["employee_id"].tolist()
    rows, seq = [], 1
    for pp in PAY_PERIODS:
        wdays = working_days(pp["start"], pp["end"])
        on_leave = rng.choice(emp_ids, size=max(1, int(len(emp_ids) * 0.20)), replace=False)
        for eid in on_leave:
            dur = int(rng.integers(1, 6))
            si = int(rng.integers(0, max(1, len(wdays) - dur)))
            ldays = wdays[si: si + dur]
            ltype = rng.choice(LEAVE_TYPES)
            status = rng.choice(LEAVE_STATUSES, p=[0.85, 0.10, 0.05])
            ded = ltype == "Unpaid"
            rows.append({
                "leave_id": fmt_leave(seq), "employee_id": eid,
                "period_id": pp["period_id"], "leave_type": ltype,
                "start_date": ldays[0].isoformat(), "end_date": ldays[-1].isoformat(),
                "days_taken": len(ldays), "status": status,
                "deduction_applied": ded, "deduction_applied_count": 1 if ded else 0,
            })
            seq += 1
    df = pd.DataFrame(rows)
    df.to_csv(DATA_DIR / "LeaveRecord.csv", index=False)
    print(f"[LeaveRecord]    {len(df):>7,} rows")
    return df


# ---------------------------------------------------------------------------
# ALLOWANCE
# ---------------------------------------------------------------------------
def generate_allowances(employees: pd.DataFrame) -> pd.DataFrame:
    rng = np.random.default_rng(GLOBAL_SEED + 3)
    emp_ids = employees["employee_id"].tolist()
    rows, seq = [], 1
    for pp in PAY_PERIODS:
        for eid in emp_ids:
            n = int(rng.integers(1, 4))
            for atype in rng.choice(ALLOWANCE_TYPES, size=n, replace=False):
                rows.append({
                    "allowance_id": fmt_allow(seq), "employee_id": eid,
                    "period_id": pp["period_id"], "allowance_type": str(atype),
                    "amount": round(float(rng.uniform(100, 2001)), 2), "approved": True,
                })
                seq += 1
    df = pd.DataFrame(rows)
    df.to_csv(DATA_DIR / "Allowance.csv", index=False)
    print(f"[Allowance]      {len(df):>7,} rows")
    return df


# ---------------------------------------------------------------------------
# DEDUCTION
# ---------------------------------------------------------------------------
def generate_deductions(employees: pd.DataFrame) -> pd.DataFrame:
    rng = np.random.default_rng(GLOBAL_SEED + 4)
    emp_ids = employees["employee_id"].tolist()
    rows, seq = [], 1
    for pp in PAY_PERIODS:
        for eid in emp_ids:
            n = int(rng.integers(2, 5))
            for dtype in rng.choice(DEDUCTION_TYPES, size=n, replace=False):
                rows.append({
                    "deduction_id": fmt_deduct(seq), "employee_id": eid,
                    "period_id": pp["period_id"], "deduction_type": str(dtype),
                    "amount": round(float(rng.uniform(50, 1501)), 2), "applied_count": 1,
                })
                seq += 1
    df = pd.DataFrame(rows)
    df.to_csv(DATA_DIR / "Deduction.csv", index=False)
    print(f"[Deduction]      {len(df):>7,} rows")
    return df


# ---------------------------------------------------------------------------
# PAYROLL SUMMARY
# ---------------------------------------------------------------------------
def generate_payroll_summary(employees, time_df, allowance_df, deduction_df) -> pd.DataFrame:
    basis_map   = employees.set_index("employee_id")["pay_basis"].to_dict()
    hourly_map  = employees.set_index("employee_id")["hourly_rate"].to_dict()
    salary_map  = employees.set_index("employee_id")["annual_salary"].to_dict()

    time_agg  = (time_df[time_df["status"] == "Approved"]
                 .groupby(["employee_id","period_id"])["hours_worked"].sum()
                 .reset_index().rename(columns={"hours_worked":"total_hours"}))
    allow_agg = (allowance_df.groupby(["employee_id","period_id"])["amount"].sum()
                 .reset_index().rename(columns={"amount":"total_allowances"}))
    deduct_agg= (deduction_df.groupby(["employee_id","period_id"])["amount"].sum()
                 .reset_index().rename(columns={"amount":"total_deductions"}))

    rows = []
    for pp in PAY_PERIODS:
        pid = pp["period_id"]
        for eid in employees["employee_id"].tolist():
            hours = float(time_agg.loc[(time_agg.employee_id==eid)&(time_agg.period_id==pid),"total_hours"].sum())
            basis = basis_map.get(eid, "Salary")
            if basis == "Hourly":
                r = hourly_map.get(eid) or 0
                base_pay = round(hours * float(r), 2)
            else:
                s = salary_map.get(eid) or 0
                base_pay = round(float(s) / 12, 2)
            allowances  = float(allow_agg.loc[(allow_agg.employee_id==eid)&(allow_agg.period_id==pid),"total_allowances"].sum())
            deductions  = float(deduct_agg.loc[(deduct_agg.employee_id==eid)&(deduct_agg.period_id==pid),"total_deductions"].sum())
            gross_pay   = round(base_pay + allowances, 2)
            net_pay     = round(gross_pay - deductions, 2)
            rows.append({
                "employee_id": eid, "period_id": pid,
                "total_hours": round(hours, 2), "base_pay": base_pay,
                "total_allowances": round(allowances, 2),
                "total_deductions": round(deductions, 2),
                "gross_pay": gross_pay, "net_pay": net_pay,
                "recorded_net_pay": net_pay,
            })
    df = pd.DataFrame(rows)
    df.to_csv(DATA_DIR / "PayrollSummary.csv", index=False)
    print(f"[PayrollSummary] {len(df):>7,} rows")
    return df


# ---------------------------------------------------------------------------
# ANOMALY INJECTION
# ---------------------------------------------------------------------------
def inject_anomalies(time_df, leave_df, allowance_df, deduction_df, payroll_df):
    gt = {"description": "Ground truth - DO NOT load in validate_payroll.py",
          "seed": GLOBAL_SEED, "anomalies": []}

    # ANO-001: Hours exceed period maximum
    A1, P1, D1 = "EMP-000042", "PP-2026-01", date(2026, 1, 30)
    mask = (time_df.employee_id==A1)&(time_df.period_id==P1)&(time_df.status=="Approved")
    cur_h = float(time_df.loc[mask, "hours_worked"].sum())
    ovf   = round(MAX_HOURS_PER_PERIOD - cur_h + 20.0, 2)
    seq1  = int(time_df["time_entry_id"].str.extract(r"TIME-(\d+)-")[0].max()) + 1
    eid1  = fmt_time(seq1, D1)
    time_df = pd.concat([time_df, pd.DataFrame([{
        "time_entry_id": eid1, "employee_id": A1, "period_id": P1,
        "entry_date": D1.isoformat(), "hours_worked": ovf,
        "status": "Approved", "submitted_by": A1, "approved_by": A1,
    }])], ignore_index=True)
    gt["anomalies"].append({"anomaly_id":"ANO-001","type":"HoursExceedPeriodMaximum",
        "employee_id":A1,"period_id":P1,"entity_id":eid1,
        "injected_hours":ovf,"total_hours_after":round(cur_h+ovf,2),
        "description":f"{A1} has {round(cur_h+ovf,2)} approved hrs in {P1} (max {MAX_HOURS_PER_PERIOD})"})
    print(f"  [ANO-001] {eid1}: +{ovf} hrs -> total {round(cur_h+ovf,2)}")

    # ANO-002: Duplicate allowance
    A2, P2 = "EMP-000137", "PP-2026-02"
    orig = allowance_df.loc[(allowance_df.employee_id==A2)&(allowance_df.period_id==P2)].iloc[0].copy()
    seq2 = int(allowance_df["allowance_id"].str.extract(r"ALW-(\d+)")[0].max()) + 1
    eid2 = fmt_allow(seq2)
    dup  = orig.copy(); dup["allowance_id"] = eid2
    allowance_df = pd.concat([allowance_df, dup.to_frame().T], ignore_index=True)
    gt["anomalies"].append({"anomaly_id":"ANO-002","type":"DuplicateAllowance",
        "employee_id":A2,"period_id":P2,"entity_id":eid2,
        "original_id":orig["allowance_id"],"allowance_type":orig["allowance_type"],
        "amount":float(orig["amount"]),
        "description":f"{orig['allowance_id']} duplicated as {eid2} for {A2} in {P2}"})
    print(f"  [ANO-002] {eid2} duplicates {orig['allowance_id']} ({A2})")

    # ANO-003: Leave deduction applied twice
    A3 = "EMP-000256"
    mask3 = (leave_df.employee_id==A3)&(leave_df.deduction_applied==True)
    a3rows = leave_df.loc[mask3]
    if a3rows.empty:
        seq3 = int(leave_df["leave_id"].str.extract(r"LVE-(\d+)")[0].max()) + 1
        eid3 = fmt_leave(seq3)
        leave_df = pd.concat([leave_df, pd.DataFrame([{
            "leave_id":eid3,"employee_id":A3,"period_id":"PP-2026-01",
            "leave_type":"Unpaid","start_date":"2026-01-05","end_date":"2026-01-05",
            "days_taken":1,"status":"Approved","deduction_applied":True,"deduction_applied_count":2,
        }])], ignore_index=True)
    else:
        idx3 = a3rows.index[0]
        eid3 = leave_df.at[idx3, "leave_id"]
        leave_df.at[idx3, "deduction_applied_count"] = 2
    gt["anomalies"].append({"anomaly_id":"ANO-003","type":"LeaveDeductionAppliedTwice",
        "employee_id":A3,"entity_id":eid3,
        "description":f"{eid3} for {A3} has deduction_applied_count=2 (must be 1)"})
    print(f"  [ANO-003] Double deduction on {eid3} ({A3})")

    # ANO-004: Unapproved time flagged for export
    A4, P4 = "EMP-000501", "PP-2026-03"
    mask4 = (time_df.employee_id==A4)&(time_df.period_id==P4)
    idx4 = time_df.loc[mask4].index[0]
    eid4 = time_df.at[idx4, "time_entry_id"]
    time_df.at[idx4, "status"] = "Pending"
    time_df.at[idx4, "approved_by"] = A4
    gt["anomalies"].append({"anomaly_id":"ANO-004","type":"UnapprovedTimeInExport",
        "employee_id":A4,"period_id":P4,"entity_id":eid4,
        "description":f"{eid4} is Pending but has approved_by set (ready for export)"})
    print(f"  [ANO-004] {eid4} Pending+approved_by ({A4})")

    # ANO-005: Payroll reconciliation failure
    A5, P5 = "EMP-000888", "PP-2026-02"
    mask5 = (payroll_df.employee_id==A5)&(payroll_df.period_id==P5)
    idx5 = payroll_df.loc[mask5].index[0]
    correct = float(payroll_df.at[idx5, "net_pay"])
    tampered = round(correct + 999.99, 2)
    payroll_df.at[idx5, "recorded_net_pay"] = tampered
    gt["anomalies"].append({"anomaly_id":"ANO-005","type":"PayrollReconciliationFailure",
        "employee_id":A5,"period_id":P5,"entity_id":f"{A5}_{P5}",
        "correct_net_pay":correct,"recorded_net_pay":tampered,"delta":round(tampered-correct,2),
        "description":f"{A5}/{P5}: net_pay={correct:.2f} but recorded={tampered:.2f}"})
    print(f"  [ANO-005] {A5}/{P5}: correct={correct:.2f}, stored={tampered:.2f}")

    return time_df, leave_df, allowance_df, deduction_df, payroll_df, gt


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------
def main():
    print("=" * 65)
    print("  YottaFlex Payroll - Synthetic Data Generator")
    print(f"  Global Seed  : {GLOBAL_SEED}")
    print(f"  Employees    : {NUM_EMPLOYEES:,}")
    print(f"  Pay Periods  : {[pp['period_id'] for pp in PAY_PERIODS]}")
    print("=" * 65)

    emp   = generate_employees()
    generate_pay_periods()
    te    = generate_time_entries(emp)
    lv    = generate_leave_records(emp)
    al    = generate_allowances(emp)
    ded   = generate_deductions(emp)
    ps    = generate_payroll_summary(emp, te, al, ded)

    print("\n-- Injecting Anomalies --")
    te, lv, al, ded, ps, gt = inject_anomalies(te, lv, al, ded, ps)

    te.to_csv(DATA_DIR / "TimeEntry.csv", index=False)
    lv.to_csv(DATA_DIR / "LeaveRecord.csv", index=False)
    al.to_csv(DATA_DIR / "Allowance.csv", index=False)
    ded.to_csv(DATA_DIR / "Deduction.csv", index=False)
    ps.to_csv(DATA_DIR / "PayrollSummary.csv", index=False)

    gt_path = DATA_DIR / "ground_truth.json"
    with open(gt_path, "w", encoding="utf-8") as f:
        json.dump(gt, f, indent=2, ensure_ascii=False)
    print(f"\n[GroundTruth] Written -> {gt_path}")
    print("  WARNING: Never load ground_truth.json in validate_payroll.py")

    print(f"\nRow counts: TimeEntry={len(te):,} | LeaveRecord={len(lv):,} | "
          f"Allowance={len(al):,} | Deduction={len(ded):,} | PayrollSummary={len(ps):,}")
    print("\nDone.")


if __name__ == "__main__":
    main()