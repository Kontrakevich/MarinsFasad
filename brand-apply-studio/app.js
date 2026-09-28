const q=s=>document.querySelector(s);
const canvas=q("#canvas"),ctx=canvas.getContext("2d",{willReadFrequently:true});
const state={
  source:null,design:null,corners:[],drag:-1,rows:6,cols:8,
  scale:0.55,opacity:1
};

function setStatus(text){q("#status").textContent=text}

function loadImage(file){
  return new Promise((resolve,reject)=>{
    const img=new Image();
    img.onload=()=>{URL.revokeObjectURL(img.src);resolve(img)};
    img.onerror=reject;
    img.src=URL.createObjectURL(file);
  });
}

function defaultCorners(){
  const w=state.source.width,h=state.source.height;
  const x=w*.15,y=h*.15;
  return [{x,y},{x:w-x,y},{x:w-x,y:h-y},{x,y:h-y}];
}

function interp(a,b,t){return{x:a.x+(b.x-a.x)*t,y:a.y+(b.y-a.y)*t}}
function bilinear(u,v){
  const [tl,tr,br,bl]=state.corners;
  return interp(interp(tl,tr,u),interp(bl,br,u),v)
}

function resizeStage(){
  if(!state.source)return;
  canvas.width=state.source.width;canvas.height=state.source.height;
  const wrap=q("#canvasWrap");
  const fit=Math.min(1,Math.max(320,wrap.clientWidth-2)/canvas.width);
  canvas.style.width=Math.round(canvas.width*fit)+"px";
  canvas.style.height=Math.round(canvas.height*fit)+"px";
  q("#stage").style.width=Math.round(canvas.width*fit)+"px";
  q("#stage").style.height=Math.round(canvas.height*fit)+"px";
  draw();
}

function line(a,b){
  ctx.beginPath();ctx.moveTo(a.x,a.y);ctx.lineTo(b.x,b.y);ctx.stroke();
}

function drawGrid(){
  if(state.corners.length!==4)return;
  ctx.save();
  ctx.strokeStyle="#00d4c7";
  ctx.lineWidth=Math.max(2,canvas.width/1000);
  ctx.setLineDash([Math.max(10,canvas.width/180),Math.max(7,canvas.width/260)]);
  for(let c=0;c<=state.cols;c++){
    const u=c/state.cols;let p=bilinear(u,0);
    for(let s=1;s<=40;s++){const n=bilinear(u,s/40);line(p,n);p=n}
  }
  for(let r=0;r<=state.rows;r++){
    const v=r/state.rows;let p=bilinear(0,v);
    for(let s=1;s<=40;s++){const n=bilinear(s/40,v);line(p,n);p=n}
  }
  ctx.strokeStyle="#fff";ctx.lineWidth=Math.max(3,canvas.width/600);
  ctx.setLineDash([Math.max(16,canvas.width/120),Math.max(10,canvas.width/180)]);
  ctx.beginPath();ctx.moveTo(state.corners[0].x,state.corners[0].y);
  state.corners.slice(1).forEach(p=>ctx.lineTo(p.x,p.y));ctx.closePath();ctx.stroke();
  ctx.setLineDash([]);
  const radius=Math.max(12,canvas.width/130);
  state.corners.forEach((p,i)=>{
    ctx.beginPath();ctx.arc(p.x,p.y,radius,0,Math.PI*2);
    ctx.fillStyle="#008a90";ctx.fill();ctx.strokeStyle="#fff";ctx.lineWidth=Math.max(3,canvas.width/700);ctx.stroke();
    ctx.fillStyle="#fff";ctx.font=`${Math.max(18,canvas.width/65)}px Arial`;ctx.textAlign="center";ctx.textBaseline="middle";ctx.fillText(String(i+1),p.x,p.y)
  });
  ctx.restore();
}

