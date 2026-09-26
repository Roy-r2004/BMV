/**
 * The About page's one moving picture: a single field of points that takes a
 * different shape for each chapter as the visitor scrolls.
 *
 *   0  the operation (six parts, their connections) with the AI as a ring around it
 *   1  noise, with one small useful core
 *   2  four layers — business, product, AI, infrastructure — on one spine
 *   3  a landscape: the work itself, before any model
 *   4  six cells, one per area we build in
 *   5  a rising path, loose at Diagnose and solid at Own
 *   6  cloud, private, hybrid
 *   7  the operation again, one part lit
 *
 * The stage is sticky inside the story wrapper, so it scrolls away with the
 * last chapter and the footer is never drawn over. Chapters are found by their
 * `data-state` attribute; each chapter's centre crossing the viewport's centre
 * moves the field to that shape. Labels are page elements pinned to 3D anchors.
 *
 * Without WebGL the stage is hidden and the chapters read as plain text. With
 * reduced motion there is no intro, drift, sway or travelling data.
 */
import { useEffect, useRef, useState, type ReactNode, type RefObject } from 'react';
import * as THREE from 'three';
import { frameView, WIDE_MIN, type Framed, type View } from '../three/frameView';

export const STATE_COUNT = 8;

type Vec = [number, number, number];

const NODES: { n: string; p: Vec; core?: boolean }[] = [
  { n: 'Demand', p: [-4.4, 2.5, 0] },
  { n: 'Customers', p: [4.4, 2.5, -0.6] },
  { n: 'Operations', p: [0, 0.2, 0.8], core: true },
  { n: 'Inventory', p: [-4.8, -2.3, 0.4] },
  { n: 'Fulfillment', p: [4.6, -2.2, -0.3] },
  { n: 'Finance', p: [0, -3.9, 0] },
];
const EDGES: [number, number][] = [[0, 2], [1, 2], [2, 3], [2, 4], [2, 5], [0, 1], [3, 5], [4, 5], [0, 3], [1, 4]];
const HOT_NODE = 4;

const VIEWS: View[] = [
  { p: [0, 0.6, 17.5], t: [0, 0, 0], w: 16 },
  { p: [0, 0, 19], t: [0, 0, 0], w: 13 },
  { p: [0, 6.5, 15.5], t: [0, -0.3, 0], w: 13.5 },
  { p: [0, 3.2, 12], t: [0, -1.8, -2], w: 13 },
  { p: [0, 8, 10.5], t: [0, -0.5, 0], w: 11 },
  { p: [0, 0.6, 17], t: [0, 0.2, 0], w: 16 },
  { p: [0, 2.4, 15], t: [0, 0, 0], w: 16 },
  { p: [3.5, 0.9, 16], t: [0.8, -0.4, 0], w: 16 },
];

const VS = /* glsl */ `
  attribute vec3 aColor; attribute float aAlpha; attribute float aSize; attribute float aSeed;
  uniform float uTime, uSize, uPR, uJitter;
  varying vec3 vColor; varying float vAlpha;
  void main() {
    vec3 p = position;
    float s = aSeed * 6.2831;
    p += vec3(sin(uTime * 0.7 + s * 3.1), cos(uTime * 0.55 + s * 5.3), sin(uTime * 0.45 + s * 1.7)) * uJitter;
    vec4 mv = modelViewMatrix * vec4(p, 1.0);
    gl_Position = projectionMatrix * mv;
    gl_PointSize = uSize * aSize * uPR / -mv.z;
    vColor = aColor; vAlpha = aAlpha;
  }`;
const FS = /* glsl */ `
  uniform float uOpacity;
  varying vec3 vColor; varying float vAlpha;
  void main() {
    float d = length(gl_PointCoord - 0.5);
    if (d > 0.5) discard;
    float a = 1.0 - smoothstep(0.3, 0.5, d);
    gl_FragColor = vec4(vColor, a * vAlpha * uOpacity);
  }`;

