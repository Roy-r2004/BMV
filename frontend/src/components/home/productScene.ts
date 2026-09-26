/**
 * The landing page's 3D story: the product itself, drawn as glass layers.
 *
 * Six layers stack up (question, conversation, test, answer, package,
 * system), come forward one per chapter, then the blueprint and the technical
 * plan flip past section by section as the reader scrolls through their long
 * chapters, and finally the system repeats in a ring for any business. Every
 * layer is generic interface drawn on a canvas: no one's data, no example
 * business.
 *
 * The page owns the DOM (stage, chapters, labels layer); this module owns the
 * WebGL scene and hands back a cleanup. Chapters are matched by `data-state`;
 * a chapter with `ls-chapter--deep` holds its state while the reader moves
 * through it, and that progress drives the flip.
 */
import * as THREE from 'three';

export const CHAPTERS = [
  'The product', 'One question', 'The conversation', 'The test', 'The answer',
  'The system', 'The blueprint', 'The technical plan', 'Any business', 'Start',
] as const;

export const CAPTIONS = [
  'Six layers: from your first sentence to a system built around your business.',
  'Layer one: what you are trying to work out.',
  'Layer two: the questions that matter, and your figures as you give them.',
  'Layer three: every explanation tested. One struck out, one circled.',
  'Layer four: the answer, and your choice.',
  'Layers five and six: the package, and the system it designs.',
  'The blueprint, section by section: nineteen of them.',
  'The technical plan: the engineering behind every module.',
  'The same rigour, a different system for every business.',
  'Start at the top layer.',
] as const;

/** Sections of the blueprint and the technical plan, as the real documents run. */
export const BLUEPRINT: [string, PageKind][] = [
  ['The decision', 'decision'], ['Executive summary', 'text'], ['The engagement: context and scope', 'text'],
  ['Where you are today', 'text'], ['The opportunity', 'text'], ['Who you serve, and how they arrive', 'journey'],
  ['How this makes money', 'money'], ['The financial case, quantified', 'money'], ['The future-state customer journey', 'journey'],
  ['The product, module by module', 'modules'], ['The organization: humans and AI on one chart', 'org'],
  ["What we'd build first", 'gantt'], ['The execution playbook', 'checks'], ['The scoreboard', 'kpi'],
  ['What could make this fail, honestly', 'risk'], ['What success looks like', 'kpi'], ['Evidence and method', 'text'],
  ['The screens', 'modules'], ['Three ways forward', 'decision'],
];
export const TECH_PLAN: [string, PageKind][] = [
  ['How your system works', 'arch'], ['The parts, one by one', 'modules'], ['Data model', 'erd'],
  ['AI agent: brain, tools, guardrails', 'agent'], ['API endpoints', 'api'], ['Integrations', 'arch'],
  ['Keeping your information safe', 'security'], ['Build order', 'gantt'], ['Acceptance checks', 'checks'],
];

type PageKind = 'decision' | 'text' | 'money' | 'journey' | 'modules' | 'org' | 'kpi' | 'risk'
  | 'arch' | 'erd' | 'agent' | 'api' | 'security' | 'gantt' | 'checks';
/** [x, y, z, rx, ry, rz, scale, opacity] */
type Pose = number[];
type Card = { tex: THREE.CanvasTexture; aspect: number };
type Obj = { mesh: THREE.Mesh<THREE.PlaneGeometry, THREE.MeshBasicMaterial>; poses: Pose[]; seed: number; dyn?: (pv: number) => Pose };
type Label = { s: number; p: [number, number, number]; el: HTMLElement; hw: number };
type Deck = { s: number; list: [string, PageKind][]; count: HTMLElement; bar: HTMLElement; last: number; hw: number };

const S = CHAPTERS.length;
const WIDE_MIN = 1024;
const UP = new THREE.Vector3(0, 1, 0);
const VIEWS: { p: [number, number, number]; t: [number, number, number]; w: number }[] = [
  { p: [0, 1.5, 15], t: [0, 0.3, 0], w: 9.5 },
  { p: [0, 0.6, 14], t: [0, 0.4, 0], w: 9.5 },
  { p: [0, 0.6, 14], t: [0, 0.4, 0], w: 9.5 },
  { p: [0, 0.6, 14], t: [0, 0.4, 0], w: 9.5 },
  { p: [0, 0.6, 14], t: [0, 0.4, 0], w: 9.5 },
  { p: [0, 0.6, 15], t: [0, 0.3, 0], w: 11 },
  { p: [0, 1.1, 14], t: [1.25, 1.05, -0.5], w: 6.9 },
  { p: [0, 1.1, 14], t: [1.25, 1.05, -0.5], w: 6.9 },
  { p: [0, 0.8, 17], t: [0, 0, 0], w: 14 },
  { p: [0, 1.5, 15], t: [0, 0.3, 0], w: 9.5 },
];

const smooth = (a: number, b: number, x: number) => { const t = Math.min(1, Math.max(0, (x - a) / (b - a))); return t * t * (3 - 2 * t); };
const lerp = (a: number, b: number, t: number) => a + (b - a) * t;

/** Fit a view into the band to the right of the text column (below it on narrow screens). */
function frameView(v: (typeof VIEWS)[number], camera: THREE.PerspectiveCamera, W: number, H: number, column: Element | null) {
  const tanH = Math.tan(THREE.MathUtils.degToRad(camera.fov / 2)), aspect = W / H, wide = W >= WIDE_MIN;
  const edge = column ? column.getBoundingClientRect().right / W : 0.42;
  const bandL = wide ? Math.min(0.62, edge + 0.02) : 0, bandR = wide ? 1 - 150 / W : 1;
  const bandFrac = bandR - bandL, centreNdc = bandL + bandR - 1;
  const tgt = new THREE.Vector3(...v.t), dir = new THREE.Vector3(...v.p).sub(tgt), d0 = dir.length(); dir.normalize();
  const right = new THREE.Vector3().crossVectors(UP, dir).normalize(), up = new THREE.Vector3().crossVectors(dir, right).normalize();
  const off = new THREE.Vector3(); let d: number;
  if (wide) { d = Math.max(d0, v.w / (bandFrac * 2 * tanH * aspect * 0.95)); off.addScaledVector(right, -centreNdc * d * tanH * aspect); }
  else { d = Math.min(Math.max(d0, (v.w * 0.9) / (2 * tanH * aspect), (v.w * 0.62) / (2 * tanH * 0.4)), d0 * 3.5); off.addScaledVector(up, -0.42 * d * tanH); }
  const t = tgt.add(off);
  return { p: t.clone().addScaledVector(dir, d), t };
}

