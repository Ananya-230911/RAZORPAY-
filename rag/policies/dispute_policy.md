# Dispute, Duplicate & Unknown-Transaction Policy

## Duplicate transactions
Two payment records with the same amount, merchant, method, and date are
very likely the same charge submitted or captured twice (e.g. a retried
checkout, a double-click, or a client-side retry after a slow response).
Both records should be flagged for human review -- do not auto-cancel or
auto-refund either one without a human confirming which charge (if either)
should stand.

## Missing invoice
A payment and settlement can exist without a matching invoice if invoicing
failed to trigger, was manually skipped, or the merchant issues invoices on
a different cycle than payment capture. This is not self-explanatory from
the payment/settlement records alone and should go to human review rather
than being auto-explained, since there's no way to confirm from transaction
data alone *why* the invoice is missing.

## Unknown transactions
A settlement record with no matching payment or invoice anywhere in the
system indicates either a data feed problem (the payment record failed to
sync) or a genuinely external/erroneous settlement. This always requires
human review -- there is no automated explanation that can responsibly
close this case, since acting on an unverified settlement risks
crediting or debiting the wrong party.

## Amount mismatches between invoice and payment
When the invoice amount differs from the payment amount but the
settlement matches the payment, the most likely cause is an invoicing
error (wrong amount entered on the invoice). This cannot be confirmed
from the transaction records alone and should be routed to human review.

## When evidence is insufficient
If a difference does not cleanly match the fee, refund, settlement-timing,
or duplicate/invoice patterns described in these policies, do not guess.
Report the case as unresolved and route it to a human -- a wrong but
confident-sounding explanation is worse than an honest "we don't know."
