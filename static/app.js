let current=null;const q=s=>document.querySelector(s);async function api(url,opt={}){const r=await fetch(url,opt);if(!r.ok)throw new Error(await r.text());return r.json()}function fd(obj){const f=new FormData();Object.entries(obj).forEach(([k,v])=>v!==undefined&&v!==null&&f.append(k,v));return f}async function refreshList(){const list=await api('/api/projects');q('#projects').innerHTML=list.map(p=>`<button data-id="${p.id}">${p.name}<br><small>${p.stage}</small></button>`).join('');q('#projects').querySelectorAll('button').forEach(b=>b.onclick=()=>openProject(b.dataset.id))}async function openProject(id){current=await api(`/api/projects/${id}`);render()}function fileUrl(k){return current&&current.files&&current.files[k]?`/api/projects/${current.id}/file/${k}?t=${Date.now()}`:''}function render(){q('#empty').hidden=true;q('#workspace').hidden=false;q('#projectName').textContent=current.name;q('#stageBadge').textContent=current.stage;let before='source',after='geometry';if(current.stage.startsWith('environment')){before='geometry';after='environment'}else if(current.stage==='branding'||current.stage.startsWith('branding')||current.stage==='complete'){before='final';after='branding'}q('#before').src=fileUrl(before);q('#after').src=fileUrl(after);q('#history').textContent=JSON.stringify(current.comments||[],null,2);loadPerspectiveImage();q('#brandingPanel').style.display=current.statuses.branding==='locked'?'none':'block';q('#runGeometry').disabled=!current.files.source;q('#runEnvironment').disabled=current.statuses.geometry!=='approved';q('#approve').disabled=!['review'].includes(current.statuses.geometry)&&!['review'].includes(current.statuses.environment)&&!['review'].includes(current.statuses.branding)}async function reload(){await openProject(current.id);await refreshList()}q('#newProject').onclick=async()=>{const name=prompt('Название проекта');if(!name)return;current=await api('/api/projects',{method:'POST',body:fd({name})});await refreshList();render()};q('#uploadSource').onclick=async()=>{const f=q('#sourceFile').files[0];if(!current||!f)return alert('Создайте проект и выберите файл');await api(`/api/projects/${current.id}/source`,{method:'POST',body:fd({file:f})});await reload()};q('#runGeometry').onclick=async()=>{await api(`/api/projects/${current.id}/geometry/run`,{method:'POST'});await reload()};q('#runEnvironment').onclick=async()=>{await api(`/api/projects/${current.id}/environment/run`,{method:'POST'});await reload()};function activeStage(){for(const s of ['geometry','environment','branding'])if(current.statuses[s]==='review')return s;return null}q('#approve').onclick=async()=>{const s=activeStage();if(!s)return;await api(`/api/projects/${current.id}/${s}/approve`,{method:'POST',body:fd({comment:q('#comment').value})});q('#comment').value='';await reload()};q('#revise').onclick=async()=>{const s=activeStage();const c=q('#comment').value.trim();if(!s||!c)return alert('Добавьте комментарий');await api(`/api/projects/${current.id}/${s}/revise`,{method:'POST',body:fd({comment:c})});q('#comment').value='';await reload()};q('#runBranding').onclick=async()=>{const logo=q('#logo').files[0];await api(`/api/projects/${current.id}/branding/run`,{method:'POST',body:fd({x:q('#bx').value||0,y:q('#by').value||0,width:q('#bw').value||500,height:q('#bh').value||150,material:q('#material').value,logo})});await reload()};refreshList();

const perspectiveState = {
  active: "left_vertical",
  points: {
    left_vertical: [],
    right_vertical: [],
    horizon: [],
  },
  image: null,
};

const guideColors = {
  left_vertical: "#ef4444",
  right_vertical: "#22c55e",
  horizon: "#2563eb",
};

function selectGuide(name) {
  perspectiveState.active = name;

  ["selectLeftGuide", "selectRightGuide", "selectHorizonGuide"]
    .forEach(id => q("#" + id)?.classList.remove("active-guide"));

  const idMap = {
    left_vertical: "selectLeftGuide",
    right_vertical: "selectRightGuide",
    horizon: "selectHorizonGuide",
  };

  q("#" + idMap[name])?.classList.add("active-guide");
  updateCanvasHint();
}

function updateCanvasHint() {
  const names = {
    left_vertical: "левую вертикаль",
    right_vertical: "правую вертикаль",
    horizon: "линию горизонта",
  };

  const count = perspectiveState.points[perspectiveState.active].length;
  q("#canvasHint").textContent = count === 0
    ? `Поставьте первую точку на ${names[perspectiveState.active]}.`
    : `Поставьте вторую точку на ${names[perspectiveState.active]}.`;
}

function completedGuides() {
  return Object.values(perspectiveState.points)
    .filter(points => points.length === 2)
    .length;
}

function updateGuideStatus() {
  q("#guideStatus").textContent =
    `${completedGuides()} из 3 направляющих`;

  q("#applyManualGeometry").disabled = completedGuides() !== 3;
}

