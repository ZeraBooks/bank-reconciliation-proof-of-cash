"""Generate fictional book and bank data for bank reconciliations.

    python3 scripts/generate_samples.py

6 fictional bank accounts, July to September 2026. For each month:
  samples/accounts/<account>/<YYYY-MM>/statement.json
  samples/accounts/<account>/<YYYY-MM>/bank.csv
  samples/accounts/<account>/<YYYY-MM>/book.csv
  samples/accounts/<account>/<YYYY-MM>/reconciliation.json
Checks clear 2 to 25 days after they're written, deposits made on the last
days of the month clear next month, and the bank charges fees, pays interest
and returns a customer check now and then, none of which is in the books
until the reconciliation finds it. One month has a transposed book entry.
The adjustments are posted at month end, so each month's book opening is
last month's adjusted balance. Seeded, so the files are the same every run.
"""
import csv
import datetime as dt
import json
import os
import random
import shutil
from decimal import Decimal

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "samples")
COLS = ["date", "ref", "description", "amount"]

ACCOUNTS = [
    ("juniper-operating", "Juniper Lane Bakery LLC, Harbor Point Savings Bank checking ...4471", 1043, "21840.55", 1.0),
    ("okafor-operating", "Okafor Family Dental PC, Cedar Valley Credit Union checking ...0932", 5210, "48211.07", 2.2),
    ("brightwater-operating", "Brightwater Landscaping Inc, Northfield National Bank checking ...7718", 3301, "16422.90", 1.5),
    ("redline-operating", "Redline Freight Co, Prairie Trust Bank checking ...2256", 8817, "33905.40", 2.8),
    ("st-brendan-pantry", "St. Brendan Parish Food Pantry, Harbor Point Savings Bank checking ...6603", 610, "9120.18", 0.5),
    ("tan-ruiz-operating", "Tan & Ruiz Law Group, Northfield National Bank operating ...9014", 7032, "57300.00", 1.8),
]
PAYEES = ["Sysco Foods", "Main Street Properties LLC", "Valley Propane Co", "Hartwell Insurance Agency", "Ortiz Plumbing",
          "Grainger", "County Treasurer", "Greenleaf Janitorial", "Riverbend Printing", "Pioneer Equipment Rental"]
ACH = [("GUSTO PAYROLL", 3000, 9000), ("PG&E ONLINE PAYMENT", 150, 700), ("COMCAST BUSINESS", 110, 260), ("AMEX EPAYMENT", 800, 4000),
       ("STATE FARM INSURANCE", 120, 600)]
DEPOSITS = [("SQUARE DEPOSIT", 400, 3200), ("MOBILE CHECK DEPOSIT", 300, 4500), ("ACH CREDIT CUSTOMER", 900, 7000), ("BRANCH DEPOSIT", 200, 2500)]


def money(rng, lo, hi, s):
    return (Decimal(rng.randint(int(lo * 100), int(hi * 100))) * Decimal(str(s)) / 100).quantize(Decimal("0.01"))


def ser(x):
    return {"date": x["date"].isoformat(), "ref": x["ref"], "description": x["description"], "amount": f"{x['amount']:.2f}"}


def write(path, items):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS, lineterminator="\r\n")
        w.writeheader()
        for x in sorted(items, key=lambda r: (r["date"], r["ref"], r["description"])):
            w.writerow(ser(x))


