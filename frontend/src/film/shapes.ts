/**
 * The shapes the light field takes. Each shape is a set of points with a
 * colour each, in the field's own space (about 6 units wide and 5 tall).
 * They draw the firm's story in plain geometry: the idea as a seed, the
 * explanations being tested, the one-page answer, the six files, the built
 * system, and one shape for each page's subject. Nothing here is data about a
 * client; the shapes stand for the method.
 */

export type RGB = readonly [number, number, number];
type Pt = [number, number, number, number, number, number];

/** A moving shape: the first `n` points travel a path instead of sitting still. */
export type Flow = { n: number; speed: number; path: (u: number, i: number, out: Float32Array) => void };
export type Shape = { data: Float32Array; flow: Flow | null };

export const COLOUR = {
  ink: [0.05, 0.08, 0.2],
  cobalt: [0.15, 0.31, 0.94],
  sky: [0.31, 0.64, 1.0],
  pale: [0.74, 0.79, 0.91],
  theirs: [0.15, 0.31, 0.94],
  derived: [0.04, 0.54, 0.39],
  ours: [0.7, 0.42, 0.02],
  cited: [0.48, 0.31, 0.88],
} as const satisfies Record<string, RGB>;
const C = COLOUR;

/** A repeatable random number in [0, 1) for a given seed. */
export function rnd(i: number): number {
  const x = Math.sin(i * 127.1 + 311.7) * 43758.5453;
  return x - Math.floor(x);
}

function P(L: Pt[], x: number, y: number, z: number, c: RGB) {
  L.push([x, y, z, c[0], c[1], c[2]]);
}

/** Spread a list of points over exactly `n` slots. */
function fill(n: number, L: Pt[], flow: Flow | null = null): Shape {
  const data = new Float32Array(n * 6);
  for (let i = 0; i < n; i++) data.set(L[(i * 7919) % L.length], i * 6);
  return { data, flow };
}

function ball(L: Pt[], cx: number, cy: number, cz: number, r: number, count: number, c: RGB) {
  for (let i = 0; i < count; i++) {
    const y = 1 - (i / (count - 1)) * 2;
    const rr = Math.sqrt(1 - y * y);
    const th = i * 2.399963;
    P(L, cx + Math.cos(th) * rr * r, cy + y * r, cz + Math.sin(th) * rr * r, c);
  }
}

function boxEdges(L: Pt[], cx: number, cy: number, cz: number, w: number, h: number, d: number, count: number, c: RGB, s: number) {
  const hx = w / 2, hy = h / 2, hz = d / 2;
  for (let i = 0; i < count; i++) {
    const t = rnd(i + s);
    const e = Math.floor(rnd(i * 3 + s) * 12);
    let x: number, y: number, z: number;
    if (e < 4) { x = e & 1 ? hx : -hx; z = e & 2 ? hz : -hz; y = -hy + h * t; }
    else if (e < 8) { y = e & 1 ? hy : -hy; z = e & 2 ? hz : -hz; x = -hx + w * t; }
    else { x = e & 1 ? hx : -hx; y = e & 2 ? hy : -hy; z = -hz + d * t; }
    P(L, cx + x, cy + y, cz + z, c);
  }
}

function rectEdge(L: Pt[], cx: number, cy: number, z: number, w: number, h: number, count: number, c: RGB) {
  for (let e = 0; e < count; e++) {
    const d = (e / count) * 2 * (w + h);
    let x: number, y: number;
    if (d < w) { x = -w / 2 + d; y = h / 2; }
    else if (d < w + h) { x = w / 2; y = h / 2 - (d - w); }
    else if (d < 2 * w + h) { x = w / 2 - (d - w - h); y = -h / 2; }
    else { x = -w / 2; y = -h / 2 + (d - 2 * w - h); }
    P(L, cx + x, cy + y, z, c);
  }
}

function line(L: Pt[], x0: number, y: number, len: number, c: RGB, count: number) {
  for (let i = 0; i < count; i++) P(L, x0 + len * (i / (count - 1)), y + (rnd(i + y * 50) - 0.5) * 0.03, 0, c);
}

