# YottaFlex Payroll Pipeline

End-to-end **synthetic data generation and validation pipeline** for the YottaFlex Code Challenge.

---

## Quick Start

```bash
# 1 – Install dependencies
pip install -r requirements.txt

# 2 – Generate synthetic data + inject anomalies
python src/generate_data.py

# 3 – Run validation engine
python src/validate_payroll.py
```

Both scripts are idempotent. Running them twice with the same seed produces
mathematically identical results.

---

## Project Structure

```
yottaflex-payroll/
├── src/
│   ├── generate_data.py      # Step 1 – Synthetic data generator + anomaly injector
│   └── validate_payroll.py   # Step 2 – Business-rule validator + export engine
├── data/                     # Auto-created on first run
│   ├── Employee.csv
│   ├── PayPeriod.csv
│   ├── TimeEntry.csv
│   ├── LeaveRecord.csv
│   ├── Allowance.csv
│   ├── Deduction.csv
│   ├── PayrollSummary.csv
│   └── ground_truth.json     # ⚠ Ground truth – NOT read by validate_payroll.py
├── output/                   # Auto-created on first run
│   ├── Exceptions.csv        # Appended on every validation run (history preserved)
│   └── PayrollExport.csv     # Clean, approved records only
├── requirements.txt
└── README.md
```

---

## Global Seed

| Parameter | Value       |
|-----------|-------------|
| Seed      | `20261022`  |
| Applied to| `numpy.random`, `random`, `Faker` |

Running `generate_data.py` **any number of times** with the same Python
environment produces the same row counts, IDs, and field values.

---

## Data Dictionary

### Employee.csv

| Column | Type | Description |
|--------|------|-------------|
| `employee_id` | string | Zero-padded ID — `EMP-000001` … `EMP-003000` |
| `first_name` | string | Faker-generated |
| `last_name` | string | Faker-generated |
| `department` | string | One of 8 departments |
| `employment_type` | string | Full-Time / Part-Time / Contractor |
| `pay_basis` | string | Hourly / Salary (Contractors are always Salary) |
| `hourly_rate` | float | Populated only when `pay_basis=Hourly` |
| `annual_salary` | float | Populated only when `pay_basis=Salary` |
| `hire_date` | date | 2015-01-01 – 2025-12-31 |
| `is_active` | bool | Always `True` in baseline |

### PayPeriod.csv

| Column | Type | Description |
|--------|------|-------------|
| `period_id` | string | `PP-2026-01`, `PP-2026-02`, `PP-2026-03` |
| `period_start` | date | First calendar day of the month |
| `period_end` | date | Last calendar day of the month |
| `working_days` | int | Count of Mon–Fri days in the period |
| `max_regular_hours` | int | `184` — business-rule ceiling |
| `status` | string | `Closed` |

### TimeEntry.csv

| Column | Type | Description |
|--------|------|-------------|
| `time_entry_id` | string | `TIME-<seq:07d>-<YYYYMMDD>` |
| `employee_id` | FK→Employee | |
| `period_id` | FK→PayPeriod | |
| `entry_date` | date | One row per working day |
| `hours_worked` | float | 4–10, rounded to nearest 0.5 |
| `status` | string | Approved 95%, Pending 3%, Rejected 2% |
| `submitted_by` | string | Always = `employee_id` |
| `approved_by` | string | Populated only for `Approved` entries |

### LeaveRecord.csv

| Column | Type | Description |
|--------|------|-------------|
| `leave_id` | string | `LVE-<seq:07d>` |
| `employee_id` | FK→Employee | |
| `period_id` | FK→PayPeriod | |
| `leave_type` | string | Annual / Sick / Unpaid / Maternity / Paternity |
| `start_date` / `end_date` | date | Within the pay period |
| `days_taken` | int | 1–5 |
| `status` | string | Approved 85%, Pending 10%, Rejected 5% |
| `deduction_applied` | bool | `True` only for Unpaid leave |
| `deduction_applied_count` | int | Should always be `0` or `1` |

### Allowance.csv

| Column | Type | Description |
|--------|------|-------------|
| `allowance_id` | string | `ALW-<seq:07d>` |
| `employee_id` | FK→Employee | |
| `period_id` | FK→PayPeriod | |
| `allowance_type` | string | Housing / Transport / Medical / Meal / Communication |
| `amount` | float | 100 – 2000 |
| `approved` | bool | Always `True` in baseline |