// ── drawing: generic interface on canvas ──
type G = CanvasRenderingContext2D;
function rr(g: G, x: number, y: number, w: number, h: number, r: number) {
  g.beginPath(); g.moveTo(x + r, y); g.arcTo(x + w, y, x + w, y + h, r); g.arcTo(x + w, y + h, x, y + h, r);
  g.arcTo(x, y + h, x, y, r); g.arcTo(x, y, x + w, y, r); g.closePath();
}
const bar = (g: G, x: number, y: number, w: number, h = 10, c = '#dbe5f5') => { g.fillStyle = c; rr(g, x, y, w, h, h / 2); g.fill(); };
const pill = (g: G, x: number, y: number, text: string, bg: string, fg: string, font = '600 12px Inter') => {
  g.font = font; const w = g.measureText(text).width + 22; g.fillStyle = bg; rr(g, x, y, w, 24, 12); g.fill(); g.fillStyle = fg; g.fillText(text, x + 11, y + 16); return w;
};
const grad = (g: G, x0: number, x1: number) => { const gr = g.createLinearGradient(x0, 0, x1, 0); gr.addColorStop(0, '#2563eb'); gr.addColorStop(1, '#06b6d4'); return gr; };

const PW = 680, PH = 440;
type Surface = 'glass' | 'dark' | 'paper';
function glass(title: string, draw: (g: G, w: number, h: number) => void, surface: Surface = 'glass', w = PW, h = PH): Card {
  const k = 2, c = document.createElement('canvas'); c.width = w * k; c.height = h * k;
  const g = c.getContext('2d')!; g.scale(k, k);
  const dark = surface === 'dark';
  const bg = g.createLinearGradient(0, 0, 0, h);
  if (dark) { bg.addColorStop(0, '#0f1b3d'); bg.addColorStop(1, '#0a1230'); }
  else if (surface === 'paper') { bg.addColorStop(0, '#ffffff'); bg.addColorStop(1, '#f1f6ff'); }
  else { bg.addColorStop(0, 'rgba(255,255,255,0.97)'); bg.addColorStop(1, 'rgba(238,245,255,0.95)'); }
  g.fillStyle = bg; rr(g, 2, 2, w - 4, h - 4, 26); g.fill();
  const br = g.createLinearGradient(0, 0, w, h); br.addColorStop(0, dark ? '#3b82f6' : '#93c5fd'); br.addColorStop(1, dark ? '#06b6d4' : '#a5f3fc');
  g.strokeStyle = br; g.lineWidth = 2; rr(g, 2, 2, w - 4, h - 4, 26); g.stroke();
  const sh = g.createLinearGradient(0, 0, 0, 90); sh.addColorStop(0, dark ? 'rgba(255,255,255,.08)' : 'rgba(255,255,255,.9)'); sh.addColorStop(1, 'rgba(255,255,255,0)');
  g.fillStyle = sh; rr(g, 4, 4, w - 8, 86, 24); g.fill();
  if (title) {
    ['#fca5a5', '#fcd34d', '#86efac'].forEach((col, i) => { g.fillStyle = col; g.beginPath(); g.arc(28 + i * 16, 26, 5, 0, 7); g.fill(); });
    g.fillStyle = dark ? '#94a3b8' : '#64748b'; g.font = '600 12px Inter'; g.fillText(title, 86, 30);
  }
  draw(g, w, h);
  const tex = new THREE.CanvasTexture(c); tex.colorSpace = THREE.SRGBColorSpace; tex.anisotropy = 8;
  return { tex, aspect: w / h };
}

const layerQuestion = () => glass('One question', (g) => {
  g.fillStyle = '#0f172a'; g.font = '700 38px Syne'; g.fillText('What are you trying', 44, 110); g.fillText('to work out?', 44, 152);
  g.strokeStyle = '#93c5fd'; g.lineWidth = 2; g.fillStyle = '#f1f6ff'; rr(g, 44, 186, 592, 128, 18); g.fill(); g.stroke();
  bar(g, 70, 216, 470, 12, '#c7d7f2'); bar(g, 70, 244, 380, 12, '#c7d7f2'); bar(g, 70, 272, 220, 12, '#c7d7f2');
  g.fillStyle = '#2563eb'; g.fillRect(296, 266, 2.5, 22);
  g.fillStyle = grad(g, 44, 270); rr(g, 44, 348, 230, 50, 25); g.fill(); g.fillStyle = '#fff'; g.font = '600 16px Inter'; g.fillText('Start the conversation', 68, 379);
  bar(g, 300, 369, 200, 9, '#dbe5f5');
});

const layerTalk = () => glass('The conversation', (g) => {
  for (let i = 0; i < 2; i++) { bar(g, 40, 60 + i * 48, 230, 9, '#c7d7f2'); bar(g, 56, 78 + i * 48, 170, 9, '#e2eaf7'); g.fillStyle = '#dbe5f5'; g.fillRect(42, 74 + i * 48, 2, 18); }
  bar(g, 40, 172, 90, 6, '#2563eb'); bar(g, 136, 172, 150, 6, '#e2eaf7');
  bar(g, 40, 200, 330, 22, '#0f172a'); bar(g, 40, 232, 250, 22, '#0f172a');
  g.strokeStyle = '#93c5fd'; g.lineWidth = 2; g.fillStyle = '#f1f6ff'; rr(g, 40, 278, 340, 60, 14); g.fill(); g.stroke();
  bar(g, 60, 302, 200, 11, '#c7d7f2');
  g.fillStyle = grad(g, 40, 160); rr(g, 40, 358, 110, 40, 20); g.fill(); g.fillStyle = '#fff'; g.font = '600 14px Inter'; g.fillText('Answer', 66, 383);
  g.strokeStyle = '#cbd5e1'; rr(g, 160, 358, 130, 40, 20); g.stroke(); g.fillStyle = '#334155'; g.fillText("I don't know", 178, 383);
  // the case file, filling in beside the conversation
  g.fillStyle = '#ffffff'; g.strokeStyle = '#dbeafe'; rr(g, 410, 56, 240, 350, 18); g.fill(); g.stroke();
  g.fillStyle = '#0f172a'; g.font = '700 16px Syne'; g.fillText('Your business, so far', 428, 88);
  for (let r = 0; r < 4; r++) for (let c = 0; c < 8; c++) { g.fillStyle = c > 5 ? '#1e3a8a' : (r + c) % 5 ? '#93c5fd' : '#e2e8f0'; g.beginPath(); g.arc(438 + c * 24, 118 + r * 20, 6, 0, 7); g.fill(); }
  [[428, 222], [540, 222], [428, 296], [540, 296]].forEach(([x, y], i) => { g.fillStyle = i === 1 ? '#2563eb' : '#0f172a'; g.font = '800 28px Syne'; g.fillText(['12', '84%', '6', '3×'][i], x, y); bar(g, x, y + 14, 80, 8, '#dbe5f5'); });
  pill(g, 428, 356, "We'll test this, not assume it", '#dbeafe', '#1d4ed8', '600 11.5px Inter');
});