/** The idea: a seed of light, cobalt and ink, with a bright core. */
function seed(n: number): Shape {
  const L: Pt[] = [];
  for (let i = 0; i < 6000; i++) {
    const y = 1 - (i / 5999) * 2, r = Math.sqrt(1 - y * y), th = i * 2.399963, R = 2.3 + (rnd(i) - 0.5) * 0.16;
    const c = rnd(i + 9) > 0.8 ? C.sky : rnd(i + 3) > 0.45 ? C.cobalt : C.ink;
    P(L, Math.cos(th) * r * R, y * R, Math.sin(th) * r * R, c);
  }
  for (let j = 0; j < 1500; j++) {
    const a = rnd(j * 3) * 6.283, b = Math.acos(2 * rnd(j * 5) - 1), rr = Math.pow(rnd(j * 7), 0.5) * 1.2;
    P(L, Math.sin(b) * Math.cos(a) * rr, Math.cos(b) * rr, Math.sin(b) * Math.sin(a) * rr, C.sky);
  }
  return fill(n, L);
}

/** Explanations branching from one point; the one that survives is ringed. */
function test(n: number): Shape {
  const L: Pt[] = [];
  const B = 7, win = 2;
  for (let b = 0; b < B; b++) {
    const ang = -1.2 + b * (2.4 / (B - 1)), ex = Math.cos(ang) * 2.6 - 0.6, ey = Math.sin(ang) * 2.3, on = b === win;
    const c = on ? C.cobalt : C.pale;
    for (let i = 0; i < 520; i++) {
      const t = i / 519, bend = Math.sin(t * Math.PI) * 0.35 * (b % 2 ? 1 : -1);
      P(L, -2.9 + (ex + 2.9) * t, ey * t + bend, (rnd(i + b * 99) - 0.5) * 0.12, c);
    }
    for (let k = 0; k < (on ? 700 : 260); k++) {
      const a = rnd(k + b * 17) * 6.283, r = Math.sqrt(rnd(k * 3 + b)) * (on ? 0.42 : 0.26);
      P(L, ex + Math.cos(a) * r, ey + Math.sin(a) * r, (rnd(k * 5) - 0.5) * 0.3, c);
    }
    if (on) for (let q = 0; q < 500; q++) { const a = (q / 500) * 6.283; P(L, ex + Math.cos(a) * 0.75, ey + Math.sin(a) * 0.75, 0, C.ink); }
  }
  for (let s = 0; s < 500; s++) { const a = rnd(s) * 6.283, r = Math.sqrt(rnd(s * 2)) * 0.35; P(L, -2.9 + Math.cos(a) * r, Math.sin(a) * r, 0, C.ink); }
  return fill(n, L);
}

/** The answer page: two bright lines of answer, the figures with their labels. */
function page(n: number, labels: RGB[]): Shape {
  const L: Pt[] = [];
  rectEdge(L, 0, 0, 0, 3.3, 4.4, 1400, C.ink);
  line(L, -1.35, 1.75, 1.5, C.cobalt, 160);
  for (let r = 0; r < 4; r++) line(L, -1.35, 1.25 - r * 0.07, 2.6 - (r % 2) * 0.9, C.ink, 240);
  for (let r = 0; r < 4; r++) line(L, -1.35, 0.95 - r * 0.07, 1.9, C.ink, 200);
  labels.forEach((lc, f) => {
    const yy = 0.3 - f * (1.2 / labels.length + 0.1);
    line(L, -1.35, yy, 1.6 - f * 0.25, C.pale, 140);
    for (let k = 0; k < 260; k++) {
      const a = rnd(k + f * 31) * 6.283, rr = Math.sqrt(rnd(k * 7 + f)) * 0.12;
      P(L, 0.95 + Math.cos(a) * rr * 2.2, yy + Math.sin(a) * rr, 0, lc);
    }
  });
  for (let m = 0; m < 3; m++) line(L, -1.35, -1.45 - m * 0.22, 2.4 - m * 0.5, C.cobalt, 160);
  return fill(n, L);
}

