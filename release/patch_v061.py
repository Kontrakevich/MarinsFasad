from pathlib import Path
import sys

runtime = Path(sys.argv[1])
main_path = runtime / "app/main.py"
index_path = runtime / "app/web/index.html"
styles_path = runtime / "app/web/styles.css"
geometry_skill_path = runtime / "skills/templates/geometry.md"
environment_skill_path = runtime / "skills/templates/environment.md"
test_path = runtime / "tests/test_workflow.py"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    if old not in text:
        raise SystemExit(f"v0.6.1 patch failed: {label}")
    return text.replace(old, new, 1)


main = main_path.read_text("utf-8")
main = replace_once(
    main,
    '''    corrected = cv2.warpPerspective(
        image,
        matrix,
        (out_width, out_height),
        flags=cv2.INTER_LANCZOS4,
        borderMode=cv2.BORDER_REFLECT_101,
    )''',
    '''    source_rgba = cv2.cvtColor(image, cv2.COLOR_BGR2BGRA)
    source_rgba[:, :, 3] = 255
    corrected = cv2.warpPerspective(
        source_rgba,
        matrix,
        (out_width, out_height),
        flags=cv2.INTER_LANCZOS4,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(0, 0, 0, 0),
    )''',
    "transparent warp",
)
main = replace_once(
    main,
    '''    if not cv2.imwrite(str(output), corrected, [cv2.IMWRITE_JPEG_QUALITY, 95]):''',
    '''    if output.suffix.lower() != ".png":
        raise HTTPException(500, "Результат геометрии должен сохраняться в PNG")
    if not cv2.imwrite(str(output), corrected, [cv2.IMWRITE_PNG_COMPRESSION, 3]):''',
    "PNG output",
)
main = replace_once(
    main,
    '''    version, output = next_version(path, "geometry")''',
    '''    version, output = next_version(path, "geometry", suffix=".png")''',
    "geometry version extension",
)
main = replace_once(
    main,
    '''    report = apply_full_frame_homography(path / source_rel, output, overlay, quad)
    report_path = path / "geometry" / "versions" / f"geometry_report_v{version:03d}.json"
    json_write(report_path, report)
    current = path / "geometry" / "geometry_current.jpg"
    shutil.copy2(output, current)''',
    '''    report = apply_full_frame_homography(path / source_rel, output, overlay, quad)
    holes = path / "geometry" / "versions" / f"geometry_holes_v{version:03d}.png"
    rgba = cv2.imread(str(output), cv2.IMREAD_UNCHANGED)
    if rgba is None or rgba.ndim != 3 or rgba.shape[2] != 4:
        raise HTTPException(500, "Результат геометрии не содержит alpha-канал")
    holes_data = np.where(rgba[:, :, 3] == 0, 255, 0).astype(np.uint8)
    if not cv2.imwrite(str(holes), holes_data, [cv2.IMWRITE_PNG_COMPRESSION, 3]):
        raise HTTPException(500, "Не удалось сохранить маску outpaint")
    report.update({
        "fill_mode": "transparent_constant",
        "mirrored_fill": False,
        "outpaint_deferred": True,
        "transparent_pixels": int(np.count_nonzero(holes_data)),
    })
    report_path = path / "geometry" / "versions" / f"geometry_report_v{version:03d}.json"
    json_write(report_path, report)
    current = path / "geometry" / "geometry_current.png"
    current_holes = path / "geometry" / "geometry_holes_current.png"
    shutil.copy2(output, current)
    shutil.copy2(holes, current_holes)''',
    "geometry mask and current files",
)
main = replace_once(
    main,
    '''        "geometry_version": safe_relative(output, path),
        "geometry_debug": safe_relative(overlay, path),''',
    '''        "geometry_version": safe_relative(output, path),
        "geometry_holes": safe_relative(current_holes, path),
        "geometry_holes_version": safe_relative(holes, path),
        "geometry_debug": safe_relative(overlay, path),''',
    "active holes files",
)
main = replace_once(
    main,
    '''            "Preserve the complete transformed frame and do not crop to the control plane."''',
    '''            "Preserve the complete transformed frame and do not crop to the control plane. "
            "Never mirror, repeat, clone, extrapolate or outpaint missing regions. "
            "Leave uncovered canvas regions transparent and export an outpaint mask."''',
    "geometry prompt rule",
)
main = replace_once(
    main,
    '''            "camera, framing, facade materials, openings and silhouette exactly. Do not crop or redesign."''',
    '''            "camera, framing, facade materials, openings and silhouette exactly. Do not crop or redesign. "
            "Transparent regions are intentional outpaint targets; fill them naturally without changing opaque geometry pixels."''',
    "environment prompt rule",
)
main_path.write_text(main, "utf-8")

