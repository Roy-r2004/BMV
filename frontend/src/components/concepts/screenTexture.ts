/**
 * Draws one app screen for the Examples scene: a window bar with the concept's
 * name, the screen's own name as its title, and a wireframe body chosen from
 * the screen name (a dashboard gets tiles and a chart, a chat gets bubbles, a
 * calendar gets a month grid...). Shapes only — no invented figures or copy.
 */
import * as THREE from 'three';

type Kind = 'dash' | 'chat' | 'calendar' | 'doc' | 'form' | 'board' | 'grid' | 'list' | 'agents' | 'heat' | 'vision';

export function screenKind(screen: string): Kind {
  const s = screen.toLowerCase();
  if (/agent command|command center/.test(s)) return 'agents';
  if (/chat|search|transcript|\bask\b/.test(s)) return 'chat'; // \b: "task board" is not a chat
  if (/map|heatmap|radar|universe/.test(s)) return 'heat';
  if (/vision|render|packaging|dubbing|room/.test(s)) return 'vision';
  if (/calendar|booking|schedule|planner/.test(s)) return 'calendar';
  if (/pipeline|campaign builder|task board|close/.test(s)) return 'board';
  if (/storefront|product|shelf|variants|storyboard|formats/.test(s)) return 'grid';
  if (/dashboard|analytics|insights|forecast|simulator|training|timeline/.test(s)) return 'dash';
  if (/report|viewer|compare|detail|results|test|notes|sources|research|review/.test(s)) return 'doc';
  if (/admin|panel|editor|posting|categories|access|builder/.test(s)) return 'form';
  return 'list';
}

const W = 640;
const H = 416;
const FONT = 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif';
const C = {
  ink: '#0f172a',
  muted: '#94a3b8',
  line: '#e2e8f0',
  soft: '#f1f5f9',
  pale: '#dbeafe',
  light: '#93c5fd',
  blue: '#2563eb',
  cyan: '#06b6d4',
};

function rng(seed: number) {
  return () => {
    seed = (seed * 1664525 + 1013904223) % 4294967296;
    return seed / 4294967296;
  };
}

function box(g: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, fill: string, r = 8) {
  g.fillStyle = fill;
  g.beginPath();
  g.roundRect(x, y, w, h, r);
  g.fill();
}