function rng(seed: number) {
  return () => {
    seed |= 0;
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
const smooth = (a: number, b: number, x: number) => {
  const t = Math.min(1, Math.max(0, (x - a) / (b - a)));
  return t * t * (3 - 2 * t);
};
const clamp01 = (x: number) => (x < 0 ? 0 : x > 1 ? 1 : x);

export default function OperationField({
  storyRef,
  onState,
  children,
}: {
  storyRef: RefObject<HTMLElement | null>;
  onState: (state: number) => void;
  children?: ReactNode;
}) {
  const stageRef = useRef<HTMLDivElement>(null);
  const labelsRef = useRef<HTMLDivElement>(null);
  const onStateRef = useRef(onState);
  onStateRef.current = onState;
  const [flat, setFlat] = useState(false);

  useEffect(() => {
    const stage = stageRef.current;
    const layer = labelsRef.current;
    const story = storyRef.current;
    if (!stage || !layer || !story) return;
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    } catch {
      setFlat(true);
      return;
    }
    let W = stage.clientWidth;
    let H = stage.clientHeight;
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.setSize(W, H);
    renderer.setClearColor(0x000000, 0);
    stage.prepend(renderer.domElement);

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(40, W / H, 0.1, 200);
    const group = new THREE.Group();
    scene.add(group);

    const R = rng(11);
    const gauss = () => {
      let u = 0;
      while (u === 0) u = R();
      return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * R());
    };
    const dirOn = (): Vec => {
      const u = R() * 2 - 1, t = R() * Math.PI * 2, r = Math.sqrt(1 - u * u);
      return [r * Math.cos(t), u, r * Math.sin(t)];
    };
    const col = (h: string): Vec => {
      const c = new THREE.Color(h);
      return [c.r, c.g, c.b];
    };

    const N = W < 700 ? 5200 : 9000;
    const S = STATE_COUNT;
    const P: Float32Array[] = [], C: Float32Array[] = [], A: Float32Array[] = [];
    for (let s = 0; s < S; s++) {
      P.push(new Float32Array(N * 3));
      C.push(new Float32Array(N * 3));
      A.push(new Float32Array(N));
    }
    const put = (s: number, i: number, x: number, y: number, z: number, c: Vec, a: number) => {
      const j = i * 3;
      P[s][j] = x; P[s][j + 1] = y; P[s][j + 2] = z;
      C[s][j] = c[0]; C[s][j + 1] = c[1]; C[s][j + 2] = c[2];
      A[s][i] = a;
    };
    const seed = new Float32Array(N), swirl = new Float32Array(N * 3), size = new Float32Array(N);
    for (let i = 0; i < N; i++) {
      seed[i] = R();
      swirl[i * 3] = gauss() * 1.3; swirl[i * 3 + 1] = gauss() * 1.3; swirl[i * 3 + 2] = gauss() * 1.3;
      size[i] = 0.55 + R() * 0.9;
    }

    const labels: { s: number; p: Vec; el: HTMLSpanElement; hw: number }[] = [];
    layer.innerHTML = '';
    const addLabel = (s: number, text: string, p: Vec, hot = false) => {
      const el = document.createElement('span');
      el.className = `about-lbl${hot ? ' about-lbl--hot' : ''}`;
      el.textContent = text;
      layer.appendChild(el);
      labels.push({ s, p, el, hw: 0 });
    };

    // 0 — the operation, with the AI as a ring around it
    const CTRL: Vec[] = EDGES.map(([a, b], k) => {
      const p0 = NODES[a].p, p2 = NODES[b].p;
      return [(p0[0] + p2[0]) / 2, (p0[1] + p2[1]) / 2 + 0.35, (p0[2] + p2[2]) / 2 + (k % 2 ? 1.5 : -1.5)];
    });
    const edgePt = (k: number, u: number, out: Vec) => {
      const [a, b] = EDGES[k], p0 = NODES[a].p, p1 = CTRL[k], p2 = NODES[b].p, v = 1 - u;
      for (let d = 0; d < 3; d++) out[d] = v * v * p0[d] + 2 * v * u * p1[d] + u * u * p2[d];
      return out;
    };
    const kind = new Uint8Array(N), nodeOf = new Int8Array(N).fill(-1);
    const wsum = NODES.reduce((s, n) => s + (n.core ? 2.2 : 1), 0);
    const cNode = col('#1e3a8a'), cCore = col('#2563eb'), cEdge = col('#60a5fa'), cRing = col('#06b6d4');
    const tmp: Vec = [0, 0, 0];
    for (let i = 0; i < N; i++) {
      const f = i / N;
      if (f < 0.38) {
        let r = R() * wsum, k = 0;
        for (; k < NODES.length; k++) {
          r -= NODES[k].core ? 2.2 : 1;
          if (r <= 0) break;
        }
        k = Math.min(k, NODES.length - 1);
        const n = NODES[k], rad = n.core ? 0.95 : 0.62;
        let x: number, y: number, z: number;
        if (R() < 0.62) {
          const d = dirOn(), rr = rad * (1 + gauss() * 0.03);
          x = d[0] * rr; y = d[1] * rr; z = d[2] * rr;
        } else {
          x = gauss() * rad * 0.4; y = gauss() * rad * 0.4; z = gauss() * rad * 0.4;
        }
        put(0, i, n.p[0] + x, n.p[1] + y, n.p[2] + z, n.core ? cCore : cNode, 0.9);
        kind[i] = 0;
        nodeOf[i] = k;
      } else if (f < 0.72) {
        edgePt(Math.floor(R() * EDGES.length), R(), tmp);
        put(0, i, tmp[0] + gauss() * 0.05, tmp[1] + gauss() * 0.05, tmp[2] + gauss() * 0.05, cEdge, 0.55);
        kind[i] = 1;
      } else {
        const th = R() * Math.PI * 2, rr = 7.4 + gauss() * 0.1, yy = rr * Math.sin(th);
        put(0, i, rr * Math.cos(th), yy * 0.7 + gauss() * 0.05, -yy * 0.71 + gauss() * 0.05, cRing, 0.85);
        kind[i] = 2;
      }
    }
    NODES.forEach((n) => addLabel(0, n.n, [n.p[0], n.p[1] + (n.core ? 1.45 : 1.1), n.p[2]]));
    const ra = -0.35, rl = 7.4 * Math.sin(ra);
    addLabel(0, 'AI', [7.4 * Math.cos(ra), rl * 0.7, -rl * 0.71], true);

    // 1 — noise, with a small useful core
    const cNoise = col('#94a3b8'), cUseful = col('#0891b2'), UC: Vec = [2.6, 0.6, 2];
    for (let i = 0; i < N; i++) {
      if (seed[i] < 0.045) {
        const d = dirOn(), rr = 0.7 * (R() < 0.7 ? 1 : Math.cbrt(R()));
        put(1, i, UC[0] + d[0] * rr, UC[1] + d[1] * rr, UC[2] + d[2] * rr, cUseful, 1);
      } else {
        put(1, i, gauss() * 9, gauss() * 5.5, gauss() * 6 - 2, cNoise, 0.42);
      }
    }
    addLabel(1, 'Useful AI', [UC[0], UC[1] + 1.3, UC[2]], true);

    // 2 — four layers on one spine
    const LAYERS = [
      { n: 'Business', y: 3.3, c: col('#1e3a8a') },
      { n: 'Product', y: 1.1, c: col('#2563eb') },
      { n: 'AI', y: -1.1, c: col('#06b6d4') },
      { n: 'Infrastructure', y: -3.3, c: col('#60a5fa') },
    ];
    const cSpine = col('#0f172a');
    for (let i = 0; i < N; i++) {
      if (seed[i] > 0.86) {
        put(2, i, gauss() * 0.12, -3.9 + R() * 7.8, gauss() * 0.12, cSpine, 0.85);
      } else {
        const L = LAYERS[i % 4], th = R() * Math.PI * 2;
        if (R() < 0.4) {
          const rr = 4.6 + gauss() * 0.03;
          put(2, i, Math.cos(th) * rr, L.y + gauss() * 0.02, Math.sin(th) * rr, L.c, 0.9);
        } else {
          const r = 4.6 * Math.sqrt(R());
          put(2, i, Math.cos(th) * r, L.y + gauss() * 0.03, Math.sin(th) * r, L.c, 0.3);
        }
      }
    }
    LAYERS.forEach((L) => addLabel(2, L.n, [5.9, L.y, 0.6]));

    // 3 — a landscape: the work itself
    const cols = Math.round(Math.sqrt(N * 2.2)), rows = Math.ceil(N / cols);
    const cLow = new THREE.Color('#bfdbfe'), cHigh = new THREE.Color('#1d4ed8'), cT = new THREE.Color();
    for (let i = 0; i < N; i++) {
      const c = i % cols, r = Math.floor(i / cols);
      const x = (c / (cols - 1) - 0.5) * 16, z = (r / Math.max(1, rows - 1) - 0.5) * 13 - 1;
      const h =
        0.9 * Math.sin(x * 0.35 + 0.5) * Math.cos(z * 0.45) + 0.45 * Math.sin(x * 0.9 + z * 0.6) + 0.22 * Math.sin(x * 1.7 - z * 1.3);
      cT.copy(cLow).lerp(cHigh, clamp01((h + 1.4) / 2.8));
      put(3, i, x, -2.6 + h, z, [cT.r, cT.g, cT.b], 0.3 + 0.6 * clamp01((z + 7.5) / 13));
    }

    // 4 — six areas as a honeycomb
    const AREAS = ['Operations', 'Customer', 'Knowledge', 'Decision making', 'AI systems', 'Private AI'];
    const cellC = ['#1e3a8a', '#1d4ed8', '#2563eb', '#3b82f6', '#0891b2', '#06b6d4'].map(col);
    const HR = 1.5, HH = 1.6;
    const hexV = (k: number) => [Math.cos((k * Math.PI) / 3) * HR, Math.sin((k * Math.PI) / 3) * HR];
    const centers = AREAS.map((_, k) => {
      const a = (k * Math.PI) / 3 + Math.PI / 6;
      return [Math.cos(a) * 3.05, Math.sin(a) * 3.05];
    });
    for (let i = 0; i < N; i++) {
      const k = i % 6, [cx, cz] = centers[k], c = cellC[k], m = R();
      if (m < 0.45) {
        const e = Math.floor(R() * 6), a = hexV(e), b = hexV((e + 1) % 6), u = R();
        put(4, i, cx + a[0] + (b[0] - a[0]) * u, R() < 0.6 ? HH / 2 : -HH / 2, cz + a[1] + (b[1] - a[1]) * u, c, 0.9);
      } else if (m < 0.58) {
        const a = hexV(Math.floor(R() * 6));
        put(4, i, cx + a[0], -HH / 2 + R() * HH, cz + a[1], c, 0.75);
      } else {
        let x: number, z: number;
        do {
          x = (R() * 2 - 1) * HR;
          z = (R() * 2 - 1) * HR;
        } while (Math.abs(z) > HR * 0.866 || Math.abs(x) * 0.866 + Math.abs(z) * 0.5 > HR * 0.866);
        put(4, i, cx + x, HH / 2 + gauss() * 0.02, cz + z, c, 0.28);
      }
    }
    AREAS.forEach((n, k) => addLabel(4, n, [centers[k][0], HH / 2 + 0.7, centers[k][1]]));

    // 5 — the engagement: loose at diagnosis, solid once you own it
    const path = (u: number): Vec => [-6.4 + 13 * u, -2.5 + 5 * Math.pow(u, 1.15), Math.sin(u * Math.PI) * 1.5];
    const ST = [0.03, 0.35, 0.66, 0.97].map(path);
    const cPath = col('#93c5fd'), cS = ['#94a3b8', '#60a5fa', '#2563eb', '#0891b2'].map(col);
    for (let i = 0; i < N; i++) {
      if (seed[i] < 0.28) {
        const p = path(R());
        put(5, i, p[0] + gauss() * 0.05, p[1] + gauss() * 0.05, p[2] + gauss() * 0.05, cPath, 0.6);
        continue;
      }
      const k = i % 4, c = ST[k];
      if (k === 3) {
        const h = 0.8, ax = Math.floor(R() * 3), q: Vec = [(R() * 2 - 1) * h, (R() * 2 - 1) * h, (R() * 2 - 1) * h];
        q[ax] = (R() < 0.5 ? -1 : 1) * h;
        put(5, i, c[0] + q[0], c[1] + q[1], c[2] + q[2], cS[3], 0.95);
      } else {
        const d = dirOn();
        const r = k === 0 ? 1.5 * Math.cbrt(R()) : k === 1 ? 1.0 + gauss() * 0.14 : R() < 0.75 ? 0.85 : 0.85 * Math.cbrt(R());
        put(5, i, c[0] + d[0] * r, c[1] + d[1] * r, c[2] + d[2] * r, cS[k], [0.45, 0.7, 0.9][k]);
      }
    }
    ['01 Diagnose', '02 Prove', '03 Ship', '04 Own'].forEach((n, k) =>
      addLabel(5, n, [ST[k][0], ST[k][1] + (k === 0 ? 2.0 : 1.55), ST[k][2]], k === 3),
    );

    // 6 — cloud, private, hybrid
    const PUFFS = [[-0.9, -0.2, 0, 0.8], [0, 0.35, 0, 1.05], [0.95, -0.1, 0, 0.85], [-0.35, -0.45, 0.35, 0.7], [0.45, -0.5, -0.25, 0.7]];
    const cCloud = col('#60a5fa'), cBox = col('#1e3a8a'), cCoreD = col('#06b6d4');
    const cloudPt = (cx: number, sc: number): Vec => {
      const p = PUFFS[Math.floor(R() * PUFFS.length)], d = dirOn();
      return [cx + (p[0] + d[0] * p[3]) * sc, (p[1] + d[1] * p[3]) * sc, (p[2] + d[2] * p[3]) * sc];
    };
    const boxEdge = (cx: number, h: number): Vec => {
      const e = Math.floor(R() * 12), u = (R() * 2 - 1) * h, a = (e & 1 ? 1 : -1) * h, b = (e & 2 ? 1 : -1) * h, ax = Math.floor(e / 4);
      return ax === 0 ? [cx + u, a, b] : ax === 1 ? [cx + a, u, b] : [cx + a, b, u];
    };
    for (let i = 0; i < N; i++) {
      const g = i % 3;
      if (g === 0) {
        const p = cloudPt(-5.4, 1.15);
        put(6, i, p[0], p[1], p[2], cCloud, 0.7);
      } else if (g === 1) {
        if (R() < 0.6) {
          const p = boxEdge(0, 1.3);
          put(6, i, p[0], p[1], p[2], cBox, 0.9);
        } else {
          const d = dirOn(), r = 0.5 * Math.cbrt(R());
          put(6, i, d[0] * r, d[1] * r, d[2] * r, cCoreD, 1);
        }
      } else if (R() < 0.5) {
        const p = cloudPt(4.6, 0.75);
        put(6, i, p[0], p[1] + 0.3, p[2], cCloud, 0.7);
      } else {
        const p = boxEdge(6.5, 0.85);
        put(6, i, p[0], p[1] - 0.2, p[2], cBox, 0.9);
      }
    }
    addLabel(6, 'Cloud', [-5.4, -2.2, 0]);
    addLabel(6, 'Private', [0, -2.2, 0]);
    addLabel(6, 'Hybrid', [5.5, -2.2, 0]);

    // 7 — the operation again, one part lit
    const cHot = col('#06b6d4');
    for (let i = 0; i < N; i++) {
      const j = i * 3, hot = kind[i] === 0 && nodeOf[i] === HOT_NODE;
      P[7][j] = P[0][j]; P[7][j + 1] = P[0][j + 1]; P[7][j + 2] = P[0][j + 2];
      C[7][j] = hot ? cHot[0] : C[0][j];
      C[7][j + 1] = hot ? cHot[1] : C[0][j + 1];
      C[7][j + 2] = hot ? cHot[2] : C[0][j + 2];
      A[7][i] = hot ? 1 : kind[i] === 2 ? 0.5 : A[0][i] * 0.28;
    }
    const hp = NODES[HOT_NODE].p;
    addLabel(7, 'The part that should work better', [hp[0], hp[1] + 1.2, hp[2]], true);

    // the field
    const geo = new THREE.BufferGeometry();
    const pos = new Float32Array(P[reduce ? 0 : 1]), clr = new Float32Array(C[reduce ? 0 : 1]), alp = new Float32Array(A[reduce ? 0 : 1]);
    geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    geo.setAttribute('aColor', new THREE.BufferAttribute(clr, 3));
    geo.setAttribute('aAlpha', new THREE.BufferAttribute(alp, 1));
    geo.setAttribute('aSize', new THREE.BufferAttribute(size, 1));
    geo.setAttribute('aSeed', new THREE.BufferAttribute(seed, 1));
    const mat = new THREE.ShaderMaterial({
      vertexShader: VS,
      fragmentShader: FS,
      transparent: true,
      depthWrite: false,
      uniforms: {
        uTime: { value: 0 },
        uSize: { value: 54 },
        uPR: { value: renderer.getPixelRatio() },
        uJitter: { value: reduce ? 0 : 0.035 },
        uOpacity: { value: 1 },
      },
    });
    group.add(new THREE.Points(geo, mat));

    // data travelling the operation's connections
    const PK = W < 700 ? 90 : 170;
    const pkGeo = new THREE.BufferGeometry();
    const pkPos = new Float32Array(PK * 3), pkCol = new Float32Array(PK * 3), pkA = new Float32Array(PK).fill(1);
    const pkS = new Float32Array(PK), pkSeed = new Float32Array(PK);
    const pkE: number[] = [], pkOff: number[] = [], pkSp: number[] = [];
    const cPk = col('#1d4ed8');
    for (let i = 0; i < PK; i++) {
      pkE.push(Math.floor(R() * EDGES.length));
      pkOff.push(R());
      pkSp.push((0.06 + R() * 0.08) * (R() < 0.5 ? 1 : -1));
      pkCol.set(cPk, i * 3);
      pkS[i] = 1 + R() * 0.6;
      pkSeed[i] = R();
    }
    pkGeo.setAttribute('position', new THREE.BufferAttribute(pkPos, 3));
    pkGeo.setAttribute('aColor', new THREE.BufferAttribute(pkCol, 3));
    pkGeo.setAttribute('aAlpha', new THREE.BufferAttribute(pkA, 1));
    pkGeo.setAttribute('aSize', new THREE.BufferAttribute(pkS, 1));
    pkGeo.setAttribute('aSeed', new THREE.BufferAttribute(pkSeed, 1));
    const pkMat = mat.clone();
    pkMat.uniforms.uSize.value = 120;
    pkMat.uniforms.uJitter.value = 0;
    const packets = new THREE.Points(pkGeo, pkMat);
    group.add(packets);

    // framing: each shape sits in the space beside the text column
    let F: Framed[] = [];
    const fitAll = () => {
      const column = story.querySelector('.about-col');
      F = VIEWS.map((v) => frameView(v, camera, W, H, column));
    };
    fitAll();

    // scroll → a continuous state index that holds while a chapter is read
    const chapters = Array.from(story.querySelectorAll<HTMLElement>('[data-state]'));
    // Wide: a chapter's centre is its anchor. Narrow: the panel starts halfway
    // down the chapter's first screen and runs long, so anchor on where it
    // starts; the new shape is in place as the panel comes into view.
    const scrollState = () => {
      const mid = window.innerHeight / 2;
      const narrow = W < WIDE_MIN;
      const c = chapters.map((el) => {
        const r = el.getBoundingClientRect();
        return narrow ? r.top + window.innerHeight * 0.45 : r.top + r.height / 2;
      });
      if (!c.length || mid <= c[0]) return 0;
      if (mid >= c[c.length - 1]) return c.length - 1;
      for (let k = 0; k < c.length - 1; k++) {
        if (mid < c[k + 1]) return k + smooth(0.2, 0.8, (mid - c[k]) / (c[k + 1] - c[k]));
      }
      return 0;
    };

    const morph = (p: number) => {
      const i0 = Math.min(S - 1, Math.max(0, Math.floor(p))), i1 = Math.min(S - 1, i0 + 1), f = p - i0;
      const a = P[i0], b = P[i1], ca = C[i0], cb = C[i1], aa = A[i0], ab = A[i1];
      for (let i = 0; i < N; i++) {
        let t = f * 1.5 - seed[i] * 0.5;
        t = t < 0 ? 0 : t > 1 ? 1 : t;
        t = t * t * (3 - 2 * t);
        const w = Math.sin(t * Math.PI), j = i * 3;
        for (let d = 0; d < 3; d++) {
          pos[j + d] = a[j + d] + (b[j + d] - a[j + d]) * t + swirl[j + d] * w;
          clr[j + d] = ca[j + d] + (cb[j + d] - ca[j + d]) * t;
        }
        alp[i] = aa[i] + (ab[i] - aa[i]) * t;
      }
      geo.attributes.position.needsUpdate = true;
      geo.attributes.aColor.needsUpdate = true;
      geo.attributes.aAlpha.needsUpdate = true;
    };

    let mx = 0, my = 0, sx = 0, sy = 0;
    const onMove = (e: MouseEvent) => {
      mx = (e.clientX / window.innerWidth) * 2 - 1;
      my = (e.clientY / window.innerHeight) * 2 - 1;
    };
    window.addEventListener('mousemove', onMove);

    let visible = true;
    const io = new IntersectionObserver(([entry]) => {
      visible = entry.isIntersecting;
    });
    io.observe(stage);

    const cp = new THREE.Vector3(), ct = new THREE.Vector3(), v = new THREE.Vector3();
    const t0 = performance.now();
    let intro = !reduce;
    let pv = reduce ? 0 : 1;
    let lastP = -1, lastState = -1, last = t0, raf = 0;

    const frame = (now: number) => {
      raf = requestAnimationFrame(frame);
      if (!visible) {
        last = now;
        return;
      }
      const dt = Math.min(0.05, (now - last) / 1000);
      last = now;
      const time = reduce ? 0 : (now - t0) / 1000;
      const target = scrollState();
      if (intro) {
        // the one load moment: the noise settles into the operation
        const q = smooth(0, 1, (now - t0) / 2600);
        pv = 1 + (target - 1) * q;
        if (q >= 1) intro = false;
      } else {
        pv += (target - pv) * (reduce ? 1 : Math.min(1, dt * 5));
      }
      if (Math.abs(pv - lastP) > 1e-4) {
        morph(pv);
        lastP = pv;
      }

      const i0 = Math.min(S - 1, Math.floor(pv)), i1 = Math.min(S - 1, i0 + 1), f = smooth(0, 1, pv - i0);
      cp.lerpVectors(F[i0].p, F[i1].p, f);
      ct.lerpVectors(F[i0].t, F[i1].t, f);
      if (!reduce) {
        sx += (mx - sx) * 0.04;
        sy += (my - sy) * 0.04;
      }
      camera.position.set(cp.x + sx * 0.7, cp.y - sy * 0.45, cp.z);
      camera.lookAt(ct);
      camera.updateMatrixWorld();
      group.rotation.y = reduce ? 0 : Math.sin(time * 0.12) * 0.16;
      group.updateMatrixWorld();
      mat.uniforms.uTime.value = time;

      const w0 = Math.max(0, 1 - Math.abs(pv) * 2.5) + Math.max(0, 1 - Math.abs(pv - 7) * 2.5);
      packets.visible = w0 > 0.01;
      if (packets.visible) {
        pkMat.uniforms.uOpacity.value = Math.min(1, w0);
        for (let i = 0; i < PK; i++) {
          let u = (pkOff[i] + time * pkSp[i]) % 1;
          if (u < 0) u += 1;
          edgePt(pkE[i], u, tmp);
          pkPos.set(tmp, i * 3);
        }
        pkGeo.attributes.position.needsUpdate = true;
      }

      for (const L of labels) {
        const op = Math.max(0, 1 - Math.abs(pv - L.s) * 3);
        if (op < 0.02) {
          L.el.style.opacity = '0';
          continue;
        }
        v.set(L.p[0], L.p[1], L.p[2]).applyMatrix4(group.matrixWorld).project(camera);
        // keep the whole label on screen (narrow screens crop the widest shapes)
        if (!L.hw) L.hw = L.el.offsetWidth / 2;
        const lx = Math.min(W - L.hw - 8, Math.max(L.hw + 8, ((v.x + 1) / 2) * W));
        L.el.style.transform = `translate(${lx.toFixed(1)}px, ${(((1 - v.y) / 2) * H).toFixed(1)}px) translate(-50%, -50%)`;
        L.el.style.opacity = op.toFixed(3);
      }

      const state = Math.round(Math.min(S - 1, Math.max(0, pv)));
      if (state !== lastState) {
        lastState = state;
        onStateRef.current(state);
      }
      renderer.render(scene, camera);
    };
    raf = requestAnimationFrame(frame);

    const onResize = () => {
      W = stage.clientWidth;
      H = stage.clientHeight;
      renderer.setSize(W, H);
      camera.aspect = W / H;
      camera.updateProjectionMatrix();
      fitAll();
    };
    window.addEventListener('resize', onResize);
    document.fonts?.ready.then(() => fitAll());

    return () => {
      cancelAnimationFrame(raf);
      io.disconnect();
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('resize', onResize);
      geo.dispose();
      pkGeo.dispose();
      mat.dispose();
      pkMat.dispose();
      renderer.dispose();
      renderer.domElement.remove();
      layer.innerHTML = '';
    };
  }, [storyRef]);

  return (
    <div className={`about-stage${flat ? ' about-stage--flat' : ''}`} ref={stageRef} aria-hidden={flat || undefined}>
      <div className="about-scrim" aria-hidden="true" />
      <div className="about-labels" ref={labelsRef} aria-hidden="true" />
      {!flat && children}
    </div>
  );
}