def main():
    rng = random.Random(20261105)
    shutil.rmtree(os.path.join(OUT, "accounts"), ignore_errors=True)
    shutil.rmtree(os.path.join(OUT, "invalid"), ignore_errors=True)
    os.makedirs(os.path.join(OUT, "invalid"))
    index = []
    for ai, (slug, name, check_no, opening, s) in enumerate(ACCOUNTS):
        bank_bal = Decimal(opening)
        # Items written in June that the bank hadn't paid by June 30.
        june = [
            {"date": dt.date(2026, 6, 26), "ref": str(check_no), "description": f"Check {check_no} {PAYEES[ai]}", "amount": -money(rng, 300, 2400, s), "clears": dt.date(2026, 7, rng.randint(2, 9))},
            {"date": dt.date(2026, 6, 29), "ref": str(check_no + 1), "description": f"Check {check_no + 1} {PAYEES[ai + 1]}", "amount": -money(rng, 200, 1800, s), "clears": dt.date(2026, 7, rng.randint(3, 12))},
            {"date": dt.date(2026, 6, 30), "ref": "", "description": "Deposit", "amount": money(rng, 600, 3000, s), "clears": dt.date(2026, 7, 1)},
        ]
        if ai == 1:
            # A check that never clears: it goes stale during the quarter.
            june.append({"date": dt.date(2026, 5, 18), "ref": str(check_no - 7), "description": f"Check {check_no - 7} A. Petrovic refund", "amount": Decimal("-185.00") , "clears": None})
        check_no += 2
        pending = june
        book_bal = bank_bal + sum(x["amount"] for x in pending)
        for m in (7, 8, 9):
            start = dt.date(2026, m, 1)
            end = dt.date(2026, m + 1, 1) - dt.timedelta(days=1)
            opening_outstanding = [ser(x) for x in pending]
            bank_open, book_open = bank_bal, book_bal
            book_rows, bank_rows, new = [], [], []
            for _ in range(rng.randint(10, 16)):
                desc, lo, hi = rng.choice(DEPOSITS)
                day = start + dt.timedelta(days=rng.randint(0, (end - start).days))
                amt = money(rng, lo, hi, s)
                lag = 0 if desc != "BRANCH DEPOSIT" else rng.randint(0, 2)
                new.append({"date": day, "ref": "", "description": desc.title(), "amount": amt, "clears": day + dt.timedelta(days=lag), "bank_desc": desc})
            # A deposit made after the bank's cutoff on the last day.
            new.append({"date": end, "ref": "", "description": "Branch Deposit", "amount": money(rng, 500, 3000, s), "clears": end + dt.timedelta(days=1), "bank_desc": "BRANCH DEPOSIT"})
            for _ in range(rng.randint(5, 9)):
                day = start + dt.timedelta(days=rng.randint(0, (end - start).days))
                payee = rng.choice(PAYEES)
                new.append({"date": day, "ref": str(check_no), "description": f"Check {check_no} {payee}", "amount": -money(rng, 80, 3000, s),
                            "clears": day + dt.timedelta(days=rng.randint(2, 25)), "bank_desc": f"CHECK {check_no}"})
                check_no += 1
            for desc, lo, hi in ACH:
                day = start + dt.timedelta(days=rng.randint(0, 27))
                new.append({"date": day, "ref": "", "description": desc.title(), "amount": -money(rng, lo, hi, s), "clears": day, "bank_desc": desc})
            book_rows = [{k: x[k] for k in COLS} for x in new]
            pool = pending + new
            still = []
            for x in pool:
                if x["clears"] is not None and x["clears"] <= end:
                    bank_rows.append({"date": x["clears"], "ref": x["ref"], "description": x.get("bank_desc", x["description"].upper()), "amount": x["amount"]})
                else:
                    still.append(x)
            # Bank-only items
            adjustments = []
            fee = money(rng, 12, 35, s)
            bank_rows.append({"date": end, "ref": "", "description": "MONTHLY SERVICE CHARGE", "amount": -fee})
            adjustments.append({"type": "bank_fee", "date": end.isoformat(), "ref": "", "description": "MONTHLY SERVICE CHARGE", "amount": f"{-fee:.2f}"})
            intr = (bank_open * Decimal("0.0004")).quantize(Decimal("0.01"))
            bank_rows.append({"date": end, "ref": "", "description": "INTEREST PAID", "amount": intr})
            adjustments.append({"type": "interest", "date": end.isoformat(), "ref": "", "description": "INTEREST PAID", "amount": f"{intr:.2f}"})
            if rng.random() < 0.35:
                dep = next(x for x in new if x["amount"] > 0 and x["clears"] <= end - dt.timedelta(days=5))
                ret_day = dep["clears"] + dt.timedelta(days=4)
                bank_rows.append({"date": ret_day, "ref": "", "description": "RETURNED ITEM NSF", "amount": -dep["amount"]})
                bank_rows.append({"date": ret_day, "ref": "", "description": "RETURNED ITEM FEE", "amount": Decimal("-12.00")})
                adjustments.append({"type": "returned_item", "date": ret_day.isoformat(), "ref": "", "description": f"Customer check returned unpaid ({dep['description']})", "amount": f"{-dep['amount']:.2f}"})
                adjustments.append({"type": "bank_fee", "date": ret_day.isoformat(), "ref": "", "description": "RETURNED ITEM FEE", "amount": "-12.00"})
            # One transposed entry: the first two digits of a check swapped in the books.
            if slug == "brightwater-operating" and m == 8:
                cleared_check = next(r for r in book_rows if r["ref"] and any(b["ref"] == r["ref"] for b in bank_rows)
                                     and f"{-r['amount']:.2f}"[0] != f"{-r['amount']:.2f}"[1] and len(f"{-r['amount']:.2f}") >= 6)
                right = cleared_check["amount"]
                digits = f"{-right:.2f}"
                swapped = Decimal("-" + digits[1] + digits[0] + digits[2:])
                cleared_check["amount"] = swapped
                adjustments.append({"type": "book_error", "book_ref": cleared_check["ref"], "booked": f"{swapped:.2f}", "correct": f"{right:.2f}",
                                    "description": f"Check {cleared_check['ref']} entered as {-swapped:.2f}, cleared for {-right:.2f}", "amount": f"{right - swapped:.2f}"})
            bank_close = bank_open + sum(r["amount"] for r in bank_rows)
            book_close = book_open + sum(r["amount"] for r in book_rows)
            dit = [x for x in still if x["amount"] > 0]
            oc = [x for x in still if x["amount"] < 0]
            adj_bank = bank_close + sum(x["amount"] for x in still)
            adj_book = book_close + sum(Decimal(a["amount"]) for a in adjustments)
            assert adj_bank == adj_book, (slug, m, adj_bank, adj_book)
            folder = os.path.join(OUT, "accounts", slug, f"2026-{m:02d}")
            os.makedirs(folder)
            st = {"account": name, "period_start": start.isoformat(), "period_end": end.isoformat(),
                  "bank_opening": f"{bank_open:.2f}", "bank_closing": f"{bank_close:.2f}",
                  "book_opening": f"{book_open:.2f}", "book_closing": f"{book_close:.2f}",
                  "opening_outstanding": opening_outstanding, "fictional": True}
            json.dump(st, open(os.path.join(folder, "statement.json"), "w", encoding="utf-8"), indent=2)
            write(os.path.join(folder, "bank.csv"), bank_rows)
            write(os.path.join(folder, "book.csv"), book_rows)
            rec = {"account": name, "period_end": end.isoformat(), "prepared_by": "Fictional preparer", "bank_closing": f"{bank_close:.2f}",
                   "deposits_in_transit": [ser(x) for x in dit], "outstanding_payments": [ser(x) for x in oc],
                   "adjusted_bank_balance": f"{adj_bank:.2f}", "book_closing": f"{book_close:.2f}",
                   "book_adjustments": adjustments, "adjusted_book_balance": f"{adj_book:.2f}", "difference": "0.00"}
            json.dump(rec, open(os.path.join(folder, "reconciliation.json"), "w", encoding="utf-8"), indent=2)
            index.append([slug, f"2026-{m:02d}", f"{bank_close:.2f}", f"{book_close:.2f}", f"{adj_book:.2f}", len(dit), len(oc), len(adjustments)])
            bank_bal, book_bal, pending = bank_close, adj_book, still
    with open(os.path.join(OUT, "index.csv"), "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, lineterminator="\r\n")
        w.writerow(["account", "month", "bank_closing", "book_closing_before_adjustments", "adjusted_balance", "deposits_in_transit", "outstanding_payments", "book_adjustments"])
        w.writerows(index)
    make_invalid()
    print(f"{len(index)} reconciliations")


def make_invalid():
    base = os.path.join(OUT, "accounts", "juniper-operating", "2026-08")
    cases = []

    def case(name, rule, why, fn):
        f = os.path.join(OUT, "invalid", name)
        shutil.copytree(base, f)
        fn(f)
        cases.append({"folder": f"samples/invalid/{name}", "must_fail": rule, "what_is_wrong": why})

    def edit_json(f, fname, fn):
        p = os.path.join(f, fname)
        d = json.load(open(p))
        fn(d)
        json.dump(d, open(p, "w"), indent=2)

    def edit_csv(f, fname, fn):
        p = os.path.join(f, fname)
        r = list(csv.DictReader(open(p)))
        fn(r)
        with open(p, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=COLS, lineterminator="\r\n")
            w.writeheader()
            w.writerows(r)

    case("no-reconciliation", "REC-001", "reconciliation.json missing", lambda f: os.remove(os.path.join(f, "reconciliation.json")))
    case("bank-rows-dont-tie", "REC-002", "a bank row dropped, so the statement no longer ties to its closing balance",
         lambda f: edit_csv(f, "bank.csv", lambda r: r.pop(3)))
    case("book-rows-dont-tie", "REC-003", "the book closing balance typed wrong",
         lambda f: edit_json(f, "statement.json", lambda d: d.update(book_closing=f"{Decimal(d['book_closing']) + 100:.2f}")))

    def drop_oc(d):
        x = d["outstanding_payments"].pop(0)
        d["adjusted_bank_balance"] = f"{Decimal(d['adjusted_bank_balance']) - Decimal(x['amount']):.2f}"
    case("outstanding-check-left-off", "REC-004", "an outstanding check missing from the list", lambda f: edit_json(f, "reconciliation.json", drop_oc))

    def cleared_as_dit(d):
        d["deposits_in_transit"].append({"date": "2026-08-12", "ref": "", "description": "Square Deposit", "amount": "500.00"})
    case("deposit-listed-twice", "REC-005", "a deposit listed in transit that isn't", lambda f: edit_json(f, "reconciliation.json", cleared_as_dit))

    def drop_fee(d):
        d["book_adjustments"] = [a for a in d["book_adjustments"] if a["type"] != "bank_fee"]
    case("fee-not-adjusted", "REC-006", "the bank's service charge never booked", lambda f: edit_json(f, "reconciliation.json", drop_fee))

    def plug(d):
        d["adjusted_book_balance"] = d["adjusted_bank_balance"]
        d["book_adjustments"].append({"type": "other", "date": "2026-08-31", "ref": "", "description": "Reconciliation discrepancy", "amount": "37.15"})
    case("plugged-difference", "REC-007", "a made-up adjustment to force the reconciliation to zero", lambda f: edit_json(f, "reconciliation.json", plug))

    def stale(d):
        d["opening_outstanding"].append({"date": "2026-04-20", "ref": "999", "description": "Check 999 old vendor", "amount": "-75.00"})
        d["book_opening"] = f"{Decimal(d['book_opening']) - 75:.2f}"
        d["book_closing"] = f"{Decimal(d['book_closing']) - 75:.2f}"

    def stale_rec(d):
        d["outstanding_payments"].append({"date": "2026-04-20", "ref": "999", "description": "Check 999 old vendor", "amount": "-75.00"})
        d["adjusted_bank_balance"] = f"{Decimal(d['adjusted_bank_balance']) - 75:.2f}"
        d["book_closing"] = f"{Decimal(d['book_closing']) - 75:.2f}"
        d["adjusted_book_balance"] = f"{Decimal(d['adjusted_book_balance']) - 75:.2f}"
    case("stale-check", "REC-009", "a check outstanding since April (warning)", lambda f: (edit_json(f, "statement.json", stale), edit_json(f, "reconciliation.json", stale_rec)))

    def beginning_off(d):
        d["opening_outstanding"].pop()
        d["book_opening"] = f"{Decimal(d['book_opening']) + 0:.2f}"
    case("prior-items-missing", "REC-012", "a deposit in transit from last month dropped from the opening items", lambda f: edit_json(f, "statement.json", beginning_off))
    json.dump(cases, open(os.path.join(OUT, "invalid", "expected.json"), "w"), indent=2)


if __name__ == "__main__":
    main()