### Deduction.csv

| Column | Type | Description |
|--------|------|-------------|
| `deduction_id` | string | `DED-<seq:07d>` |
| `employee_id` | FK→Employee | |
| `period_id` | FK→PayPeriod | |
| `deduction_type` | string | Tax / Pension / Health Insurance / Loan Repayment / Union Fee |
| `amount` | float | 50 – 1500 |
| `applied_count` | int | Should always be `1` |

### PayrollSummary.csv

| Column | Type | Description |
|--------|------|-------------|
| `employee_id` | FK→Employee | |
| `period_id` | FK→PayPeriod | |
| `total_hours` | float | Sum of approved TimeEntry hours |
| `base_pay` | float | Hourly × hours or salary / 12 |
| `total_allowances` | float | Sum of Allowance.amount |
| `total_deductions` | float | Sum of Deduction.amount |
| `gross_pay` | float | `base_pay + total_allowances` |
| `net_pay` | float | `gross_pay − total_deductions` |
| `recorded_net_pay` | float | Stored value — should equal `net_pay` |

### output/Exceptions.csv

| Column | Description |
|--------|-------------|
| `exception_id` | UUID |
| `run_timestamp` | UTC ISO-8601 timestamp of the validation run |
| `rule_id` | BR-001 … BR-005 |
| `rule_name` | Human-readable rule name |
| `employee_id` | Affected employee |
| `period_id` | Affected period |
| `entity_id` | The specific record ID (time_entry_id, leave_id, etc.) |
| `severity` | HIGH / MEDIUM / CRITICAL |
| `description` | Full plain-English explanation |
| `detected_value` | What was found |
| `expected_value` | What the rule requires |

### output/PayrollExport.csv

Clean, approved records only. Contains all PayrollSummary columns merged with
employee metadata (`first_name`, `last_name`, `department`, `employment_type`,
`pay_basis`) plus `export_timestamp` and `export_status = APPROVED`.

---

## Injected Anomalies & Detection Logic

| ID | Type | Target | Detection Rule |
|----|------|--------|----------------|
| ANO-001 | HoursExceedPeriodMaximum | EMP-000042, PP-2026-01 | BR-001: sum(approved hours) > 184 |
| ANO-002 | DuplicateAllowance | EMP-000137, PP-2026-02 | BR-002: duplicate (employee, period, allowance_type) |
| ANO-003 | LeaveDeductionAppliedTwice | EMP-000256 | BR-003: deduction_applied_count > 1 |
| ANO-004 | UnapprovedTimeInExport | EMP-000501, PP-2026-03 | BR-004: status != Approved but approved_by set |
| ANO-005 | PayrollReconciliationFailure | EMP-000888, PP-2026-02 | BR-005: recorded_net_pay ≠ gross − deductions (tol 0.01) |

### Ground Truth Firewall

`data/ground_truth.json` is written **only** by `generate_data.py`.
`validate_payroll.py` does **not** import, open, or read this file at any point.
Detection is based solely on business rules applied to the raw CSVs.

---

## Arithmetic Correctness

| Pay Basis | Formula |
|-----------|---------|
| Hourly | `base_pay = total_approved_hours × hourly_rate` |
| Salary | `base_pay = annual_salary / 12` |
| Gross | `gross_pay = base_pay + total_allowances` |
| Net | `net_pay = gross_pay − total_deductions` |

All monetary values are rounded to 2 decimal places.

---

## Foreign Key Integrity

- Every `employee_id` in TimeEntry, LeaveRecord, Allowance, Deduction, and PayrollSummary
  exists in Employee.csv (`EMP-000001` … `EMP-003000`).
- Every `period_id` in those tables matches one of `PP-2026-01`, `PP-2026-02`, `PP-2026-03`.
- Anomaly injection targets specific existing employees — no orphan keys are created.

---

## Reproducibility Guarantee

```
Seed 20261022 → identical results across any two runs on the same Python/library version.
```

Libraries pinned in `requirements.txt`. Tested with Python 3.10+, NumPy 1.26+,
pandas 2.1+, Faker 24+.