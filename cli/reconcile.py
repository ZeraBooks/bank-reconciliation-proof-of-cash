#!/usr/bin/env python3
"""Match book and bank items, check a bank reconciliation, and build a
four-column proof of cash.

    python3 cli/reconcile.py check samples/accounts/juniper-operating/2026-08
    python3 cli/reconcile.py build samples/accounts/juniper-operating/2026-08 > draft.json
    python3 cli/reconcile.py proof samples/accounts/juniper-operating/2026-08

A month folder holds:
  statement.json       bank and book opening and closing balances, and the
                       items outstanding at the start of the month
  bank.csv             the bank statement's rows
  book.csv             the cash account's rows from the general ledger
  reconciliation.json  the preparer's reconciliation (for `check` and `proof`)
Rules: rules/reconciliation-rules.csv. Exit 0 = ties, 1 = errors, 2 = can't read.

Part of https://github.com/ZeraBooks/bank-reconciliation-proof-of-cash
(ZeraBooks, https://www.zerabooks.com/bank-reconciliation-software).
"""
import argparse
import csv
import datetime as dt
import json
import os
import sys
from collections import Counter
from decimal import Decimal

D0 = Decimal("0")


class Issue:
    def __init__(self, rule, severity, message):
        self.rule, self.severity, self.message = rule, severity, message

    def __repr__(self):
        return f"{self.severity.upper():7} {self.rule}: {self.message}"


def rows(path):
    with open(path, encoding="utf-8-sig", newline="") as fh:
        out = []
        for r in csv.DictReader(fh):
            r = {k: (v or "").strip() for k, v in r.items()}
            r["amount"] = Decimal(r["amount"])
            r["date"] = dt.date.fromisoformat(r["date"])
            out.append(r)
        return out


def load(folder):
    st = json.load(open(os.path.join(folder, "statement.json"), encoding="utf-8"))
    bank = rows(os.path.join(folder, "bank.csv"))
    book = rows(os.path.join(folder, "book.csv"))
    rec_path = os.path.join(folder, "reconciliation.json")
    rec = json.load(open(rec_path, encoding="utf-8")) if os.path.exists(rec_path) else None
    return st, bank, book, rec


def item(d):
    return {"date": dt.date.fromisoformat(d["date"]), "ref": d.get("ref", ""), "description": d.get("description", ""), "amount": Decimal(d["amount"])}


def match(bank, book_pool, max_lag_days=60):
    """Pair bank rows with book items: same amount, same reference when both
    have one, bank date no more than 3 days before the book date and no more
    than max_lag_days after. Returns (pairs, unmatched_bank, unmatched_book)."""
    used = set()
    pairs, bank_only = [], []
    for b in sorted(bank, key=lambda r: r["date"]):
        best = None
        for i, k in enumerate(book_pool):
            if i in used or k["amount"] != b["amount"]:
                continue
            if b.get("ref") and k.get("ref") and b["ref"] != k["ref"]:
                continue
            lag = (b["date"] - k["date"]).days
            if lag < -3 or lag > max_lag_days:
                continue
            score = (0 if b.get("ref") and b["ref"] == k.get("ref") else 1, abs(lag))
            if best is None or score < best[0]:
                best = (score, i)
        if best is None:
            bank_only.append(b)
        else:
            used.add(best[1])
            pairs.append((b, book_pool[best[1]]))
    return pairs, bank_only, [k for i, k in enumerate(book_pool) if i not in used]


def apply_corrections(book, corrections):
    """Book errors the preparer found: change the booked amount to the correct one before matching."""
    fixed = [dict(r) for r in book]
    for c in corrections:
        for r in fixed:
            if r.get("ref") == c["book_ref"] and r["amount"] == Decimal(c["booked"]):
                r["amount"] = Decimal(c["correct"])
                break
    return fixed


def build(st, bank, book, corrections=()):
    pool = [item(x) for x in st.get("opening_outstanding", [])] + apply_corrections(book, corrections)
    pairs, bank_only, outstanding = match(bank, pool)
    end = dt.date.fromisoformat(st["period_end"])
    dit = [o for o in outstanding if o["amount"] > 0]
    oc = [o for o in outstanding if o["amount"] < 0]
    adjustments = [{"type": guess_type(b), "date": b["date"].isoformat(), "ref": b.get("ref", ""), "description": b.get("description", ""), "amount": str(b["amount"])} for b in bank_only]
    for c in corrections:
        adjustments.append(dict(c, type="book_error", amount=str(Decimal(c["correct"]) - Decimal(c["booked"]))))

    def ser(x):
        return {"date": x["date"].isoformat(), "ref": x.get("ref", ""), "description": x.get("description", ""), "amount": str(x["amount"])}

    bank_close, book_close = Decimal(st["bank_closing"]), Decimal(st["book_closing"])
    adj_bank = bank_close + sum((x["amount"] for x in dit), D0) + sum((x["amount"] for x in oc), D0)
    adj_book = book_close + sum((Decimal(a["amount"]) for a in adjustments), D0)
    return {
        "account": st["account"], "period_end": end.isoformat(),
        "bank_closing": str(bank_close), "deposits_in_transit": [ser(x) for x in dit], "outstanding_payments": [ser(x) for x in oc],
        "adjusted_bank_balance": str(adj_bank),
        "book_closing": str(book_close), "book_adjustments": adjustments, "adjusted_book_balance": str(adj_book),
        "difference": str(adj_bank - adj_book),
    }