function clearGuides() {
  perspectiveState.points = {
    left_vertical: [],
    right_vertical: [],
    horizon: [],
  };
  selectGuide("left_vertical");
  drawPerspectiveCanvas();
  updateGuideStatus();
}

function loadPerspectiveImage() {
  if (!current?.files?.source) return;

  const image = new Image();
  image.onload = () => {
    perspectiveState.image = image;
    resizePerspectiveCanvas();
    clearGuides();
  };
  image.src = fileUrl("source");
}

function resizePerspectiveCanvas() {
  const canvas = q("#perspectiveCanvas");
  const wrap = q("#canvasWrap");
  const image = perspectiveState.image;

  if (!canvas || !wrap || !image) return;

  const availableWidth = Math.max(320, wrap.clientWidth);
  const scale = Math.min(1, availableWidth / image.naturalWidth);

  canvas.width = image.naturalWidth;
  canvas.height = image.naturalHeight;
  canvas.style.width = `${Math.round(image.naturalWidth * scale)}px`;
  canvas.style.height = `${Math.round(image.naturalHeight * scale)}px`;

  drawPerspectiveCanvas();
}

function drawPerspectiveCanvas() {
  const canvas = q("#perspectiveCanvas");
  const image = perspectiveState.image;
  if (!canvas || !image) return;

  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.drawImage(image, 0, 0, canvas.width, canvas.height);

  const lineWidth = Math.max(4, canvas.width / 400);
  const radius = Math.max(8, canvas.width / 180);

  Object.entries(perspectiveState.points).forEach(([name, points]) => {
    ctx.strokeStyle = guideColors[name];
    ctx.fillStyle = guideColors[name];
    ctx.lineWidth = lineWidth;
    ctx.setLineDash(name === "horizon" ? [18, 12] : []);

    if (points.length === 2) {
      ctx.beginPath();
      ctx.moveTo(points[0].x, points[0].y);
      ctx.lineTo(points[1].x, points[1].y);
      ctx.stroke();
    }

    points.forEach((point, index) => {
      ctx.beginPath();
      ctx.arc(point.x, point.y, radius, 0, Math.PI * 2);
      ctx.fill();

      ctx.fillStyle = "#ffffff";
      ctx.font = `${Math.max(18, canvas.width / 55)}px sans-serif`;
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(String(index + 1), point.x, point.y);
      ctx.fillStyle = guideColors[name];
    });
  });

  ctx.setLineDash([]);
}

function canvasCoordinates(event) {
  const canvas = q("#perspectiveCanvas");
  const rect = canvas.getBoundingClientRect();

  return {
    x: (event.clientX - rect.left) * canvas.width / rect.width,
    y: (event.clientY - rect.top) * canvas.height / rect.height,
  };
}

q("#perspectiveCanvas")?.addEventListener("click", event => {
  if (!perspectiveState.image) return;

  const points = perspectiveState.points[perspectiveState.active];

  if (points.length >= 2) {
    points.length = 0;
  }

  points.push(canvasCoordinates(event));
  drawPerspectiveCanvas();
  updateGuideStatus();
  updateCanvasHint();

  if (points.length === 2) {
    const order = ["left_vertical", "right_vertical", "horizon"];
    const currentIndex = order.indexOf(perspectiveState.active);
    const next = order.find(
      (name, index) =>
        index > currentIndex &&
        perspectiveState.points[name].length < 2
    );

    if (next) selectGuide(next);
  }
});

q("#selectLeftGuide")?.addEventListener(
  "click",
  () => selectGuide("left_vertical"),
);

q("#selectRightGuide")?.addEventListener(
  "click",
  () => selectGuide("right_vertical"),
);

q("#selectHorizonGuide")?.addEventListener(
  "click",
  () => selectGuide("horizon"),
);

q("#undoGuide")?.addEventListener("click", () => {
  const activePoints =
    perspectiveState.points[perspectiveState.active];

  if (activePoints.length) {
    activePoints.pop();
  } else {
    const reversed = [
      "horizon",
      "right_vertical",
      "left_vertical",
    ];

    const previous = reversed.find(
      name => perspectiveState.points[name].length,
    );

    if (previous) {
      perspectiveState.points[previous].pop();
      selectGuide(previous);
    }
  }

  drawPerspectiveCanvas();
  updateGuideStatus();
  updateCanvasHint();
});

q("#resetGuides")?.addEventListener("click", clearGuides);

q("#applyManualGeometry")?.addEventListener("click", async () => {
  if (!current) return;

  if (completedGuides() !== 3) {
    alert("Постройте все три направляющие.");
    return;
  }

  const button = q("#applyManualGeometry");
  button.disabled = true;
  button.textContent = "Выполняется коррекция…";

  try {
    await api(
      `/api/projects/${current.id}/geometry/manual`,
      {
        method: "POST",
        body: fd({
          guides_json: JSON.stringify(perspectiveState.points),
        }),
      },
    );

    await reload();
  } catch (error) {
    alert(`Ошибка коррекции: ${error.message}`);
  } finally {
    button.textContent = "Применить ручное выравнивание";
    updateGuideStatus();
  }
});

window.addEventListener("resize", resizePerspectiveCanvas);

selectGuide("left_vertical");
updateGuideStatus();
