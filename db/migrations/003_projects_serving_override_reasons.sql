-- §9.1: route optimization + inference capture default ON for every real-time
-- endpoint. Turning either off requires an explicit, logged override reason —
-- governance enforced structurally, not as a skippable checklist item.
ALTER TABLE {catalog}.{schema}.projects ADD COLUMNS (
  route_optimization_override_reason STRING COMMENT 'non-empty = route optimization deliberately disabled; §9.1 logged override',
  inference_capture_override_reason STRING COMMENT 'non-empty = inference capture deliberately disabled; §9.1 logged override'
)
