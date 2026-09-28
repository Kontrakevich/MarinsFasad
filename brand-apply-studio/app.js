const q = selector => document.querySelector(selector);
const canvas = q("#canvas");
const ctx = canvas.getContext("2d", { willReadFrequently: true });

const state = {
  source: null,
  design: null,
  sourceSize: { width: 0, height: 0 },
  corners: [],
  gridLocked: false,
  showGrid: true,
  rows: 6,
  cols: 8,
  drag: null,
  brand: {
    u: 0.5,
    v: 0.5,
    width: 0.45
  },
  designPixels: null
};

function setStatus(text) {
  q("#status").textContent = text;
}

function setStep(id, mode) {
  const el = q(id);
  el.classList.remove("active", "done");
  if (mode) el.classList.add(mode);
}

function loadImage(file) {
  return new Promise((resolve, reject) => {
    const image = new Image();
    const url = URL.createObjectURL(file);
    image.onload = () => {
      URL.revokeObjectURL(url);
      resolve(image);
    };
    image.onerror = reject;
    image.src = url;
  });
}

function defaultCorners() {
  return [
    { x: 0.15, y: 0.15 },
    { x: 0.85, y: 0.15 },
    { x: 0.85, y: 0.85 },
    { x: 0.15, y: 0.85 }
  ];
}

function canvasPoint(normalized) {
  return {
    x: normalized.x * canvas.width,
    y: normalized.y * canvas.height
  };
}

function normalizedPoint(point) {
  return {
    x: point.x / canvas.width,
    y: point.y / canvas.height
  };
}

function quadPixels() {
  return state.corners.map(canvasPoint);
}

function solve(A, b) {
  const n = b.length;
  const matrix = A.map((row, i) => [...row, b[i]]);

  for (let col = 0; col < n; col += 1) {
    let pivot = col;
    for (let row = col + 1; row < n; row += 1) {
      if (Math.abs(matrix[row][col]) > Math.abs(matrix[pivot][col])) {
        pivot = row;
      }
    }

    [matrix[col], matrix[pivot]] = [matrix[pivot], matrix[col]];
    const divisor = matrix[col][col];

    if (Math.abs(divisor) < 1e-12) {
      throw new Error("Некорректная плоскость перспективы");
    }

    for (let c = col; c <= n; c += 1) matrix[col][c] /= divisor;

    for (let row = 0; row < n; row += 1) {
      if (row === col) continue;
      const factor = matrix[row][col];
      for (let c = col; c <= n; c += 1) {
        matrix[row][c] -= factor * matrix[col][c];
      }
    }
  }

  return matrix.map(row => row[n]);
}

function homography(src, dst) {
  const A = [];
  const b = [];

  for (let i = 0; i < 4; i += 1) {
    const { x, y } = src[i];
    const X = dst[i].x;
    const Y = dst[i].y;

    A.push([x, y, 1, 0, 0, 0, -x * X, -y * X]);
    b.push(X);

    A.push([0, 0, 0, x, y, 1, -x * Y, -y * Y]);
    b.push(Y);
  }

  const h = solve(A, b);

  return [
    [h[0], h[1], h[2]],
    [h[3], h[4], h[5]],
    [h[6], h[7], 1]
  ];
}

function invert3(m) {
  const a = m[0][0], b = m[0][1], c = m[0][2];
  const d = m[1][0], e = m[1][1], f = m[1][2];
  const g = m[2][0], h = m[2][1], i = m[2][2];

  const A = e * i - f * h;
  const B = -(d * i - f * g);
  const C = d * h - e * g;
  const D = -(b * i - c * h);
  const E = a * i - c * g;
  const F = -(a * h - b * g);
  const G = b * f - c * e;
  const H = -(a * f - c * d);
  const I = a * e - b * d;

  const det = a * A + b * B + c * C;
  if (Math.abs(det) < 1e-12) throw new Error("Некорректная матрица перспективы");

  return [
    [A / det, D / det, G / det],
    [B / det, E / det, H / det],
    [C / det, F / det, I / det]
  ];
}

function applyH(H, x, y) {
  const z = H[2][0] * x + H[2][1] * y + H[2][2];
  return {
    x: (H[0][0] * x + H[0][1] * y + H[0][2]) / z,
    y: (H[1][0] * x + H[1][1] * y + H[1][2]) / z
  };
}