const layerTest = () => glass('Watching it think', (g) => {
  const rows = [
    { chip: 'Your explanation', verdict: "Doesn't hold up", vb: '#fff1dc', vf: '#a85b00', strike: true, lead: false },
    { chip: 'Capacity', verdict: 'Supported', vb: '#dcfce7', vf: '#047857', strike: false, lead: false },
    { chip: 'Price', verdict: 'Holds up best', vb: '#cffafe', vf: '#0e7490', strike: false, lead: true },
    { chip: 'Process', verdict: 'Ruled out', vb: '#f1f5f9', vf: '#64748b', strike: true, lead: false },
  ];
  rows.forEach((r, i) => {
    const y = 56 + i * 90;
    g.fillStyle = r.lead ? '#e8f0ff' : '#ffffff'; g.strokeStyle = '#dbeafe'; rr(g, 30, y, 470, 76, 14); g.fill(); g.stroke();
    g.fillStyle = r.lead ? '#1e3a8a' : '#94a3b8'; g.font = '700 22px Syne'; g.fillText(String(i + 1), 46, y + 46);
    pill(g, 78, y + 12, r.chip, i === 0 ? '#dbeafe' : '#eef2f9', i === 0 ? '#1d4ed8' : '#475569', '600 11px Inter');
    bar(g, 78, y + 46, 220, 11, r.strike ? '#cbd5e1' : '#0f172a'); bar(g, 304, y + 46, 70, 11, r.strike ? '#cbd5e1' : '#0f172a');
    if (r.strike) { g.strokeStyle = '#1e3a8a'; g.lineWidth = 2.5; g.beginPath(); g.moveTo(72, y + 52); g.bezierCurveTo(160, y + 46, 260, y + 58, 380, y + 50); g.stroke(); }
    pill(g, 388, y + 12, r.verdict, r.vb, r.vf, '600 11px Inter');
    if (r.lead) {
      g.strokeStyle = '#2563eb'; g.lineWidth = 3; g.beginPath(); g.ellipse(265, y + 38, 258, 50, -0.02, 0.15, Math.PI * 2 + 0.05); g.stroke();
      g.fillStyle = '#2563eb'; g.font = '700 22px Caveat'; g.fillText('holds up best', 370, y - 6);
    }
  });
  g.fillStyle = '#dc2626'; g.font = '600 12px Inter'; g.fillText('Two reviewers', 520, 70);
  g.font = '700 21px Caveat';
  ['Anything else', 'explain it?', 'held ✓', '', 'Just agreeing', 'with them?', 'held ✓'].forEach((t, i) => { g.fillStyle = t.startsWith('held') ? '#059669' : '#dc2626'; g.fillText(t, 520, 108 + i * 30); });
});

const layerAnswer = () => glass('Your answer', (g) => {
  bar(g, 40, 64, 150, 9, '#cbd5e1');
  bar(g, 40, 90, 330, 30, '#0f172a'); bar(g, 40, 132, 210, 30, '#0f172a'); bar(g, 40, 174, 260, 30, '#2563eb');
  bar(g, 40, 226, 300, 10, '#dbe5f5'); bar(g, 40, 246, 270, 10, '#dbe5f5'); bar(g, 40, 266, 190, 10, '#dbe5f5');
  g.fillStyle = '#ffffff'; g.strokeStyle = '#dbeafe'; rr(g, 400, 60, 250, 210, 16); g.fill(); g.stroke();
  for (let i = 0; i < 7; i++) { const hgt = [60, 80, 70, 95, 120, 150, 155][i]; g.fillStyle = i > 4 ? '#1e3a8a' : '#93c5fd'; rr(g, 420 + i * 32, 250 - hgt, 22, hgt, 5); g.fill(); }
  g.strokeStyle = '#e2e8f0'; g.lineWidth = 1; g.beginPath(); g.moveTo(410, 250); g.lineTo(640, 250); g.stroke();
  g.strokeStyle = '#dbeafe'; g.beginPath(); g.moveTo(40, 300); g.lineTo(640, 300); g.stroke();
  [40, 200].forEach((x) => { bar(g, x, 322, 120, 22, '#0f172a'); bar(g, x, 354, 90, 8, '#dbe5f5'); });
  bar(g, 360, 322, 150, 22, '#2563eb'); bar(g, 360, 354, 110, 8, '#dbe5f5');
  g.fillStyle = grad(g, 40, 220); rr(g, 40, 382, 170, 40, 20); g.fill(); g.fillStyle = '#fff'; g.font = '600 13.5px Inter'; g.fillText('Start the pilot', 72, 407);
  g.strokeStyle = '#93c5fd'; g.lineWidth = 1.5; rr(g, 222, 382, 170, 40, 20); g.stroke(); g.fillStyle = '#0f172a'; g.fillText('Build the system', 246, 407);
  g.fillStyle = '#64748b'; g.font = '500 13px Inter'; g.fillText("This isn't right", 410, 407);
});

const layerPackage = () => glass('Your package', (g) => {
  g.fillStyle = '#e4edff'; rr(g, 30, 52, 300, 360, 18); g.fill();
  g.fillStyle = '#0f172a'; g.font = '700 20px Syne'; g.fillText('Start here on Monday', 50, 88);
  for (let i = 0; i < 3; i++) {
    const y = 120 + i * 92; g.fillStyle = '#2563eb'; g.beginPath(); g.arc(64, y + 14, 15, 0, 7); g.fill();
    g.fillStyle = '#fff'; g.font = '700 14px Inter'; g.fillText(String(i + 1), 60, y + 19);
    bar(g, 92, y + 4, 200, 11, '#0f172a'); bar(g, 92, y + 24, 150, 11, '#0f172a'); bar(g, 92, y + 46, 180, 8, '#94a3b8');
  }
  g.fillStyle = '#0f172a'; g.font = '700 18px Syne'; g.fillText('Your documents', 356, 88);
  ['Pilot plan', 'Blueprint', 'Technical plan', 'Operations manual'].forEach((t, i) => {
    const y = 110 + i * 74;
    g.strokeStyle = '#dbeafe'; g.beginPath(); g.moveTo(356, y - 6); g.lineTo(650, y - 6); g.stroke();
    g.fillStyle = '#f3f7ff'; g.strokeStyle = '#93c5fd'; rr(g, 356, y + 6, 32, 42, 4); g.fill(); g.stroke();
    for (let l = 0; l < 4; l++) bar(g, 362, y + 14 + l * 8, l ? 20 : 14, 3, l ? '#93c5fd' : '#2563eb');
    g.fillStyle = '#0f172a'; g.font = '600 14px Inter'; g.fillText(t, 400, y + 26); bar(g, 400, y + 36, 110, 7, '#dbe5f5');
    g.fillStyle = i === 0 ? grad(g, 560, 650) : '#ffffff';
    rr(g, 560, y + 14, 86, 28, 14); g.fill(); if (i) { g.strokeStyle = '#93c5fd'; g.stroke(); }
    g.fillStyle = i === 0 ? '#fff' : '#0f172a'; g.font = '600 12px Inter'; g.fillText('Download', 575, y + 32);
  });
});