function body(g: CanvasRenderingContext2D, kind: Kind, R: () => number) {
  const top = 112;
  switch (kind) {
    case 'dash': {
      for (let i = 0; i < 3; i++) {
        box(g, 28 + i * 198, top, 184, 74, C.soft);
        box(g, 44 + i * 198, top + 16, 60, 10, C.muted, 5);
        box(g, 44 + i * 198, top + 38, 90 + R() * 50, 18, i === 0 ? C.blue : C.light, 6);
      }
      box(g, 28, top + 92, 584, 186, C.soft);
      for (let i = 0; i < 12; i++) {
        const h = 30 + R() * 120;
        box(g, 52 + i * 46, top + 262 - h, 26, h, i % 4 === 3 ? C.cyan : C.light, 5);
      }
      break;
    }
    case 'chat': {
      let y = top;
      for (let i = 0; i < 5; i++) {
        const mine = i % 2 === 1;
        const w = 180 + R() * 200;
        const h = 36 + (i % 3) * 12;
        box(g, mine ? W - 28 - w : 28, y, w, h, mine ? C.blue : C.soft, 16);
        y += h + 12;
      }
      box(g, 28, H - 58, W - 56, 36, C.soft, 18);
      box(g, W - 92, H - 54, 56, 28, C.blue, 14);
      break;
    }
    case 'calendar': {
      const cw = 80, ch = 50;
      for (let r = 0; r < 5; r++)
        for (let c = 0; c < 7; c++) {
          const on = R() < 0.3;
          box(g, 36 + c * cw, top + r * ch, cw - 8, ch - 8, on ? C.pale : C.soft, 6);
          if (on) box(g, 44 + c * cw, top + 10 + r * ch, 40, 8, C.blue, 4);
        }
      break;
    }
    case 'board': {
      for (let c = 0; c < 4; c++) {
        box(g, 28 + c * 148, top, 136, 272, C.soft);
        box(g, 40 + c * 148, top + 14, 70, 10, C.muted, 5);
        const n = 2 + Math.floor(R() * 3);
        for (let i = 0; i < n; i++) {
          box(g, 40 + c * 148, top + 38 + i * 58, 112, 48, '#ffffff', 8);
          box(g, 50 + c * 148, top + 50 + i * 58, 70 + R() * 20, 8, c === 3 ? C.cyan : C.light, 4);
        }
      }
      break;
    }
    case 'grid': {
      for (let r = 0; r < 2; r++)
        for (let c = 0; c < 4; c++) {
          const x = 28 + c * 148, y = top + r * 142;
          box(g, x, y, 136, 90, r === 0 && c === 1 ? C.light : C.pale, 10);
          box(g, x, y + 100, 100, 9, C.muted, 5);
          box(g, x, y + 116, 60, 9, C.blue, 5);
        }
      break;
    }
    case 'doc': {
      for (let i = 0; i < 9; i++) box(g, 28, top + i * 30, 300 + R() * 60 - (i % 4 === 3 ? 140 : 0), 11, i === 0 ? C.ink : C.line, 5);
      box(g, 420, top, 192, 272, C.soft);
      g.strokeStyle = C.blue;
      g.lineWidth = 16;
      g.beginPath();
      g.arc(516, top + 92, 52, -Math.PI / 2, -Math.PI / 2 + Math.PI * (1 + R() * 0.7));
      g.stroke();
      g.strokeStyle = C.pale;
      g.beginPath();
      g.arc(516, top + 92, 52, -Math.PI / 2 + Math.PI * 1.75, Math.PI * 1.5);
      g.stroke();
      for (let i = 0; i < 3; i++) box(g, 440, top + 180 + i * 26, 150 - i * 30, 10, C.light, 5);
      break;
    }
    case 'form': {
      box(g, 28, top - 8, 126, H - top - 20, C.soft);
      for (let i = 0; i < 6; i++) box(g, 44, top + 10 + i * 40, 90, 12, i === 1 ? C.blue : C.muted, 6);
      for (let i = 0; i < 4; i++) {
        box(g, 180, top + i * 64, 90, 10, C.muted, 5);
        box(g, 180, top + 18 + i * 64, 420, 32, C.soft, 8);
      }
      box(g, 180, top + 262, 120, 34, C.blue, 10);
      break;
    }
    case 'agents': {
      // a network of agents around a hub, each with a status bar
      const hub = { x: W / 2, y: top + 136 };
      const nodes = Array.from({ length: 6 }, (_, i) => {
        const a = (i / 6) * Math.PI * 2 - Math.PI / 2;
        return { x: hub.x + Math.cos(a) * 210, y: hub.y + Math.sin(a) * 104 };
      });
      g.strokeStyle = C.light;
      g.lineWidth = 3;
      for (const n of nodes) {
        g.beginPath();
        g.moveTo(hub.x, hub.y);
        g.lineTo(n.x, n.y);
        g.stroke();
      }
      g.strokeStyle = C.pale;
      g.beginPath();
      nodes.forEach((n, i) => (i ? g.lineTo(n.x, n.y) : g.moveTo(n.x, n.y)));
      g.closePath();
      g.stroke();
      nodes.forEach((n, i) => {
        box(g, n.x - 52, n.y - 20, 104, 40, '#ffffff', 12);
        g.strokeStyle = i % 3 === 0 ? C.blue : C.light;
        g.lineWidth = 2;
        g.stroke();
        g.fillStyle = i % 3 === 0 ? C.cyan : C.light;
        g.beginPath();
        g.arc(n.x - 34, n.y, 7, 0, Math.PI * 2);
        g.fill();
        box(g, n.x - 20, n.y - 5, 50 + R() * 16, 10, C.muted, 5);
      });
      g.fillStyle = C.blue;
      g.beginPath();
      g.arc(hub.x, hub.y, 30, 0, Math.PI * 2);
      g.fill();
      g.fillStyle = '#ffffff';
      g.beginPath();
      g.arc(hub.x, hub.y, 11, 0, Math.PI * 2);
      g.fill();
      break;
    }
    case 'heat': {
      // a grid whose cells run from pale to deep blue, with a few hot spots
      const cols = 14, rows = 6, cw = 40, ch = 42;
      const ramp = ['#eff6ff', '#dbeafe', '#bfdbfe', '#93c5fd', '#60a5fa', '#2563eb'];
      for (let r = 0; r < rows; r++)
        for (let c = 0; c < cols; c++) {
          const wave = (Math.sin(c * 0.55 + r * 0.8) + 1) / 2;
          const v = Math.min(ramp.length - 1, Math.floor((wave * 0.7 + R() * 0.3) * ramp.length));
          box(g, 36 + c * cw, top + r * ch, cw - 5, ch - 5, ramp[v], 5);
        }
      for (let i = 0; i < 3; i++) {
        const x = 36 + Math.floor(R() * cols) * cw, y = top + Math.floor(R() * rows) * ch;
        g.strokeStyle = C.cyan;
        g.lineWidth = 3;
        g.beginPath();
        g.roundRect(x - 3, y - 3, cw + 1, ch + 1, 7);
        g.stroke();
      }
      break;
    }
    case 'vision': {
      // a camera or render view: a scene with detection boxes over it
      const grad = g.createLinearGradient(0, top, 0, H - 24);
      grad.addColorStop(0, '#e0ecfb');
      grad.addColorStop(1, '#f8fafc');
      box(g, 28, top, W - 56, H - top - 24, '#ffffff', 12);
      g.fillStyle = grad;
      g.beginPath();
      g.roundRect(28, top, W - 56, H - top - 24, 12);
      g.fill();
      g.strokeStyle = C.line;
      g.lineWidth = 2;
      g.beginPath();
      g.moveTo(28, top + 200);
      g.lineTo(W - 28, top + 200);
      g.stroke();
      const shapes = [
        [70, top + 60, 120, 140],
        [230, top + 100, 150, 100],
        [420, top + 40, 150, 160],
      ];
      shapes.forEach(([x, y, w, h], i) => {
        box(g, x, y, w, h, i === 1 ? C.light : C.pale, 10);
        g.strokeStyle = i === 2 ? C.cyan : C.blue;
        g.lineWidth = 3;
        g.setLineDash([10, 6]);
        g.beginPath();
        g.roundRect(x - 8, y - 8, w + 16, h + 16, 8);
        g.stroke();
        g.setLineDash([]);
        box(g, x - 8, y - 30, 70 + R() * 30, 18, i === 2 ? C.cyan : C.blue, 6);
      });
      break;
    }
    default: {
      for (let i = 0; i < 5; i++) {
        const y = top + i * 56;
        box(g, 28, y, W - 56, 46, i === 0 ? C.pale : C.soft, 10);
        g.fillStyle = i === 0 ? C.blue : C.light;
        g.beginPath();
        g.arc(56, y + 23, 13, 0, Math.PI * 2);
        g.fill();
        box(g, 82, y + 12, 160 + R() * 120, 9, C.ink, 5);
        box(g, 82, y + 28, 110 + R() * 80, 8, C.muted, 4);
        box(g, W - 120, y + 13, 70, 20, i % 2 ? C.pale : C.light, 10);
      }
    }
  }
}

/** A texture of `screen` from the concept `concept`. */
export function drawScreen(concept: string, screen: string, seed: number): THREE.CanvasTexture {
  const canvas = document.createElement('canvas');
  canvas.width = W;
  canvas.height = H;
  const g = canvas.getContext('2d');
  if (g) {
    g.fillStyle = '#ffffff';
    g.fillRect(0, 0, W, H);
    g.fillStyle = C.soft;
    g.fillRect(0, 0, W, 56);
    [0, 1, 2].forEach((i) => {
      g.fillStyle = C.line;
      g.beginPath();
      g.arc(26 + i * 20, 28, 6, 0, Math.PI * 2);
      g.fill();
    });
    g.fillStyle = C.muted;
    g.font = `600 17px ${FONT}`;
    g.textBaseline = 'middle';
    g.fillText(concept, 96, 29);
    g.fillStyle = C.ink;
    g.font = `700 26px ${FONT}`;
    g.fillText(screen, 28, 86);
    body(g, screenKind(screen), rng(seed * 7919 + 17));
  }
  const tex = new THREE.CanvasTexture(canvas);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 4;
  return tex;
}
