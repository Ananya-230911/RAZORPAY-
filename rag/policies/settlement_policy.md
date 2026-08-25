# Settlement Timing Policy

## Standard settlement window
Under normal operation, funds for a captured payment settle to the
merchant's account **T+2 business days** after the payment date -- i.e.
settlement_date is typically 2 days after payment_date.

## Missing settlement
If a payment was captured recently (within the last few days) and no
settlement record exists yet, this is normal and expected -- the
settlement simply hasn't landed yet. This should be auto-explained as
"pending settlement," not treated as an error requiring human review,
unless the payment is old enough that T+2 has clearly been exceeded by a
wide margin.

## Delayed / mismatched settlement dates
A settlement date that lands **far outside** the T+2 window (more than a
few days early or more than roughly 3 weeks late) is not explained by
normal processing delays and should be flagged as a date mismatch for
human review. Common causes include bank processing holidays, incorrect
settlement batch assignment, or a data entry error in the settlement
record -- none of which can be confirmed from the settlement date alone.

## What settlement timing does NOT explain
A large settlement date gap does not, by itself, explain an amount
difference. Treat date issues and amount issues as separate questions.
