# Bank reconciliation and proof of cash

A bank reconciliation proves the books' cash balance against the bank: bank closing balance, plus deposits in transit, minus outstanding checks, must equal the book balance after you add the items only the bank knows about (fees, interest, returned checks) and fix any book errors. A four-column proof of cash goes further and proves the month's receipts and disbursements, not just the ending balance. [ZeraBooks](https://www.zerabooks.com/bank-reconciliation-software) reconciles every account month by month as statements come in: each statement must add up, follow the previous one and agree with the general ledger.

This repo is the method in files: JSON Schemas, 11 rules, 18 fictional month-end reconciliations across 6 accounts that carry month to month, 9 that are wrong on purpose, and a Python tool that matches items, checks a reconciliation and prints the proof of cash.

- Schemas: [`schema/`](schema/)
- Rules: [`rules/reconciliation-rules.csv`](rules/reconciliation-rules.csv)
- Tool: [`cli/reconcile.py`](cli/reconcile.py) (Python 3.8+, standard library)
- Samples: [`samples/`](samples/), all fictional
- Release zip: [latest](https://github.com/ZeraBooks/bank-reconciliation-proof-of-cash/releases/latest)

## The reconciliation

```
Balance per bank, Aug 31                     24,235.00
+ deposits in transit                         5,258.62
- outstanding checks                         -7,213.72
= adjusted bank balance                      22,279.90

Balance per books, Aug 31                    20,522.31
+ interest paid by the bank                       4.29
- monthly service charge                        -46.70
+ check 3312 entered as 3,152.82, cleared
  for 1,352.82                                1,800.00
= adjusted book balance                      22,279.90
```

That's `samples/accounts/brightwater-operating/2026-08`. The 1,800.00 is a transposition: 13 and 31 swapped. A difference that divides evenly by 9 is the classic sign of one.

## The proof of cash

A balance-only reconciliation can tie while the month is wrong: a $500 receipt booked in August that the bank shows in July nets out by September. The four-column proof checks each column on its own.

```
$ python3 cli/reconcile.py proof samples/accounts/brightwater-operating/2026-08
                                       Beginning      Receipts Disbursements        Ending
Balance per bank                       10,728.97     43,839.34    -30,333.31     24,235.00
Deposits in transit, beginning          2,987.30     -2,987.30          0.00          0.00
Deposits in transit, ending                 0.00      5,258.62          0.00      5,258.62
Outstanding payments, beginning       -11,554.77          0.00     11,554.77          0.00
Outstanding payments, ending                0.00          0.00     -7,213.72     -7,213.72
------------------------------------------------------------------------------------------
Adjusted balance per bank               2,161.50     46,110.66    -25,992.26     22,279.90

Balance per books                       2,161.50     46,106.37    -27,745.56     20,522.31
Adjustments not yet in the books            0.00          4.29      1,753.30      1,757.59
------------------------------------------------------------------------------------------
Adjusted balance per books              2,161.50     46,110.66    -25,992.26     22,279.90
```

Every column ties across, and every row ties down (beginning + receipts + disbursements = ending). Auditors use this when they test cash; it's also the fastest way to find which side of the month a reconciliation difference is on.

## The rules

| ID | Rule |
|---|---|
| REC-001 | All four files are there; every row is inside the period |
| REC-002 | Bank opening + bank rows = bank closing |
| REC-003 | Book opening + book rows = book closing |
| REC-004 | Outstanding payments listed = book payments the bank hasn't paid, including older ones |
| REC-005 | Deposits in transit listed = book receipts the bank hasn't credited |
| REC-006 | Every bank-only item is an adjustment, and every adjustment (other than a book error fix) has a bank item |
| REC-007 | Adjusted bank = adjusted book |
| REC-009 | Nothing outstanding more than 90 days (warning) |
| REC-010 | Proof of cash, receipts column ties |
| REC-011 | Proof of cash, disbursements column ties |
| REC-012 | Proof of cash, beginning column ties: last month carried in correctly |

REC-006 is the anti-plug rule. "Reconciliation discrepancy, 37.15" with no bank item behind it is the line every reviewer is looking for, and `samples/invalid/plugged-difference/` is exactly that.

## Files for one month

| File | What |
|---|---|
| `statement.json` | Bank and book opening and closing balances, and last month's outstanding items |
| `bank.csv` | Rows from the bank statement: `date,ref,description,amount` |
| `book.csv` | Rows from the cash account in the general ledger, same columns |
| `reconciliation.json` | The preparer's reconciliation ([schema](schema/reconciliation.schema.json)) |

Amounts are signed: money in positive, money out negative. The book adjustments are posted at month end, so next month's `book_opening` is this month's adjusted book balance.

## Run it

```bash
python3 cli/reconcile.py check samples/accounts/*/*            # all 18 months
python3 cli/reconcile.py proof samples/accounts/okafor-operating/2026-09
python3 cli/reconcile.py build samples/accounts/juniper-operating/2026-08 > draft.json
python3 cli/reconcile.py check samples/invalid/fee-not-adjusted --json
```

`build` matches items for you and drafts a reconciliation: same amount, same check number when both sides have one, and a bank date no more than 3 days before and 60 days after the book date. Unmatched book items become outstanding; unmatched bank items become adjustments. It can't find book errors on its own (a check booked at the wrong amount won't match), so look at any unmatched pair with amounts that differ by a multiple of 9.

Exit code 0 means reconciled, 1 means errors, 2 means a file couldn't be read.

## Samples

`scripts/generate_samples.py` writes them from a fixed seed. Six fictional accounts (a bakery, a dental office, a landscaper, a freight company, a food pantry and a law firm), July to September 2026, starting from June's outstanding items. Checks clear 2 to 25 days after they're written, the last deposit of each month clears the next day, the bank charges a service fee and pays interest every month, and a customer check bounces now and then (returned item plus a $12 fee). The dental account carries a $185 refund check from May that never clears, so it goes stale during the quarter and triggers REC-009.

| Folder | What |
|---|---|
| `samples/accounts/<account>/2026-07` to `2026-09` | 18 month folders |
| `samples/invalid/` | 9 broken months with `expected.json` |
| `samples/index.csv` | One row per month |

## Where ZeraBooks fits

Doing this by hand means ticking items off two lists every month. [ZeraBooks](https://www.zerabooks.com/bank-reconciliation-software) does the matching as each statement is uploaded: the statement has to add up on its own, follow the previous month's closing balance and agree with the [general ledger](https://www.zerabooks.com/general-ledger-software). When a month doesn't tie, AI re-reads the statement and proposes the fix for you to apply. One plan, $79 a month billed annually or $149 month to month, with a 7-day trial.

## Tests

```bash
python3 scripts/generate_samples.py
python3 -m unittest discover -s tests -v
```

## License and citation

Code MIT ([`LICENSE`](LICENSE)). Samples, schemas, rules and docs CC BY 4.0 ([`LICENSE-SAMPLES`](LICENSE-SAMPLES)). See [`CITATION.cff`](CITATION.cff). `MANIFEST.json` and `checksums.txt` list every data file with its SHA-256.

Stale-check handling and unclaimed property rules vary by state; REC-009 only flags the item.
