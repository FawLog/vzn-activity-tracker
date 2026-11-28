# Calendar v3.10.1 — cycle integrity

Explicit entry grouping is the source of expected sessions for final attendance. All scheduled grouped members must link to the same actual event and matching session identity, host and UTC minute. Partial publication remains available; it does not establish missing players' absence. Historical events without explicit grouping keep existing review behavior. Reopen finalized events before changing grouped membership or unlinking. Deletion invalidates affected calendar revisions.

## Calendar v4 compatibility

Keep internal occurrence IDs, actual event/session links and evidence independent of scheduling providers. Local prediction, manual/OCR and optional external API adapters should emit normalized schedule candidates with provenance, external identifiers (when available), scope, precision and confidence. Reconcile candidates explicitly; never let a provider overwrite confirmed officer decisions, actual records or finalized attendance. No paid dependency or provider implementation is introduced here.
