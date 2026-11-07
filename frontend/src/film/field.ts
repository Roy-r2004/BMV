/**
 * The light field behind every public page: several thousand points of ink
 * and cobalt light that re-form into the shape of the shot on screen. It
 * owns its WebGL scene and its animation loop; the page tells it which shape
 * to take, how far the reader is through the shot, and when a cut happens.
 */
import * as THREE from 'three';
import { COLOUR, POSE, SHAPES, rnd, words, type Shape, type ShapeName } from './shapes';

const VERTEX = /* glsl */ `
  attribute float aSize;
  attribute vec3 aColor;
  uniform float uPR;
  uniform float uTime;
  varying vec3 vColor;
  varying float vFade;
  void main() {
    vec4 mv = modelViewMatrix * vec4(position, 1.0);
    float tw = 0.8 + 0.2 * sin(uTime * 1.7 + position.x * 3.1 + position.y * 2.3);
    gl_PointSize = aSize * uPR * tw * (26.0 / -mv.z);
    gl_Position = projectionMatrix * mv;
    vColor = aColor;
    vFade = clamp(1.3 - (-mv.z - 8.0) * 0.1, 0.4, 1.0);
  }
`;
const FRAGMENT = /* glsl */ `
  varying vec3 vColor;
  varying float vFade;
  void main() {
    float d = length(gl_PointCoord - 0.5);
    float a = smoothstep(0.5, 0.12, d);
    gl_FragColor = vec4(vColor, a * vFade * 0.92);
  }
`;

export class LightField {
  private renderer: THREE.WebGLRenderer;
  private scene = new THREE.Scene();
  private camera = new THREE.PerspectiveCamera(42, 1, 0.1, 100);
  private group = new THREE.Group();
  private geo = new THREE.BufferGeometry();
  private mat: THREE.ShaderMaterial;
  private dust: THREE.Points;
  private dustPos: Float32Array;
  private readonly n: number;
  private base: Float32Array;
  private pos: Float32Array;
  private col: Float32Array;
  private offs: Float32Array;
  private rate: Float32Array;
  private flowU: Float32Array;
  private cache = new Map<string, Shape>();
  private current: { name: ShapeName; text: string } = { name: 'seed', text: '' };
  private home = new THREE.Vector3();
  private target = new THREE.Vector3();
  private pointer = new THREE.Vector2(9, 9);
  private tilt = { x: 0, y: 0 };
  private ray = new THREE.Raycaster();
  private plane = new THREE.Plane(new THREE.Vector3(0, 0, 1), 0);
  private hit = new THREE.Vector3();
  private tmp = new Float32Array(6);
  private clock = new THREE.Clock();
  private spin = 0;
  private dolly = 0;
  private camZ = 11;
  private raf = 0;
  private readonly reduce: boolean;

