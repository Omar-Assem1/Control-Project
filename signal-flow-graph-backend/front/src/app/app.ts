import {
  Component, signal, computed, viewChild,
  ElementRef, afterNextRender, OnDestroy,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { SfgService } from './services/sfg.service';
import { GraphInput, GraphAnalysisResult, ForwardPath, Loop, NonTouchingGroup, DeltaK } from './models/sfg.models';

export type DrawMode = 'idle' | 'addNode' | 'addEdge' | 'delete';

export interface CanvasNode { id: number; label: string; x: number; y: number; }
export interface CanvasEdge { id: number; from: number; to: number; gain: string; }

const NR = 24; // node radius
const HR = 30; // hit radius

@Component({
  selector: 'app-root', standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './app.html', styleUrl: './app.css',
})
export class App implements OnDestroy {
  canvasRef = viewChild<ElementRef<HTMLCanvasElement>>('sfgCanvas');

  // ── draw state ──────────────────────────────────────────────────────────
  mode           = signal<DrawMode>('idle');
  canvasNodes    = signal<CanvasNode[]>([]);
  canvasEdges    = signal<CanvasEdge[]>([]);
  hoveredNodeId  = signal<number | null>(null);
  selectedNodeId = signal<number | null>(null);   // first node in edge mode
  pendingEdge    = signal<{ from: CanvasNode; to: CanvasNode } | null>(null);
  pendingGain    = '';
  mouseX = 0; mouseY = 0;                          // live mouse for preview
  gainPromptPos  = signal<{ x: number; y: number }>({ x: 0, y: 0 });

  // ── analysis state ──────────────────────────────────────────────────────
  sourceId    = signal<number | null>(null);
  sinkId      = signal<number | null>(null);
  loading     = signal(false);
  errorMsg    = signal<string | null>(null);
  result      = signal<GraphAnalysisResult | null>(null);
  activeTab   = signal<'paths'|'loops'|'delta'|'result'>('paths');
  showJson    = signal(false);

  // ── derived ─────────────────────────────────────────────────────────────
  forwardPaths  = computed(() => this.result()?.forward_paths ?? []);
  loops         = computed(() => this.result()?.loops ?? []);
  nonTouching   = computed(() => this.result()?.non_touching_groups ?? []);
  deltaK        = computed(() => this.result()?.delta_k ?? []);
  jsonPreview   = computed(() => this.result() ? JSON.stringify(this.result(), null, 2) : '');
  sourceNode    = computed(() => this.canvasNodes().find(n => n.id === this.sourceId()) ?? null);
  sinkNode      = computed(() => this.canvasNodes().find(n => n.id === this.sinkId()) ?? null);

  private _nc = 0; private _ec = 0;
  private _history: { nodes: CanvasNode[]; edges: CanvasEdge[] }[] = [];

  constructor(private sfg: SfgService) {
    afterNextRender(() => { this.initDefault(); });
  }
  ngOnDestroy() {}

  // ── init ────────────────────────────────────────────────────────────────
  initDefault() {
    const el = this.canvasRef()?.nativeElement; if (!el) return;
    const W = el.getBoundingClientRect().width;
    const H = el.getBoundingClientRect().height;
    const cy = H / 2; const step = (W - 120) / 5;
    const nodes: CanvasNode[] = [];
    for (let i = 0; i < 6; i++) nodes.push({ id: ++this._nc, label: `x${this._nc}`, x: 60 + i * step, y: cy });
    this.canvasNodes.set(nodes);
    const ev = (f: number, t: number, g: string): CanvasEdge => ({ id: ++this._ec, from: f, to: t, gain: g });
    this.canvasEdges.set([
      ev(1,2,'a'), ev(2,3,'b'), ev(3,4,'c'), ev(4,5,'d'), ev(5,6,'e'),
      ev(4,3,'f'), ev(2,5,'g'),
    ]);
    this.sourceId.set(1); this.sinkId.set(6);
    this.redraw();
  }

  // ── mode control ────────────────────────────────────────────────────────
  setMode(m: DrawMode) {
    if (this.mode() === m) { this.mode.set('idle'); }
    else { this.mode.set(m); }
    this.selectedNodeId.set(null);
    this.pendingEdge.set(null);
    this.redraw();
  }

  // ── canvas events ────────────────────────────────────────────────────────
  onCanvasClick(ev: MouseEvent) {
    const pt = this.toLogical(ev);
    const hit = this.hitNode(pt.x, pt.y);

    if (this.mode() === 'addNode') {
      if (hit) return; // don't place on existing node
      this.pushHistory();
      this.canvasNodes.update(ns => [...ns, { id: ++this._nc, label: `x${this._nc}`, x: pt.x, y: pt.y }]);
      this.redraw(); return;
    }

    if (this.mode() === 'addEdge') {
      if (!hit) { this.selectedNodeId.set(null); this.redraw(); return; }
      const sel = this.selectedNodeId();
      if (!sel) { this.selectedNodeId.set(hit.id); this.redraw(); return; }
      if (hit.id === sel) return; // same node
      const fromNode = this.canvasNodes().find(n => n.id === sel)!;
      const toNode = hit;
      const mid = { x: (fromNode.x + toNode.x) / 2, y: (fromNode.y + toNode.y) / 2 };
      this.pendingEdge.set({ from: fromNode, to: toNode });
      this.gainPromptPos.set({ x: mid.x - 70, y: mid.y - 50 });
      this.pendingGain = '';
      this.selectedNodeId.set(null);
      this.redraw(); return;
    }

    if (this.mode() === 'delete') {
      if (hit) {
        this.pushHistory();
        this.canvasNodes.update(ns => ns.filter(n => n.id !== hit.id));
        this.canvasEdges.update(es => es.filter(e => e.from !== hit.id && e.to !== hit.id));
        if (this.sourceId() === hit.id) this.sourceId.set(null);
        if (this.sinkId() === hit.id) this.sinkId.set(null);
        this.redraw(); return;
      }
      const edgeHit = this.hitEdge(pt.x, pt.y);
      if (edgeHit) {
        this.pushHistory();
        this.canvasEdges.update(es => es.filter(e => e.id !== edgeHit.id));
        this.redraw();
      }
    }
  }

  onMouseMove(ev: MouseEvent) {
    const pt = this.toLogical(ev);
    this.mouseX = pt.x; this.mouseY = pt.y;
    const hit = this.hitNode(pt.x, pt.y);
    this.hoveredNodeId.set(hit?.id ?? null);
    this.redraw();
  }

  onMouseLeave() { this.hoveredNodeId.set(null); this.redraw(); }

  confirmEdge() {
    const pe = this.pendingEdge(); if (!pe) return;
    const gain = this.pendingGain.trim() || '1';
    this.pushHistory();
    this.canvasEdges.update(es => [...es, { id: ++this._ec, from: pe.from.id, to: pe.to.id, gain }]);
    this.pendingEdge.set(null);
    this.pendingGain = '';
    this.redraw();
  }

  cancelEdge() {
    this.pendingEdge.set(null);
    this.selectedNodeId.set(null);
    this.redraw();
  }

  updateEdgeGain(id: number, val: string) {
    this.canvasEdges.update(es => es.map(e => e.id === id ? { ...e, gain: val } : e));
  }

  removeEdge(id: number) { this.pushHistory(); this.canvasEdges.update(es => es.filter(e => e.id !== id)); this.redraw(); }
  removeNode(id: number) {
    this.pushHistory();
    this.canvasNodes.update(ns => ns.filter(n => n.id !== id));
    this.canvasEdges.update(es => es.filter(e => e.from !== id && e.to !== id));
    if (this.sourceId() === id) this.sourceId.set(null);
    if (this.sinkId() === id) this.sinkId.set(null);
    this.redraw();
  }

  undoLast() {
    const prev = this._history.pop(); if (!prev) return;
    this.canvasNodes.set(prev.nodes); this.canvasEdges.set(prev.edges);
    this.redraw();
  }

  clearCanvas() {
    this.pushHistory();
    this.canvasNodes.set([]); this.canvasEdges.set([]);
    this.sourceId.set(null); this.sinkId.set(null);
    this.result.set(null);
    this.redraw();
  }

  // ── analysis ─────────────────────────────────────────────────────────────
  analyze() {
    this.errorMsg.set(null);
    const nodes = this.canvasNodes(); const edges = this.canvasEdges();
    if (nodes.length < 2) { this.errorMsg.set('Add at least 2 nodes.'); return; }
    if (!this.sourceId()) { this.errorMsg.set('Select a source node.'); return; }
    if (!this.sinkId())   { this.errorMsg.set('Select a sink node.'); return; }
    if (this.sourceId() === this.sinkId()) { this.errorMsg.set('Source and sink must differ.'); return; }
    if (edges.length === 0) { this.errorMsg.set('Add at least one edge.'); return; }

    const cast = (v: string) => { const n = Number(v); return isNaN(n) ? v : n; };
    const labelOf = (id: number) => nodes.find(n => n.id === id)!.label;

    const payload: GraphInput = {
      nodes: nodes.map(n => cast(n.label)),
      branches: edges.map(e => ({ from: cast(labelOf(e.from)), to: cast(labelOf(e.to)), gain: e.gain })),
      source: cast(labelOf(this.sourceId()!)),
      sink:   cast(labelOf(this.sinkId()!)),
    };

    this.loading.set(true);
    this.sfg.analyze(payload).subscribe({
      next: (res) => { this.result.set(res); this.loading.set(false); setTimeout(() => this.renderResult(res), 60); },
      error: (err: Error) => { this.errorMsg.set(err.message); this.loading.set(false); },
    });
  }

  resetAll() {
    this._nc = 0; this._ec = 0; this._history = [];
    this.canvasNodes.set([]); this.canvasEdges.set([]);
    this.sourceId.set(null); this.sinkId.set(null);
    this.result.set(null); this.errorMsg.set(null);
    this.mode.set('idle'); this.selectedNodeId.set(null); this.pendingEdge.set(null);
    setTimeout(() => this.initDefault(), 20);
  }

  setTab(t: 'paths'|'loops'|'delta'|'result') { this.activeTab.set(t); }
  loopLabel(idx: number[]) { return idx.map(i => 'L' + i).join(', '); }

  nodeLabelById(id: number) { return this.canvasNodes().find(n => n.id === id)?.label ?? '?'; }

  // ── helpers ───────────────────────────────────────────────────────────────
  private pushHistory() {
    this._history.push({ nodes: [...this.canvasNodes()], edges: [...this.canvasEdges()] });
    if (this._history.length > 40) this._history.shift();
  }

  private toLogical(ev: MouseEvent) {
    const rect = this.canvasRef()!.nativeElement.getBoundingClientRect();
    return { x: ev.clientX - rect.left, y: ev.clientY - rect.top };
  }

  private hitNode(x: number, y: number): CanvasNode | null {
    return this.canvasNodes().find(n => Math.hypot(n.x - x, n.y - y) <= HR) ?? null;
  }

  private hitEdge(x: number, y: number): CanvasEdge | null {
    const nodes = this.canvasNodes();
    const nodePos = (id: number) => nodes.find(n => n.id === id);
    for (const e of this.canvasEdges()) {
      const a = nodePos(e.from); const b = nodePos(e.to); if (!a || !b) continue;
      const isCurved = this.isCurved(e);
      let mx: number, my: number;
      if (isCurved) {
        const cp = this.curveCtrl(a, b);
        mx = (a.x + 2*cp.x + b.x)/4; my = (a.y + 2*cp.y + b.y)/4;
      } else {
        mx = (a.x + b.x)/2; my = (a.y + b.y)/2;
      }
      if (Math.hypot(mx - x, my - y) < 16) return e;
    }
    return null;
  }

  private isCurved(e: CanvasEdge): boolean {
    return this.canvasEdges().some(o => o.id !== e.id && o.from === e.to && o.to === e.from);
  }

  private curveCtrl(a: CanvasNode, b: CanvasNode) {
    const mx = (a.x + b.x)/2, my = (a.y + b.y)/2;
    const dx = b.x - a.x, dy = b.y - a.y;
    const len = Math.hypot(dx, dy) || 1;
    return { x: mx - (dy/len)*45, y: my + (dx/len)*45 };
  }

  // ── rendering ─────────────────────────────────────────────────────────────
  private getCtx(): { ctx: CanvasRenderingContext2D; W: number; H: number } | null {
    const el = this.canvasRef()?.nativeElement; if (!el) return null;
    const dpr = window.devicePixelRatio || 1;
    const rect = el.getBoundingClientRect();
    el.width = rect.width * dpr; el.height = rect.height * dpr;
    const ctx = el.getContext('2d')!; ctx.scale(dpr, dpr);
    return { ctx, W: rect.width, H: rect.height };
  }

  redraw() {
    if (this.result()) return; // don't overwrite result view
    const r = this.getCtx(); if (!r) return;
    const { ctx, W, H } = r;
    this.drawBg(ctx, W, H);

    const nodes = this.canvasNodes();
    const edges = this.canvasEdges();
    const selId  = this.selectedNodeId();
    const hovId  = this.hoveredNodeId();
    const srcId  = this.sourceId();
    const snkId  = this.sinkId();

    // edges
    for (const e of edges) {
      const a = nodes.find(n => n.id === e.from); const b = nodes.find(n => n.id === e.to);
      if (!a || !b) continue;
      const curved = this.isCurved(e);
      if (a.id === b.id) { this.drawSelfLoop(ctx, a.x, a.y, e.gain); }
      else if (curved) {
        const cp = this.curveCtrl(a, b);
        this.drawCurvedEdge(ctx, a.x, a.y, b.x, b.y, cp.x, cp.y, e.gain, '#6366f1');
      } else {
        this.drawStraightEdge(ctx, a.x, a.y, b.x, b.y, e.gain, '#6366f1');
      }
    }

    // edge preview
    if (this.mode() === 'addEdge' && selId !== null) {
      const selNode = nodes.find(n => n.id === selId);
      if (selNode) {
        ctx.save();
        ctx.strokeStyle = 'rgba(99,102,241,0.5)'; ctx.lineWidth = 1.5;
        ctx.setLineDash([5, 4]);
        ctx.beginPath(); ctx.moveTo(selNode.x, selNode.y);
        ctx.lineTo(this.mouseX, this.mouseY); ctx.stroke();
        ctx.restore();
      }
    }

    // nodes
    for (const n of nodes) {
      const isSrc = n.id === srcId; const isSnk = n.id === snkId;
      const isSel = n.id === selId; const isHov = n.id === hovId;
      const color = isSrc ? '#10b981' : isSnk ? '#f97316' : isSel ? '#a78bfa' : '#6366f1';
      const glow  = isSrc ? '#10b981' : isSnk ? '#f97316' : isSel ? '#a78bfa' : '#6366f1';
      ctx.save();
      ctx.shadowBlur = isHov || isSel ? 20 : 10; ctx.shadowColor = glow;
      const g = ctx.createRadialGradient(n.x-5, n.y-5, 2, n.x, n.y, NR);
      g.addColorStop(0, lighten(color, 30)); g.addColorStop(1, color);
      ctx.beginPath(); ctx.arc(n.x, n.y, NR, 0, Math.PI*2);
      ctx.fillStyle = g; ctx.fill();
      ctx.strokeStyle = color + '99'; ctx.lineWidth = 1.5; ctx.shadowBlur = 0; ctx.stroke();
      ctx.fillStyle = '#fff'; ctx.font = '600 12px Inter,sans-serif';
      ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
      ctx.fillText(n.label, n.x, n.y);
      if (isSrc || isSnk) {
        ctx.font = '500 9px Inter,sans-serif';
        ctx.fillStyle = color;
        ctx.fillText(isSrc ? 'IN' : 'OUT', n.x, n.y + NR + 10);
      }
      ctx.restore();
    }
  }

  private drawBg(ctx: CanvasRenderingContext2D, W: number, H: number) {
    ctx.fillStyle = '#0f1121'; ctx.fillRect(0, 0, W, H);
    ctx.fillStyle = 'rgba(99,102,241,0.08)';
    for (let x = 30; x < W; x += 30) for (let y = 30; y < H; y += 30) {
      ctx.beginPath(); ctx.arc(x, y, 1.2, 0, Math.PI*2); ctx.fill();
    }
  }

  private drawStraightEdge(ctx: CanvasRenderingContext2D, x1: number, y1: number, x2: number, y2: number, gain: string, color: string) {
    const angle = Math.atan2(y2-y1, x2-x1);
    const ex = x2 - Math.cos(angle)*NR; const ey = y2 - Math.sin(angle)*NR;
    const sx = x1 + Math.cos(angle)*NR; const sy = y1 + Math.sin(angle)*NR;
    ctx.save();
    ctx.strokeStyle = color; ctx.lineWidth = 1.8;
    ctx.shadowBlur = 6; ctx.shadowColor = color;
    ctx.beginPath(); ctx.moveTo(sx, sy); ctx.lineTo(ex, ey); ctx.stroke();
    ctx.shadowBlur = 0;
    drawArrow(ctx, sx, sy, ex, ey, color);
    drawGainLabel(ctx, (sx+ex)/2, (sy+ey)/2, gain, color);
    ctx.restore();
  }

  private drawCurvedEdge(ctx: CanvasRenderingContext2D, x1: number, y1: number, x2: number, y2: number, cpx: number, cpy: number, gain: string, color: string) {
    const angle1 = Math.atan2(y1-cpy, x1-cpx);
    const angle2 = Math.atan2(y2-cpy, x2-cpx);
    const sx = x1 - Math.cos(angle1)*NR; const sy = y1 - Math.sin(angle1)*NR;
    const ex = x2 - Math.cos(angle2)*NR; const ey = y2 - Math.sin(angle2)*NR;
    ctx.save();
    ctx.strokeStyle = color; ctx.lineWidth = 1.8;
    ctx.shadowBlur = 6; ctx.shadowColor = color;
    ctx.beginPath(); ctx.moveTo(sx, sy); ctx.quadraticCurveTo(cpx, cpy, ex, ey); ctx.stroke();
    ctx.shadowBlur = 0;
    drawArrow(ctx, cpx, cpy, ex, ey, color);
    const mx = (sx + 2*cpx + ex)/4; const my = (sy + 2*cpy + ey)/4;
    drawGainLabel(ctx, mx, my, gain, color);
    ctx.restore();
  }

  private drawSelfLoop(ctx: CanvasRenderingContext2D, x: number, y: number, gain: string) {
    ctx.save();
    ctx.strokeStyle = '#f97316'; ctx.lineWidth = 1.8;
    ctx.shadowBlur = 6; ctx.shadowColor = '#f97316';
    ctx.beginPath(); ctx.ellipse(x, y - NR - 12, 14, 10, 0, 0, Math.PI*2); ctx.stroke();
    ctx.shadowBlur = 0;
    drawGainLabel(ctx, x, y - NR - 26, gain, '#f97316');
    ctx.restore();
  }

  renderResult(res: GraphAnalysisResult) {
    const r = this.getCtx(); if (!r) return;
    const { ctx, W, H } = r;
    const layout = res.layout;
    if (!layout?.nodes?.length) return;
    let minX=Infinity, maxX=-Infinity, minY=Infinity, maxY=-Infinity;
    for (const n of layout.nodes) { minX=Math.min(minX,n.x); maxX=Math.max(maxX,n.x); minY=Math.min(minY,n.y); maxY=Math.max(maxY,n.y); }
    const pad=80;
    const sx = maxX===minX ? 1 : (W-pad*2)/(maxX-minX);
    const sy = maxY===minY ? 1 : (H-pad*2)/(maxY-minY);
    const sc = Math.min(sx,sy);
    const ox = (W-(maxX-minX)*sc)/2 - minX*sc;
    const oy = (H-(maxY-minY)*sc)/2 - minY*sc;
    const tx = (x:number) => x*sc+ox; const ty = (y:number) => y*sc+oy;

    this.drawBg(ctx, W, H);

    const pos: Record<string, {x:number;y:number;label:string}> = {};
    for (const n of layout.nodes) pos[String(n.id)] = { x:tx(n.x), y:ty(n.y), label:n.label };

    for (const e of layout.edges) {
      const a = pos[String(e.from)]; const b = pos[String(e.to)]; if (!a||!b) continue;
      const col = e.is_back_edge ? '#f97316' : '#6366f1';
      if (e.is_self_loop) { this.drawSelfLoop(ctx, a.x, a.y, e.gain); }
      else if (e.control_x !== null && e.control_y !== null) {
        this.drawCurvedEdge(ctx, a.x, a.y, b.x, b.y, tx(e.control_x!), ty(e.control_y!), e.gain, col);
      } else { this.drawStraightEdge(ctx, a.x, a.y, b.x, b.y, e.gain, col); }
    }
    for (const n of layout.nodes) {
      const p = pos[String(n.id)]; if (!p) continue;
      const isSrc = String(n.id)===String(res.graph_summary.source);
      const isSnk = String(n.id)===String(res.graph_summary.sink);
      const color = isSrc ? '#10b981' : isSnk ? '#f97316' : '#6366f1';
      ctx.save();
      ctx.shadowBlur = 14; ctx.shadowColor = color;
      const g = ctx.createRadialGradient(p.x-5, p.y-5, 2, p.x, p.y, NR);
      g.addColorStop(0, lighten(color,30)); g.addColorStop(1, color);
      ctx.beginPath(); ctx.arc(p.x, p.y, NR, 0, Math.PI*2);
      ctx.fillStyle = g; ctx.fill();
      ctx.strokeStyle = color+'99'; ctx.lineWidth=1.5; ctx.shadowBlur=0; ctx.stroke();
      ctx.fillStyle='#fff'; ctx.font='600 12px Inter,sans-serif';
      ctx.textAlign='center'; ctx.textBaseline='middle'; ctx.fillText(p.label, p.x, p.y);
      if (isSrc||isSnk) { ctx.font='500 9px Inter,sans-serif'; ctx.fillStyle=color; ctx.fillText(isSrc?'IN':'OUT', p.x, p.y+NR+10); }
      ctx.restore();
    }
  }
}

function lighten(hex: string, pct: number): string {
  const n = parseInt(hex.slice(1),16);
  const r=Math.min(255,((n>>16)&0xff)+pct), g=Math.min(255,((n>>8)&0xff)+pct), b=Math.min(255,(n&0xff)+pct);
  return `rgb(${r},${g},${b})`;
}
function drawArrow(ctx: CanvasRenderingContext2D, x1:number,y1:number,x2:number,y2:number,color:string){
  const a=Math.atan2(y2-y1,x2-x1); const L=9; const s=0.42;
  ctx.fillStyle=color;
  ctx.beginPath(); ctx.moveTo(x2,y2);
  ctx.lineTo(x2-L*Math.cos(a-s), y2-L*Math.sin(a-s));
  ctx.lineTo(x2-L*Math.cos(a+s), y2-L*Math.sin(a+s));
  ctx.closePath(); ctx.fill();
}
function drawGainLabel(ctx: CanvasRenderingContext2D, mx:number,my:number,gain:string,color:string){
  ctx.save();
  ctx.font='500 11px JetBrains Mono,monospace';
  const tw = ctx.measureText(gain).width;
  ctx.fillStyle='rgba(15,17,33,0.88)';
  ctx.fillRect(mx-tw/2-4, my-8, tw+8, 16);
  ctx.fillStyle=color; ctx.textAlign='center'; ctx.textBaseline='middle';
  ctx.fillText(gain, mx, my);
  ctx.restore();
}
