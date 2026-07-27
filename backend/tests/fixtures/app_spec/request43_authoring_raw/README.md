# Request #43 authoring regression fixtures

## Historical production evidence

Request ID 43 failed AppSpec authoring on deployed revision
`dff8bb4fc5a54c1560780b53ed490b9780b749f2`.

Three early rejected revisions (1–3) share:

- `raw_response_sha256`: `d2cbc22bd09ff1e0c7ff82081ab56a9669e5d83bbe9e9b52ae935c76adc731d5`
- `json_extraction.error`: `No valid JSON object found in model output`
- `finish_reason`: `null`
- model: `google/gemini-2.5-flash`
- `calls_used`: 1 (one provider call persisted three ways)

The full raw provider body was **not** persisted historically (only a 2000-char
excerpt length and SHA). These fixtures therefore:

1. Record sanitized diagnostics in `../request43_authoring_diagnostics.json`
2. Provide synthetic raw bodies that reproduce the failure classes

## Classification

With the unrecovered body, production evidence supports:

- **F** — no usable JSON object detected by the historical extractor
- **H** — secondary: empty `{}` fallthrough re-persisted the same failure as
  `schema_parse_failed` then `deterministic_validation_failed`

Truncation (**D**) is unproven (`finish_reason` null; OpenRouter already fails
truncated completions as `provider_truncated_output` before authoring parse).

## Synthetic files

| File | Expected typed result |
|------|------------------------|
| `request43_class_f_prose_only.txt` | `app_spec_authoring_no_json_object` |
| `direct_valid.json` | ok / direct |
| `fenced_valid.json.txt` | ok / markdown_fence |
| `prose_wrapped_valid.txt` | ok / balanced_scan |
| `truncated_object.txt` | `app_spec_authoring_json_truncated` |
| `invalid_syntax.txt` | `app_spec_authoring_json_syntax_invalid` |
| `braces_in_strings.txt` | ok |
| `nested_valid.txt` | ok / balanced_scan |
| `multiple_objects.txt` | first object only |
| `production_shaped_valid_booking.json` | full AppSpec schema + deterministic validation |