function surfaceMatrix() {
  const src = [
    { x: 0, y: 0 },
    { x: 1, y: 0 },
    { x: 1, y: 1 },
    { x: 0, y: 1 }
  ];
  return homography(src, quadPixels());
}

function surfacePoint(u, v) {
  return applyH(surfaceMatrix(), u, v);
}

function pointerToSurface(point) {
  return applyH(invert3(surfaceMatrix()), point.x, point.y);
}

function surfaceAspect() {
  const points = state.corners.map(point => ({
    x: point.x * state.sourceSize.width,
    y: point.y * state.sourceSize.height
  }));

  const [tl, tr, br, bl] = points;
  const top = Math.hypot(tr.x - tl.x, tr.y - tl.y);
  const bottom = Math.hypot(br.x - bl.x, br.y - bl.y);
  const left = Math.hypot(bl.x - tl.x, bl.y - tl.y);
  const right = Math.hypot(br.x - tr.x, br.y - tr.y);

  return Math.max(1e-6, (top + bottom) / Math.max(1e-6, left + right));
}

function brandSize() {
  if (!state.design) return { width: state.brand.width, height: state.brand.width };

  const designAspect = state.design.width / state.design.height;
  const planeAspect = surfaceAspect();
  const height = state.brand.width * planeAspect / designAspect;

  return {
    width: state.brand.width,
    height
  };
}

function clampBrand() {
  const size = brandSize();
  const halfW = size.width / 2;
  const halfH = size.height / 2;

  state.brand.u = Math.max(halfW, Math.min(1 - halfW, state.brand.u));
  state.brand.v = Math.max(halfH, Math.min(1 - halfH, state.brand.v));
}

function brandQuadUv() {
  const size = brandSize();
  const u0 = state.brand.u - size.width / 2;
  const u1 = state.brand.u + size.width / 2;
  const v0 = state.brand.v - size.height / 2;
  const v1 = state.brand.v + size.height / 2;

  return [
    { x: u0, y: v0 },
    { x: u1, y: v0 },
    { x: u1, y: v1 },
    { x: u0, y: v1 }
  ];
}

function brandQuadPixels() {
  return brandQuadUv().map(point => surfacePoint(point.x, point.y));
}

function prepareDesignPixels() {
  if (!state.design) {
    state.designPixels = null;
    return;
  }

  const maxSide = 900;
  const scale = Math.min(1, maxSide / Math.max(state.design.width, state.design.height));
  const width = Math.max(1, Math.round(state.design.width * scale));
  const height = Math.max(1, Math.round(state.design.height * scale));

  const off = document.createElement("canvas");
  off.width = width;
  off.height = height;

  const offCtx = off.getContext("2d", { willReadFrequently: true });
  offCtx.drawImage(state.design, 0, 0, width, height);

  state.designPixels = {
    width,
    height,
    data: offCtx.getImageData(0, 0, width, height)
  };
}

function drawSource() {
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.drawImage(state.source, 0, 0, canvas.width, canvas.height);
}

function drawGrid() {
  if (!state.showGrid || state.corners.length !== 4) return;

  const H = surfaceMatrix();

  ctx.save();
  ctx.strokeStyle = "#00d4c7";
  ctx.lineWidth = 1.5;
  ctx.setLineDash([8, 6]);

  for (let col = 0; col <= state.cols; col += 1) {
    const u = col / state.cols;
    let previous = applyH(H, u, 0);

    for (let step = 1; step <= 40; step += 1) {
      const point = applyH(H, u, step / 40);
      ctx.beginPath();
      ctx.moveTo(previous.x, previous.y);
      ctx.lineTo(point.x, point.y);
      ctx.stroke();
      previous = point;
    }
  }

  for (let row = 0; row <= state.rows; row += 1) {
    const v = row / state.rows;
    let previous = applyH(H, 0, v);

    for (let step = 1; step <= 40; step += 1) {
      const point = applyH(H, step / 40, v);
      ctx.beginPath();
      ctx.moveTo(previous.x, previous.y);
      ctx.lineTo(point.x, point.y);
      ctx.stroke();
      previous = point;
    }
  }

  const points = quadPixels();

  ctx.strokeStyle = "#ffffff";
  ctx.lineWidth = 2;
  ctx.setLineDash([12, 8]);
  ctx.beginPath();
  ctx.moveTo(points[0].x, points[0].y);
  points.slice(1).forEach(point => ctx.lineTo(point.x, point.y));
  ctx.closePath();
  ctx.stroke();
  ctx.setLineDash([]);

  if (!state.gridLocked) {
    const radius = 12;
    points.forEach((point, index) => {
      ctx.beginPath();
      ctx.arc(point.x, point.y, radius, 0, Math.PI * 2);
      ctx.fillStyle = "#008a90";
      ctx.fill();
      ctx.strokeStyle = "#ffffff";
      ctx.lineWidth = 2;
      ctx.stroke();

      ctx.fillStyle = "#ffffff";
      ctx.font = "bold 13px Arial";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText("P" + (index + 1), point.x, point.y);
    });
  }

  ctx.restore();
}

