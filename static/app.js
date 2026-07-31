let current = null;

const q = selector => document.querySelector(selector);

async function api(url, options = {}) {
  const response = await fetch(url, options);

  if (!response.ok) {
    throw new Error(await response.text());
  }

  return response.json();
}

function formData(values) {
  const data = new FormData();

  Object.entries(values).forEach(([key, value]) => {
    if (value !== undefined && value !== null) {
      data.append(key, value);
    }
  });

  return data;
}

function fileUrl(key) {
  if (!current?.files?.[key]) {
    return "";
  }

  return (
    `/api/projects/${current.id}/file/${key}` +
    `?t=${Date.now()}`
  );
}

async function refreshProjectList() {
  const projects = await api("/api/projects");

  q("#projects").innerHTML = projects.map(project => `
    <button data-id="${project.id}">
      ${project.name}
      <br>
      <small>${project.stage}</small>
    </button>
  `).join("");

  q("#projects")
    .querySelectorAll("button")
    .forEach(button => {
      button.addEventListener("click", () => {
        openProject(button.dataset.id);
      });
    });
}

async function openProject(projectId) {
  current = await api(`/api/projects/${projectId}`);
  render();
}

async function reloadProject() {
  if (!current) {
    return;
  }

  await openProject(current.id);
  await refreshProjectList();
}

function activeReviewStage() {
  for (const stage of [
    "geometry",
    "environment",
    "branding",
  ]) {
    if (current?.statuses?.[stage] === "review") {
      return stage;
    }
  }

  return null;
}

function currentComparison() {
  if (
    current.stage === "branding" ||
    current.stage.startsWith("branding") ||
    current.stage === "complete"
  ) {
    return {
      before: "final",
      after: "branding",
    };
  }

  if (current.stage.startsWith("environment")) {
    return {
      before: "geometry",
      after: "environment",
    };
  }

  return {
    before: "source",
    after: "geometry",
  };
}

function render() {
  q("#empty").hidden = true;
  q("#workspace").hidden = false;

  q("#projectName").textContent = current.name;
  q("#stageBadge").textContent = current.stage;

  const comparison = currentComparison();

  q("#before").src = fileUrl(comparison.before);
  q("#after").src = fileUrl(comparison.after);

  q("#history").textContent = JSON.stringify(
    current.comments || [],
    null,
    2,
  );

  q("#brandingPanel").style.display =
    current.statuses.branding === "locked"
      ? "none"
      : "block";

  const reviewStage = activeReviewStage();

  q("#approve").disabled = !reviewStage;
  q("#revise").disabled = !reviewStage;

  loadPerspectiveSource();
  loadSystemPrompt(q("#aiStage").value);
}

q("#newProject").addEventListener("click", async () => {
  const name = prompt("Название проекта");

  if (!name) {
    return;
  }

  current = await api("/api/projects", {
    method: "POST",
    body: formData({ name }),
  });

  await refreshProjectList();
  render();
});

q("#uploadSource").addEventListener("click", async () => {
  const file = q("#sourceFile").files[0];

  if (!current || !file) {
    alert("Создайте проект и выберите изображение");
    return;
  }

  await api(`/api/projects/${current.id}/source`, {
    method: "POST",
    body: formData({ file }),
  });

  perspective.projectId = null;
  await reloadProject();
});

/* ================================================================
   Perspective grid
   ================================================================ */

const perspective = {
  projectId: null,
  sourcePath: null,
  image: null,
  corners: [],
  dragIndex: -1,
  rows: 6,
  columns: 8,
};

function defaultCorners(image) {
  const insetX = image.naturalWidth * 0.12;
  const insetY = image.naturalHeight * 0.12;

  return [
    { x: insetX, y: insetY },
    {
      x: image.naturalWidth - insetX,
      y: insetY,
    },
    {
      x: image.naturalWidth - insetX,
      y: image.naturalHeight - insetY,
    },
    {
      x: insetX,
      y: image.naturalHeight - insetY,
    },
  ];
}