function solve(A,b){
  const n=b.length;
  const M=A.map((row,i)=>[...row,b[i]]);
  for(let col=0;col<n;col++){
    let pivot=col;
    for(let r=col+1;r<n;r++)if(Math.abs(M[r][col])>Math.abs(M[pivot][col]))pivot=r;
    [M[col],M[pivot]]=[M[pivot],M[col]];
    const d=M[col][col];if(Math.abs(d)<1e-12)throw new Error("Degenerate homography");
    for(let c=col;c<=n;c++)M[col][c]/=d;
    for(let r=0;r<n;r++){
      if(r===col)continue;const f=M[r][col];
      for(let c=col;c<=n;c++)M[r][c]-=f*M[col][c];
    }
  }
  return M.map(row=>row[n]);
}

function homography(src,dst){
  const A=[],b=[];
  for(let i=0;i<4;i++){
    const {x,y}=src[i],X=dst[i].x,Y=dst[i].y;
    A.push([x,y,1,0,0,0,-x*X,-y*X]);b.push(X);
    A.push([0,0,0,x,y,1,-x*Y,-y*Y]);b.push(Y);
  }
  const h=solve(A,b);
  return [[h[0],h[1],h[2]],[h[3],h[4],h[5]],[h[6],h[7],1]];
}

function invert3(m){
  const a=m[0][0],b=m[0][1],c=m[0][2],d=m[1][0],e=m[1][1],f=m[1][2],g=m[2][0],h=m[2][1],i=m[2][2];
  const A=e*i-f*h,B=-(d*i-f*g),C=d*h-e*g,D=-(b*i-c*h),E=a*i-c*g,F=-(a*h-b*g),G=b*f-c*e,H=-(a*f-c*d),I=a*e-b*d;
  const det=a*A+b*B+c*C;if(Math.abs(det)<1e-12)throw new Error("Singular homography");
  return [[A/det,D/det,G/det],[B/det,E/det,H/det],[C/det,F/det,I/det]];
}

function applyH(H,x,y){
  const z=H[2][0]*x+H[2][1]*y+H[2][2];
  return {x:(H[0][0]*x+H[0][1]*y+H[0][2])/z,y:(H[1][0]*x+H[1][1]*y+H[1][2])/z};
}

function surfaceAspect(){
  const [tl,tr,br,bl]=state.corners;
  const top=Math.hypot(tr.x-tl.x,tr.y-tl.y);
  const bottom=Math.hypot(br.x-bl.x,br.y-bl.y);
  const left=Math.hypot(bl.x-tl.x,bl.y-tl.y);
  const right=Math.hypot(br.x-tr.x,br.y-tr.y);
  return Math.max(1e-6,(top+bottom)/(left+right));
}

function designTargetQuad(){
  const s=state.scale;
  const designAspect=state.design ? state.design.width/state.design.height : 1;
  const planeAspect=surfaceAspect();
  const ratio=designAspect/planeAspect;

  let uSize=s,vSize=s;
  if(ratio>=1){uSize=s;vSize=s/ratio}
  else{uSize=s*ratio;vSize=s}

  const u0=.5-uSize/2,u1=.5+uSize/2;
  const v0=.5-vSize/2,v1=.5+vSize/2;

  return [bilinear(u0,v0),bilinear(u1,v0),bilinear(u1,v1),bilinear(u0,v1)];
}

