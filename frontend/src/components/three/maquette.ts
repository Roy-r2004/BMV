/**
 * The white architectural-model look shared by the Private AI, Solutions and
 * Examples scenes: soft daylight with shadows, a floor that only shows those
 * shadows plus a faint dot grid, white solids outlined in ink, and labels that
 * are page elements pinned to 3D points.
 */
import * as THREE from 'three';

export const INK = 0x0f172a;
export const BLUE = 0x2563eb;
export const CYAN = 0x06b6d4;
export const PALE_BLUE = 0xbfdbfe;

/** Daylight for three.js's physical light units, with one soft shadow caster. */
export function addLights(scene: THREE.Scene, shadow: { left: number; right: number; top: number; bottom: number }) {
  scene.add(new THREE.HemisphereLight(0xffffff, 0xd6e2f5, 2.1));
  const sun = new THREE.DirectionalLight(0xffffff, 1.5);
  sun.position.set(-8, 16, 10);
  sun.castShadow = true;
  sun.shadow.mapSize.set(2048, 2048);
  Object.assign(sun.shadow.camera, { ...shadow, near: 1, far: 70 });
  sun.shadow.radius = 4;
  scene.add(sun);
}

/** A floor that shows only shadows, and a dot grid `half` units each way. */
export function addGround(scene: THREE.Scene, half = 30, step = 1) {
  const ground = new THREE.Mesh(new THREE.PlaneGeometry(240, 240), new THREE.ShadowMaterial({ opacity: 0.09 }));
  ground.rotation.x = -Math.PI / 2;
  ground.receiveShadow = true;
  scene.add(ground);
  const pts: number[] = [];
  for (let x = -half; x <= half; x += step) for (let z = -half; z <= half; z += step) pts.push(x, 0.001, z);
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.Float32BufferAttribute(pts, 3));
  scene.add(new THREE.Points(geo, new THREE.PointsMaterial({ color: 0xa5b8d6, size: 0.07, transparent: true, opacity: 0.8 })));
}

export type SolidOpts = { mat?: THREE.Material | THREE.Material[]; edges?: boolean };

/** Builds white solids with ink outlines; every solid casts and takes shadow. */
export function solidMaker() {
  const white = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.88, metalness: 0 });
  const edgeMat = new THREE.LineBasicMaterial({ color: INK, transparent: true, opacity: 0.45 });
  const solid = (geo: THREE.BufferGeometry, parent: THREE.Object3D, x: number, y: number, z: number, opts: SolidOpts = {}) => {
    const g = new THREE.Group();
    const m = new THREE.Mesh(geo, opts.mat ?? white);
    m.castShadow = true;
    m.receiveShadow = true;
    g.add(m);
    if (opts.edges !== false) g.add(new THREE.LineSegments(new THREE.EdgesGeometry(geo, 28), edgeMat));
    g.position.set(x, y, z);
    parent.add(g);
    return g;
  };
  return { solid, white, edgeMat };
}

/** Frees every geometry, material and texture the scene holds. */
export function disposeScene(scene: THREE.Scene) {
  const mats = new Set<THREE.Material>();
  scene.traverse((o) => {
    const m = o as THREE.Mesh;
    m.geometry?.dispose();
    const mat = m.material;
    if (Array.isArray(mat)) mat.forEach((x) => mats.add(x));
    else if (mat) mats.add(mat);
  });
  mats.forEach((m) => {
    for (const v of Object.values(m)) if (v instanceof THREE.Texture) v.dispose();
    m.dispose();
  });
}

const _v = new THREE.Vector3();
/**
 * Pins a page element to a world point: centred on it, kept inside the stage,
 * hidden when faded out or behind the camera.
 */
export function pinLabel(
  el: HTMLElement,
  p: THREE.Vector3,
  camera: THREE.Camera,
  W: number,
  H: number,
  opacity: number,
  size: { hw: number },
) {
  if (opacity < 0.02) {
    el.style.opacity = '0';
    el.style.visibility = 'hidden';
    return;
  }
  _v.copy(p).project(camera);
  if (_v.z > 1) {
    el.style.visibility = 'hidden';
    return;
  }
  if (!size.hw) size.hw = el.offsetWidth / 2;
  const x = Math.min(W - size.hw - 6, Math.max(size.hw + 6, ((_v.x + 1) / 2) * W));
  el.style.visibility = 'visible';
  el.style.transform = `translate(${x.toFixed(1)}px, ${(((1 - _v.y) / 2) * H).toFixed(1)}px) translate(-50%, -50%)`;
  el.style.opacity = opacity.toFixed(3);
}
