/**
 * The landing page's example week, assembled in 3D.
 *
 * Loose dots fly in and settle into one studio's week: 6 days x 6 classes x
 * 12 reformer spots. The 6pm and 7pm columns then lift and turn deep blue, the
 * waiting-list rings drop in as hollow dots in front of them, and only then
 * does the finding appear (the parent listens through `onReveal`). Nothing is
 * varied that the owner did not say: about 10 of 12 in a daytime class, every
 * evening full.
 *
 * Without WebGL — or with reduced motion asked for — the same week is drawn
 * flat and the finding shows straight away.
 */
import { useEffect, useRef, useState } from 'react';
import * as THREE from 'three';

const TIMES = ['7am', '9:30', '12pm', '4pm', '6pm', '7pm'];
const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const WAITING = 3;

function FlatWeek() {
  return (
    <div className="home-flat" aria-hidden="true">
      <div className="home-flat-row">
        <span />
        {TIMES.map((t, i) => (
          <span key={t} className={`home-flat-t${i >= 4 ? ' eve' : ''}`}>{t}</span>
        ))}
      </div>
      {DAYS.map((d) => (
        <div className="home-flat-row" key={d}>
          <span className="home-flat-d">{d}</span>
          {TIMES.map((t, i) => {
            const eve = i >= 4;
            return (
              <span key={t} className={`home-flat-dots${eve ? ' eve' : ''}`}>
                {Array.from({ length: 12 }, (_, k) => (
                  <i key={k} className={k < (eve ? 12 : 10) ? 'on' : ''} />
                ))}
                {eve && Array.from({ length: WAITING }, (_, k) => <i key={`w${k}`} className="wait" />)}
              </span>
            );
          })}
        </div>
      ))}
    </div>
  );
}