function renderBrandTo(target,maskOnly=false){
  const out=target.getContext("2d",{willReadFrequently:true});
  target.width=state.source.width;target.height=state.source.height;
  if(maskOnly){out.fillStyle="#000";out.fillRect(0,0,target.width,target.height)}
  else out.drawImage(state.source,0,0);

  if(!state.design||state.corners.length!==4)return;

  const off=document.createElement("canvas");
  off.width=state.design.width;off.height=state.design.height;
  const octx=off.getContext("2d",{willReadFrequently:true});octx.drawImage(state.design,0,0);
  const srcData=octx.getImageData(0,0,off.width,off.height);
  const dstQuad=designTargetQuad();
  const srcQuad=[{x:0,y:0},{x:off.width-1,y:0},{x:off.width-1,y:off.height-1},{x:0,y:off.height-1}];
  const H=homography(srcQuad,dstQuad),Hi=invert3(H);
  const xs=dstQuad.map(p=>p.x),ys=dstQuad.map(p=>p.y);
  const minX=Math.max(0,Math.floor(Math.min(...xs))),maxX=Math.min(target.width-1,Math.ceil(Math.max(...xs)));
  const minY=Math.max(0,Math.floor(Math.min(...ys))),maxY=Math.min(target.height-1,Math.ceil(Math.max(...ys)));
  const base=out.getImageData(minX,minY,maxX-minX+1,maxY-minY+1);
  const bd=base.data,sd=srcData.data,sw=off.width,sh=off.height;

  for(let y=minY;y<=maxY;y++){
    for(let x=minX;x<=maxX;x++){
      const p=applyH(Hi,x,y);
      if(p.x<0||p.y<0||p.x>sw-1||p.y>sh-1)continue;
      const sx=Math.max(0,Math.min(sw-1,Math.round(p.x))),sy=Math.max(0,Math.min(sh-1,Math.round(p.y)));
      const si=(sy*sw+sx)*4;
      let a=(sd[si+3]/255)*state.opacity;if(a<=0)continue;
      const di=((y-minY)*(maxX-minX+1)+(x-minX))*4;
      if(maskOnly){
        const v=Math.round(255*a);bd[di]=v;bd[di+1]=v;bd[di+2]=v;bd[di+3]=255;
      }else{
        bd[di]=sd[si]*a+bd[di]*(1-a);
        bd[di+1]=sd[si+1]*a+bd[di+1]*(1-a);
        bd[di+2]=sd[si+2]*a+bd[di+2]*(1-a);
        bd[di+3]=255;
      }
    }
  }
  out.putImageData(base,minX,minY);
  return H;
}

function renderOutputs(){
  if(!state.source)return;
  const m=q("#masterPreview"),g=q("#guidePreview"),b=q("#brandPreview"),mask=q("#maskPreview");
  [m,g,b,mask].forEach(c=>{c.width=state.source.width;c.height=state.source.height});
  m.getContext("2d").drawImage(state.source,0,0);
  g.getContext("2d").drawImage(state.source,0,0);
  const old=ctx; // guide is redrawn from the main canvas snapshot for exact same geometry
  drawGuideToCanvas(g);
  let H=null;
  if(state.design){H=renderBrandTo(b,false);renderBrandTo(mask,true)}
  else{b.getContext("2d").drawImage(state.source,0,0);mask.getContext("2d").fillStyle="#000";mask.getContext("2d").fillRect(0,0,mask.width,mask.height)}
  updateScene(H);
}

function drawGuideToCanvas(target){
  const c=target.getContext("2d");
  c.drawImage(state.source,0,0);
  c.save();c.strokeStyle="#00d4c7";c.lineWidth=Math.max(2,target.width/1000);c.setLineDash([Math.max(10,target.width/180),Math.max(7,target.width/260)]);
  const L=(a,b)=>{c.beginPath();c.moveTo(a.x,a.y);c.lineTo(b.x,b.y);c.stroke()};
  for(let col=0;col<=state.cols;col++){const u=col/state.cols;let p=bilinear(u,0);for(let s=1;s<=40;s++){const n=bilinear(u,s/40);L(p,n);p=n}}
  for(let row=0;row<=state.rows;row++){const v=row/state.rows;let p=bilinear(0,v);for(let s=1;s<=40;s++){const n=bilinear(s/40,v);L(p,n);p=n}}
  c.strokeStyle="#fff";c.lineWidth=Math.max(3,target.width/600);c.setLineDash([Math.max(16,target.width/120),Math.max(10,target.width/180)]);
  c.beginPath();c.moveTo(state.corners[0].x,state.corners[0].y);state.corners.slice(1).forEach(p=>c.lineTo(p.x,p.y));c.closePath();c.stroke();c.restore();
}