/** Six files, stacked; the top one is the answer. */
function layers(n: number): Shape {
  const L: Pt[] = [];
  for (let s = 0; s < 6; s++) {
    const y = -1.4 + s * 0.56, top = s === 5;
    for (let i = 0; i < 1250; i++) {
      const edge = rnd(i + s * 77) < 0.55;
      if (edge) {
        const t = rnd(i * 3 + s), side = Math.floor(rnd(i * 5 + s) * 4);
        const x = side < 2 ? -1.9 + 3.8 * t : side === 2 ? -1.9 : 1.9;
        const z = side < 2 ? (side ? -1.25 : 1.25) : -1.25 + 2.5 * t;
        P(L, x, y, z, top ? C.cobalt : C.ink);
      } else {
        P(L, -1.6 + rnd(i * 7 + s) * 3.2, y, -1.0 + Math.floor(rnd(i * 11 + s) * 8) * 0.28, top ? C.sky : C.pale);
      }
    }
  }
  return fill(n, L);
}

/** A working system: blocks of different heights on one grid, some lit. */
function city(n: number): Shape {
  const L: Pt[] = [];
  const G = 6, sp = 0.78;
  for (let gx = 0; gx < G; gx++) for (let gz = 0; gz < G; gz++) {
    const hgt = 0.3 + Math.pow(rnd(gx * 13 + gz * 7), 1.6) * 3.0;
    const x0 = (gx - G / 2 + 0.5) * sp, z0 = (gz - G / 2 + 0.5) * sp, lit = rnd(gx * 3 + gz * 5) > 0.62;
    boxEdges(L, x0, hgt / 2 - 1.6, z0, 0.52, hgt, 0.52, 200, lit ? C.cobalt : C.ink, gx * 50 + gz * 500);
    for (let w = 0; w < 50; w++) P(L, x0 + (rnd(w * 7 + gx) - 0.5) * 0.46, -1.6 + Math.floor((rnd(w * 3 + gz) * hgt) / 0.2) * 0.2, z0 + 0.26, lit ? C.sky : C.pale);
  }
  for (let k = 0; k < 900; k++) P(L, (rnd(k) - 0.5) * G * sp * 1.15, -1.62, (rnd(k * 3) - 0.5) * G * sp * 1.15, C.pale);
  return fill(n, L);
}

/** The three services: a consultation, blocks being built, a sealed box. */
function trio(n: number): Shape {
  const L: Pt[] = [];
  ball(L, -2.1, 0.2, 0, 0.75, 1800, C.cobalt);
  for (let bx = 0; bx < 3; bx++) for (let by = 0; by <= 2 - bx; by++) {
    boxEdges(L, -0.4 + bx * 0.42, -0.5 + by * 0.42, 0, 0.36, 0.36, 0.36, 160, by === 2 - bx ? C.cobalt : C.ink, bx * 9 + by);
  }
  boxEdges(L, 2.2, 0.1, 0, 1.4, 1.4, 1.4, 1500, C.ink, 3);
  ball(L, 2.2, 0.1, 0, 0.36, 700, C.sky);
  return fill(n, L);
}

/** Stages on one line; the last is lit. */
function timeline(n: number, count = 6): Shape {
  const L: Pt[] = [];
  const at = (k: number) => [-2.7 + k * (5.4 / (count - 1)), Math.sin((k / (count - 1)) * Math.PI) * 0.9 - 0.3] as const;
  for (let k = 0; k < count; k++) {
    const [x, y] = at(k), last = k === count - 1;
    for (let q = 0; q < 360; q++) { const a = (q / 360) * 6.283; P(L, x + Math.cos(a) * 0.3, y + Math.sin(a) * 0.3, 0, last ? C.cobalt : C.ink); }
    ball(L, x, y, 0, 0.1, 140, last ? C.cobalt : C.sky);
    if (k < count - 1) {
      const [x2, y2] = at(k + 1);
      for (let i = 0; i < 300; i++) { const t = 0.12 + 0.76 * (i / 299); P(L, x + (x2 - x) * t, y + (y2 - y) * t, 0, C.pale); }
    }
  }
  return fill(n, L);
}

