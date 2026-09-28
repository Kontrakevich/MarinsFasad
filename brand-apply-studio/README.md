# Brand Apply Studio — MVP 0.1

Standalone bootstrap extracted from the working perspective-grid logic in MarinsFasad.

## Goal

Use one immutable master image and one manually defined perspective surface to produce:

- perspective guide overlay;
- deterministic pre-warped brand preview;
- design mask;
- rectified surface;
- scene.json with the exact quad and homography matrix.

The master image is never regenerated or geometrically changed.

## Run

```bash
cd brand-apply-studio
python -m venv .venv
# Windows
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8015
```

Open:

```
http://127.0.0.1:8015
```

## MVP workflow

1. Create a project.
2. Upload the product photo.
3. Drag P1–P4 so the grid matches the branding surface.
4. Upload a transparent PNG logo/design.
5. Click **Зафиксировать плоскость**.
6. Click **Построить брендирование**.
7. Compare:
   - source;
   - perspective guide;
   - deterministic brand preview;
   - mask.

## Geometry contract

Point order is strict:

```
P1 ---- P2
|        |
P4 ---- P3
```

Coordinates are stored in master-image pixels. The same quad and the same homography are used for the guide, brand projection, mask and scene metadata.

## Next

The next layer is generator integration: the generator receives the immutable source + guide overlay + deterministic pre-warped brand preview and is instructed to preserve placement while integrating material, light, folds and occlusions.