function renderBrand() {
  if (!state.designPixels || !state.gridLocked) return;

  const pixels = state.designPixels;
  const srcData = pixels.data.data;
  const dstQuad = brandQuadPixels();

  const srcQuad = [
    { x: 0, y: 0 },
    { x: pixels.width - 1, y: 0 },
    { x: pixels.width - 1, y: pixels.height - 1 },
    { x: 0, y: pixels.height - 1 }
  ];

  const H = homography(srcQuad, dstQuad);
  const inverse = invert3(H);

  const xs = dstQuad.map(point => point.x);
  const ys = dstQuad.map(point => point.y);

  const minX = Math.max(0, Math.floor(Math.min(...xs)));
  const maxX = Math.min(canvas.width - 1, Math.ceil(Math.max(...xs)));
  const minY = Math.max(0, Math.floor(Math.min(...ys)));
  const maxY = Math.min(canvas.height - 1, Math.ceil(Math.max(...ys)));

  if (maxX <= minX || maxY <= minY) return;

  const width = maxX - minX + 1;
  const height = maxY - minY + 1;
  const base = ctx.getImageData(minX, minY, width, height);
  const dstData = base.data;

  for (let y = minY; y <= maxY; y += 1) {
    for (let x = minX; x <= maxX; x += 1) {
      const sourcePoint = applyH(inverse, x, y);

      if (
        sourcePoint.x < 0 ||
        sourcePoint.y < 0 ||
        sourcePoint.x > pixels.width - 1 ||
        sourcePoint.y > pixels.height - 1
      ) {
        continue;
      }

      const sx = Math.max(0, Math.min(pixels.width - 1, Math.round(sourcePoint.x)));
      const sy = Math.max(0, Math.min(pixels.height - 1, Math.round(sourcePoint.y)));

      const sourceIndex = (sy * pixels.width + sx) * 4;
      const alpha = srcData[sourceIndex + 3] / 255;

      if (alpha <= 0) continue;

      const destinationIndex = ((y - minY) * width + (x - minX)) * 4;

      dstData[destinationIndex] =
        srcData[sourceIndex] * alpha + dstData[destinationIndex] * (1 - alpha);
      dstData[destinationIndex + 1] =
        srcData[sourceIndex + 1] * alpha + dstData[destinationIndex + 1] * (1 - alpha);
      dstData[destinationIndex + 2] =
        srcData[sourceIndex + 2] * alpha + dstData[destinationIndex + 2] * (1 - alpha);
      dstData[destinationIndex + 3] = 255;
    }
  }

  ctx.putImageData(base, minX, minY);
}

function drawBrandControls() {
  if (!state.design || !state.gridLocked) return;

  const quad = brandQuadPixels();

  ctx.save();
  ctx.strokeStyle = "#ffffff";
  ctx.lineWidth = 2;
  ctx.setLineDash([7, 5]);

  ctx.beginPath();
  ctx.moveTo(quad[0].x, quad[0].y);
  quad.slice(1).forEach(point => ctx.lineTo(point.x, point.y));
  ctx.closePath();
  ctx.stroke();
  ctx.setLineDash([]);

  const handle = quad[2];

  ctx.fillStyle = "#008a90";
  ctx.fillRect(handle.x - 8, handle.y - 8, 16, 16);
  ctx.strokeStyle = "#ffffff";
  ctx.strokeRect(handle.x - 8, handle.y - 8, 16, 16);

  ctx.restore();
}

