#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PARTS_DIR="$ROOT/release/v060_xz"
RUNTIME_ROOT="$ROOT/.runtime"
RUNTIME="$RUNTIME_ROOT/MarinsFacade_v0.6.0"
ARCHIVE="$RUNTIME_ROOT/MarinsFacade_v0.6.0.tar.xz"
PROJECTS_BACKUP="$RUNTIME_ROOT/.projects_backup"
NAMED_USER_BACKUP="$RUNTIME_ROOT/.named_user_projects_backup"
EXPECTED_SHA256="12a3ecb31f96dcd76ec6de9fc79ba7c56b1fae2d3f8e91825c60a095a534898a"

if [ ! -d "$PARTS_DIR" ]; then
  echo "Build archive parts not found: $PARTS_DIR" >&2
  exit 1
fi

mapfile -t PARTS < <(find "$PARTS_DIR" -maxdepth 1 -type f -name '*.part' | sort)
if [ "${#PARTS[@]}" -ne 4 ]; then
  echo "Expected 4 archive parts, found ${#PARTS[@]}" >&2
  exit 1
fi

mkdir -p "$RUNTIME_ROOT"
cat "${PARTS[@]}" | base64 --decode > "$ARCHIVE"

ACTUAL_SHA256="$(sha256sum "$ARCHIVE" | awk '{print $1}')"
if [ "$ACTUAL_SHA256" != "$EXPECTED_SHA256" ]; then
  echo "Archive checksum mismatch" >&2
  echo "Expected: $EXPECTED_SHA256" >&2
  echo "Actual:   $ACTUAL_SHA256" >&2
  exit 1
fi

rm -rf "$PROJECTS_BACKUP"
if [ -d "$RUNTIME/data/projects" ]; then
  mkdir -p "$PROJECTS_BACKUP"
  cp -a "$RUNTIME/data/projects/." "$PROJECTS_BACKUP/"
fi

rm -rf "$RUNTIME"
tar -xJf "$ARCHIVE" -C "$RUNTIME_ROOT"

if [ -d "$PROJECTS_BACKUP" ]; then
  mkdir -p "$RUNTIME/data/projects"
  cp -a "$PROJECTS_BACKUP/." "$RUNTIME/data/projects/"
  rm -rf "$PROJECTS_BACKUP"
fi

python - "$RUNTIME/app/web/app.js" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text("utf-8")

old_upload = "$('upload-source').onclick=async()=>{const file=$('source-file').files[0];if(!current||!file)return alert('Создайте проект и выберите изображение');await busy($('upload-source'),'Загрузка исходника',()=>api(`/api/projects/${current.id}/source`,{method:'POST',body:formData({file})}));await reload()}"
new_upload = "$('upload-source').onclick=async()=>{const file=$('source-file').files[0];if(!current||!file)return alert('Создайте проект и выберите изображение');await busy($('upload-source'),'Загрузка исходника',()=>api(`/api/projects/${current.id}/source`,{method:'POST',body:formData({file})}));geo.image=null;geo.projectId=null;geo.sourcePath=null;await reload()}"

old_geo = "const geo={image:null,corners:[],drag:-1,history:[],future:[],projectId:null};"
new_geo = "const geo={image:null,corners:[],drag:-1,history:[],future:[],projectId:null,sourcePath:null};"

old_loader = "function loadGeometryImage(){if(geo.projectId===current.id&&geo.image){drawGeometry();return}const img=new Image();img.onload=()=>{geo.image=img;geo.projectId=current.id;"
new_loader = "function loadGeometryImage(){if(geo.projectId===current.id&&geo.sourcePath===current.active_files.source&&geo.image){drawGeometry();return}const img=new Image();img.onload=()=>{geo.image=img;geo.projectId=current.id;geo.sourcePath=current.active_files.source;"

replacements = [
    (old_upload, new_upload, "upload handler"),
    (old_geo, new_geo, "geometry cache state"),
    (old_loader, new_loader, "geometry image loader"),
]

for old, new, label in replacements:
    if new in text:
        continue
    if old not in text:
        raise SystemExit(f"Runtime UI patch failed: {label} pattern not found")
    text = text.replace(old, new, 1)

path.write_text(text, "utf-8")
print("Applied source-upload geometry refresh patch")
PY

python "$ROOT/release/patch_v061.py" "$RUNTIME"

rm -rf "$NAMED_USER_BACKUP"
python - "$RUNTIME" "$NAMED_USER_BACKUP" <<'PY'
import json
import shutil
import sys
from pathlib import Path

runtime = Path(sys.argv[1])
backup = Path(sys.argv[2])
names = {"Test facade", "Revision test", "No mirror fill"}
projects = runtime / "data/projects"
for folder in projects.iterdir() if projects.exists() else []:
    state_file = folder / "project.json"
    passport_file = folder / "source/scene_passport.json"
    if not state_file.exists():
        continue
    try:
        state = json.loads(state_file.read_text("utf-8"))
        passport = json.loads(passport_file.read_text("utf-8")) if passport_file.exists() else {}
    except Exception:
        continue
    automated_fixture = passport.get("width") == 800 and passport.get("height") == 600
    if state.get("name") in names and not automated_fixture:
        target = backup / folder.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(folder, target)
PY

python "$ROOT/release/patch_v062.py" "$RUNTIME"

if [ -d "$NAMED_USER_BACKUP" ]; then
  mkdir -p "$RUNTIME/data/projects"
  cp -a "$NAMED_USER_BACKUP/." "$RUNTIME/data/projects/"
  rm -rf "$NAMED_USER_BACKUP"
fi

python -m pip install --upgrade pip
python -m pip install -r "$RUNTIME/requirements.txt"

cd "$RUNTIME"
python -m compileall app
rm -rf "$RUNTIME/.test-data"
MARINS_DATA_ROOT="$RUNTIME/.test-data/projects" pytest -q
rm -rf "$RUNTIME/.test-data"

echo "Marins Facade v0.6.2 installed in $RUNTIME"