def guess_type(b):
    d = b.get("description", "").upper()
    if "INTEREST" in d:
        return "interest"
    if "NSF" in d or "RETURNED" in d:
        return "returned_item"
    if "FEE" in d or "CHARGE" in d:
        return "bank_fee"
    return "other"


def amounts(items):
    return Counter(Decimal(x["amount"]) for x in items)


def check(folder):
    issues = []
    st, bank, book, rec = load(folder)
    if rec is None:
        return [Issue("REC-001", "error", "reconciliation.json is missing")], None
    start, end = dt.date.fromisoformat(st["period_start"]), dt.date.fromisoformat(st["period_end"])
    bank_sum = sum((r["amount"] for r in bank), D0)
    if Decimal(st["bank_opening"]) + bank_sum != Decimal(st["bank_closing"]):
        issues.append(Issue("REC-002", "error", f"bank opening {st['bank_opening']} + rows {bank_sum} != closing {st['bank_closing']}"))
    book_sum = sum((r["amount"] for r in book), D0)
    if Decimal(st["book_opening"]) + book_sum != Decimal(st["book_closing"]):
        issues.append(Issue("REC-003", "error", f"book opening {st['book_opening']} + rows {book_sum} != closing {st['book_closing']}"))
    for r in bank + book:
        if not start <= r["date"] <= end:
            issues.append(Issue("REC-001", "error", f"{r['date']} {r.get('description', '')} is outside the period"))

    corrections = [a for a in rec.get("book_adjustments", []) if a.get("type") == "book_error"]
    auto = build(st, bank, book, corrections)
    # What the preparer listed versus what the items say
    if amounts(rec["outstanding_payments"]) != amounts(auto["outstanding_payments"]):
        extra = amounts(rec["outstanding_payments"]) - amounts(auto["outstanding_payments"])
        missing = amounts(auto["outstanding_payments"]) - amounts(rec["outstanding_payments"])
        issues.append(Issue("REC-004", "error", f"outstanding payments listed but not outstanding: {sorted(map(str, extra.elements()))}; outstanding but not listed: {sorted(map(str, missing.elements()))}"))
    if amounts(rec["deposits_in_transit"]) != amounts(auto["deposits_in_transit"]):
        extra = amounts(rec["deposits_in_transit"]) - amounts(auto["deposits_in_transit"])
        missing = amounts(auto["deposits_in_transit"]) - amounts(rec["deposits_in_transit"])
        issues.append(Issue("REC-005", "error", f"deposits in transit listed but not in transit: {sorted(map(str, extra.elements()))}; in transit but not listed: {sorted(map(str, missing.elements()))}"))
    rec_bank_only = [a for a in rec.get("book_adjustments", []) if a.get("type") != "book_error"]
    auto_bank_only = [a for a in auto["book_adjustments"] if a.get("type") != "book_error"]
    if amounts(rec_bank_only) != amounts(auto_bank_only):
        missing = amounts(auto_bank_only) - amounts(rec_bank_only)
        extra = amounts(rec_bank_only) - amounts(auto_bank_only)
        issues.append(Issue("REC-006", "error", f"bank items not in the books and not adjusted: {sorted(map(str, missing.elements()))}; adjustments with no bank item: {sorted(map(str, extra.elements()))}"))

    adj_bank = Decimal(st["bank_closing"]) + sum((Decimal(x["amount"]) for x in rec["deposits_in_transit"] + rec["outstanding_payments"]), D0)
    adj_book = Decimal(st["book_closing"]) + sum((Decimal(a["amount"]) for a in rec.get("book_adjustments", [])), D0)
    if adj_bank != adj_book:
        issues.append(Issue("REC-007", "error", f"adjusted bank {adj_bank} vs adjusted book {adj_book} (difference {adj_bank - adj_book})"))
    for k, v in (("adjusted_bank_balance", adj_bank), ("adjusted_book_balance", adj_book)):
        if k in rec and Decimal(rec[k]) != v:
            issues.append(Issue("REC-007", "error", f"{k} says {rec[k]}, the items add to {v}"))

    for x in rec["outstanding_payments"] + rec["deposits_in_transit"]:
        if (end - dt.date.fromisoformat(x["date"])).days > 90:
            issues.append(Issue("REC-009", "warning", f"{x.get('ref', '')} {x['amount']} from {x['date']} is stale (over 90 days)"))

    proof, perr = proof_of_cash(st, bank, book, rec)
    issues += perr
    return issues, proof