let renderQueued = false;

function requestDraw() {
  if (renderQueued) return;
  renderQueued = true;

  requestAnimationFrame(() => {
    renderQueued = false;
    if (!state.source) return;

    drawSource();
    renderBrand();
    drawGrid();
    drawBrandControls();
  });
}

function resizeCanvas() {
  if (!state.source) return;

  const wrap = q("#canvasWrap");
  const availableWidth = Math.max(320, wrap.clientWidth);
  const maxHeight = Math.max(420, window.innerHeight - 300);

  let width = Math.min(state.source.width, availableWidth);
  let height = width * state.source.height / state.source.width;

  if (height > maxHeight) {
    height = Math.min(state.source.height, maxHeight);
    width = height * state.source.width / state.source.height;
  }

  canvas.width = Math.max(1, Math.round(width));
  canvas.height = Math.max(1, Math.round(height));

  requestDraw();
}

function pointerPosition(event) {
  const bounds = canvas.getBoundingClientRect();
  return {
    x: (event.clientX - bounds.left) * canvas.width / bounds.width,
    y: (event.clientY - bounds.top) * canvas.height / bounds.height
  };
}

function nearestGridCorner(point) {
  if (state.gridLocked) return -1;

  const corners = quadPixels();
  let result = -1;
  let min = Infinity;

  corners.forEach((corner, index) => {
    const distance = Math.hypot(point.x - corner.x, point.y - corner.y);
    if (distance < 24 && distance < min) {
      result = index;
      min = distance;
    }
  });

  return result;
}

function distance(a, b) {
  return Math.hypot(a.x - b.x, a.y - b.y);
}

function pointInUvBrand(uv) {
  const size = brandSize();
  return (
    uv.x >= state.brand.u - size.width / 2 &&
    uv.x <= state.brand.u + size.width / 2 &&
    uv.y >= state.brand.v - size.height / 2 &&
    uv.y <= state.brand.v + size.height / 2
  );
}

function maxBrandWidthAtCurrentCenter() {
  if (!state.design) return 0.95;

  const planeAspect = surfaceAspect();
  const designAspect = state.design.width / state.design.height;
  const heightPerWidth = planeAspect / designAspect;

  const horizontal = Math.max(
    0.05,
    2 * Math.min(state.brand.u, 1 - state.brand.u)
  );

  const vertical = Math.max(
    0.05,
    2 * Math.min(state.brand.v, 1 - state.brand.v) / Math.max(heightPerWidth, 1e-6)
  );

  return Math.min(0.98, horizontal, vertical);
}

canvas.addEventListener("pointerdown", event => {
  if (!state.source) return;

  const point = pointerPosition(event);
  const corner = nearestGridCorner(point);

  if (corner >= 0) {
    state.drag = { type: "grid", index: corner };
    canvas.setPointerCapture(event.pointerId);
    return;
  }

  if (!state.gridLocked || !state.design) return;

  const brandQuad = brandQuadPixels();
  const scaleHandle = brandQuad[2];

  if (distance(point, scaleHandle) <= 24) {
    state.drag = { type: "brand-scale" };
    canvas.setPointerCapture(event.pointerId);
    return;
  }

  const uv = pointerToSurface(point);

  if (pointInUvBrand(uv)) {
    state.drag = {
      type: "brand-move",
      offsetU: uv.x - state.brand.u,
      offsetV: uv.y - state.brand.v
    };
    canvas.setPointerCapture(event.pointerId);
  }
});

canvas.addEventListener("pointermove", event => {
  if (!state.drag) return;

  const point = pointerPosition(event);

  if (state.drag.type === "grid") {
    const normalized = normalizedPoint(point);
    state.corners[state.drag.index] = {
      x: Math.max(0, Math.min(1, normalized.x)),
      y: Math.max(0, Math.min(1, normalized.y))
    };
    requestDraw();
    return;
  }

  const uv = pointerToSurface(point);

  if (state.drag.type === "brand-move") {
    state.brand.u = uv.x - state.drag.offsetU;
    state.brand.v = uv.y - state.drag.offsetV;
    clampBrand();
    requestDraw();
    return;
  }

  if (state.drag.type === "brand-scale") {
    const desired = Math.max(
      Math.abs(uv.x - state.brand.u) * 2,
      0.05
    );

    state.brand.width = Math.min(desired, maxBrandWidthAtCurrentCenter());
    clampBrand();
    requestDraw();
  }
});