  constructor(canvas: HTMLCanvasElement, reduce: boolean) {
    this.reduce = reduce;
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: false, alpha: true });
    this.n = window.innerWidth < 700 ? 6000 : 9000;
    const n = this.n;
    this.base = new Float32Array(n * 3);
    this.pos = new Float32Array(n * 3);
    this.col = new Float32Array(n * 3).fill(0.9);
    this.offs = new Float32Array(n * 3);
    this.rate = new Float32Array(n);
    this.flowU = new Float32Array(n);
    const size = new Float32Array(n);
    for (let i = 0; i < n; i++) {
      // start scattered wide, so the first frames are the field gathering
      const a = rnd(i * 3) * 6.283, r = 6 + rnd(i * 5) * 10;
      this.base[i * 3] = Math.cos(a) * r;
      this.base[i * 3 + 1] = (rnd(i * 7) - 0.5) * 10;
      this.base[i * 3 + 2] = Math.sin(a) * r - 4;
      size[i] = 1.1 + Math.pow(rnd(i * 11), 3) * 2.6;
      this.rate[i] = 0.55 + rnd(i * 13) * 0.9;
      this.flowU[i] = rnd(i * 17);
    }
    this.geo.setAttribute('position', new THREE.BufferAttribute(this.pos, 3));
    this.geo.setAttribute('aColor', new THREE.BufferAttribute(this.col, 3));
    this.geo.setAttribute('aSize', new THREE.BufferAttribute(size, 1));
    this.mat = new THREE.ShaderMaterial({
      vertexShader: VERTEX,
      fragmentShader: FRAGMENT,
      transparent: true,
      depthWrite: false,
      uniforms: { uPR: { value: 1 }, uTime: { value: 0 } },
    });
    const points = new THREE.Points(this.geo, this.mat);
    points.frustumCulled = false;
    this.group.add(points);
    this.scene.add(this.group);

    // the far layer: fine dust in depth that drifts and moves at its own speed
    const dn = window.innerWidth < 700 ? 700 : 1400;
    this.dustPos = new Float32Array(dn * 3);
    const dcol = new Float32Array(dn * 3), dsize = new Float32Array(dn);
    for (let d = 0; d < dn; d++) {
      this.dustPos[d * 3] = (rnd(d * 31) - 0.5) * 28;
      this.dustPos[d * 3 + 1] = (rnd(d * 37) - 0.5) * 18;
      this.dustPos[d * 3 + 2] = -11 + rnd(d * 41) * 12;
      const c = rnd(d * 43) > 0.6 ? COLOUR.sky : COLOUR.pale;
      dcol.set(c, d * 3);
      dsize[d] = 0.5 + rnd(d * 47) * 1.3;
    }
    const dgeo = new THREE.BufferGeometry();
    dgeo.setAttribute('position', new THREE.BufferAttribute(this.dustPos, 3));
    dgeo.setAttribute('aColor', new THREE.BufferAttribute(dcol, 3));
    dgeo.setAttribute('aSize', new THREE.BufferAttribute(dsize, 1));
    this.dust = new THREE.Points(dgeo, this.mat);
    this.dust.frustumCulled = false;
    this.scene.add(this.dust);

    this.camera.position.set(0, 0, 11);
    this.resize();
    this.group.position.copy(this.home);
    window.addEventListener('resize', this.resize);
    window.addEventListener('pointermove', this.onPointer, { passive: true });
    if (reduce) {
      const s = this.shape('seed', '');
      for (let i = 0; i < n; i++) this.base.set(s.data.subarray(i * 6, i * 6 + 3), i * 3);
    }
    this.raf = requestAnimationFrame(this.frame);
  }

  /** Take a shape. `text` is the sentence for the words shape. A quiet change skips the burst. */
  setShape(name: ShapeName, text = '', quiet = false) {
    if (name === this.current.name && (name !== 'words' || text === this.current.text)) return;
    const sameKind = name === this.current.name;
    this.current = { name, text };
    if (!sameKind) this.spin = 0;
    if (!this.reduce && !quiet && !sameKind) this.burst();
  }

  /** How far the reader is through the shot on screen, from -0.5 to 0.5. */
  setDolly(p: number) {
    this.dolly = Math.max(-0.5, Math.min(0.5, p));
  }

  /** A cut: the camera starts further back and pushes in. */
  pushIn(from = 16) {
    if (!this.reduce) this.camera.position.z = from;
  }

  /** Forget the words shapes, so they are drawn again in the loaded display face. */
  refreshText() {
    for (const k of [...this.cache.keys()]) if (k.startsWith('words:')) this.cache.delete(k);
  }

  dispose() {
    cancelAnimationFrame(this.raf);
    window.removeEventListener('resize', this.resize);
    window.removeEventListener('pointermove', this.onPointer);
    this.geo.dispose();
    this.dust.geometry.dispose();
    this.mat.dispose();
    this.renderer.dispose();
  }

  private shape(name: ShapeName, text: string): Shape {
    const k = name === 'words' ? `words:${text}` : name;
    let s = this.cache.get(k);
    if (!s) {
      if (name === 'words') {
        // one sentence at a time: drop the words drawn for an earlier one
        for (const old of [...this.cache.keys()]) if (old.startsWith('words:')) this.cache.delete(old);
        s = words(this.n, text || 'Your idea');
      } else {
        s = SHAPES[name](this.n);
      }
      this.cache.set(k, s);
    }
    return s;
  }

  // between shots the light scatters outward for a moment before it gathers again
  private burst() {
    const { base, offs } = this;
    for (let i = 0; i < this.n; i++) {
      const i3 = i * 3, x = base[i3], y = base[i3 + 1], z = base[i3 + 2];
      const l = Math.hypot(x, y, z) || 1, f = (0.25 + rnd(i * 19)) * 0.9;
      offs[i3] += (x / l) * f;
      offs[i3 + 1] += (y / l) * f;
      offs[i3 + 2] += (z / l) * f + 0.3;
    }
  }

  private resize = () => {
    const w = window.innerWidth, h = window.innerHeight;
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    this.renderer.setSize(w, h, false);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
    // beside the words on a wide screen; above them on a phone
    if (w > 980) this.home.set(2.9, 0.1, 0);
    else this.home.set(0, 2.0, -2.5);
    this.mat.uniforms.uPR.value = this.renderer.getPixelRatio();
  };

  private onPointer = (e: PointerEvent) => {
    this.pointer.set((e.clientX / window.innerWidth) * 2 - 1, -(e.clientY / window.innerHeight) * 2 + 1);
    this.tilt.x = this.pointer.y * 0.12;
    this.tilt.y = this.pointer.x * 0.22;
  };

  private frame = () => {
    this.raf = requestAnimationFrame(this.frame);
    const dt = Math.min(this.clock.getDelta(), 1 / 20), t = this.clock.elapsedTime;
    const { base, pos, col, offs, rate, flowU, tmp, reduce } = this;
    const s = this.shape(this.current.name, this.current.text), d = s.data, fl = s.flow;
    this.mat.uniforms.uTime.value = t;
    const k = reduce ? 1 : 1 - Math.exp(-dt * 2.6);

    this.ray.setFromCamera(this.pointer, this.camera);
    const lp = this.ray.ray.intersectPlane(this.plane, this.hit) ? this.group.worldToLocal(this.hit.clone()) : null;

    for (let i = 0; i < this.n; i++) {
      const i3 = i * 3, i6 = i * 6, kk = Math.min(1, k * rate[i]);
      let tx, ty, tz, cr, cg, cb;
      if (fl && i < fl.n) {
        fl.path((flowU[i] + t * fl.speed) % 1, i, tmp);
        [tx, ty, tz, cr, cg, cb] = tmp;
      } else {
        tx = d[i6]; ty = d[i6 + 1]; tz = d[i6 + 2]; cr = d[i6 + 3]; cg = d[i6 + 4]; cb = d[i6 + 5];
      }
      base[i3] += (tx - base[i3]) * kk;
      base[i3 + 1] += (ty - base[i3 + 1]) * kk;
      base[i3 + 2] += (tz - base[i3 + 2]) * kk;
      col[i3] += (cr - col[i3]) * kk * 0.8;
      col[i3 + 1] += (cg - col[i3 + 1]) * kk * 0.8;
      col[i3 + 2] += (cb - col[i3 + 2]) * kk * 0.8;
      if (lp && !reduce) {
        // the field parts around the pointer, then closes again
        const dx = base[i3] - lp.x, dy = base[i3 + 1] - lp.y, d2 = dx * dx + dy * dy;
        if (d2 < 1.1) {
          const f = (1.1 - d2) * 0.09;
          offs[i3] += dx * f; offs[i3 + 1] += dy * f; offs[i3 + 2] += f * 1.4;
        }
      }
      offs[i3] *= 0.93; offs[i3 + 1] *= 0.93; offs[i3 + 2] *= 0.93;
      const w = reduce ? 0 : 0.03;
      pos[i3] = base[i3] + offs[i3] + Math.sin(t * 0.9 + i * 0.37) * w;
      pos[i3 + 1] = base[i3 + 1] + offs[i3 + 1] + Math.cos(t * 0.8 + i * 0.21) * w;
      pos[i3 + 2] = base[i3 + 2] + offs[i3 + 2];
    }
    (this.geo.attributes.position as THREE.BufferAttribute).needsUpdate = true;
    (this.geo.attributes.aColor as THREE.BufferAttribute).needsUpdate = true;

    const { pose, spin } = POSE[this.current.name];
    this.spin += dt * (reduce ? 0 : spin);
    const g = this.group;
    g.rotation.x += (pose[0] + this.tilt.x - g.rotation.x) * 0.05;
    g.rotation.y += (this.spin + pose[1] + this.tilt.y - g.rotation.y) * 0.05;
    // the camera dollies in as the reader moves through a shot; the field rises with it
    this.target.copy(this.home);
    if (!reduce) this.target.y += this.dolly * 0.9;
    g.position.lerp(this.target, 0.05);
    const cz = this.camZ - (reduce ? 0 : this.dolly * 1.6);
    this.camera.position.z += (cz - this.camera.position.z) * (reduce ? 1 : 0.035);

    if (!reduce) {
      const dp = this.dustPos;
      for (let q = 1; q < dp.length; q += 3) { dp[q] += dt * 0.06; if (dp[q] > 9) dp[q] = -9; }
      (this.dust.geometry.attributes.position as THREE.BufferAttribute).needsUpdate = true;
      this.dust.position.y += (window.scrollY * 0.0016 - this.dust.position.y) * 0.08;
      this.dust.rotation.y += (this.tilt.y * 0.35 - this.dust.rotation.y) * 0.04;
      this.dust.rotation.x += (this.tilt.x * 0.25 - this.dust.rotation.x) * 0.04;
    }
    this.renderer.render(this.scene, this.camera);
  };
}

/** A field, or null where WebGL is not available (the pages still read and work). */
export function createLightField(canvas: HTMLCanvasElement, reduce: boolean): LightField | null {
  try {
    return new LightField(canvas, reduce);
  } catch {
    return null;
  }
}
