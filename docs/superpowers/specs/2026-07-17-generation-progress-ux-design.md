# Customer-visible generation progress (approved design)

## Problem
Customers left the result page thinking generation was stuck or finished early because `is_generating` flipped false as soon as the MVP blueprint existed, while codegen + Vite often continued for 10+ minutes.

## Approach
Keep `GenerationCinematic` and make polling + progress truthful until a terminal stage.

## Behavior
- Backend `is_generating` follows progress stage (`done` / `failed` / `ready`), not blueprint presence.
- Preview + progress endpoints stay in sync; progress includes `is_generating`, `is_failed`, `updated_at`.
- Result page polls every ~3s while `is_generating`.
- Cinematic shows stage label, %, file counts, elapsed time, reconnect notice, stalled reassurance (~90s), and a failure panel with retry / new request.
- Pipeline crashes always set `status=failed` so the UI can stop and explain.

## Out of scope
SSE/WebSockets; redesigning the cinematic graph.
