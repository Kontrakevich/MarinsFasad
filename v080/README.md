# Marins Facade v0.8.0

Standalone rebuild without runtime patch chains.

## Principles

- master image is immutable and stored at original resolution;
- previews are separate derivatives and never enter the production pipeline;
- comments are stored by stage and injected into compiled prompts;
- quality checks validate canvas size and border-connected black regions;
- UI updates are event-driven and do not use self-triggering MutationObserver loops;
- `.runtime` is no longer a source of truth.

## Structure

- `app/image_engine.py` — master and preview image handling;
- `app/prompt_engine.py` — compiled prompt builder;
- `app/quality_engine.py` — canvas and outpaint validation;
- `app/project_engine.py` — project state and storage;
- `app/main.py` — API and static UI;
- `tests/` — automated checks;
- `build.sh` — clean build and test;
- `start.sh` — persistent Uvicorn launcher.

## Run in Codespaces

```bash
cd /workspaces/MarinsFasad/v080
bash build.sh
bash start.sh
```

Open forwarded port `8070`.
