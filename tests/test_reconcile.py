import contextlib
import glob
import io
import json
import os
import sys
import unittest
from decimal import Decimal

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "cli"))
import reconcile as rc  # noqa: E402


def months():
    return sorted(glob.glob(os.path.join(ROOT, "samples", "accounts", "*", "*")))


class Samples(unittest.TestCase):
    def test_every_month_reconciles(self):
        self.assertEqual(len(months()), 18)
        for m in months():
            issues, proof = rc.check(m)
            self.assertEqual([i for i in issues if i.severity == "error"], [], m)
            adj_bank, adj_book = proof["rows"][5], proof["rows"][8]
            self.assertEqual(adj_bank[1:], adj_book[1:], m)

    def test_build_finds_the_same_outstanding_items(self):
        for m in months():
            st, bank, book, rec = rc.load(m)
            fixes = [a for a in rec["book_adjustments"] if a["type"] == "book_error"]
            auto = rc.build(st, bank, book, fixes)
            self.assertEqual(rc.amounts(auto["outstanding_payments"]), rc.amounts(rec["outstanding_payments"]), m)
            self.assertEqual(rc.amounts(auto["deposits_in_transit"]), rc.amounts(rec["deposits_in_transit"]), m)
            self.assertEqual(Decimal(auto["difference"]), 0, m)

    def test_months_chain(self):
        for acct in glob.glob(os.path.join(ROOT, "samples", "accounts", "*")):
            ms = sorted(glob.glob(os.path.join(acct, "*")))
            for a, b in zip(ms, ms[1:]):
                ra = json.load(open(os.path.join(a, "reconciliation.json")))
                sb = json.load(open(os.path.join(b, "statement.json")))
                self.assertEqual(ra["adjusted_book_balance"], sb["book_opening"])
                self.assertEqual(ra["bank_closing"], sb["bank_opening"])
                self.assertEqual(rc.amounts(ra["outstanding_payments"] + ra["deposits_in_transit"]), rc.amounts(sb["opening_outstanding"]))

    def test_transposition_is_a_multiple_of_nine(self):
        rec = json.load(open(os.path.join(ROOT, "samples", "accounts", "brightwater-operating", "2026-08", "reconciliation.json")))
        err = next(a for a in rec["book_adjustments"] if a["type"] == "book_error")
        self.assertEqual(Decimal(err["amount"]) % 9, 0)

    def test_invalid_months_fail_their_rule(self):
        cases = json.load(open(os.path.join(ROOT, "samples", "invalid", "expected.json")))
        self.assertEqual(len(cases), 9)
        for c in cases:
            issues, _ = rc.check(os.path.join(ROOT, c["folder"]))
            self.assertIn(c["must_fail"], {i.rule for i in issues}, c["folder"])

    def test_rules_file_covers_tool(self):
        import csv
        ids = {r["rule_id"] for r in csv.DictReader(open(os.path.join(ROOT, "rules", "reconciliation-rules.csv")))}
        src = open(os.path.join(ROOT, "cli", "reconcile.py")).read()
        self.assertEqual({f"REC-{n:03d}" for n in range(1, 30) if f'"REC-{n:03d}"' in src} - ids, set())

    def test_cli(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(rc.main(["proof", months()[0]]), 0)
            self.assertEqual(rc.main(["check", os.path.join(ROOT, "samples", "invalid", "plugged-difference")]), 1)
            self.assertEqual(rc.main(["build", months()[0]]), 0)


if __name__ == "__main__":
    unittest.main()