function stopDrag(event) {
  if (!state.drag) return;
  state.drag = null;
  try {
    canvas.releasePointerCapture(event.pointerId);
  } catch (_) {}
}

canvas.addEventListener("pointerup", stopDrag);
canvas.addEventListener("pointercancel", stopDrag);

q("#sourceFile").addEventListener("change", async event => {
  const file = event.target.files[0];
  if (!file) return;

  setStatus("Загрузка исходника…");

  state.source = await loadImage(file);
  state.sourceSize = {
    width: state.source.width,
    height: state.source.height
  };
  state.corners = defaultCorners();
  state.gridLocked = false;
  state.design = null;
  state.designPixels = null;
  state.brand = { u: 0.5, v: 0.5, width: 0.45 };

  q("#canvasWrap").classList.remove("empty");
  q("#resetGrid").disabled = false;
  q("#lockGrid").disabled = false;
  q("#showGrid").disabled = false;
  q("#designFile").disabled = true;
  q("#designLabel").classList.add("disabled");
  q("#resetBrand").disabled = true;

  setStep("#step1", "done");
  setStep("#step2", "active");
  setStep("#step3", null);
  setStep("#step4", null);

  q("#editorTitle").textContent = "2. Установите сетку перспективы";
  q("#editorHint").textContent = "Перетащите P1–P4 на реальные углы поверхности, куда будет наноситься брендинг.";

  resizeCanvas();
  setStatus("2. Установите P1–P4");
});

q("#resetGrid").addEventListener("click", () => {
  if (!state.source) return;
  state.corners = defaultCorners();
  requestDraw();
});

q("#lockGrid").addEventListener("click", () => {
  if (!state.source) return;

  state.gridLocked = !state.gridLocked;

  if (state.gridLocked) {
    q("#lockGrid").textContent = "Изменить сетку";
    q("#designFile").disabled = false;
    q("#designLabel").classList.remove("disabled");

    setStep("#step2", "done");
    setStep("#step3", state.design ? "done" : "active");

    q("#editorTitle").textContent = state.design
      ? "4. Разместите брендинг"
      : "3. Загрузите файл брендинга";

    q("#editorHint").textContent = state.design
      ? "Перемещайте логотип мышью. Потяните квадратный маркер для масштабирования."
      : "Сетка зафиксирована и больше не двигается.";

    setStatus(state.design ? "4. Разместите брендинг" : "3. Загрузите брендинг");
  } else {
    q("#lockGrid").textContent = "Зафиксировать сетку";
    setStep("#step2", "active");
    setStep("#step3", null);
    setStep("#step4", null);

    q("#editorTitle").textContent = "2. Установите сетку перспективы";
    q("#editorHint").textContent = "Перетащите P1–P4. После корректировки снова зафиксируйте сетку.";
    setStatus("2. Корректировка сетки");
  }

  requestDraw();
});

q("#designFile").addEventListener("change", async event => {
  const file = event.target.files[0];
  if (!file || !state.gridLocked) return;

  setStatus("Загрузка брендинга…");

  state.design = await loadImage(file);
  prepareDesignPixels();
  state.brand = { u: 0.5, v: 0.5, width: 0.45 };
  clampBrand();

  q("#resetBrand").disabled = false;

  setStep("#step3", "done");
  setStep("#step4", "active");

  q("#editorTitle").textContent = "4. Разместите брендинг";
  q("#editorHint").textContent = "Перемещайте логотип мышью. Потяните квадратный маркер в правом нижнем углу для масштабирования.";

  setStatus("4. Перемещайте и масштабируйте логотип");
  requestDraw();
});

q("#resetBrand").addEventListener("click", () => {
  if (!state.design) return;
  state.brand = { u: 0.5, v: 0.5, width: 0.45 };
  clampBrand();
  requestDraw();
});

q("#showGrid").addEventListener("change", event => {
  state.showGrid = event.target.checked;
  requestDraw();
});

window.addEventListener("resize", resizeCanvas);