function vaultBase(L: Pt[], cx: number, dim = false) {
  boxEdges(L, cx, 0, 0, 3, 3, 3, 3200, dim ? C.pale : C.ink, 7);
  for (let f = 0; f < 900; f++) P(L, cx + (rnd(f) - 0.5) * 3, (rnd(f * 3) - 0.5) * 3, 1.5 * (rnd(f * 5) > 0.5 ? 1 : -1), C.pale);
  ball(L, cx, 0, 0, 0.55, 1300, C.cobalt);
}

/** Private AI: the model inside a boundary you own. */
function vault(n: number): Shape {
  const L: Pt[] = [];
  vaultBase(L, 0);
  for (let s = 0; s < 6; s++) ball(L, Math.cos(s) * 0.95, Math.sin(s * 1.7) * 0.8, Math.sin(s) * 0.7, 0.1, 90, C.sky);
  return fill(n, L);
}

/** The four reasons, each a light inside the boundary. */
function vaultdots(n: number): Shape {
  const L: Pt[] = [];
  vaultBase(L, 0);
  [[0.8, 0.8], [-0.8, 0.8], [0.8, -0.8], [-0.8, -0.8]].forEach(([x, y], k) => ball(L, x, y, 0.4, 0.22, 400, k % 2 ? C.cobalt : C.sky));
  return fill(n, L);
}

/** Requests that go round inside the boundary and never leave it. */
function privateflow(n: number): Shape {
  const L: Pt[] = [];
  vaultBase(L, -0.6);
  return fill(n, L, {
    n: 1600,
    speed: 0.12,
    path: (u, i, o) => {
      const a = u * 6.283, j = (rnd(i) - 0.5) * 0.18;
      o[0] = -0.6 + Math.cos(a) * (1.05 + j); o[1] = Math.sin(a) * (0.7 + j); o[2] = Math.sin(a * 2) * 0.4;
      o[3] = C.sky[0]; o[4] = C.sky[1]; o[5] = C.sky[2];
    },
  });
}

/** Requests that leave the boundary for a provider's servers and come back. */
function cloudflow(n: number): Shape {
  const L: Pt[] = [];
  vaultBase(L, -1.2, true);
  ball(L, 2.3, 1.6, -0.5, 0.7, 1400, C.pale);
  const dx = 3.5, dy = 1.6, cx = -1.2 + dx / 2, cy = dy / 2, len = Math.hypot(dx, dy), ux = dx / len, uy = dy / len;
  return fill(n, L, {
    n: 1600,
    speed: 0.1,
    path: (u, i, o) => {
      const a = u * 6.283, j = (rnd(i) - 0.5) * 0.16, c = Math.cos(a) * (len / 2 + 0.2), s = Math.sin(a) * (0.32 + j);
      o[0] = cx + ux * c - uy * s; o[1] = cy + uy * c + ux * s; o[2] = j;
      o[3] = C.ours[0]; o[4] = C.ours[1]; o[5] = C.ours[2];
    },
  });
}

/** The operation in the middle, the AI as the ring around it. */
function ring(n: number): Shape {
  const L: Pt[] = [];
  ball(L, 0, 0, 0, 0.85, 2600, C.ink);
  for (let i = 0; i < 4200; i++) {
    const a = (i / 4200) * 6.283, r = 2.3 + (rnd(i) - 0.5) * 0.22, y = (rnd(i * 3) - 0.5) * 0.12;
    P(L, Math.cos(a) * r, y + Math.sin(a) * r * 0.32, Math.sin(a) * r, rnd(i * 5) > 0.7 ? C.sky : C.cobalt);
  }
  return fill(n, L);
}

/** Before the work is understood: scattered, mostly pale. */
function loose(n: number): Shape {
  const L: Pt[] = [];
  for (let i = 0; i < 6000; i++) P(L, (rnd(i) - 0.5) * 5.4, (rnd(i * 3) - 0.5) * 4.2, (rnd(i * 7) - 0.5) * 3, rnd(i * 11) > 0.85 ? C.cobalt : C.pale);
  return fill(n, L);
}

