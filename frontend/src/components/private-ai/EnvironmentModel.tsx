/**
 * The Private AI page's picture: a white architectural model of the CLIENT's
 * environment. Every labelled part is something the client owns — their team,
 * application, model, data and hardware — inside a blue security boundary.
 * Nothing in it is a BMV facility.
 *
 * Each chapter (`data-stage`) sets what is built and where the camera stands:
 *   hero / why   everything, sealed; `why` rings the part each reason is about
 *   how1..how4   built in order: people and data, the stack, the boundary, the wiring
 *   compare      the provider's servers appear; the page's toggle decides whether
 *                requests leave through the wall (cloud) or stay inside (private)
 *   honest       both at once
 *   cta          close on the model
 *
 * The stage is sticky inside the story wrapper, like About's. Without WebGL it
 * is hidden and the chapters read as plain text; with reduced motion nothing
 * drifts, orbits or travels.
 */
import { useEffect, useRef, useState, type ReactNode, type RefObject } from 'react';
import * as THREE from 'three';
import { frameView, WIDE_MIN, type Framed, type View } from '../three/frameView';
import { addGround, addLights, BLUE, disposeScene, pinLabel, solidMaker } from '../three/maquette';

export type Stage = 'hero' | 'why' | 'how1' | 'how2' | 'how3' | 'how4' | 'compare' | 'honest' | 'cta';
export type Mode = 'cloud' | 'private';
type Part = 'team' | 'app' | 'model' | 'data' | 'racks' | 'boundary' | 'links' | 'cloud';
type Vec = [number, number, number];

/** The part each "why" reason is about, in the page's order (WHY in PrivateAIPage). */
const WHY_PARTS: Part[] = ['data', 'model', 'racks', 'boundary'];

const ALL: Record<Part, number> = { team: 1, app: 1, model: 1, data: 1, racks: 1, boundary: 1, links: 1, cloud: 0 };
type StageDef = Record<Part, number> & { mode: number | 'user'; view: keyof typeof VIEWS; halo?: Part | 'why' };
const STAGES: Record<Stage, StageDef> = {
  hero: { ...ALL, mode: 0, view: 'hero' },
  why: { ...ALL, mode: 0, view: 'why', halo: 'why' },
  how1: { ...ALL, app: 0, model: 0, racks: 0, boundary: 0, links: 0, mode: 0, view: 'how', halo: 'data' },
  how2: { ...ALL, app: 0, boundary: 0, links: 0, mode: 0, view: 'how', halo: 'model' },
  how3: { ...ALL, app: 0, links: 0, mode: 0, view: 'how', halo: 'boundary' },
  how4: { ...ALL, mode: 0, view: 'how', halo: 'app' },
  compare: { ...ALL, cloud: 1, mode: 'user', view: 'compare' },
  honest: { ...ALL, cloud: 1, mode: 0.5, view: 'honest' },
  cta: { ...ALL, mode: 0, view: 'cta' },
};
const VIEWS = {
  hero: { p: [12, 9, 15], t: [0.6, 1.6, 0], w: 15.5 },
  why: { p: [9, 12, 14], t: [0.8, 1.4, 0], w: 15 },
  how: { p: [9, 10.5, 16], t: [0.6, 1.4, 0], w: 15.5 },
  compare: { p: [6, 15, 27], t: [6.5, 3, -3], w: 30 },
  honest: { p: [7, 19, 31], t: [6.5, 3, -3], w: 32 },
  cta: { p: [7, 5.5, 11], t: [0.8, 1.6, 0], w: 15 },
} satisfies Record<string, View>;

/** Floor ring for a highlighted part: x, z, radius. The boundary glows instead. */
const HALO: Partial<Record<Part, Vec>> = {
  data: [4.6, 1.6, 1.4],
  model: [1.8, -0.2, 1.6],
  racks: [3.9, -2.6, 1.9],
  app: [-1.6, 1.8, 1.6],
  team: [-5, 2.1, 1.4],
};

const LABELS: { part: Part; text: string; p: Vec }[] = [
  { part: 'team', text: 'Your team', p: [-5, 1.95, 2.1] },
  { part: 'app', text: 'Your application', p: [-1.6, 3.0, 1.8] },
  { part: 'model', text: 'Private model', p: [1.2, 4.05, -0.2] },
  { part: 'data', text: 'Your data', p: [4.6, 2.05, 1.6] },
  { part: 'racks', text: 'Your hardware', p: [4.8, 2.8, -2.6] },
  { part: 'boundary', text: 'Your environment', p: [-6.4, 5.35, 4.7] },
  { part: 'cloud', text: 'Provider’s servers', p: [18, 9.7, -9] },
];


