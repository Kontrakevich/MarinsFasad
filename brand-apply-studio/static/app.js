let current = null;

const q = selector => document.querySelector(selector);

async function api(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

function formData(values) {
  const data = new FormData();
  Object.entries(values).forEach(([key, value]) => {
    if (value !== undefined && value !== null) data.append(key, value);
  });
  return data;
}

function fileUrl(key) {
  if (!current?.files?.[key]) return "";
  return `/api/projects/${current.id}/file/${key}?t=${Date.now()}`;
}

const perspective = {
  projectId: null,
  image: null,
  corners: [],
  dragIndex: -1,
  rows: 6,
  columns: 8,
};

function defaultCorners(image) {
  const x = image.naturalWidth * 0.15;
  const y = image.naturalHeight * 0.15;
  return [
    {x, y},
    {x: image.naturalWidth - x, y},
    {x: image.naturalWidth - x, y: image.naturalHeight - y},
    {x, y: image.naturalHeight - y},
  ];
}

function interpolate(a, b, t) {
  return {x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t};
}

function bilinearPoint(u, v) {
  const [tl, tr, br, bl] = perspective.corners;
  return interpolate(interpolate(tl, tr, u), interpolate(bl, br, u), v);
}

function resizeCanvas() {
  const canvas = q("#perspectiveCanvas");
  const wrap = q("#canvasWrap");
  const image = perspective.image;
  if (!canvas || !wrap || !image) return;

  canvas.width = image.naturalWidth;
  canvas.height = image.naturalHeight;

  const available = Math.max(320, wrap.clientWidth);
  const scale = Math.min(1, available / image.naturalWidth);

  canvas.style.width = `${Math.round(image.naturalWidth * scale)}px`;
  canvas.style.height = `${Math.round(image.naturalHeight * scale)}px`;

  drawGrid();
}

function drawLine(ctx, a, b) {
  ctx.beginPath();
  ctx.moveTo(a.x, a.y);
  ctx.lineTo(b.x, b.y);
  ctx.stroke();
}

function drawGrid() {
  const canvas = q("#perspectiveCanvas");
  const image = perspective.image;
  if (!canvas || !image || perspective.corners.length !== 4) return;

  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.drawImage(image, 0, 0, canvas.width, canvas.height);

  ctx.strokeStyle = "#00d4c7";
  ctx.lineWidth = Math.max(2, canvas.width / 1000);
  ctx.setLineDash([Math.max(10, canvas.width / 180), Math.max(7, canvas.width / 260)]);

  for (let c = 0; c <= perspective.columns; c += 1) {
    const u = c / perspective.columns;
    let previous = bilinearPoint(u, 0);
    for (let step = 1; step <= 40; step += 1) {
      const point = bilinearPoint(u, step / 40);
      drawLine(ctx, previous, point);
      previous = point;
    }
  }

  for (let r = 0; r <= perspective.rows; r += 1) {
    const v = r / perspective.rows;
    let previous = bilinearPoint(0, v);
    for (let step = 1; step <= 40; step += 1) {
      const point = bilinearPoint(step / 40, v);
      drawLine(ctx, previous, point);
      previous = point;
    }
  }

  ctx.strokeStyle = "#ffffff";
  ctx.lineWidth = Math.max(3, canvas.width / 600);
  ctx.setLineDash([Math.max(16, canvas.width / 120), Math.max(10, canvas.width / 180)]);
  ctx.beginPath();
  ctx.moveTo(perspective.corners[0].x, perspective.corners[0].y);
  perspective.corners.slice(1).forEach(point => ctx.lineTo(point.x, point.y));
  ctx.closePath();
  ctx.stroke();
  ctx.setLineDash([]);

  const radius = Math.max(12, canvas.width / 130);
  perspective.corners.forEach((point, index) => {
    ctx.beginPath();
    ctx.arc(point.x, point.y, radius, 0, Math.PI * 2);
    ctx.fillStyle = "#008a90";
    ctx.fill();
    ctx.strokeStyle = "#ffffff";
    ctx.lineWidth = Math.max(3, canvas.width / 700);
    ctx.stroke();
    ctx.fillStyle = "#ffffff";
    ctx.font = `${Math.max(18, canvas.width / 65)}px Arial`;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(String(index + 1), point.x, point.y);
  });
}

function eventPosition(event) {
  const canvas = q("#perspectiveCanvas");
  const bounds = canvas.getBoundingClientRect();
  return {
    x: (event.clientX - bounds.left) * canvas.width / bounds.width,
    y: (event.clientY - bounds.top) * canvas.height / bounds.height,
  };
}

function closestCorner(position) {
  const canvas = q("#perspectiveCanvas");
  const bounds = canvas.getBoundingClientRect();
  const hitRadius = 28 * canvas.width / bounds.width;
  let result = -1;
  let minimum = Infinity;

  perspective.corners.forEach((point, index) => {
    const distance = Math.hypot(position.x - point.x, position.y - point.y);
    if (distance <= hitRadius && distance < minimum) {
      minimum = distance;
      result = index;
    }
  });
  return result;
}

const canvas = q("#perspectiveCanvas");

canvas.addEventListener("pointerdown", event => {
  const index = closestCorner(eventPosition(event));
  if (index === -1) return;
  perspective.dragIndex = index;
  canvas.setPointerCapture(event.pointerId);
});

canvas.addEventListener("pointermove", event => {
  if (perspective.dragIndex === -1) return;
  const point = eventPosition(event);
  perspective.corners[perspective.dragIndex] = {
    x: Math.max(0, Math.min(canvas.width, point.x)),
    y: Math.max(0, Math.min(canvas.height, point.y)),
  };
  drawGrid();
});

function stopDrag(event) {
  if (perspective.dragIndex === -1) return;
  perspective.dragIndex = -1;
  try { canvas.releasePointerCapture(event.pointerId); } catch (_) {}
}
canvas.addEventListener("pointerup", stopDrag);
canvas.addEventListener("pointercancel", stopDrag);

async function refreshProjects(preferredId = null) {
  const projects = await api("/api/projects");
  q("#projects").innerHTML = projects.length
    ? projects.map(p => `<option value="${p.id}">${p.name}</option>`).join("")
    : '<option value="">Нет проектов</option>';

  if (preferredId) q("#projects").value = preferredId;
  if (!q("#projects").value && projects[0]) q("#projects").value = projects[0].id;
  if (q("#projects").value) await openProject(q("#projects").value);
}

async function openProject(id) {
  current = await api(`/api/projects/${id}`);
  q("#status").textContent = current.name;
  q("#sourcePreview").src = fileUrl("source");
  q("#guidePreview").src = fileUrl("guide");
  q("#brandPreview").src = fileUrl("branded");
  q("#maskPreview").src = fileUrl("mask");

  if (current.files?.source) {
    const image = new Image();
    image.onload = () => {
      perspective.image = image;
      perspective.projectId = current.id;
      perspective.corners = Array.isArray(current.surface?.quad)
        ? current.surface.quad.map(p => ({x: Number(p.x), y: Number(p.y)}))
        : defaultCorners(image);
      resizeCanvas();
    };
    image.src = fileUrl("source");
  }
}

q("#projects").addEventListener("change", event => {
  if (event.target.value) openProject(event.target.value);
});

q("#newProject").addEventListener("click", async () => {
  const name = prompt("Название проекта", "Brand Apply Test");
  if (!name) return;
  const created = await api("/api/projects", {
    method: "POST",
    body: formData({name}),
  });
  await refreshProjects(created.id);
});

q("#uploadSource").addEventListener("click", async () => {
  if (!current) return alert("Сначала создайте проект");
  const file = q("#sourceFile").files[0];
  if (!file) return alert("Выберите исходник");
  current = await api(`/api/projects/${current.id}/source`, {
    method: "POST",
    body: formData({file}),
  });
  await openProject(current.id);
});

q("#uploadDesign").addEventListener("click", async () => {
  if (!current) return alert("Сначала создайте проект");
  const file = q("#designFile").files[0];
  if (!file) return alert("Выберите дизайн");
  current = await api(`/api/projects/${current.id}/design`, {
    method: "POST",
    body: formData({file}),
  });
  q("#status").textContent = "Дизайн загружен";
});

q("#resetGrid").addEventListener("click", () => {
  if (!perspective.image) return;
  perspective.corners = defaultCorners(perspective.image);
  drawGrid();
});

q("#saveSurface").addEventListener("click", async () => {
  if (!current || perspective.corners.length !== 4) return;
  q("#status").textContent = "Сохраняю геометрию…";
  current = await api(`/api/projects/${current.id}/surface`, {
    method: "POST",
    body: formData({
      guides_json: JSON.stringify({quad: perspective.corners}),
    }),
  });
  q("#guidePreview").src = fileUrl("guide");
  q("#status").textContent = "Плоскость зафиксирована";
});

q("#renderBrand").addEventListener("click", async () => {
  if (!current) return;
  q("#status").textContent = "Строю техническое нанесение…";
  try {
    current = await api(`/api/projects/${current.id}/render`, {method: "POST"});
    q("#brandPreview").src = fileUrl("branded");
    q("#maskPreview").src = fileUrl("mask");
    q("#status").textContent = "Нанесение построено";
  } catch (error) {
    q("#status").textContent = "Ошибка";
    alert(error.message);
  }
});

window.addEventListener("resize", resizeCanvas);
refreshProjects();