/** Four disciplines on one engagement. */
function four(n: number): Shape {
  const L: Pt[] = [];
  const pts: [number, number, RGB][] = [[-1.2, 1, C.cobalt], [1.2, 1, C.ink], [1.2, -1, C.ink], [-1.2, -1, C.sky]];
  pts.forEach(([x, y, c]) => ball(L, x, y, 0, 0.7, 1500, c));
  for (let i = 0; i < 800; i++) {
    const t = rnd(i), e = Math.floor(rnd(i * 3) * 4), a = pts[e], b = pts[(e + 1) % 4];
    P(L, a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, 0, C.pale);
  }
  return fill(n, L);
}

/** Six areas of a business around one centre. */
function hexa(n: number): Shape {
  const L: Pt[] = [];
  ball(L, 0, 0, 0, 0.35, 700, C.cobalt);
  for (let k = 0; k < 6; k++) {
    const a = (k / 6) * 6.283 + 0.52, x = Math.cos(a) * 2.1, y = Math.sin(a) * 2.1;
    ball(L, x, y, 0, 0.42, 800, k % 2 ? C.ink : C.sky);
    for (let i = 0; i < 260; i++) { const t = 0.18 + 0.64 * (i / 259); P(L, x * t, y * t, 0, C.pale); }
  }
  return fill(n, L);
}

/** Solid by the time you own it. */
function solid(n: number): Shape {
  const L: Pt[] = [];
  boxEdges(L, 0, 0, 0, 2.4, 2.4, 2.4, 3200, C.ink, 11);
  for (let f = 0; f < 5000; f++) {
    const face = Math.floor(rnd(f) * 6), u = (rnd(f * 3) - 0.5) * 2.4, v = (rnd(f * 5) - 0.5) * 2.4;
    let x: number, y: number, z: number;
    if (face < 2) { x = face ? 1.2 : -1.2; y = u; z = v; }
    else if (face < 4) { y = face === 3 ? 1.2 : -1.2; x = u; z = v; }
    else { z = face === 5 ? 1.2 : -1.2; x = u; y = v; }
    P(L, x, y, z, face === 3 ? C.cobalt : face === 5 ? C.sky : C.pale);
  }
  return fill(n, L);
}

/** Systems, screen by screen. */
function screens(n: number): Shape {
  const L: Pt[] = [];
  for (let k = 0; k < 6; k++) {
    const gx = k % 3, gy = Math.floor(k / 3), cx = -2.2 + gx * 2.2, cy = 0.75 - gy * 1.7, z = (gx - 1) * -0.5;
    rectEdge(L, cx, cy, z, 1.9, 1.3, 520, C.ink);
    for (let r = 0; r < 4; r++) for (let i = 0; i < 70; i++) P(L, cx - 0.75 + (1.1 - r * 0.18) * (i / 69), cy + 0.35 - r * 0.22, z, r === 0 ? C.cobalt : C.pale);
  }
  return fill(n, L);
}

/** Writing to the firm: a signal going out. */
function beacon(n: number): Shape {
  const L: Pt[] = [];
  for (let i = 0; i < 1600; i++) P(L, 0, -1.8 + 3.6 * (i / 1599), 0, i > 1200 ? C.cobalt : C.ink);
  for (let r = 1; r <= 4; r++) for (let q = 0; q < 900; q++) { const a = (q / 900) * 6.283; P(L, Math.cos(a) * r * 0.62, -1.8, Math.sin(a) * r * 0.62, r === 1 ? C.cobalt : C.pale); }
  ball(L, 0, 1.9, 0, 0.3, 600, C.cobalt);
  return fill(n, L);
}

/** Signing in: a ring and a key. */
function key(n: number): Shape {
  const L: Pt[] = [];
  for (let i = 0; i < 3200; i++) { const a = (i / 3200) * 6.283, r = 1.5 + (rnd(i) - 0.5) * 0.12; P(L, Math.cos(a) * r, Math.sin(a) * r + 0.3, (rnd(i * 3) - 0.5) * 0.1, C.ink); }
  ball(L, 0, 0.55, 0, 0.38, 1100, C.cobalt);
  for (let k = 0; k < 1400; k++) { const t = rnd(k), half = 0.12 + t * 0.2; P(L, (rnd(k * 3) - 0.5) * 2 * half, 0.25 - t * 1.0, 0, C.cobalt); }
  return fill(n, L);
}

