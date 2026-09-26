/**
 * Framing shared by the scroll-story pages (About, Private AI): a sticky 3D
 * stage behind a column of text.
 *
 * Wide screens (>= 1024px): the text column sits on the left, so each view is
 * pulled back until its subject (`w` world units wide) fits the band between
 * the column's right edge and the chapter index, and shifted so the subject
 * sits in the middle of that band.
 *
 * Narrow screens: each chapter's text panel starts halfway down the screen,
 * so the subject is fitted into the band between the nav and the panel.
 */
import * as THREE from 'three';

export type View = { p: [number, number, number]; t: [number, number, number]; w: number };
export type Framed = { p: THREE.Vector3; t: THREE.Vector3 };

export const WIDE_MIN = 1024;
const UP = new THREE.Vector3(0, 1, 0);

export function frameView(
  v: View,
  camera: THREE.PerspectiveCamera,
  W: number,
  H: number,
  column: Element | null,
): Framed {
  const tanH = Math.tan(THREE.MathUtils.degToRad(camera.fov / 2));
  const aspect = W / H;
  const wide = W >= WIDE_MIN;
  const edge = column ? column.getBoundingClientRect().right / W : 0.42;
  const bandL = wide ? Math.min(0.62, edge + 0.02) : 0;
  const bandR = wide ? 1 - 150 / W : 1;
  const bandFrac = bandR - bandL;
  const centreNdc = bandL + bandR - 1;

  const tgt = new THREE.Vector3(...v.t);
  const dir = new THREE.Vector3(...v.p).sub(tgt);
  const d0 = dir.length();
  dir.normalize();
  const right = new THREE.Vector3().crossVectors(UP, dir).normalize();
  const up = new THREE.Vector3().crossVectors(dir, right).normalize();
  const off = new THREE.Vector3();
  let d: number;
  if (wide) {
    d = Math.max(d0, v.w / (bandFrac * 2 * tanH * aspect * 0.95));
    off.addScaledVector(right, -centreNdc * d * tanH * aspect);
  } else {
    d = Math.min(Math.max(d0, (v.w * 0.9) / (2 * tanH * aspect), (v.w * 0.62) / (2 * tanH * 0.4)), d0 * 3.5);
    off.addScaledVector(up, -0.42 * d * tanH);
  }
  const t = tgt.add(off);
  return { p: t.clone().addScaledVector(dir, d), t };
}
