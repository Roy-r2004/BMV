/**
 * The Examples page's picture: the chosen concept's own screens (from
 * `screens` in data/concepts) as a fan of floating app panels over a white
 * floor. Choosing another concept flips the panels one after another to the
 * new concept's screens. Labels name each screen.
 *
 * Without WebGL the screens are listed flat instead. With reduced motion the
 * panels change without flipping and nothing floats.
 */
import { useEffect, useRef, useState } from 'react';
import * as THREE from 'three';
import { addGround, addLights, BLUE, disposeScene, pinLabel, solidMaker } from '../three/maquette';
import { drawScreen } from './screenTexture';

type Concept = { name: string; screens: string[] };

const PW = 3.0;
const PH = 1.95;
const MAX = 4;

function layout(n: number, i: number) {
  const a = (i - (n - 1) / 2) * 0.5;
  return {
    x: Math.sin(a) * 5.2,
    z: Math.cos(a) * 5.2 - 5.2 + Math.abs(a) * 0.4,
    y: 1.9 + [0.25, 0.55, 0.4, 0.15][i % 4],
    ry: -a * 0.8,
  };
}

export default function ConceptScreens({ concepts, selected }: { concepts: Concept[]; selected: number }) {
  const stageRef = useRef<HTMLDivElement>(null);
  const labelRefs = useRef<(HTMLSpanElement | null)[]>([]);
  const live = useRef(selected);
  live.current = selected;
  const [flat, setFlat] = useState(false);
  const screens = concepts[selected].screens.slice(0, MAX);

  useEffect(() => {
    const stage = stageRef.current;
    if (!stage) return;
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
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    stage.prepend(renderer.domElement);

    const scene = new THREE.Scene();
    scene.fog = new THREE.Fog(0xf5f9ff, 22, 48);
    const camera = new THREE.PerspectiveCamera(35, W / H, 0.1, 200);
    addLights(scene, { left: -10, right: 10, top: 10, bottom: -10 });
    addGround(scene, 16, 0.8);
    const { white } = solidMaker();

    // a thin ring on the floor under the fan
    const ring = new THREE.Mesh(
      new THREE.RingGeometry(3.3, 3.34, 128),
      new THREE.MeshBasicMaterial({ color: BLUE, transparent: true, opacity: 0.5, side: THREE.DoubleSide }),
    );
    ring.rotation.x = -Math.PI / 2;
    ring.position.set(0, 0.01, -1.5);
    scene.add(ring);

    // textures are drawn once per concept screen, on first use
    const cache = new Map<string, THREE.CanvasTexture>();
    const tex = (c: number, s: number) => {
      const key = `${c}:${s}`;
      let t = cache.get(key);
      if (!t) {
        const concept = concepts[c];
        t = drawScreen(concept.name, concept.screens[s] ?? '', c * 10 + s);
        t.anisotropy = Math.min(8, renderer.capabilities.getMaxAnisotropy());
        cache.set(key, t);
      }
      return t;
    };

    const geo = new THREE.BoxGeometry(PW, PH, 0.06);
    const panels = Array.from({ length: MAX }, (_, i) => {
      const front = new THREE.MeshBasicMaterial();
      const back = new THREE.MeshBasicMaterial();
      const mesh = new THREE.Mesh(geo, [white, white, white, white, front, back]);
      const edges = new THREE.LineSegments(
        new THREE.EdgesGeometry(geo),
        new THREE.LineBasicMaterial({ color: 0x0f172a, transparent: true, opacity: 0.18 }),
      );
      const g = new THREE.Group();
      g.add(mesh, edges);
      scene.add(g);
      return { g, front, back, i, flipFrom: -1 };
    });

    let shown = -1;
    let flipStart = 0;
    const show = (c: number, now: number, instant: boolean) => {
      const n = Math.min(MAX, concepts[c].screens.length);
      for (const p of panels) {
        if (p.i >= n) continue;
        if (instant) {
          p.front.map = tex(c, p.i);
          p.front.needsUpdate = true;
          p.flipFrom = -1;
        } else {
          // the back face carries the new screen; half a turn later it faces us
          p.back.map = tex(c, p.i);
          p.back.needsUpdate = true;
          p.flipFrom = now;
        }
      }
      shown = c;
      flipStart = now;
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

    const fit = () => {
      const tanH = Math.tan(THREE.MathUtils.degToRad(camera.fov / 2));
      return Math.max(8.5, 10.2 / (2 * tanH * (W / H)));
    };
    let dist = fit();
    const target = new THREE.Vector3(0, 2.1, -0.9);
    const tmp = new THREE.Vector3();
    const sizes = Array.from({ length: MAX }, () => ({ hw: 0 }));
    const ease = (x: number) => (x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2);
    const t0 = performance.now();
    let raf = 0;

    const frame = (now: number) => {
      raf = requestAnimationFrame(frame);
      if (!visible) return;
      const time = reduce ? 0 : (now - t0) / 1000;
      const want = live.current;
      if (want !== shown) {
        show(want, now, shown === -1 || reduce);
        sizes.forEach((s) => (s.hw = 0)); // new screen names, new label widths
      }
      const n = Math.min(MAX, concepts[shown].screens.length);

      for (const p of panels) {
        p.g.visible = p.i < n;
        if (!p.g.visible) continue;
        const L = layout(n, p.i);
        let turn = 0;
        if (p.flipFrom >= 0) {
          const k = Math.min(1, Math.max(0, (now - p.flipFrom - p.i * 90) / 750));
          turn = ease(k) * Math.PI;
          if (k >= 1) {
            p.front.map = p.back.map;
            p.front.needsUpdate = true;
            p.flipFrom = -1;
            turn = 0;
          }
        }
        p.g.position.set(L.x, L.y + (reduce ? 0 : Math.sin(time * 0.8 + p.i * 1.3) * 0.07), L.z);
        p.g.rotation.set(0, L.ry + turn, 0);
      }
      ring.rotation.z = time * 0.05;

      if (!reduce) {
        sx += (mx - sx) * 0.04;
        sy += (my - sy) * 0.04;
      }
      const az = sx * 0.12 + (reduce ? 0 : Math.sin(time * 0.1) * 0.05);
      camera.position.set(target.x + Math.sin(az) * dist, target.y + 1.1 + dist * 0.05 - sy * 0.3, target.z + Math.cos(az) * dist);
      camera.lookAt(target);
      camera.updateMatrixWorld();

      const settling = now - flipStart < 1200 + n * 90;
      labelRefs.current.forEach((el, i) => {
        if (!el || i >= n) return;
        const L = layout(n, i);
        // a narrow stage puts every other name under its panel so they don't collide
        const below = W < 560 && i % 2 === 1;
        tmp.set(L.x, below ? L.y - PH / 2 - 0.38 : L.y + PH / 2 + 0.38, L.z);
        pinLabel(el, tmp, camera, W, H, settling && !reduce ? 0.35 : 1, sizes[i]);
      });
      renderer.render(scene, camera);
    };
    raf = requestAnimationFrame(frame);

    const onResize = () => {
      W = stage.clientWidth;
      H = stage.clientHeight;
      renderer.setSize(W, H);
      camera.aspect = W / H;
      camera.updateProjectionMatrix();
      dist = fit();
      sizes.forEach((s) => (s.hw = 0));
    };
    window.addEventListener('resize', onResize);

    return () => {
      cancelAnimationFrame(raf);
      io.disconnect();
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('resize', onResize);
      cache.forEach((t) => t.dispose());
      disposeScene(scene);
      renderer.dispose();
      renderer.domElement.remove();
    };
  }, [concepts]);

  if (flat) {
    return (
      <ul className="show-flat-screens">
        {screens.map((s) => (
          <li key={s}>{s}</li>
        ))}
      </ul>
    );
  }
  return (
    <div className="show-stage show-stage--screens" ref={stageRef} aria-hidden="true">
      <div className="show-labels">
        {screens.map((s, i) => (
          <span
            key={`${selected}-${s}`}
            className="show-lbl"
            ref={(el) => {
              labelRefs.current[i] = el;
            }}
          >
            {s}
          </span>
        ))}
      </div>
    </div>
  );
}
