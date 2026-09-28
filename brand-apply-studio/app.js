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
  brand: { u: 0.5, v: 0.5, width: 0.45 },
  designPixels: null,
  aiResultUrl: null
};

function setStatus(text) { q("#status").textContent = text; }
function setAiStatus(text) { q("#aiStatus").textContent = text; }

function setStep(id, mode) {
  const el = q(id);
  el.classList.remove("active", "done");
  if (mode) el.classList.add(mode);
}

function loadImage(file) {
  return new Promise((resolve, reject) => {
    const image = new Image();
    const url = URL.createObjectURL(file);
    image.onload = () => { URL.revokeObjectURL(url); resolve(image); };
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

function solve(A, b) {
  const n = b.length;
  const m = A.map((row, i) => [...row, b[i]]);
  for (let col = 0; col < n; col += 1) {
    let pivot = col;
    for (let row = col + 1; row < n; row += 1) {
      if (Math.abs(m[row][col]) > Math.abs(m[pivot][col])) pivot = row;
    }
    [m[col], m[pivot]] = [m[pivot], m[col]];
    const divisor = m[col][col];
    if (Math.abs(divisor) < 1e-12) throw new Error("Некорректная плоскость перспективы");
    for (let c = col; c <= n; c += 1) m[col][c] /= divisor;
    for (let row = 0; row < n; row += 1) {
      if (row === col) continue;
      const factor = m[row][col];
      for (let c = col; c <= n; c += 1) m[row][c] -= factor * m[col][c];
    }
  }
  return m.map(row => row[n]);
}

function homography(src, dst) {
  const A = [], b = [];
  for (let i = 0; i < 4; i += 1) {
    const { x, y } = src[i];
    const X = dst[i].x, Y = dst[i].y;
    A.push([x, y, 1, 0, 0, 0, -x * X, -y * X]); b.push(X);
    A.push([0, 0, 0, x, y, 1, -x * Y, -y * Y]); b.push(Y);
  }
  const h = solve(A, b);
  return [[h[0],h[1],h[2]],[h[3],h[4],h[5]],[h[6],h[7],1]];
}

function invert3(m) {
  const a=m[0][0],b=m[0][1],c=m[0][2],d=m[1][0],e=m[1][1],f=m[1][2],g=m[2][0],h=m[2][1],i=m[2][2];
  const A=e*i-f*h,B=-(d*i-f*g),C=d*h-e*g,D=-(b*i-c*h),E=a*i-c*g,F=-(a*h-b*g),G=b*f-c*e,H=-(a*f-c*d),I=a*e-b*d;
  const det=a*A+b*B+c*C;
  if (Math.abs(det) < 1e-12) throw new Error("Некорректная матрица перспективы");
  return [[A/det,D/det,G/det],[B/det,E/det,H/det],[C/det,F/det,I/det]];
}

function applyH(H, x, y) {
  const z=H[2][0]*x+H[2][1]*y+H[2][2];
  return { x:(H[0][0]*x+H[0][1]*y+H[0][2])/z, y:(H[1][0]*x+H[1][1]*y+H[1][2])/z };
}

function quadPixelsFor(width, height) {
  return state.corners.map(point => ({ x: point.x * width, y: point.y * height }));
}

function surfaceMatrixFor(width, height) {
  return homography(
    [{x:0,y:0},{x:1,y:0},{x:1,y:1},{x:0,y:1}],
    quadPixelsFor(width, height)
  );
}

function surfacePointFor(u, v, width, height) {
  return applyH(surfaceMatrixFor(width, height), u, v);
}

function pointerToSurface(point) {
  return applyH(invert3(surfaceMatrixFor(canvas.width, canvas.height)), point.x, point.y);
}

function surfaceAspect() {
  const points = quadPixelsFor(state.sourceSize.width, state.sourceSize.height);
  const [tl,tr,br,bl]=points;
  const top=Math.hypot(tr.x-tl.x,tr.y-tl.y);
  const bottom=Math.hypot(br.x-bl.x,br.y-bl.y);
  const left=Math.hypot(bl.x-tl.x,bl.y-tl.y);
  const right=Math.hypot(br.x-tr.x,br.y-tr.y);
  return Math.max(1e-6,(top+bottom)/Math.max(1e-6,left+right));
}

function brandSize() {
  if (!state.design) return { width: state.brand.width, height: state.brand.width };
  const designAspect=state.design.width/state.design.height;
  const planeAspect=surfaceAspect();
  return { width:state.brand.width, height:state.brand.width*planeAspect/designAspect };
}

function clampBrand() {
  const size=brandSize(),halfW=size.width/2,halfH=size.height/2;
  state.brand.u=Math.max(halfW,Math.min(1-halfW,state.brand.u));
  state.brand.v=Math.max(halfH,Math.min(1-halfH,state.brand.v));
}

function brandQuadUv() {
  const size=brandSize(),u0=state.brand.u-size.width/2,u1=state.brand.u+size.width/2,v0=state.brand.v-size.height/2,v1=state.brand.v+size.height/2;
  return [{x:u0,y:v0},{x:u1,y:v0},{x:u1,y:v1},{x:u0,y:v1}];
}

function brandQuadPixelsFor(width, height) {
  return brandQuadUv().map(point => surfacePointFor(point.x, point.y, width, height));
}

function prepareDesignPixels() {
  if (!state.design) { state.designPixels=null; return; }
  const maxSide=1200;
  const scale=Math.min(1,maxSide/Math.max(state.design.width,state.design.height));
  const width=Math.max(1,Math.round(state.design.width*scale));
  const height=Math.max(1,Math.round(state.design.height*scale));
  const off=document.createElement("canvas");
  off.width=width; off.height=height;
  const offCtx=off.getContext("2d",{willReadFrequently:true});
  offCtx.drawImage(state.design,0,0,width,height);
  state.designPixels={width,height,data:offCtx.getImageData(0,0,width,height)};
}

function sampleRgba(data,width,height,x,y) {
  const x0=Math.max(0,Math.min(width-1,Math.floor(x)));
  const y0=Math.max(0,Math.min(height-1,Math.floor(y)));
  const x1=Math.min(width-1,x0+1),y1=Math.min(height-1,y0+1);
  const dx=x-x0,dy=y-y0;
  const weights=[(1-dx)*(1-dy),dx*(1-dy),(1-dx)*dy,dx*dy];
  const points=[[x0,y0],[x1,y0],[x0,y1],[x1,y1]];
  const out=[0,0,0,0];
  for(let k=0;k<4;k++){
    const idx=(points[k][1]*width+points[k][0])*4;
    for(let c=0;c<4;c++) out[c]+=data[idx+c]*weights[k];
  }
  return out;
}

function renderBrandTo(target, mode) {
  const out=target.getContext("2d",{willReadFrequently:true});
  const width=target.width,height=target.height;

  if (mode === "composite") out.drawImage(state.source,0,0,width,height);
  else if (mode === "mask") { out.fillStyle="#000"; out.fillRect(0,0,width,height); }
  else out.clearRect(0,0,width,height);

  if (!state.designPixels || !state.gridLocked) return;

  const pixels=state.designPixels;
  const srcData=pixels.data.data;
  const dstQuad=brandQuadPixelsFor(width,height);
  const srcQuad=[{x:0,y:0},{x:pixels.width-1,y:0},{x:pixels.width-1,y:pixels.height-1},{x:0,y:pixels.height-1}];
  const H=homography(srcQuad,dstQuad),inverse=invert3(H);
  const xs=dstQuad.map(p=>p.x),ys=dstQuad.map(p=>p.y);
  const minX=Math.max(0,Math.floor(Math.min(...xs))),maxX=Math.min(width-1,Math.ceil(Math.max(...xs)));
  const minY=Math.max(0,Math.floor(Math.min(...ys))),maxY=Math.min(height-1,Math.ceil(Math.max(...ys)));
  if(maxX<=minX||maxY<=minY)return;

  const boxW=maxX-minX+1,boxH=maxY-minY+1;
  const base=out.getImageData(minX,minY,boxW,boxH),dst=base.data;

  for(let y=minY;y<=maxY;y++){
    for(let x=minX;x<=maxX;x++){
      const sp=applyH(inverse,x,y);
      if(sp.x<0||sp.y<0||sp.x>pixels.width-1||sp.y>pixels.height-1)continue;
      const rgba=sampleRgba(srcData,pixels.width,pixels.height,sp.x,sp.y);
      const alpha=rgba[3]/255;
      if(alpha<=0)continue;
      const di=((y-minY)*boxW+(x-minX))*4;

      if(mode==="mask"){
        const v=Math.round(255*alpha);
        dst[di]=v;dst[di+1]=v;dst[di+2]=v;dst[di+3]=255;
      } else if(mode==="layer"){
        dst[di]=rgba[0];dst[di+1]=rgba[1];dst[di+2]=rgba[2];dst[di+3]=Math.round(255*alpha);
      } else {
        dst[di]=rgba[0]*alpha+dst[di]*(1-alpha);
        dst[di+1]=rgba[1]*alpha+dst[di+1]*(1-alpha);
        dst[di+2]=rgba[2]*alpha+dst[di+2]*(1-alpha);
        dst[di+3]=255;
      }
    }
  }
  out.putImageData(base,minX,minY);
}

function drawSource() {
  ctx.clearRect(0,0,canvas.width,canvas.height);
  ctx.drawImage(state.source,0,0,canvas.width,canvas.height);
}

function drawGrid() {
  if(!state.showGrid||state.corners.length!==4)return;
  const H=surfaceMatrixFor(canvas.width,canvas.height);
  ctx.save();
  ctx.strokeStyle="#00d4c7";ctx.lineWidth=1;ctx.setLineDash([7,6]);

  for(let col=0;col<=state.cols;col++){
    const u=col/state.cols;let prev=applyH(H,u,0);
    for(let step=1;step<=32;step++){
      const point=applyH(H,u,step/32);
      ctx.beginPath();ctx.moveTo(prev.x,prev.y);ctx.lineTo(point.x,point.y);ctx.stroke();prev=point;
    }
  }
  for(let row=0;row<=state.rows;row++){
    const v=row/state.rows;let prev=applyH(H,0,v);
    for(let step=1;step<=32;step++){
      const point=applyH(H,step/32,v);
      ctx.beginPath();ctx.moveTo(prev.x,prev.y);ctx.lineTo(point.x,point.y);ctx.stroke();prev=point;
    }
  }

  const points=quadPixelsFor(canvas.width,canvas.height);
  ctx.strokeStyle="#fff";ctx.lineWidth=1.5;ctx.setLineDash([10,7]);
  ctx.beginPath();ctx.moveTo(points[0].x,points[0].y);points.slice(1).forEach(p=>ctx.lineTo(p.x,p.y));ctx.closePath();ctx.stroke();ctx.setLineDash([]);

  if(!state.gridLocked){
    const radius=5;
    points.forEach((point,index)=>{
      ctx.beginPath();ctx.arc(point.x,point.y,radius,0,Math.PI*2);
      ctx.fillStyle="#008a90";ctx.fill();ctx.strokeStyle="#fff";ctx.lineWidth=1;ctx.stroke();
      if(state.drag && state.drag.type==="grid" && state.drag.index===index){
        ctx.fillStyle="#fff";ctx.font="10px Arial";ctx.textAlign="left";ctx.textBaseline="middle";
        ctx.fillText("P"+(index+1),point.x+8,point.y);
      }
    });
  }
  ctx.restore();
}

function drawBrandControls() {
  if(!state.design||!state.gridLocked)return;
  const quad=brandQuadPixelsFor(canvas.width,canvas.height);
  ctx.save();ctx.strokeStyle="#fff";ctx.lineWidth=1.5;ctx.setLineDash([6,5]);
  ctx.beginPath();ctx.moveTo(quad[0].x,quad[0].y);quad.slice(1).forEach(p=>ctx.lineTo(p.x,p.y));ctx.closePath();ctx.stroke();ctx.setLineDash([]);
  const handle=quad[2];
  ctx.fillStyle="#008a90";ctx.fillRect(handle.x-6,handle.y-6,12,12);
  ctx.strokeStyle="#fff";ctx.strokeRect(handle.x-6,handle.y-6,12,12);
  ctx.restore();
}

let renderQueued=false;
function requestDraw(){
  if(renderQueued)return;
  renderQueued=true;
  requestAnimationFrame(()=>{
    renderQueued=false;
    if(!state.source)return;
    drawSource();
    if(state.design&&state.gridLocked){
      const temp=document.createElement("canvas");
      temp.width=canvas.width;temp.height=canvas.height;
      renderBrandTo(temp,"composite");
      ctx.clearRect(0,0,canvas.width,canvas.height);
      ctx.drawImage(temp,0,0);
    }
    drawGrid();
    drawBrandControls();
  });
}

function resizeCanvas(){
  if(!state.source)return;
  const wrap=q("#canvasWrap");
  const availableWidth=Math.max(320,wrap.clientWidth);
  const maxHeight=Math.max(420,window.innerHeight-300);
  let width=Math.min(state.source.width,availableWidth);
  let height=width*state.source.height/state.source.width;
  if(height>maxHeight){height=Math.min(state.source.height,maxHeight);width=height*state.source.width/state.source.height}
  canvas.width=Math.max(1,Math.round(width));canvas.height=Math.max(1,Math.round(height));
  requestDraw();
}

function pointerPosition(event){
  const bounds=canvas.getBoundingClientRect();
  return {x:(event.clientX-bounds.left)*canvas.width/bounds.width,y:(event.clientY-bounds.top)*canvas.height/bounds.height};
}

function nearestGridCorner(point){
  if(state.gridLocked)return -1;
  const corners=quadPixelsFor(canvas.width,canvas.height);
  let result=-1,min=Infinity;
  corners.forEach((corner,index)=>{
    const d=Math.hypot(point.x-corner.x,point.y-corner.y);
    if(d<18&&d<min){result=index;min=d}
  });
  return result;
}

function pointInUvBrand(uv){
  const size=brandSize();
  return uv.x>=state.brand.u-size.width/2&&uv.x<=state.brand.u+size.width/2&&uv.y>=state.brand.v-size.height/2&&uv.y<=state.brand.v+size.height/2;
}

function maxBrandWidthAtCurrentCenter(){
  if(!state.design)return .95;
  const planeAspect=surfaceAspect(),designAspect=state.design.width/state.design.height,heightPerWidth=planeAspect/designAspect;
  const horizontal=Math.max(.05,2*Math.min(state.brand.u,1-state.brand.u));
  const vertical=Math.max(.05,2*Math.min(state.brand.v,1-state.brand.v)/Math.max(heightPerWidth,1e-6));
  return Math.min(.98,horizontal,vertical);
}

canvas.addEventListener("pointerdown",event=>{
  if(!state.source)return;
  const point=pointerPosition(event),corner=nearestGridCorner(point);
  if(corner>=0){state.drag={type:"grid",index:corner};canvas.setPointerCapture(event.pointerId);requestDraw();return}
  if(!state.gridLocked||!state.design)return;
  const quad=brandQuadPixelsFor(canvas.width,canvas.height),handle=quad[2];
  if(Math.hypot(point.x-handle.x,point.y-handle.y)<=20){state.drag={type:"brand-scale"};canvas.setPointerCapture(event.pointerId);return}
  const uv=pointerToSurface(point);
  if(pointInUvBrand(uv)){
    state.drag={type:"brand-move",offsetU:uv.x-state.brand.u,offsetV:uv.y-state.brand.v};
    canvas.setPointerCapture(event.pointerId);
  }
});

canvas.addEventListener("pointermove",event=>{
  if(!state.drag)return;
  const point=pointerPosition(event);
  if(state.drag.type==="grid"){
    state.corners[state.drag.index]={x:Math.max(0,Math.min(1,point.x/canvas.width)),y:Math.max(0,Math.min(1,point.y/canvas.height))};
    requestDraw();return;
  }
  const uv=pointerToSurface(point);
  if(state.drag.type==="brand-move"){
    state.brand.u=uv.x-state.drag.offsetU;state.brand.v=uv.y-state.drag.offsetV;clampBrand();requestDraw();return;
  }
  if(state.drag.type==="brand-scale"){
    const desired=Math.max(Math.abs(uv.x-state.brand.u)*2,.05);
    state.brand.width=Math.min(desired,maxBrandWidthAtCurrentCenter());clampBrand();requestDraw();
  }
});

function stopDrag(event){
  if(!state.drag)return;
  state.drag=null;
  try{canvas.releasePointerCapture(event.pointerId)}catch(_){}
  requestDraw();
}
canvas.addEventListener("pointerup",stopDrag);
canvas.addEventListener("pointercancel",stopDrag);

function newExportCanvas(){
  const out=document.createElement("canvas");
  out.width=state.sourceSize.width;out.height=state.sourceSize.height;
  return out;
}

function downloadCanvas(target,name){
  target.toBlob(blob=>{
    const a=document.createElement("a");
    const url=URL.createObjectURL(blob);
    a.href=url;a.download=name;a.click();
    setTimeout(()=>URL.revokeObjectURL(url),1000);
  },"image/png");
}

function canvasDataUrl(target){ return target.toDataURL("image/png"); }

function exportCanvas(mode){
  const out=newExportCanvas();
  renderBrandTo(out,mode);
  return out;
}

function enableBrandActions(enabled){
  q("#exportComposite").disabled=!enabled;
  q("#exportLogoLayer").disabled=!enabled;
  q("#exportMask").disabled=!enabled;
  q("#processAI").disabled=!enabled;
  setAiStatus(enabled ? "Готово к обработке" : "Не готово");
}

q("#sourceFile").addEventListener("change",async event=>{
  const file=event.target.files[0];if(!file)return;
  setStatus("Загрузка исходника…");
  state.source=await loadImage(file);
  state.sourceSize={width:state.source.width,height:state.source.height};
  state.corners=defaultCorners();state.gridLocked=false;state.design=null;state.designPixels=null;state.brand={u:.5,v:.5,width:.45};
  q("#canvasWrap").classList.remove("empty");
  q("#resetGrid").disabled=false;q("#lockGrid").disabled=false;q("#showGrid").disabled=false;q("#fullscreenToggle").disabled=false;
  q("#designFile").disabled=true;q("#designLabel").classList.add("disabled");q("#resetBrand").disabled=true;
  enableBrandActions(false);
  setStep("#step1","done");setStep("#step2","active");setStep("#step3",null);setStep("#step4",null);
  q("#editorTitle").textContent="2. Установите сетку перспективы";
  q("#editorHint").textContent="Перетащите маленькие точки P1–P4 на реальные углы поверхности.";
  resizeCanvas();setStatus("2. Установите P1–P4");
});

q("#resetGrid").addEventListener("click",()=>{if(!state.source)return;state.corners=defaultCorners();requestDraw()});

q("#lockGrid").addEventListener("click",()=>{
  if(!state.source)return;
  state.gridLocked=!state.gridLocked;
  if(state.gridLocked){
    q("#lockGrid").textContent="Изменить сетку";
    q("#designFile").disabled=false;q("#designLabel").classList.remove("disabled");
    setStep("#step2","done");setStep("#step3",state.design?"done":"active");
    q("#editorTitle").textContent=state.design?"4. Разместите брендинг":"3. Загрузите файл брендинга";
    q("#editorHint").textContent=state.design?"Перемещайте логотип мышью. Квадратный маркер меняет масштаб.":"Сетка зафиксирована.";
    setStatus(state.design?"4. Разместите брендинг":"3. Загрузите брендинг");
  }else{
    q("#lockGrid").textContent="Зафиксировать";
    setStep("#step2","active");setStep("#step3",null);setStep("#step4",null);
    q("#editorTitle").textContent="2. Установите сетку перспективы";
    q("#editorHint").textContent="Скорректируйте точки и снова зафиксируйте сетку.";
    setStatus("2. Корректировка сетки");
  }
  requestDraw();
});

q("#designFile").addEventListener("change",async event=>{
  const file=event.target.files[0];if(!file||!state.gridLocked)return;
  setStatus("Загрузка брендинга…");
  state.design=await loadImage(file);prepareDesignPixels();state.brand={u:.5,v:.5,width:.45};clampBrand();
  q("#resetBrand").disabled=false;enableBrandActions(true);
  setStep("#step3","done");setStep("#step4","active");
  q("#editorTitle").textContent="4. Разместите брендинг";
  q("#editorHint").textContent="Перемещайте логотип мышью. Квадратный маркер в правом нижнем углу меняет масштаб.";
  setStatus("4. Разместите логотип");requestDraw();
});

q("#resetBrand").addEventListener("click",()=>{if(!state.design)return;state.brand={u:.5,v:.5,width:.45};clampBrand();requestDraw()});
q("#showGrid").addEventListener("change",event=>{state.showGrid=event.target.checked;requestDraw()});

q("#fullscreenToggle").addEventListener("click",async()=>{
  const wrap=q("#canvasWrap");
  try{
    if(!document.fullscreenElement)await wrap.requestFullscreen();
    else await document.exitFullscreen();
  }catch(error){alert("Полноэкранный режим недоступен: "+error.message)}
});
document.addEventListener("fullscreenchange",()=>{q("#fullscreenToggle").textContent=document.fullscreenElement?"Выйти из полноэкранного":"Во весь экран";setTimeout(resizeCanvas,50)});

q("#exportComposite").addEventListener("click",()=>downloadCanvas(exportCanvas("composite"),"brand-apply-composite.png"));
q("#exportLogoLayer").addEventListener("click",()=>downloadCanvas(exportCanvas("layer"),"brand-apply-logo-layer.png"));
q("#exportMask").addEventListener("click",()=>downloadCanvas(exportCanvas("mask"),"brand-apply-logo-mask.png"));

function nearestAspectRatio(width,height){
  const ratios=[["1:1",1],["16:9",16/9],["9:16",9/16],["4:3",4/3],["3:4",3/4],["3:2",3/2],["2:3",2/3],["4:5",4/5],["5:4",5/4]];
  const target=width/height;
  return ratios.reduce((best,current)=>Math.abs(current[1]-target)<Math.abs(best[1]-target)?current:best,ratios[0])[0];
}

function baseAiPrompt(){
  const material=q("#material").value;
  const application=q("#applicationMode").value;
  const extra=q("#aiPrompt").value.trim();
  return [
    "Reference 1 is the immutable master mockup photo.",
    "Reference 2 is the exact perspective-aligned brand layer on a transparent canvas.",
    "Reference 3 is the monochrome brand mask.",
    "Preserve the original camera, crop, object geometry, object proportions, background and composition.",
    "Preserve the exact logo identity, spelling, proportions, scale, position and perspective from Reference 2.",
    "Do not redesign, move, resize, rotate or reinterpret the branding.",
    "Only integrate the branding physically into the photographed surface.",
    "Material: "+material+". Application method: "+application+".",
    "Add only realistic local texture, lighting, shadow, highlight, reflection, relief or fold response required by that material.",
    extra
  ].filter(Boolean).join("\n");
}

function saveGateway(){
  const value=q("#gatewayUrl").value.trim().replace(/\/$/,"");
  localStorage.setItem("brandApplyGateway",value);
  setAiStatus(value?"Gateway сохранен":"Gateway не указан");
}

q("#saveGateway").addEventListener("click",saveGateway);

q("#processAI").addEventListener("click",async()=>{
  if(!state.source||!state.design||!state.gridLocked)return;
  const gateway=q("#gatewayUrl").value.trim().replace(/\/$/,"");
  if(!gateway){alert("Укажите URL OpenRouter Gateway.");q("#gatewayUrl").focus();return}

  q("#processAI").disabled=true;setAiStatus("Подготовка референсов…");
  try{
    const sourceCanvas=newExportCanvas();
    sourceCanvas.getContext("2d").drawImage(state.source,0,0,sourceCanvas.width,sourceCanvas.height);
    const layerCanvas=exportCanvas("layer");
    const maskCanvas=exportCanvas("mask");

    setAiStatus("OpenRouter обрабатывает изображение…");

    const response=await fetch(gateway+"/api/openrouter/image",{
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({
        model:q("#aiModel").value,
        prompt:baseAiPrompt(),
        quality:q("#quality").value,
        aspect_ratio:nearestAspectRatio(state.sourceSize.width,state.sourceSize.height),
        references:[
          canvasDataUrl(sourceCanvas),
          canvasDataUrl(layerCanvas),
          canvasDataUrl(maskCanvas)
        ]
      })
    });

    const payload=await response.json().catch(()=>({}));
    if(!response.ok)throw new Error(payload.error||payload.detail||("HTTP "+response.status));
    if(!payload.b64_json)throw new Error("OpenRouter не вернул изображение");

    const mediaType=payload.media_type||"image/png";
    state.aiResultUrl="data:"+mediaType+";base64,"+payload.b64_json;
    q("#aiResult").src=state.aiResultUrl;
    q(".ai-result-wrap").classList.add("has-result");
    q("#downloadAI").disabled=false;
    const cost=payload.usage&&payload.usage.cost!=null?" · $"+Number(payload.usage.cost).toFixed(4):"";
    setAiStatus("Готово"+cost);
  }catch(error){
    console.error(error);setAiStatus("Ошибка");alert("OpenRouter: "+error.message);
  }finally{
    q("#processAI").disabled=false;
  }
});

q("#downloadAI").addEventListener("click",()=>{
  if(!state.aiResultUrl)return;
  const a=document.createElement("a");a.href=state.aiResultUrl;a.download="brand-apply-ai-result.png";a.click();
});

const query=new URLSearchParams(location.search);
const gatewayFromQuery=(query.get("api")||"").trim().replace(/\/$/,"");
if(gatewayFromQuery)localStorage.setItem("brandApplyGateway",gatewayFromQuery);
q("#gatewayUrl").value=gatewayFromQuery||localStorage.getItem("brandApplyGateway")||"";

window.addEventListener("resize",resizeCanvas);
enableBrandActions(false);