/** Words, set in the display face and sampled into points. */
export function words(n: number, text: string): Shape {
  const cw = 1400, ch = 520;
  const cv = document.createElement('canvas');
  cv.width = cw; cv.height = ch;
  const g = cv.getContext('2d', { willReadFrequently: true });
  if (!g) return seed(n);
  g.fillStyle = '#000'; g.textAlign = 'center'; g.textBaseline = 'middle';
  let fs = 150, lines: string[];
  do {
    g.font = `italic 400 ${fs}px "Instrument Serif", Georgia, serif`;
    lines = wrap(g, text, cw * 0.62);
    fs -= 8;
  } while ((lines.length > 3 || lines.length * fs * 1.05 > ch * 0.9) && fs > 50);
  fs += 8;
  const lh = fs * 1.02, y0 = ch / 2 - ((lines.length - 1) * lh) / 2;
  lines.forEach((l, k) => g.fillText(l, cw / 2, y0 + k * lh));
  const d = g.getImageData(0, 0, cw, ch).data;
  const L: Pt[] = [];
  for (let y = 0; y < ch; y += 3) for (let x = 0; x < cw; x += 3) {
    if (d[(y * cw + x) * 4 + 3] > 128) {
      P(L, ((x - cw / 2) / cw) * 7.2 + 0.2, (-(y - ch / 2) / cw) * 7.2, (rnd(x + y * 3) - 0.5) * 0.25, rnd(x * 0.37 + y) > 0.75 ? C.cobalt : C.ink);
    }
  }
  return L.length > 50 ? fill(n, L) : seed(n);
}

function wrap(g: CanvasRenderingContext2D, text: string, max: number): string[] {
  const lines: string[] = [];
  let cur = '';
  for (const word of text.split(/\s+/)) {
    const t = cur ? `${cur} ${word}` : word;
    if (g.measureText(t).width > max && cur) { lines.push(cur); cur = word; } else cur = t;
  }
  if (cur) lines.push(cur);
  return lines;
}

export const SHAPES = {
  seed,
  test,
  page: (n: number) => page(n, [C.theirs, C.derived, C.ours]),
  page4: (n: number) => page(n, [C.theirs, C.derived, C.cited, C.ours]),
  layers,
  city,
  trio,
  timeline: (n: number) => timeline(n, 6),
  timeline4: (n: number) => timeline(n, 4),
  vault,
  vaultdots,
  privateflow,
  cloudflow,
  ring,
  loose,
  four,
  hexa,
  solid,
  screens,
  beacon,
  key,
} as const;

export type ShapeName = keyof typeof SHAPES | 'words';

/** How each shape sits: [tilt about x, turn about y], and how fast it turns on its own. */
export const POSE: Record<ShapeName, { pose: [number, number]; spin: number }> = {
  seed: { pose: [0.2, 0], spin: 0.12 },
  words: { pose: [0, 0], spin: 0 },
  test: { pose: [0, 0], spin: 0 },
  page: { pose: [0, -0.18], spin: 0 },
  page4: { pose: [0, -0.18], spin: 0 },
  layers: { pose: [0.45, 0.65], spin: 0.18 },
  city: { pose: [0.42, 0.7], spin: 0.12 },
  trio: { pose: [0.2, 0], spin: 0.1 },
  timeline: { pose: [0, 0], spin: 0 },
  timeline4: { pose: [0, 0], spin: 0 },
  vault: { pose: [0.45, 0.6], spin: 0.14 },
  vaultdots: { pose: [0.4, 0.5], spin: 0.14 },
  privateflow: { pose: [0.3, 0.4], spin: 0.06 },
  cloudflow: { pose: [0.2, 0.1], spin: 0 },
  ring: { pose: [0.25, 0], spin: 0.1 },
  loose: { pose: [0.2, 0], spin: 0.04 },
  four: { pose: [0, 0], spin: 0 },
  hexa: { pose: [0, 0], spin: 0.05 },
  solid: { pose: [0.5, 0.7], spin: 0.16 },
  screens: { pose: [0, -0.25], spin: 0 },
  beacon: { pose: [0.35, 0], spin: 0.2 },
  key: { pose: [0, 0], spin: 0 },
};