def proof_of_cash(st, bank, book, rec):
    """Four columns: beginning balance, receipts, disbursements, ending balance."""
    issues = []
    open_items = st.get("opening_outstanding", [])
    b_dit = sum((Decimal(x["amount"]) for x in open_items if Decimal(x["amount"]) > 0), D0)
    b_oc = sum((Decimal(x["amount"]) for x in open_items if Decimal(x["amount"]) < 0), D0)
    e_dit = sum((Decimal(x["amount"]) for x in rec["deposits_in_transit"]), D0)
    e_oc = sum((Decimal(x["amount"]) for x in rec["outstanding_payments"]), D0)
    bank_in = sum((r["amount"] for r in bank if r["amount"] > 0), D0)
    bank_out = sum((r["amount"] for r in bank if r["amount"] < 0), D0)
    book_in = sum((r["amount"] for r in book if r["amount"] > 0), D0)
    book_out = sum((r["amount"] for r in book if r["amount"] < 0), D0)
    adj_in = adj_out = D0
    for a in rec.get("book_adjustments", []):
        amt = Decimal(a["amount"])
        if a.get("type") == "book_error":
            side_in = Decimal(a["booked"]) > 0
        else:
            side_in = amt > 0
        if side_in:
            adj_in += amt
        else:
            adj_out += amt
    bank_open, bank_close = Decimal(st["bank_opening"]), Decimal(st["bank_closing"])
    book_open, book_close = Decimal(st["book_opening"]), Decimal(st["book_closing"])
    rows_ = [
        ("Balance per bank", bank_open, bank_in, bank_out, bank_close),
        ("Deposits in transit, beginning", b_dit, -b_dit, D0, D0),
        ("Deposits in transit, ending", D0, e_dit, D0, e_dit),
        ("Outstanding payments, beginning", b_oc, D0, -b_oc, D0),
        ("Outstanding payments, ending", D0, D0, e_oc, e_oc),
    ]
    adj_bank = [sum(c) for c in zip(*[r[1:] for r in rows_])]
    book_rows = [
        ("Balance per books", book_open, book_in, book_out, book_close),
        ("Adjustments not yet in the books", D0, adj_in, adj_out, adj_in + adj_out),
    ]
    adj_book = [sum(c) for c in zip(*[r[1:] for r in book_rows])]
    names = ["beginning balance", "receipts", "disbursements", "ending balance"]
    for n, a, b in zip(names, adj_bank, adj_book):
        if a != b:
            rule = {"beginning balance": "REC-012", "receipts": "REC-010", "disbursements": "REC-011", "ending balance": "REC-007"}[n]
            issues.append(Issue(rule, "error", f"proof of cash, {n}: bank side {a}, book side {b} (difference {a - b})"))
    table = {"columns": ["", "Beginning", "Receipts", "Disbursements", "Ending"],
             "rows": [[r[0]] + [str(v) for v in r[1:]] for r in rows_] + [["Adjusted balance per bank"] + [str(v) for v in adj_bank]]
             + [[r[0]] + [str(v) for v in r[1:]] for r in book_rows] + [["Adjusted balance per books"] + [str(v) for v in adj_book]]}
    return table, issues


def print_proof(table):
    w = [34, 14, 14, 14, 14]
    print("".join(c.ljust(w[0]) if i == 0 else c.rjust(w[i]) for i, c in enumerate(table["columns"])))
    for r in table["rows"]:
        if r[0].startswith("Adjusted"):
            print("-" * sum(w))
        print("".join(c.ljust(w[0]) if i == 0 else f"{Decimal(c):,.2f}".rjust(w[i]) for i, c in enumerate(r)))
        if r[0].startswith("Adjusted balance per bank"):
            print()


def main(argv=None):
    ap = argparse.ArgumentParser(description="Bank reconciliation and proof of cash.")
    ap.add_argument("command", choices=["check", "build", "proof"])
    ap.add_argument("folder", nargs="+")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    worst = 0
    for folder in a.folder:
        try:
            if a.command == "build":
                st, bank, book, _ = load(folder)
                print(json.dumps(build(st, bank, book), indent=2))
                continue
            issues, proof = check(folder)
        except (OSError, ValueError, KeyError) as exc:
            print(f"could not read {folder}: {exc}", file=sys.stderr)
            worst = 2
            continue
        errors = [i for i in issues if i.severity == "error"]
        worst = max(worst, 1 if errors else 0)
        if a.json:
            print(json.dumps({"folder": folder, "ok": not errors, "issues": [vars(i) for i in issues], "proof_of_cash": proof}, indent=2))
            continue
        if a.command == "proof" and proof:
            print(f"Proof of cash: {folder}")
            print_proof(proof)
            print()
        for i in issues:
            print(i)
        print(f"{folder}: " + ("reconciled" if not errors else f"{len(errors)} error(s)"))
    return worst


if __name__ == "__main__":
    sys.exit(main())
