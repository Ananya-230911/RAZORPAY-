# Platform Fee Policy

## Standard transaction fee
FinControl-processed payments carry a platform fee deducted automatically
at settlement time -- the fee never appears as a separate line item on the
payment record itself, only as the gap between the payment amount and the
settlement amount.

- Card payments: 2.00% of the transaction amount + applicable taxes.
- UPI payments: 1.50% of the transaction amount + applicable taxes.
- Netbanking payments: 1.75% of the transaction amount + applicable taxes.
- Wallet payments: 2.25% of the transaction amount + applicable taxes.

In practice, after taxes and rounding, the total deduction typically lands
between **1.5% and 2.5%** of the original payment amount.

## What this looks like in reconciliation
A transaction where `settlement_amount = payment_amount - small_deduction`,
with the deduction between roughly 1.5% and 2.5% of the payment amount, and
where the invoice amount still matches the original payment amount, is
consistent with a routine platform fee deduction. This is expected
behavior, not an error, and does not require a refund or dispute record.

## What this does NOT cover
- Deductions larger than ~10% of the payment amount are **not** explained
  by the standard fee schedule and should not be auto-classified as a fee
  deduction just because they resemble one in shape.
- Fee-only explanations require the invoice amount to match the original
  payment amount. If the invoice amount itself differs from the payment,
  investigate as a possible invoicing error instead (see dispute_policy.md).