function loadPerspectiveSource() {
  if (!current?.files?.source) {
    return;
  }

  if (
    perspective.projectId === current.id &&
    perspective.sourcePath === current.files.source &&
    perspective.image
  ) {
    resizePerspectiveCanvas();
    return;
  }

  const image = new Image();

  image.onload = () => {
    perspective.image = image;
    perspective.projectId = current.id;
    perspective.sourcePath = current.files.source;

    const stored = current.geometry_grid;

    perspective.corners = (
      Array.isArray(stored) &&
      stored.length === 4
    )
      ? stored.map(point => ({
          x: Number(point.x),
          y: Number(point.y),
        }))
      : defaultCorners(image);

    resizePerspectiveCanvas();
  };

  image.src = fileUrl("source");
}

function resizePerspectiveCanvas() {
  const canvas = q("#perspectiveCanvas");
  const wrap = q("#canvasWrap");
  const image = perspective.image;

  if (!canvas || !wrap || !image) {
    return;
  }

  canvas.width = image.naturalWidth;
  canvas.height = image.naturalHeight;

  const availableWidth = Math.max(
    300,
    wrap.clientWidth,
  );

  const scale = Math.min(
    1,
    availableWidth / image.naturalWidth,
  );

  canvas.style.width =
    `${Math.round(image.naturalWidth * scale)}px`;

  canvas.style.height =
    `${Math.round(image.naturalHeight * scale)}px`;

  drawPerspectiveGrid();
}

function interpolate(pointA, pointB, amount) {
  return {
    x: pointA.x + (pointB.x - pointA.x) * amount,
    y: pointA.y + (pointB.y - pointA.y) * amount,
  };
}

function bilinearPoint(u, v) {
  const [tl, tr, br, bl] = perspective.corners;

  const top = interpolate(tl, tr, u);
  const bottom = interpolate(bl, br, u);

  return interpolate(top, bottom, v);
}

function drawLine(context, from, to) {
  context.beginPath();
  context.moveTo(from.x, from.y);
  context.lineTo(to.x, to.y);
  context.stroke();
}

function drawPerspectiveGrid() {
  const canvas = q("#perspectiveCanvas");
  const image = perspective.image;

  if (
    !canvas ||
    !image ||
    perspective.corners.length !== 4
  ) {
    return;
  }

  const context = canvas.getContext("2d");

  context.clearRect(
    0,
    0,
    canvas.width,
    canvas.height,
  );

  context.drawImage(
    image,
    0,
    0,
    canvas.width,
    canvas.height,
  );

  const mainWidth = Math.max(
    3,
    canvas.width / 600,
  );

  const gridWidth = Math.max(
    2,
    canvas.width / 1000,
  );

  context.strokeStyle = "#00d4c7";
  context.lineWidth = gridWidth;
  context.setLineDash([
    Math.max(10, canvas.width / 180),
    Math.max(7, canvas.width / 260),
  ]);

  for (
    let column = 0;
    column <= perspective.columns;
    column += 1
  ) {
    const u = column / perspective.columns;
    let previous = bilinearPoint(u, 0);

    for (
      let step = 1;
      step <= 40;
      step += 1
    ) {
      const currentPoint = bilinearPoint(
        u,
        step / 40,
      );

      drawLine(
        context,
        previous,
        currentPoint,
      );

      previous = currentPoint;
    }
  }

  for (
    let row = 0;
    row <= perspective.rows;
    row += 1
  ) {
    const v = row / perspective.rows;
    let previous = bilinearPoint(0, v);

    for (
      let step = 1;
      step <= 40;
      step += 1
    ) {
      const currentPoint = bilinearPoint(
        step / 40,
        v,
      );

      drawLine(
        context,
        previous,
        currentPoint,
      );

      previous = currentPoint;
    }
  }

  context.strokeStyle = "#ffffff";
  context.lineWidth = mainWidth;
  context.setLineDash([
    Math.max(16, canvas.width / 120),
    Math.max(10, canvas.width / 180),
  ]);

  context.beginPath();
  context.moveTo(
    perspective.corners[0].x,
    perspective.corners[0].y,
  );

  perspective.corners.slice(1).forEach(point => {
    context.lineTo(point.x, point.y);
  });

  context.closePath();
  context.stroke();
  context.setLineDash([]);

  const handleRadius = Math.max(
    12,
    canvas.width / 130,
  );

  perspective.corners.forEach((point, index) => {
    context.beginPath();
    context.arc(
      point.x,
      point.y,
      handleRadius,
      0,
      Math.PI * 2,
    );

    context.fillStyle = "#008a90";
    context.fill();

    context.lineWidth = Math.max(
      3,
      canvas.width / 700,
    );

    context.strokeStyle = "#ffffff";
    context.stroke();

    context.fillStyle = "#ffffff";
    context.font =
      `${Math.max(18, canvas.width / 65)}px Arial`;

    context.textAlign = "center";
    context.textBaseline = "middle";

    context.fillText(
      String(index + 1),
      point.x,
      point.y,
    );
  });
}

