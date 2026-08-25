# Refund Policy

## Full refunds
When a transaction is fully refunded, the settlement amount for that
transaction drops to zero (or a value indistinguishable from zero after
rounding). The payment and invoice records remain unchanged -- only the
settlement reflects the refund. No further settlement is expected for a
fully refunded transaction.

## Partial refunds
A partial refund reduces the settlement amount by the refunded portion,
while the payment and invoice records keep their original amounts. Partial
refunds in our data typically range from **10% to 50%** of the original
payment amount. The resulting settlement amount is:

```
settlement_amount = payment_amount - refund_amount
```

## Distinguishing a refund from a fee deduction
Both look similar on paper (settlement lower than payment), so the
magnitude matters:
- A gap under ~10% of the payment amount is more consistent with a
  platform fee (see fee_policy.md) than a refund.
- A gap of 10% or more, especially if it doesn't cleanly match a
  documented fee percentage, is more consistent with a refund.
- A refund with no corresponding refund request or dispute ticket on file
  should be flagged for human review rather than auto-explained -- the
  settlement math alone does not prove a refund was authorized.

## Refund timing
Refunds are expected to settle within 5 business days of the original
payment date. A refund-shaped gap appearing well outside that window
should be treated with lower confidence.
