# MarinsFasad → MARINS Platform Adapter

Compatibility level: `compatible`.

The existing v0.8.1 runtime remains canonical. The platform adapter maps existing endpoints/state to MARINS Project Contract v1 without rewriting working business logic.

## Module runtime

- Working directory: `v080`
- Entrypoint: `app.main:app`
- Start: `bash start.sh`
- Build/tests: `bash build.sh`
- Port: `8070`
- Health: `GET /api/health`

## Identity mapping

- Module ID: `marins-fasad`
- Workspace Project ID: existing MarinsFasad project ID
- Run ID: background generation job/run identity
- Artifact IDs: platform adapter should derive stable IDs from project asset role + SHA256 until native artifact IDs are added

Do not reuse module IDs as workspace project IDs.

## Project mapping

Existing endpoints under `/api/projects` remain the source of workspace project state.

Platform run states map as follows:

- queued → `queued`
- processing → `processing`
- review → `review`
- approved → `approved`
- error → `error`

The adapter must not invent `healthy`, `completed` or `approved` states from file existence alone.

## Skill mapping

The project manifest declares five platform-visible skills:

- `geometry`
- `image-edit`
- `relight`
- `outpaint`
- `hybrid`

Generation skills share the current OpenRouter/Nano Banana engine and are selected through the existing generation mode + Intent Skill Router.

## Artifact mapping

Existing source master is treated as an immutable `source` artifact.

Derived assets (preview, geometry candidate/approved, environment candidate/final) are separate artifacts. The adapter must preserve lineage and never replace the source master with preview/transport/generated files.

Provider transport images are `working` artifacts only and must never be exposed as original/final downloads.

## Diagnostics mapping

Existing System №1 and project diagnostics map to `contracts/diagnostics.schema.json`.

Required redaction:

- API keys/secrets;
- base64 image payloads;
- credentials/tokens;
- unintended personal/production-sensitive payloads.

## Secrets

`OPENROUTER_API_KEY` is declared by name only in `marins.project.json` and remains runtime-injected.

## Migration direction

MarinsFasad stays a standalone canonical repository while the visual-production domain is proven. Reusable capabilities may later move to `marins-platform/packages` or `domains/visual`, but only after at least one second module demonstrates real reuse.