function eventPosition(event) {
  const canvas = q("#perspectiveCanvas");
  const bounds = canvas.getBoundingClientRect();

  return {
    x: (
      (event.clientX - bounds.left) *
      canvas.width /
      bounds.width
    ),
    y: (
      (event.clientY - bounds.top) *
      canvas.height /
      bounds.height
    ),
  };
}

function closestCorner(position) {
  const canvas = q("#perspectiveCanvas");
  const bounds = canvas.getBoundingClientRect();

  const hitRadius =
    28 * canvas.width / bounds.width;

  let result = -1;
  let minimum = Number.POSITIVE_INFINITY;

  perspective.corners.forEach((point, index) => {
    const distance = Math.hypot(
      position.x - point.x,
      position.y - point.y,
    );

    if (
      distance <= hitRadius &&
      distance < minimum
    ) {
      minimum = distance;
      result = index;
    }
  });

  return result;
}

const perspectiveCanvas = q("#perspectiveCanvas");

perspectiveCanvas.addEventListener(
  "pointerdown",
  event => {
    const position = eventPosition(event);
    const index = closestCorner(position);

    if (index === -1) {
      return;
    }

    perspective.dragIndex = index;
    perspectiveCanvas.setPointerCapture(
      event.pointerId,
    );
  },
);

perspectiveCanvas.addEventListener(
  "pointermove",
  event => {
    if (perspective.dragIndex === -1) {
      return;
    }

    const position = eventPosition(event);
    const canvas = perspectiveCanvas;

    perspective.corners[perspective.dragIndex] = {
      x: Math.max(
        0,
        Math.min(canvas.width, position.x),
      ),
      y: Math.max(
        0,
        Math.min(canvas.height, position.y),
      ),
    };

    drawPerspectiveGrid();
  },
);

function stopPerspectiveDrag(event) {
  if (perspective.dragIndex === -1) {
    return;
  }

  perspective.dragIndex = -1;

  try {
    perspectiveCanvas.releasePointerCapture(
      event.pointerId,
    );
  } catch (_) {
    // Pointer may already be released by browser.
  }
}

perspectiveCanvas.addEventListener(
  "pointerup",
  stopPerspectiveDrag,
);

perspectiveCanvas.addEventListener(
  "pointercancel",
  stopPerspectiveDrag,
);

q("#resetPerspectiveGrid").addEventListener(
  "click",
  () => {
    if (!perspective.image) {
      return;
    }

    perspective.corners = defaultCorners(
      perspective.image,
    );

    drawPerspectiveGrid();
  },
);