function systemScreen(accent: string, accent2: string, variant = 0) {
  return glass('', (g, _w, h) => {
    g.fillStyle = 'rgba(255,255,255,.05)'; rr(g, 16, 16, 120, h - 32, 14); g.fill();
    g.fillStyle = accent; g.beginPath(); g.arc(42, 44, 10, 0, 7); g.fill();
    for (let i = 0; i < 6; i++) bar(g, 32, 80 + i * 32, i === 0 ? 86 : 70, 9, i === 0 ? accent : 'rgba(148,163,184,.35)');
    bar(g, 160, 32, 220, 18, '#e2e8f0'); bar(g, 160, 60, 150, 9, 'rgba(148,163,184,.5)');
    for (let i = 0; i < 4; i++) {
      const x = 160 + i * 124; g.fillStyle = 'rgba(255,255,255,.06)'; rr(g, x, 90, 112, 72, 12); g.fill();
      bar(g, x + 12, 106, 50, 7, 'rgba(148,163,184,.5)'); bar(g, x + 12, 124, 60, 18, '#f8fafc'); bar(g, x + 12, 148, 36, 6, i % 2 ? accent2 : accent);
    }
    g.fillStyle = 'rgba(255,255,255,.05)'; rr(g, 160, 176, 300, 234, 12); g.fill();
    g.strokeStyle = accent; g.lineWidth = 3; g.beginPath();
    const pts = variant % 2 ? [0.7, 0.62, 0.66, 0.5, 0.42, 0.3, 0.22] : [0.75, 0.6, 0.64, 0.45, 0.5, 0.32, 0.2];
    pts.forEach((p, i) => { const x = 176 + i * 44, y = 190 + p * 200; if (i) g.lineTo(x, y); else g.moveTo(x, y); }); g.stroke();
    g.lineTo(176 + 6 * 44, 400); g.lineTo(176, 400); g.closePath();
    const fill = g.createLinearGradient(0, 200, 0, 400); fill.addColorStop(0, accent + '55'); fill.addColorStop(1, accent + '00'); g.fillStyle = fill; g.fill();
    g.fillStyle = 'rgba(255,255,255,.05)'; rr(g, 472, 176, 192, 234, 12); g.fill();
    for (let i = 0; i < 5; i++) {
      g.fillStyle = i === variant % 5 ? accent2 : 'rgba(148,163,184,.4)'; g.beginPath(); g.arc(494, 206 + i * 40, 7, 0, 7); g.fill();
      bar(g, 510, 200 + i * 40, 110, 9, 'rgba(226,232,240,.7)'); bar(g, 510, 216 + i * 40, 70, 6, 'rgba(148,163,184,.4)');
    }
  }, 'dark');
}

const agentChip = (name: string) => glass('', (g, _w, h) => {
  g.fillStyle = '#22d3ee'; g.beginPath(); g.arc(34, h / 2, 9, 0, 7); g.fill();
  g.fillStyle = 'rgba(34,211,238,.25)'; g.beginPath(); g.arc(34, h / 2, 16, 0, 7); g.fill();
  g.fillStyle = '#fff'; g.font = '700 17px Syne'; g.fillText(name, 60, h / 2 - 2);
  bar(g, 60, h / 2 + 10, 120, 7, 'rgba(148,163,184,.5)');
}, 'dark', 280, 84);