function updateScene(H){
  const scene={
    version:"0.1-browser",
    master:state.source?{width:state.source.width,height:state.source.height}:null,
    point_order:["top_left","top_right","bottom_right","bottom_left"],
    quad:state.corners.map(p=>({x:+p.x.toFixed(2),y:+p.y.toFixed(2)})),
    grid:{columns:state.cols,rows:state.rows},
    brand:{scale:+state.scale.toFixed(2),opacity:+state.opacity.toFixed(2)},
    homography:H?H.map(r=>r.map(v=>+v.toFixed(8))):null
  };
  q("#sceneJson").textContent=JSON.stringify(scene,null,2)
}

function draw(){
  if(!state.source)return;
  ctx.clearRect(0,0,canvas.width,canvas.height);ctx.drawImage(state.source,0,0);drawGrid();renderOutputs()
}

function eventPos(e){
  const r=canvas.getBoundingClientRect();
  return{x:(e.clientX-r.left)*canvas.width/r.width,y:(e.clientY-r.top)*canvas.height/r.height}
}
function nearestCorner(p){
  const r=canvas.getBoundingClientRect(),hit=28*canvas.width/r.width;
  let idx=-1,min=Infinity;
  state.corners.forEach((c,i)=>{const d=Math.hypot(p.x-c.x,p.y-c.y);if(d<=hit&&d<min){idx=i;min=d}});
  return idx
}

canvas.addEventListener("pointerdown",e=>{
  const i=nearestCorner(eventPos(e));if(i<0)return;state.drag=i;canvas.setPointerCapture(e.pointerId)
});
canvas.addEventListener("pointermove",e=>{
  if(state.drag<0)return;const p=eventPos(e);
  state.corners[state.drag]={x:Math.max(0,Math.min(canvas.width,p.x)),y:Math.max(0,Math.min(canvas.height,p.y))};draw()
});
function endDrag(e){if(state.drag<0)return;state.drag=-1;try{canvas.releasePointerCapture(e.pointerId)}catch(_){}}
canvas.addEventListener("pointerup",endDrag);canvas.addEventListener("pointercancel",endDrag);

q("#sourceFile").addEventListener("change",async e=>{
  const file=e.target.files[0];if(!file)return;
  setStatus("Загрузка исходника…");state.source=await loadImage(file);state.corners=defaultCorners();
  q("#sourceSize").textContent=`${state.source.width} × ${state.source.height}`;resizeStage();setStatus("Совместите P1–P4 с поверхностью")
});
q("#designFile").addEventListener("change",async e=>{
  const file=e.target.files[0];if(!file)return;state.design=await loadImage(file);draw();setStatus("Брендинг проецируется по заданной геометрии")
});
q("#resetGrid").addEventListener("click",()=>{if(!state.source)return;state.corners=defaultCorners();draw()});
q("#brandScale").addEventListener("input",e=>{state.scale=+e.target.value/100;draw()});
q("#brandOpacity").addEventListener("input",e=>{state.opacity=+e.target.value/100;draw()});

function downloadCanvas(c,name){
  c.toBlob(blob=>{const a=document.createElement("a");a.href=URL.createObjectURL(blob);a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000)},"image/png")
}
q("#exportGuide").addEventListener("click",()=>{if(!state.source)return;downloadCanvas(q("#guidePreview"),"brand-apply-guide.png")});
q("#exportComposite").addEventListener("click",()=>{if(!state.source||!state.design)return;downloadCanvas(q("#brandPreview"),"brand-apply-technical-preview.png")});
window.addEventListener("resize",resizeStage);
updateScene(null);