q("#applyPerspectiveGrid").addEventListener(
  "click",
  async () => {
    if (!current || perspective.corners.length !== 4) {
      return;
    }

    const button = q("#applyPerspectiveGrid");
    const originalText = button.textContent;

    button.disabled = true;
    button.textContent = "Трансформация…";

    try {
      await api(
        `/api/projects/${current.id}/geometry/manual`,
        {
          method: "POST",
          body: formData({
            guides_json: JSON.stringify({
              quad: perspective.corners,
            }),
          }),
        },
      );

      await reloadProject();
    } catch (error) {
      alert(
        `Ошибка перспективной трансформации:\n${error.message}`,
      );
    } finally {
      button.disabled = false;
      button.textContent = originalText;
    }
  },
);

window.addEventListener(
  "resize",
  resizePerspectiveCanvas,
);

/* ================================================================
   Skill prompt and Nano Banana
   ================================================================ */

async function loadSystemPrompt(stage) {
  if (!current) {
    return;
  }

  q("#systemPrompt").value =
    "Формирование системного prompt…";

  try {
    const result = await api(
      `/api/projects/${current.id}/prompt/${stage}`,
    );

    q("#systemPrompt").value = result.prompt;
    q("#aiModel").textContent = result.model;

    const stageNames = {
      geometry: "Исправить геометрию — Nano Banana",
      environment: "Дорисовать окружение — Nano Banana",
      branding: "Создать вывеску — Nano Banana",
    };

    q("#runAiStage").textContent =
      stageNames[stage];
  } catch (error) {
    q("#systemPrompt").value =
      `Ошибка формирования prompt:\n${error.message}`;
  }
}

q("#aiStage").addEventListener(
  "change",
  event => {
    loadSystemPrompt(event.target.value);
  },
);

q("#refreshPrompt").addEventListener(
  "click",
  () => {
    loadSystemPrompt(q("#aiStage").value);
  },
);

q("#runAiStage").addEventListener(
  "click",
  async () => {
    if (!current) {
      return;
    }

    const stage = q("#aiStage").value;
    const comment = q("#aiComment").value;
    const button = q("#runAiStage");
    const originalText = button.textContent;

    button.disabled = true;
    button.textContent = "Генерация…";

    q("#aiStatus").textContent =
      "Nano Banana обрабатывает текущий результат этапа.";

    try {
      await api(
        `/api/projects/${current.id}/ai/${stage}`,
        {
          method: "POST",
          body: formData({
            operator_comment: comment,
          }),
        },
      );

      q("#aiStatus").textContent =
        "Изображение получено. Требуется проверка.";

      await reloadProject();
    } catch (error) {
      q("#aiStatus").textContent =
        `Ошибка: ${error.message}`;

      alert(`Ошибка Nano Banana:\n${error.message}`);
    } finally {
      button.disabled = false;
      button.textContent = originalText;
    }
  },
);

/* ================================================================
   Review
   ================================================================ */

q("#approve").addEventListener(
  "click",
  async () => {
    const stage = activeReviewStage();

    if (!stage) {
      return;
    }

    await api(
      `/api/projects/${current.id}/${stage}/approve`,
      {
        method: "POST",
        body: formData({
          comment: q("#comment").value,
        }),
      },
    );

    q("#comment").value = "";
    await reloadProject();
  },
);

q("#revise").addEventListener(
  "click",
  async () => {
    const stage = activeReviewStage();
    const comment = q("#comment").value.trim();

    if (!stage || !comment) {
      alert("Добавьте комментарий к доработке");
      return;
    }

    await api(
      `/api/projects/${current.id}/${stage}/revise`,
      {
        method: "POST",
        body: formData({ comment }),
      },
    );

    q("#comment").value = "";
    await reloadProject();
  },
);

q("#runBrandingZone").addEventListener(
  "click",
  async () => {
    const logo = q("#logo").files[0];

    await api(
      `/api/projects/${current.id}/branding/run`,
      {
        method: "POST",
        body: formData({
          x: q("#bx").value || 0,
          y: q("#by").value || 0,
          width: q("#bw").value || 500,
          height: q("#bh").value || 150,
          material: q("#material").value,
          logo,
        }),
      },
    );

    await reloadProject();
  },
);

refreshProjectList();