/** One page of a document: its header band (number and section title) is what shows in the cascade. */
function page(doc: string, no: number, title: string, kind: PageKind, accent: string) {
  return glass('', (g, w, h) => {
    const tag = String(no).padStart(2, '0');
    g.fillStyle = accent; rr(g, 26, 16, 34, 24, 7); g.fill(); g.fillStyle = '#fff'; g.font = '700 12.5px Inter'; g.fillText(tag, 43 - g.measureText(tag).width / 2, 32.5);
    const x0 = 72;
    let fs = 17; g.font = `700 ${fs}px Syne`;
    while (g.measureText(title).width > w - x0 - 28 && fs > 11) { fs -= 0.5; g.font = `700 ${fs}px Syne`; }
    g.fillStyle = '#0f172a'; g.fillText(title, x0, 34);
    g.fillStyle = accent; g.globalAlpha = 0.35; g.fillRect(26, 52, w - 52, 1.5); g.globalAlpha = 1;
    let y = 80;
    const B = (x: number, yy: number, ww: number, hh = 7, c = '#dbe5f5') => bar(g, x, yy, ww, hh, c);
    const para = (n: number) => { for (let i = 0; i < n; i++) { B(28, y, i % 4 === 3 ? 180 : w - 70); y += 15; } y += 8; };
    const box = (x: number, yy: number, ww: number, hh: number, fill = '#f3f7ff', stroke = '#bfdbfe', r = 8) => {
      g.fillStyle = fill; g.strokeStyle = stroke; g.lineWidth = 1.2; rr(g, x, yy, ww, hh, r); g.fill(); g.stroke();
    };
    const table = (rows: number, rowH: number, cells: (r: number, yy: number) => void) => {
      for (let r = 0; r < rows; r++) { const yy = y + r * rowH; g.fillStyle = r === 0 ? accent : r % 2 ? '#f6f9ff' : '#fff'; g.fillRect(28, yy, w - 56, rowH); cells(r, yy); }
      y += rows * rowH + 14;
    };
    const head = 'rgba(255,255,255,.8)';
    switch (kind) {
      case 'decision': para(3); box(28, y, w - 56, 70, '#eff6ff', '#93c5fd'); B(44, y + 18, 220, 9, '#2563eb'); B(44, y + 38, 280, 7); y += 90; para(4); break;
      case 'text': para(5); box(28, y, w - 56, 46, '#fff', '#dbeafe'); B(44, y + 20, 200, 7, '#93c5fd'); y += 64; para(4); break;
      case 'money': para(2); table(6, 26, (r, yy) => [0, 150, 250, 330].forEach((c, i) => B(38 + c, yy + 10, i === 0 ? 110 : 55, 6, r === 0 ? head : i === 3 ? '#0f172a' : '#c7d7f2'))); para(3); break;
      case 'kpi': para(1); table(7, 24, (r, yy) => { B(38, yy + 9, 130, 6, r === 0 ? head : '#334155'); B(190, yy + 9, 50, 6, r === 0 ? head : '#c7d7f2'); B(260, yy + 9, 60, 6, r === 0 ? head : r % 3 === 0 ? '#86efac' : '#c7d7f2'); }); para(2); break;
      case 'journey':
        para(2);
        for (let i = 0; i < 5; i++) {
          const x = 28 + i * 76; box(x, y, 64, 56, i === 2 ? '#e0f2fe' : '#f3f7ff'); B(x + 8, y + 14, 40, 6, '#1e40af'); B(x + 8, y + 30, 46, 5);
          if (i < 4) { g.strokeStyle = '#93c5fd'; g.beginPath(); g.moveTo(x + 64, y + 28); g.lineTo(x + 76, y + 28); g.stroke(); }
        }
        y += 76; for (let r = 0; r < 3; r++) { for (let i = 0; i < 5; i++) B(28 + i * 76, y, 56, 6, r === 2 ? '#a5f3fc' : '#dbe5f5'); y += 16; } y += 10; para(2); break;
      case 'modules':
        para(1);
        for (let i = 0; i < 6; i++) {
          const x = 28 + (i % 2) * 190, yy = y + Math.floor(i / 2) * 78; box(x, yy, 176, 66, '#fff', '#dbeafe');
          g.fillStyle = accent; g.font = '700 10px Inter'; g.fillText(`M${i + 1}`, x + 10, yy + 18);
          B(x + 34, yy + 12, 100, 7, '#0f172a'); B(x + 10, yy + 30, 150, 5); B(x + 10, yy + 42, 120, 5); B(x + 10, yy + 54, 60, 5, '#a5f3fc');
        }
        y += 240; break;
      case 'org':
        para(1); box(160, y, 90, 34, '#e0e7ff', '#a5b4fc'); B(176, y + 14, 58, 6, '#312e81'); y += 50;
        g.strokeStyle = '#94a3b8'; g.beginPath(); g.moveTo(205, y - 16); g.lineTo(205, y); g.moveTo(70, y); g.lineTo(340, y); g.stroke();
        [40, 150, 260].forEach((x, i) => {
          g.beginPath(); g.moveTo(x + 40, y); g.lineTo(x + 40, y + 14); g.stroke();
          box(x, y + 14, 80, 34, i === 1 ? '#cffafe' : '#f3f7ff', i === 1 ? '#67e8f9' : '#bfdbfe'); B(x + 10, y + 28, 56, 6, i === 1 ? '#0e7490' : '#1e40af');
        });
        y += 70; for (let i = 0; i < 4; i++) { B(28, y, 90, 7, '#0f172a'); B(130, y, 220, 7); y += 18; } y += 8; para(2); break;
      case 'risk':
        para(1);
        for (let i = 0; i < 4; i++) {
          box(28, y, w - 56, 54, '#fff', '#fecaca'); g.fillStyle = ['#ef4444', '#f59e0b', '#f59e0b', '#22c55e'][i]; g.beginPath(); g.arc(46, y + 27, 6, 0, 7); g.fill();
          B(62, y + 16, 170, 7, '#0f172a'); B(62, y + 32, 250, 5); y += 64;
        }
        para(1); break;
      case 'arch': {
        para(2);
        const nodes = [[40, 0], [170, 0], [300, 0], [100, 80], [240, 80], [170, 160]];
        g.strokeStyle = '#93c5fd'; g.lineWidth = 1.5;
        [[0, 3], [1, 3], [1, 4], [2, 4], [3, 5], [4, 5]].forEach(([a, b]) => { g.beginPath(); g.moveTo(nodes[a][0] + 40, y + nodes[a][1] + 36); g.lineTo(nodes[b][0] + 40, y + nodes[b][1]); g.stroke(); });
        nodes.forEach(([x, yy], i) => { box(x, y + yy, 80, 36, i === 5 ? '#0f172a' : i > 2 ? '#e0f2fe' : '#f3f7ff', i === 5 ? '#0f172a' : '#93c5fd'); B(x + 12, y + yy + 15, 54, 6, i === 5 ? '#67e8f9' : '#1e40af'); });
        y += 216; para(2); break;
      }
      case 'erd':
        para(1);
        [[28, 0], [210, 0], [28, 130], [210, 130]].forEach(([x, yy]) => {
          box(x, y + yy, 160, 104, '#fff', '#93c5fd', 6); g.fillStyle = '#1e3a8a'; g.fillRect(x, y + yy, 160, 22); B(x + 10, y + yy + 8, 70, 6, '#fff');
          for (let f = 0; f < 5; f++) { B(x + 10, y + yy + 32 + f * 14, 60, 5, f === 0 ? '#f59e0b' : '#c7d7f2'); B(x + 90, y + yy + 32 + f * 14, 50, 5, '#e2e8f0'); }
        });
        g.strokeStyle = '#2563eb'; g.lineWidth = 1.5; g.beginPath();
        g.moveTo(188, y + 50); g.lineTo(210, y + 50); g.moveTo(108, y + 104); g.lineTo(108, y + 130); g.moveTo(290, y + 104); g.lineTo(290, y + 130); g.stroke();
        y += 250; break;
      case 'agent':
        para(1);
        ([['Brain', '#e0e7ff', '#6366f1'], ['Tools', '#e0f2fe', '#0891b2'], ['Guardrails', '#fee2e2', '#ef4444'], ['Hands off to', '#dcfce7', '#16a34a']] as const).forEach(([t, f, c]) => {
          box(28, y, w - 56, 50, f, c); g.fillStyle = c; g.font = '700 12px Inter'; g.fillText(t, 44, y + 22);
          B(44, y + 32, 240, 5, '#fff'); B(150, y + 17, 160, 6, 'rgba(15,23,42,.25)'); y += 60;
        });
        para(1); break;
      case 'api': {
        para(1);
        const col: Record<string, string> = { GET: '#16a34a', POST: '#2563eb', PATCH: '#d97706', DELETE: '#dc2626' };
        const paths = ['/v1/bookings', '/v1/bookings', '/v1/customers/{id}', '/v1/schedule/{id}', '/v1/waitlist/offer', '/v1/reports/weekly', '/v1/holds/{id}'];
        ['GET', 'POST', 'GET', 'PATCH', 'POST', 'GET', 'DELETE'].forEach((m, i) => {
          g.fillStyle = col[m]; rr(g, 28, y, 50, 18, 4); g.fill(); g.fillStyle = '#fff'; g.font = '700 9.5px Inter'; g.fillText(m, 34, y + 13);
          g.fillStyle = '#334155'; g.font = '500 11px monospace'; g.fillText(paths[i], 88, y + 13); y += 26;
        });
        y += 6; para(2); break;
      }
      case 'security':
        para(2);
        ['Encrypted at rest and in transit', 'Role-based access', 'Audit log of every change', 'Your data stays yours'].forEach((t) => {
          g.strokeStyle = '#16a34a'; g.lineWidth = 2; g.beginPath(); g.moveTo(32, y + 6); g.lineTo(37, y + 11); g.lineTo(46, y); g.stroke();
          g.fillStyle = '#0f172a'; g.font = '500 12.5px Inter'; g.fillText(t, 58, y + 10); y += 26;
        });
        y += 6; para(3); break;
      case 'gantt':
        para(1);
        for (let i = 0; i < 7; i++) { B(28, y + 4, 80, 6, '#334155'); g.fillStyle = i < 2 ? '#2563eb' : i < 5 ? '#60a5fa' : '#a5f3fc'; rr(g, 120 + i * 30, y, 70 + (i % 3) * 20, 14, 4); g.fill(); y += 24; }
        y += 10; para(2); break;
      case 'checks':
        para(1);
        for (let i = 0; i < 7; i++) {
          g.strokeStyle = '#2563eb'; g.lineWidth = 1.5; rr(g, 28, y, 14, 14, 3); g.stroke();
          if (i < 4) { g.beginPath(); g.moveTo(31, y + 7); g.lineTo(34, y + 11); g.lineTo(40, y + 3); g.stroke(); }
          B(52, y + 4, 180 + (i % 3) * 40, 6, '#334155'); y += 24;
        }
        y += 6; para(2); break;
    }
    // the rest of the section, in subsections, down to the foot
    y += 10;
    while (y < h - 80) {
      B(28, y, 90 + (y % 60), 8, '#334155'); y += 20;
      for (let i = 0; i < 4 && y < h - 56; i++) { B(28, y, i === 3 ? 150 + (y % 90) : w - 70 - (i * 13) % 40); y += 14; }
      y += 12;
    }
    g.fillStyle = '#94a3b8'; g.font = '600 9.5px Inter'; g.fillText(doc, 28, h - 20);
    g.fillText('Build My Version', w - 28 - g.measureText('Build My Version').width, h - 20);
  }, 'paper', 440, 620);
}