index = index_path.read_text("utf-8")
index = index.replace("/static/styles.css?v=0.6.0", "/static/styles.css?v=0.6.1")
index = index.replace("/static/app.js?v=0.6.0", "/static/app.js?v=0.6.1")
index = replace_once(
    index,
    '<div class="comparison-panel"><span class="panel-kicker">CORRECTED</span><img id="geometry-after" alt="Результат геометрии"></div>',
    '<div class="comparison-panel geometry-corrected-panel"><span class="panel-kicker">CORRECTED — EMPTY AREAS FOR OUTPAINT</span><img id="geometry-after" alt="Геометрия без зеркальной дорисовки"></div>',
    "corrected preview",
)
index_path.write_text(index, "utf-8")

styles = styles_path.read_text("utf-8")
if "v0.6.1 transparent geometry preview" not in styles:
    styles += '''\n/* v0.6.1 transparent geometry preview */
.geometry-corrected-panel img{background-color:#dfe4e6;background-image:linear-gradient(45deg,rgba(0,48,80,.08) 25%,transparent 25%),linear-gradient(-45deg,rgba(0,48,80,.08) 25%,transparent 25%),linear-gradient(45deg,transparent 75%,rgba(0,48,80,.08) 75%),linear-gradient(-45deg,transparent 75%,rgba(0,48,80,.08) 75%);background-size:24px 24px;background-position:0 0,0 12px,12px -12px,-12px 0}\n'''
styles_path.write_text(styles, "utf-8")

geometry_skill = geometry_skill_path.read_text("utf-8")
if "## Transparent Warp Rule" not in geometry_skill:
    geometry_skill += '''\n\n## Transparent Warp Rule
- Never invent, mirror, clone, repeat, extrapolate or outpaint missing image regions during geometry correction.
- Leave uncovered areas transparent and export a binary holes mask.
- Outpaint is strictly deferred to the Environment stage.
'''
geometry_skill_path.write_text(geometry_skill, "utf-8")

environment_skill = environment_skill_path.read_text("utf-8")
if "## Outpaint Input Rule" not in environment_skill:
    environment_skill += '''\n\n## Outpaint Input Rule
- Transparent pixels in approved geometry are intentional outpaint targets.
- Fill missing regions while preserving opaque geometry pixels and the facade unchanged.
'''
environment_skill_path.write_text(environment_skill, "utf-8")

tests = test_path.read_text("utf-8")
tests = tests.replace(
    "assert state['active_files']['geometry'].endswith('geometry_current.jpg')",
    "assert state['active_files']['geometry'].endswith('geometry_current.png')\n    assert state['active_files']['geometry_holes'].endswith('geometry_holes_current.png')",
)
if "test_geometry_has_transparent_outpaint_areas" not in tests:
    tests += '''\n\ndef test_geometry_has_transparent_outpaint_areas():
    created = client.post('/api/projects', data={'name': 'No mirror fill'}).json()
    project_id = created['id']
    client.post(f'/api/projects/{project_id}/source', files={'file': ('source.jpg', sample_image(), 'image/jpeg')})
    quad = [{'x': 190, 'y': 120}, {'x': 650, 'y': 150}, {'x': 700, 'y': 520}, {'x': 140, 'y': 500}]
    applied = client.post(f'/api/projects/{project_id}/geometry/apply-grid', data={'quad_json': __import__('json').dumps(quad)})
    assert applied.status_code == 200, applied.text
    corrected = Image.open(BytesIO(client.get(f'/api/projects/{project_id}/file/geometry').content))
    assert corrected.mode == 'RGBA'
    assert corrected.getchannel('A').getextrema() == (0, 255)
    mask = Image.open(BytesIO(client.get(f'/api/projects/{project_id}/file/geometry_holes').content)).convert('L')
    assert mask.getextrema() == (0, 255)
'''
test_path.write_text(tests, "utf-8")

print("Applied v0.6.1 transparent geometry / deferred outpaint patch")