export default function WeekScene({ onReveal }: { onReveal: () => void }) {
  const stageRef = useRef<HTMLDivElement>(null);
  const labelsRef = useRef<HTMLDivElement>(null);
  const noteRef = useRef<HTMLParagraphElement>(null);
  const revealRef = useRef(onReveal);
  revealRef.current = onReveal;
  const [flat, setFlat] = useState(false);

  useEffect(() => {
    const stage = stageRef.current;
    const labels = labelsRef.current;
    const note = noteRef.current;
    if (!stage || !labels || !note) return;
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    } catch {
      setFlat(true);
      revealRef.current();
      return;
    }

    let W = stage.clientWidth;
    let H = stage.clientHeight;
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.setSize(W, H);
    stage.prepend(renderer.domElement);

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(20, W / H, 0.1, 100);
    scene.add(new THREE.HemisphereLight(0xffffff, 0xcfdcff, 1.25));
    const sun = new THREE.DirectionalLight(0xffffff, 1.35);
    sun.position.set(-3, 8, 5);
    scene.add(sun);

    const COLS = 6, ROWS = 6, PER = 12, SX = 0.21, SZ = 0.21;
    const CPX = 4 * SX + 0.5, RPZ = 3 * SZ + 0.42;
    const width = (COLS - 1) * CPX, depth = (ROWS - 1) * RPZ;
    const cellOrigin = (c: number, r: number) => new THREE.Vector3(c * CPX - width / 2, 0, r * RPZ - depth / 2);
    const isEve = (c: number) => c >= 4;

    const light = new THREE.Color('#9DBDFB');
    const empty = new THREE.Color('#E3EAF8');
    const deep = new THREE.Color('#1E3FB3');

    const spotGeo = new THREE.SphereGeometry(0.072, 18, 14);
    const spotMat = new THREE.MeshStandardMaterial({ roughness: 0.35, metalness: 0.05 });
    const N = ROWS * COLS * PER;
    const spots = new THREE.InstancedMesh(spotGeo, spotMat, N);
    scene.add(spots);
    const target: THREE.Vector3[] = [], from: THREE.Vector3[] = [], delay: number[] = [], eve: boolean[] = [];
    let i = 0;
    for (let r = 0; r < ROWS; r++) {
      for (let c = 0; c < COLS; c++) {
        const o = cellOrigin(c, r);
        for (let k = 0; k < PER; k++) {
          target.push(new THREE.Vector3(o.x + (k % 4) * SX - 1.5 * SX, 0, o.z + Math.floor(k / 4) * SZ - SZ));
          const a = Math.random() * Math.PI * 2, b = Math.acos(2 * Math.random() - 1), rad = 4 + Math.random() * 5;
          from.push(new THREE.Vector3(Math.sin(b) * Math.cos(a) * rad, 2.5 + Math.cos(b) * rad * 0.6, Math.sin(b) * Math.sin(a) * rad));
          delay.push(Math.random() * 1.2 + (r + c) * 0.04);
          eve.push(isEve(c));
          spots.setColorAt(i, isEve(c) || k < 10 ? light : empty);
          i++;
        }
      }
    }

    // The waiting list: hollow rings in front of every evening class.
    const ringGeo = new THREE.TorusGeometry(0.058, 0.016, 10, 32);
    const ringMat = new THREE.MeshStandardMaterial({ color: deep, roughness: 0.4 });
    const ringCells: { r: number; c: number; j: number }[] = [];
    for (let r = 0; r < ROWS; r++) for (let c = 4; c < COLS; c++) for (let j = 0; j < WAITING; j++) ringCells.push({ r, c, j });
    const rings = new THREE.InstancedMesh(ringGeo, ringMat, ringCells.length);
    scene.add(rings);

    // A soft glow under the week, so it sits on something.
    const shadow = document.createElement('canvas');
    shadow.width = shadow.height = 256;
    const g = shadow.getContext('2d');
    if (g) {
      const grad = g.createRadialGradient(128, 128, 10, 128, 128, 128);
      grad.addColorStop(0, 'rgba(37,99,235,0.18)');
      grad.addColorStop(1, 'rgba(37,99,235,0)');
      g.fillStyle = grad;
      g.fillRect(0, 0, 256, 256);
    }
    const groundTex = new THREE.CanvasTexture(shadow);
    const ground = new THREE.Mesh(
      new THREE.PlaneGeometry(width + 3.2, depth + 3.2),
      new THREE.MeshBasicMaterial({ map: groundTex, transparent: true, depthWrite: false }),
    );
    ground.rotation.x = -Math.PI / 2;
    ground.position.y = -0.1;
    scene.add(ground);

    // Labels live in the page, pinned to 3D anchors every frame.
    labels.innerHTML = '';
    const anchors: { el: HTMLSpanElement; p: THREE.Vector3 }[] = [];
    TIMES.forEach((t, c) => {
      const el = document.createElement('span');
      el.textContent = t;
      el.className = `home-lbl${isEve(c) ? ' eve' : ''}`;
      labels.appendChild(el);
      anchors.push({ el, p: cellOrigin(c, 0).add(new THREE.Vector3(0, 0.9, -0.5)) });
    });
    DAYS.forEach((d, r) => {
      const el = document.createElement('span');
      el.textContent = d;
      el.className = 'home-lbl day';
      labels.appendChild(el);
      anchors.push({ el, p: cellOrigin(0, r).add(new THREE.Vector3(-0.72, 0, 0)) });
    });
    const noteAnchor = cellOrigin(4, 0).add(new THREE.Vector3(0.67, 1.75, -0.5));

    const m = new THREE.Matrix4(), q = new THREE.Quaternion(), s = new THREE.Vector3(), v = new THREE.Vector3();
    const xAxis = new THREE.Vector3(1, 0, 0);
    const col = new THREE.Color();
    let mx = 0, my = 0, sx = 0, sy = 0;
    const onMove = (e: MouseEvent) => {
      mx = (e.clientX / window.innerWidth) * 2 - 1;
      my = (e.clientY / window.innerHeight) * 2 - 1;
    };
    window.addEventListener('mousemove', onMove);

    const clamp = (x: number) => Math.max(0, Math.min(1, x));
    const outCubic = (x: number) => 1 - Math.pow(1 - x, 3);
    const inOut = (x: number) => (x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2);
    const outBack = (x: number) => 1 + 2.9 * Math.pow(x - 1, 3) + 1.9 * Math.pow(x - 1, 2);
    const project = (p: THREE.Vector3): [number, number] => {
      v.copy(p).project(camera);
      return [((v.x + 1) / 2) * W, ((1 - v.y) / 2) * H];
    };

    const t0 = performance.now();
    let revealed = false;
    let raf = 0;
    let visible = true;
    const io = new IntersectionObserver(([entry]) => {
      visible = entry.isIntersecting;
    });
    io.observe(stage);

    const frame = (now: number) => {
      raf = requestAnimationFrame(frame);
      const t = reduce ? 60 : (now - t0) / 1000;
      if (!visible && t > 6) return;
      const rise = inOut(clamp((t - 2.9) / 0.8));

      for (let n = 0; n < N; n++) {
        const e = outCubic(clamp((t - delay[n]) / 1.7));
        s.setScalar(0.35 + 0.65 * e);
        v.lerpVectors(from[n], target[n], e);
        if (eve[n]) {
          v.y += rise * 0.34;
          col.copy(light).lerp(deep, rise);
          spots.setColorAt(n, col);
        }
        m.compose(v, q, s);
        spots.setMatrixAt(n, m);
      }
      spots.instanceMatrix.needsUpdate = true;
      if (spots.instanceColor) spots.instanceColor.needsUpdate = true;

      ringCells.forEach(({ r, c, j }, n) => {
        const p = clamp((t - 3.6 - n * 0.03) / 0.55);
        const o = cellOrigin(c, r);
        s.setScalar(Math.max(0.0001, p === 0 ? 0 : outBack(p)));
        v.set(o.x + (j - 1.5) * SX, 0.34 + (1 - p) * 0.9, o.z + 2 * SZ);
        q.setFromAxisAngle(xAxis, -Math.PI / 2);
        m.compose(v, q, s);
        rings.setMatrixAt(n, m);
        q.identity();
      });
      rings.instanceMatrix.needsUpdate = true;

      // The camera leans toward the pointer, and breathes a little on its own.
      sx += (mx - sx) * 0.04;
      sy += (my - sy) * 0.04;
      const ang = sx * 0.2 + Math.sin(t * 0.3) * 0.05;
      camera.position.set(Math.sin(ang) * 9.0, 14.2 - sy * 1.0, Math.cos(ang) * 12.4);
      camera.lookAt(-0.35, 0.25, -0.2);

      for (const a of anchors) {
        const [x, y] = project(a.p);
        a.el.style.transform = `translate(${x}px, ${y}px) translate(-50%, -50%)`;
        a.el.style.opacity = String(clamp((t - 1.4) / 0.6));
      }
      const [nx, ny] = project(noteAnchor);
      note.style.transform = `translate(${nx}px, ${ny}px) translate(-50%, -100%) rotate(-4deg)`;

      if (!revealed && t > 4.0) {
        revealed = true;
        revealRef.current();
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
    };
    window.addEventListener('resize', onResize);

    return () => {
      cancelAnimationFrame(raf);
      io.disconnect();
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('resize', onResize);
      spotGeo.dispose();
      spotMat.dispose();
      ringGeo.dispose();
      ringMat.dispose();
      groundTex.dispose();
      renderer.dispose();
      renderer.domElement.remove();
    };
  }, []);

  if (flat) return <FlatWeek />;
  return (
    <div className="home-stage" ref={stageRef}>
      <div className="home-labels" ref={labelsRef} aria-hidden="true" />
      <p className="home-evenote" ref={noteRef} aria-hidden="true">every evening sells out</p>
    </div>
  );
}