export default function EnvironmentModel({
  storyRef,
  why,
  mode,
  onStage,
  children,
}: {
  storyRef: RefObject<HTMLElement | null>;
  why: number;
  mode: Mode;
  onStage: (stage: Stage) => void;
  children?: ReactNode;
}) {
  const stageRef = useRef<HTMLDivElement>(null);
  const labelsRef = useRef<HTMLDivElement>(null);
  const live = useRef({ why, mode, onStage });
  live.current = { why, mode, onStage };
  const [flat, setFlat] = useState(false);

  useEffect(() => {
    const stageEl = stageRef.current;
    const layer = labelsRef.current;
    const story = storyRef.current;
    if (!stageEl || !layer || !story) return;
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    } catch {
      setFlat(true);
      return;
    }
    let W = stageEl.clientWidth;
    let H = stageEl.clientHeight;
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.setSize(W, H);
    renderer.setClearColor(0x000000, 0);
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    stageEl.prepend(renderer.domElement);

    const scene = new THREE.Scene();
    scene.fog = new THREE.Fog(0xf5f9ff, 38, 90);
    const camera = new THREE.PerspectiveCamera(40, W / H, 0.1, 400);

    addLights(scene, { left: -18, right: 26, top: 18, bottom: -18 });
    addGround(scene);
    const { solid, white, edgeMat } = solidMaker();
    const vis: Record<Part, number> = { team: 0, app: 0, model: 0, data: 0, racks: 0, boundary: 0, links: 0, cloud: 0 };
    const anchor = (x: number, z: number) => {
      const g = new THREE.Group();
      g.position.set(x, 0, z);
      scene.add(g);
      return g;
    };

    // your team
    const team = anchor(-5, 2.1);
    for (const [x, z] of [[-0.6, -0.3], [0.35, -0.55], [-0.1, 0.55]]) {
      solid(new THREE.CylinderGeometry(0.2, 0.3, 0.85, 18), team, x, 0.425, z);
      solid(new THREE.SphereGeometry(0.21, 22, 16), team, x, 1.08, z, { edges: false });
    }

    // your application: a screen showing a plain UI
    const app = anchor(-1.6, 1.8);
    app.rotation.y = 0.32;
    solid(new THREE.CylinderGeometry(0.42, 0.46, 0.06, 32), app, 0, 0.03, 0);
    solid(new THREE.CylinderGeometry(0.05, 0.05, 1.0, 12), app, 0, 0.55, 0, { edges: false });
    const sc = document.createElement('canvas');
    sc.width = 512;
    sc.height = 320;
    const g2 = sc.getContext('2d');
    if (g2) {
      g2.fillStyle = '#f8fafc';
      g2.fillRect(0, 0, 512, 320);
      g2.fillStyle = '#0f172a';
      g2.fillRect(0, 0, 512, 30);
      g2.fillStyle = '#dbe4f0';
      for (let i = 0; i < 6; i++) g2.fillRect(26, 58 + i * 40, 280 - (i % 3) * 64, 14);
      g2.fillStyle = '#2563eb';
      g2.fillRect(344, 58, 142, 96);
      g2.fillStyle = '#bfdbfe';
      g2.fillRect(344, 170, 142, 14);
      g2.fillRect(344, 196, 100, 14);
    }
    const screenTex = new THREE.CanvasTexture(sc);
    const screenMat = new THREE.MeshBasicMaterial({ map: screenTex });
    solid(new THREE.BoxGeometry(2.4, 1.5, 0.1), app, 0, 1.78, 0, { mat: [white, white, white, white, screenMat, white] });

    // the private model
    const model = anchor(1.8, -0.2);
    solid(new THREE.CylinderGeometry(0.95, 1.05, 0.5, 48), model, 0, 0.25, 0);
    const ico = solid(new THREE.IcosahedronGeometry(1.0, 0), model, 0, 2.05, 0, {
      mat: new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.6, flatShading: true, transparent: true, opacity: 0.92 }),
    });
    const blue = new THREE.MeshBasicMaterial({ color: BLUE });
    const core = new THREE.Mesh(new THREE.SphereGeometry(0.3, 24, 16), blue);
    core.position.y = 2.05;
    model.add(core);
    const orbit = new THREE.Mesh(new THREE.TorusGeometry(1.45, 0.014, 8, 120), new THREE.MeshBasicMaterial({ color: 0x06b6d4 }));
    orbit.position.y = 2.05;
    orbit.rotation.x = 1.25;
    model.add(orbit);

    // your data
    const data = anchor(4.6, 1.6);
    for (let k = 0; k < 3; k++) solid(new THREE.CylinderGeometry(0.85, 0.85, 0.42, 48), data, 0, 0.21 + k * 0.5, 0);

    // your hardware
    const racks = anchor(3.9, -2.6);
    for (const x of [-0.62, 0.62]) {
      solid(new THREE.BoxGeometry(1.1, 2.4, 0.9), racks, x, 1.2, 0);
      const pts: number[] = [];
      for (let y = 0.35; y < 2.3; y += 0.26) pts.push(x - 0.45, y, 0.452, x + 0.3, y, 0.452);
      const lg = new THREE.BufferGeometry();
      lg.setAttribute('position', new THREE.Float32BufferAttribute(pts, 3));
      racks.add(new THREE.LineSegments(lg, edgeMat));
      for (let y = 0.35; y < 2.3; y += 0.52) {
        const led = new THREE.Mesh(new THREE.BoxGeometry(0.07, 0.07, 0.02), blue);
        led.position.set(x + 0.4, y + 0.13, 0.46);
        racks.add(led);
      }
    }

    // your security boundary: solid blue when sealed, dashed grey when requests leave
    const boundary = anchor(0.3, 0.3);
    const BW = 13.6, BH = 5, BD = 8.8;
    const bGeo = new THREE.BoxGeometry(BW, BH, BD);
    const faceMat = new THREE.MeshBasicMaterial({ color: BLUE, transparent: true, opacity: 0.045, side: THREE.DoubleSide, depthWrite: false });
    const faces = new THREE.Mesh(bGeo, faceMat);
    faces.position.y = BH / 2;
    boundary.add(faces);
    const bEdges = new THREE.EdgesGeometry(bGeo);
    const sealMat = new THREE.LineBasicMaterial({ color: BLUE, transparent: true, opacity: 0.9 });
    const seal = new THREE.LineSegments(bEdges, sealMat);
    seal.position.y = BH / 2;
    boundary.add(seal);
    const openMat = new THREE.LineDashedMaterial({ color: 0x94a3b8, dashSize: 0.35, gapSize: 0.28, transparent: true, opacity: 0 });
    const open = new THREE.LineSegments(bEdges, openMat);
    open.computeLineDistances();
    open.position.y = BH / 2;
    boundary.add(open);

    // who talks to what
    const PT: Record<'team' | 'app' | 'model' | 'data' | 'racks', Vec> = {
      team: [-5, 1.0, 2.1],
      app: [-1.6, 1.78, 1.8],
      model: [1.8, 2.05, -0.2],
      data: [4.6, 1.2, 1.6],
      racks: [3.9, 1.6, -2.6],
    };
    const V = (a: Vec) => new THREE.Vector3(...a);
    const arc = (a: Vec, b: Vec, lift: number) =>
      new THREE.QuadraticBezierCurve3(V(a), V(a).add(V(b)).multiplyScalar(0.5).add(new THREE.Vector3(0, lift, 0)), V(b));
    const chain = new THREE.CurvePath<THREE.Vector3>();
    chain.add(arc(PT.team, PT.app, 1.0));
    chain.add(arc(PT.app, PT.model, 1.3));
    chain.add(arc(PT.model, PT.data, 1.1));
    const toRacks = arc(PT.model, PT.racks, 0.9);
    const linkMat = new THREE.LineBasicMaterial({ color: BLUE, transparent: true, opacity: 0 });
    for (const c of [chain, toRacks]) scene.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(c.getPoints(120)), linkMat));
    const route = new THREE.CatmullRomCurve3([V(PT.app), V([1.5, 4.4, 1.2]), V([7.1, 4.4, 0.6]), V([12.5, 7.2, -4.5]), V([18, 7.6, -9])]);
    const routeMat = new THREE.LineDashedMaterial({ color: 0x64748b, dashSize: 0.4, gapSize: 0.3, transparent: true, opacity: 0 });
    const routeLine = new THREE.Line(new THREE.BufferGeometry().setFromPoints(route.getPoints(160)), routeMat);
    routeLine.computeLineDistances();
    scene.add(routeLine);

    const pkGeo = new THREE.SphereGeometry(0.1, 14, 10);
    const packets: { m: THREE.Mesh; curve: THREE.Curve<THREE.Vector3>; inner: boolean; off: number; sp: number }[] = [];
    const addPackets = (curve: THREE.Curve<THREE.Vector3>, n: number, inner: boolean, sp: number) => {
      for (let i = 0; i < n; i++) {
        const m = new THREE.Mesh(pkGeo, blue);
        scene.add(m);
        packets.push({ m, curve, inner, off: (i / n) * 2, sp });
      }
    };
    addPackets(chain, 12, true, 0.09);
    addPackets(toRacks, 4, true, 0.16);
    addPackets(route, 10, false, 0.07);

    // the provider's servers, outside the boundary
    const cloud = anchor(18, -9);
    const cloudMat = new THREE.MeshStandardMaterial({ color: 0xe2e8f0, roughness: 0.95, transparent: true, opacity: 1 });
    for (const [x, y, z, r] of [[0, 7.6, 0, 1.5], [-1.5, 7.1, 0.3, 1.1], [1.6, 7.2, -0.2, 1.2], [0.5, 6.7, 1, 0.9], [-0.6, 6.8, -1, 1.0]]) {
      const m = new THREE.Mesh(new THREE.SphereGeometry(r, 28, 20), cloudMat);
      m.position.set(x, y, z);
      m.castShadow = true;
      cloud.add(m);
    }
    const groups: Partial<Record<Part, THREE.Group>> = { team, app, model, data, racks };

    // a ring on the floor under whatever the chapter is about
    const halo = new THREE.Group();
    scene.add(halo);
    const ringMat = new THREE.MeshBasicMaterial({ color: BLUE, transparent: true, opacity: 0, side: THREE.DoubleSide, depthWrite: false });
    const discMat = new THREE.MeshBasicMaterial({ color: BLUE, transparent: true, opacity: 0, side: THREE.DoubleSide, depthWrite: false });
    const ring = new THREE.Mesh(new THREE.RingGeometry(0.96, 1, 96), ringMat);
    ring.rotation.x = -Math.PI / 2;
    ring.position.y = 0.02;
    halo.add(ring);
    const disc = new THREE.Mesh(new THREE.CircleGeometry(0.96, 96), discMat);
    disc.rotation.x = -Math.PI / 2;
    disc.position.y = 0.015;
    halo.add(disc);
    const haloNow = { x: 0.3, z: 0.3, r: 8, o: 0 };

    layer.innerHTML = '';
    const labels = LABELS.map((l) => {
      const el = document.createElement('span');
      el.className = 'pai-lbl';
      el.textContent = l.text;
      layer.appendChild(el);
      return { ...l, el, hw: 0 };
    });

    // framing and stage detection
    let F = {} as Record<keyof typeof VIEWS, Framed>;
    const fitAll = () => {
      const column = story.querySelector('.pai-col');
      for (const k of Object.keys(VIEWS) as (keyof typeof VIEWS)[]) F[k] = frameView(VIEWS[k], camera, W, H, column);
    };
    fitAll();
    const chapters = Array.from(story.querySelectorAll<HTMLElement>('[data-stage]'));
    const currentStage = (): Stage => {
      // wide: a chapter is current once its top passes 55% of the screen;
      // narrow: once its panel (half a screen below its top) reaches 85%
      const line = window.innerHeight * (W < WIDE_MIN ? 0.35 : 0.55);
      let s: Stage = 'hero';
      for (const el of chapters) if (el.getBoundingClientRect().top <= line) s = el.dataset.stage as Stage;
      return s;
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
    io.observe(stageEl);

    const ease = (x: number) => 1 - Math.pow(1 - x, 3);
    const cp = new THREE.Vector3(), ct = new THREE.Vector3(), off = new THREE.Vector3(), v = new THREE.Vector3();
    const Y = new THREE.Vector3(0, 1, 0);
    const t0 = performance.now();
    let first = true, stage: Stage = 'hero', modeV = 0, glow = 0, far = 0, last = t0, raf = 0;

    const frame = (now: number) => {
      raf = requestAnimationFrame(frame);
      if (!visible) {
        last = now;
        return;
      }
      const dt = Math.min(0.05, (now - last) / 1000);
      last = now;
      const time = reduce ? 0 : (now - t0) / 1000;
      const k = reduce ? 1 : 1 - Math.exp(-dt * 4.5);

      const s = currentStage();
      if (s !== stage || first) {
        stage = s;
        live.current.onStage(s);
      }
      const def = STAGES[stage];
      const modeTarget = def.mode === 'user' ? (live.current.mode === 'cloud' ? 1 : 0) : def.mode;
      if (first) {
        // open complete: no build-up on load
        for (const p of Object.keys(vis) as Part[]) vis[p] = def[p];
        modeV = modeTarget;
      }
      for (const p of Object.keys(vis) as Part[]) vis[p] += (def[p] - vis[p]) * k;
      modeV += (modeTarget - modeV) * k;

      const hk = def.halo === 'why' ? WHY_PARTS[live.current.why] : def.halo;

      for (const [p, g] of Object.entries(groups) as [Part, THREE.Group][]) {
        g.visible = vis[p] > 0.003;
        g.scale.setScalar(Math.max(0.0001, ease(Math.min(1, vis[p]))));
      }
      const bv = vis.boundary;
      boundary.visible = bv > 0.003;
      boundary.scale.set(1, Math.max(0.0001, ease(bv)), 1);
      sealMat.opacity = 0.9 * bv * (1 - modeV);
      openMat.opacity = 0.9 * bv * modeV;
      glow += ((hk === 'boundary' ? 1 : 0) - glow) * k;
      faceMat.opacity = (0.045 + 0.04 * glow) * bv * (1 - modeV);
      linkMat.opacity = 0.75 * vis.links;
      cloud.visible = vis.cloud > 0.003;
      cloud.scale.setScalar(Math.max(0.0001, ease(vis.cloud)));
      cloudMat.opacity = 0.35 + 0.65 * modeV;
      const innerVis = modeV <= 0.5 ? 1 : (1 - modeV) * 2;
      const routeVis = modeV >= 0.5 ? 1 : modeV * 2;
      routeMat.opacity = 0.9 * vis.cloud * routeVis;
      for (const pk of packets) {
        const pv = pk.inner ? vis.links * innerVis : vis.links * vis.cloud * routeVis;
        pk.m.visible = pv > 0.02;
        if (!pk.m.visible) continue;
        let u = (pk.off + time * pk.sp) % 2;
        u = u > 1 ? 2 - u : u;
        pk.curve.getPointAt(Math.min(0.9999, Math.max(0, u)), pk.m.position);
        pk.m.scale.setScalar(pv);
      }
      ico.rotation.y = time * 0.25;
      ico.rotation.x = Math.sin(time * 0.3) * 0.2;
      orbit.rotation.z = time * 0.4;

      const h = hk ? HALO[hk] : undefined;
      if (h) {
        if (first) Object.assign(haloNow, { x: h[0], z: h[1], r: h[2] });
        haloNow.x += (h[0] - haloNow.x) * k;
        haloNow.z += (h[1] - haloNow.z) * k;
        haloNow.r += (h[2] - haloNow.r) * k;
      }
      haloNow.o += ((h ? 1 : 0) - haloNow.o) * k;
      halo.position.set(haloNow.x, 0, haloNow.z);
      halo.scale.setScalar(haloNow.r * (reduce ? 1 : 1 + Math.sin(time * 2.4) * 0.04));
      ringMat.opacity = 0.85 * haloNow.o;
      discMat.opacity = 0.07 * haloNow.o;

      const view = F[def.view];
      const farTarget = def.view === 'compare' || def.view === 'honest' ? 1 : 0;
      far += (farTarget - far) * k;
      if (first) {
        far = farTarget;
        cp.copy(view.p);
        ct.copy(view.t);
      }
      const kc = reduce ? 1 : 1 - Math.exp(-dt * 2.2);
      cp.lerp(view.p, kc);
      ct.lerp(view.t, kc);
      if (!reduce) {
        sx += (mx - sx) * 0.04;
        sy += (my - sy) * 0.04;
      }
      off.copy(cp).sub(ct).applyAxisAngle(Y, (reduce ? 0 : Math.sin(time * 0.07) * 0.1) + sx * 0.08);
      camera.position.copy(ct).add(off);
      camera.position.y -= sy * 0.5;
      camera.lookAt(ct);
      camera.updateMatrixWorld();

      for (const L of labels) {
        let op = Math.min(1, Math.max(0, vis[L.part]));
        if (L.part === 'cloud') op *= 0.5 + 0.5 * modeV;
        else if (L.part !== 'boundary') op *= 1 - far;
        L.el.classList.toggle('pai-lbl--hot', hk === L.part);
        pinLabel(L.el, v.set(...L.p), camera, W, H, op, L);
      }

      first = false;
      renderer.render(scene, camera);
    };
    raf = requestAnimationFrame(frame);

    const onResize = () => {
      W = stageEl.clientWidth;
      H = stageEl.clientHeight;
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
      disposeScene(scene);
      renderer.dispose();
      renderer.domElement.remove();
      layer.innerHTML = '';
    };
  }, [storyRef]);

  return (
    <div className={`pai-stage${flat ? ' pai-stage--flat' : ''}`} ref={stageRef}>
      <div className="pai-scrim" aria-hidden="true" />
      <div className="pai-labels" ref={labelsRef} aria-hidden="true" />
      {!flat && children}
    </div>
  );
}