// ── the light: points rising through the stack, and dust ──
const VS = `attribute float aSeed; uniform float uTime, uSize, uPR, uAlpha; varying float vA; varying float vS;
  void main(){ vec3 p = position; float t = fract(aSeed * 7.13 + uTime * (0.05 + aSeed * 0.07));
    p.y += t * 5.2; vA = sin(t * 3.14159) * uAlpha; vS = aSeed;
    vec4 mv = modelViewMatrix * vec4(p, 1.0); gl_Position = projectionMatrix * mv; gl_PointSize = uSize * (0.6 + aSeed) * uPR / -mv.z; }`;
const FS = `varying float vA; varying float vS; void main(){ float d = length(gl_PointCoord - .5); if (d > .5) discard;
  vec3 c = mix(vec3(0.15,0.39,0.92), vec3(0.02,0.71,0.83), vS); gl_FragColor = vec4(c, (1. - smoothstep(.2,.5,d)) * vA); }`;

type Mount = { stage: HTMLElement; story: HTMLElement; labels: HTMLElement; onState: (s: number) => void };

/** Build the scene into `stage`. Returns a cleanup; marks the stage flat when WebGL is missing. */
export function mountProductScene({ stage, story, labels: layer, onState }: Mount): () => void {
  let renderer: THREE.WebGLRenderer;
  try {
    renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  } catch {
    stage.classList.add('ls-stage--flat');
    return () => stage.classList.remove('ls-stage--flat');
  }
  let disposed = false, raf = 0;
  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  let W = stage.clientWidth, H = stage.clientHeight;
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2)); renderer.setSize(W, H); renderer.setClearColor(0, 0);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  stage.prepend(renderer.domElement);
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(34, W / H, 0.1, 200);
  const world = new THREE.Group(); scene.add(world);

  let mx = 0, my = 0;
  const onMove = (e: MouseEvent) => { mx = (e.clientX / window.innerWidth) * 2 - 1; my = (e.clientY / window.innerHeight) * 2 - 1; };
  let onResize = () => {};
  const resize = () => onResize();
  window.addEventListener('mousemove', onMove);
  window.addEventListener('resize', resize);

  // canvases are drawn in the page's fonts, so wait for them first
  Promise.all(['600 30px Inter', '700 30px Syne', '700 40px Caveat'].map((f) => document.fonts.load(f).catch(() => [])))
    .then(() => { if (!disposed) build(); });

  function build() {
    const objs: Obj[] = [], labels: Label[] = [], decks: Deck[] = [];
    const add = (card: Card, h: number, poses: Pose[], order = 0) => {
      const mesh = new THREE.Mesh(new THREE.PlaneGeometry(card.aspect * h, h),
        new THREE.MeshBasicMaterial({ map: card.tex, transparent: true, depthWrite: false, side: THREE.DoubleSide }));
      mesh.renderOrder = order; world.add(mesh);
      const o: Obj = { mesh, poses, seed: Math.random() * 10 }; objs.push(o); return o;
    };
    const addLabel = (s: number, text: string, p: [number, number, number], hot = false) => {
      const el = document.createElement('span'); el.className = 'ls-lbl' + (hot ? ' ls-lbl--hot' : ''); el.textContent = text;
      layer.appendChild(el); labels.push({ s, p, el, hw: 0 });
    };

    // the stack: six layers lying flat, exploded, seen from above at an angle
    const FLAT = -1.12, TW = 0.62;
    const stackPose = (k: number, gap = 0.62, y0 = -1.45, opacity = 1, x = 0): Pose => [x, y0 + (5 - k) * gap, 0, FLAT, 0, TW, 1, opacity];
    const FRONT: Pose = [0.3, 0.55, 3.2, -0.06, -0.12, 0, 1.3, 1];
    const LAYERS = [layerQuestion(), layerTalk(), layerTest(), layerAnswer(), layerPackage(), systemScreen('#3b82f6', '#22d3ee', 0)];
    LAYERS.forEach((card, k) => {
      const poses: Pose[] = [];
      for (let s = 0; s < S; s++) {
        if (s === 0 || s === 9) poses.push(stackPose(k, s === 9 ? 0.5 : 0.62));
        else if (s === 6 || s === 7) poses.push([-5.8 - k * 0.15, 3.6 + k * 0.1, -6 - k * 0.4, FLAT * 0.6, 0.35, TW * 0.6, 0.4, 0]);
        else if (s >= 1 && s <= 4) {
          const focus = s - 1;
          if (k === focus) poses.push(FRONT);
          else if (k < focus) poses.push([-3.6 - (focus - k) * 0.3, 2.6 + (focus - k) * 0.35, -3.5 - (focus - k) * 0.6, FLAT * 0.6, 0.35, TW * 0.6, 0.55, 0.35]);
          else poses.push(stackPose(k, 0.5, -3.4 - focus * 0.3, 0.55, 1.2));
        } else if (s === 5) {
          poses.push(k === 4 ? [-1.9, 0.9, 1.8, -0.04, 0.22, 0, 0.95, 1]
            : k === 5 ? [2.1, -0.25, 1.2, -0.04, -0.25, 0, 0.95, 1]
              : [-4.2 - k * 0.2, 3.2 + k * 0.2, -4 - k * 0.5, FLAT * 0.6, 0.35, TW * 0.6, 0.5, 0.25]);
        } else { // 8: any business
          poses.push(k === 5 ? [0, 0.35, 1.4, -0.04, 0, 0, 0.72, 1] : [-5 - k * 0.2, 3.4, -5, FLAT * 0.6, 0.3, TW * 0.6, 0.4, 0]);
        }
      }
      add(card, 3, poses, 10 - k);
    });
    // the AI team, in front of the system
    ['Front desk AI', 'Scheduling AI', 'Follow-up AI'].forEach((n, i) => {
      const hide: Pose = [2.1, -0.2, 0.4, -0.04, -0.25, 0, 0.2, 0];
      const poses = Array.from({ length: S }, () => hide);
      poses[5] = [3.9 + (i % 2) * 0.4, 1.6 - i * 0.95, 2.4 + i * 0.1, 0, -0.3, 0, 0.8, 1];
      add(agentChip(n), 0.7, poses, 20);
    });
    // any business: the system, many times, each built differently
    const ACC = [['#10b981', '#6ee7b7'], ['#f59e0b', '#fcd34d'], ['#ec4899', '#f9a8d4'], ['#8b5cf6', '#c4b5fd'], ['#06b6d4', '#67e8f9'], ['#ef4444', '#fca5a5'], ['#22c55e', '#bbf7d0'], ['#6366f1', '#a5b4fc']];
    ACC.forEach(([a, b], i) => {
      const ang = (i / ACC.length) * Math.PI * 2;
      const hide: Pose = [0, 0.35, 1.2, -0.04, 0, 0, 0.2, 0];
      const poses = Array.from({ length: S }, () => hide);
      poses[8] = [Math.cos(ang) * 5.4, 0.35 + Math.sin(ang) * 2.9, -1.2 - Math.abs(Math.sin(ang)) * 0.8, 0, -Math.cos(ang) * 0.35, 0, 0.5, 0.95];
      add(systemScreen(a, b, i + 1), 3, poses, 5);
    });

    // the documents: the page being read at the front, every later section
    // receding behind it, read pages turning away to the left
    const LP: Record<number, number> = {}, LPS: Record<number, number> = {};
    const DECK_AT = [0.2, 0.25, 2.6];
    const deckPose = (i: number, cur: number): Pose => {
      const d = i - cur, [X, Y, Z] = DECK_AT;
      if (d >= 0) {
        const q = Math.min(d, 9);
        return [X + q * 0.3, Y + q * 0.27, Z - q * 0.5, -0.03, -0.4, 0, 1, Math.max(0, 1 - Math.max(0, d - 6) * 0.3)];
      }
      const e = Math.min(1, -d);
      return [X - e * 2.6, Y + e * 0.35, Z + e * 0.9, -0.03, -0.42 + e * 1.35, 0, 1 - e * 0.1, 1 - e];
    };
    const makeDeck = (s: number, doc: string, list: [string, PageKind][], accent: string) => {
      const hide: Pose = [7, -2, -6, 0, -0.6, 0, 0.6, 0];
      const count = document.createElement('div'); count.className = 'ls-deck-count'; layer.appendChild(count);
      const barEl = document.createElement('div'); barEl.className = 'ls-deck-bar'; barEl.appendChild(document.createElement('i')); layer.appendChild(barEl);
      decks.push({ s, list, count, bar: barEl, last: -1, hw: 0 });
      list.forEach(([t, kind], i) => {
        const o = add(page(doc, i + 1, t, kind, accent), 3.3, Array.from({ length: S }, () => hide), 100 - i);
        o.dyn = (pv) => {
          const w = smooth(0, 1, 1 - Math.abs(pv - s) * 1.25);
          if (w <= 0) return hide;
          const P = deckPose(i, (LPS[s] || 0) * (list.length - 1));
          // arriving: the deck slides in, pages trailing one after another
          const lag = smooth(0, 1, w * 1.6 - Math.min(i, 10) * 0.06);
          return P.map((v, k) => (k === 7 ? v * lag : lerp(hide[k], v, lag)));
        };
      });
    };
    makeDeck(6, 'The Blueprint', BLUEPRINT, '#2563eb');
    makeDeck(7, 'Technical plan', TECH_PLAN, '#0891b2');

    const NP = 900, pg = new THREE.BufferGeometry(), pp = new Float32Array(NP * 3), ps = new Float32Array(NP);
    for (let i = 0; i < NP; i++) { const a = Math.random() * 6.28, r = Math.sqrt(Math.random()) * 2.4; pp[i * 3] = Math.cos(a) * r; pp[i * 3 + 1] = -2.2; pp[i * 3 + 2] = Math.sin(a) * r * 0.6; ps[i] = Math.random(); }
    pg.setAttribute('position', new THREE.BufferAttribute(pp, 3)); pg.setAttribute('aSeed', new THREE.BufferAttribute(ps, 1));
    const pm = new THREE.ShaderMaterial({ vertexShader: VS, fragmentShader: FS, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
      uniforms: { uTime: { value: 0 }, uSize: { value: 90 }, uPR: { value: renderer.getPixelRatio() }, uAlpha: { value: 1 } } });
    const beam = new THREE.Points(pg, pm); beam.renderOrder = 30; world.add(beam);
    const dn = 500, dg = new THREE.BufferGeometry(), dp = new Float32Array(dn * 3), ds = new Float32Array(dn);
    for (let i = 0; i < dn; i++) { dp[i * 3] = (Math.random() - 0.5) * 26; dp[i * 3 + 1] = (Math.random() - 0.5) * 14 - 2; dp[i * 3 + 2] = (Math.random() - 0.5) * 14 - 4; ds[i] = Math.random(); }
    dg.setAttribute('position', new THREE.BufferAttribute(dp, 3)); dg.setAttribute('aSeed', new THREE.BufferAttribute(ds, 1));
    const dust = pm.clone(); dust.uniforms.uSize.value = 45; dust.uniforms.uAlpha.value = 0.35; world.add(new THREE.Points(dg, dust));

    ['Your question', 'The conversation', 'The test', 'The answer', 'The package', 'Your system'].forEach((t, k) => addLabel(0, t, [3.3, -1.45 + (5 - k) * 0.62 + 0.15, 0.6], k === 5));
    addLabel(5, 'The package', [-1.9, 2.6, 1.8]); addLabel(5, 'Your system', [2.1, 1.45, 1.2], true);
    addLabel(8, 'Built around one business: yours', [0, 1.7, 1.4], true);

    // scroll → chapter index; deep chapters hold from a to b while their deck flips
    let F: { p: THREE.Vector3; t: THREE.Vector3 }[] = [];
    const fitAll = () => { F = VIEWS.map((v) => frameView(v, camera, W, H, story.querySelector('.ls-col'))); };
    fitAll();
    onResize = () => { W = stage.clientWidth; H = stage.clientHeight; renderer.setSize(W, H); camera.aspect = W / H; camera.updateProjectionMatrix(); fitAll(); };
    const chapters = [...story.querySelectorAll<HTMLElement>('[data-state]')];
    const scrollState = () => {
      const vh = window.innerHeight, mid = vh / 2, narrow = W < WIDE_MIN;
      const iv = chapters.map((el) => {
        const r = el.getBoundingClientRect();
        if (el.classList.contains('ls-chapter--deep')) return [r.top + vh * 0.5, r.bottom - vh * 0.5];
        const c = narrow ? r.top + vh * 0.45 : r.top + r.height / 2; return [c, c];
      });
      iv.forEach(([a, b], k) => { if (b > a) LP[k] = Math.min(1, Math.max(0, (mid - a) / (b - a))); });
      if (mid <= iv[0][1]) return 0;
      if (mid >= iv[iv.length - 1][0]) return iv.length - 1;
      for (let k = 0; k < iv.length - 1; k++) {
        if (mid <= iv[k][1]) return k;
        if (mid < iv[k + 1][0]) return k + smooth(0.15, 0.85, (mid - iv[k][1]) / (iv[k + 1][0] - iv[k][1]));
      }
      return 0;
    };

    const cp = new THREE.Vector3(), ct = new THREE.Vector3(), v = new THREE.Vector3();
    const eul = new THREE.Euler(), qa = new THREE.Quaternion(), qb = new THREE.Quaternion();
    const t0 = performance.now();
    let pv = scrollState(), last = t0, lastState = -1, sx = 0, sy = 0;

    const frame = (now: number) => {
      raf = requestAnimationFrame(frame);
      const dt = Math.min(0.05, (now - last) / 1000); last = now;
      const time = reduce ? 0 : (now - t0) / 1000;
      pv += (scrollState() - pv) * (reduce ? 1 : Math.min(1, dt * 4.2));
      for (const k in LP) { const prev = LPS[k] ?? LP[k]; LPS[k] = reduce ? LP[k] : prev + (LP[k] - prev) * Math.min(1, dt * 5); }
      const i0 = Math.min(S - 1, Math.floor(pv)), i1 = Math.min(S - 1, i0 + 1), f0 = pv - i0;

      objs.forEach((o, n) => {
        // the load moment: layers drop into the stack one after another
        const intro = reduce ? 1 : smooth(0, 1, ((now - t0) / 1000 - 0.15 * (n % 6)) / 1.1);
        const m = o.mesh;
        if (o.dyn) {
          const P = o.dyn(pv);
          m.position.set(P[0], P[1] + (reduce ? 0 : Math.sin(time * 0.8 + o.seed) * 0.02), P[2]);
          m.quaternion.setFromEuler(eul.set(P[3], P[4], P[5])); m.scale.setScalar(Math.max(0.001, P[6]));
          m.material.opacity = P[7] * intro; m.visible = m.material.opacity > 0.01;
          return;
        }
        const f = smooth(0, 1, f0 * 1.25 - (o.seed % 1) * 0.25);
        const a = o.poses[i0], b = o.poses[i1];
        const bob = reduce ? 0 : Math.sin(time * 0.8 + o.seed) * 0.05;
        m.position.set(lerp(a[0], b[0], f), lerp(a[1], b[1], f) + bob + (1 - intro) * 3.2, lerp(a[2], b[2], f));
        qa.setFromEuler(eul.set(a[3], a[4], a[5])); qb.setFromEuler(eul.set(b[3], b[4], b[5])); m.quaternion.slerpQuaternions(qa, qb, f);
        m.scale.setScalar(Math.max(0.001, lerp(a[6], b[6], f)));
        m.material.opacity = lerp(a[7], b[7], f) * intro;
        m.visible = m.material.opacity > 0.01;
      });

      const stacked = Math.max(0, 1 - Math.min(pv, S - 1 - pv) * 1.6); // the beam runs while the layers are stacked
      pm.uniforms.uAlpha.value = stacked; pm.uniforms.uTime.value = time; dust.uniforms.uTime.value = time;
      beam.visible = stacked > 0.01;

      const fc = smooth(0, 1, f0);
      cp.lerpVectors(F[i0].p, F[i1].p, fc); ct.lerpVectors(F[i0].t, F[i1].t, fc);
      if (!reduce) { sx += (mx - sx) * 0.05; sy += (my - sy) * 0.05; }
      camera.position.set(cp.x + sx * 1.1, cp.y - sy * 0.7, cp.z); camera.lookAt(ct); camera.updateMatrixWorld();
      world.rotation.y = reduce ? 0 : Math.sin(time * 0.18) * 0.06 * stacked + sx * 0.08;
      world.updateMatrixWorld();

      for (const L of labels) {
        const op = Math.max(0, 1 - Math.abs(pv - L.s) * 2.6) * (L.s === 0 && !reduce ? smooth(0, 1, (now - t0) / 1000 - 1.6) : 1);
        if (op < 0.02) { L.el.style.opacity = '0'; continue; }
        v.set(...L.p).applyMatrix4(world.matrixWorld).project(camera);
        if (!L.hw) L.hw = L.el.offsetWidth / 2;
        const lx = Math.min(W - L.hw - 8, Math.max(L.hw + 8, ((v.x + 1) / 2) * W));
        L.el.style.transform = `translate(${lx.toFixed(1)}px, ${(((1 - v.y) / 2) * H).toFixed(1)}px) translate(-50%, -50%)`;
        L.el.style.opacity = op.toFixed(3);
      }
      for (const dk of decks) {
        const op = smooth(0, 1, 1 - Math.abs(pv - dk.s) * 2.2);
        dk.count.style.opacity = dk.bar.style.opacity = op.toFixed(3);
        if (op < 0.02) continue;
        const n = dk.list.length, i = Math.min(n - 1, Math.round((LPS[dk.s] || 0) * (n - 1)));
        if (i !== dk.last) {
          dk.last = i;
          dk.count.replaceChildren(Object.assign(document.createElement('b'), { textContent: `${String(i + 1).padStart(2, '0')} / ${n}` }), dk.list[i][0]);
          dk.hw = dk.count.offsetWidth / 2;
        }
        v.set(DECK_AT[0], DECK_AT[1] - 1.85, DECK_AT[2]).applyMatrix4(world.matrixWorld).project(camera);
        const cx = ((v.x + 1) / 2) * W, cy = ((1 - v.y) / 2) * H;
        const lx = Math.min(W - 2 * dk.hw - 8, Math.max(8, cx - dk.hw));
        dk.count.style.transform = `translate(${lx.toFixed(1)}px, ${(cy + 4).toFixed(1)}px)`;
        dk.bar.style.transform = `translate(${(cx - 90).toFixed(1)}px, ${(cy + 44).toFixed(1)}px)`;
        (dk.bar.firstChild as HTMLElement).style.width = `${((i + 1) / n) * 100}%`;
      }
      const state = Math.round(Math.min(S - 1, Math.max(0, pv)));
      if (state !== lastState) { lastState = state; onState(state); }
      renderer.render(scene, camera);
    };
    raf = requestAnimationFrame(frame);
  }

  return () => {
    disposed = true;
    cancelAnimationFrame(raf);
    window.removeEventListener('mousemove', onMove);
    window.removeEventListener('resize', resize);
    world.traverse((o) => {
      if (o instanceof THREE.Mesh || o instanceof THREE.Points) {
        o.geometry.dispose();
        const mat = o.material as THREE.Material & { map?: THREE.Texture | null };
        mat.map?.dispose(); mat.dispose();
      }
    });
    renderer.dispose();
    renderer.domElement.remove();
    layer.replaceChildren();
  };
}
