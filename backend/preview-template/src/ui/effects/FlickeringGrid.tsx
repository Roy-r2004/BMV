import * as React from 'react';

import { cn } from '../lib/cn';
import { useMotionSafe } from '../motion/presets';

export interface FlickeringGridProps {
  /** Square edge in px. */
  squareSize?: number;
  /** Gap between squares in px. */
  gridGap?: number;
  /** Fraction of cells that re-roll per second. */
  flickerChance?: number;
  /** Any CSS color; defaults to the brand token. */
  color?: string;
  maxOpacity?: number;
  className?: string;
}

/** Ten flicker steps per second — quantized so timing is frame-rate independent. */
const TICKS_PER_SECOND = 10;

/** Deterministic [0, 1) from a cell index and a tick — the grid is never randomized. */
function hash01(cell: number, tick: number): number {
  let h = (Math.imul(cell + 1, 0x9e3779b1) ^ Math.imul(tick + 1, 0x85ebca6b)) >>> 0;
  h ^= h >>> 16;
  h = Math.imul(h, 0x045d9f3b) >>> 0;
  h ^= h >>> 16;
  return h / 0x100000000;
}

/**
 * Canvas backdrop of softly flickering squares — the electric texture behind
 * nocturne heroes and loud retail banners.
 * Adapted from Magic UI `flickering-grid` (MIT) — see PROVENANCE.json.
 * Rewritten for the kit: every random call became an index+tick hash and
 * skipped frames replay their missed ticks, so the texture is identical
 * run-to-run at any frame rate (the screenshot critic must see the same
 * frame twice); color defaults to the brand token and is resolved from
 * computed style (a canvas cannot read var()); reduced motion draws tick
 * zero once and never re-rolls — texture without flicker.
 */
export function FlickeringGrid({
  squareSize = 4,
  gridGap = 6,
  flickerChance = 0.3,
  color = 'var(--color-brand)',
  maxOpacity = 0.3,
  className,
}: FlickeringGridProps) {
  const safe = useMotionSafe();
  const canvasRef = React.useRef<HTMLCanvasElement | null>(null);
  const containerRef = React.useRef<HTMLDivElement | null>(null);

  React.useEffect(() => {
    const canvas = canvasRef.current;
    const container = containerRef.current;
    const ctx = canvas?.getContext('2d');
    if (!canvas || !container || !ctx) return;

    const resolvedColor = getComputedStyle(container).color;
    const perTickChance = flickerChance / TICKS_PER_SECOND;
    let cols = 0;
    let rows = 0;
    let squares = new Float32Array(0);
    let dpr = 1;
    let inView = false;
    let frameId: number | null = null;
    let startTime: number | null = null;
    let lastTick = 0;

    const setup = () => {
      const width = container.clientWidth;
      const height = container.clientHeight;
      dpr = window.devicePixelRatio || 1;
      canvas.width = width * dpr;
      canvas.height = height * dpr;
      canvas.style.width = `${width}px`;
      canvas.style.height = `${height}px`;
      cols = Math.ceil(width / (squareSize + gridGap));
      rows = Math.ceil(height / (squareSize + gridGap));
      squares = new Float32Array(cols * rows);
      for (let i = 0; i < squares.length; i++) {
        squares[i] = hash01(i, 0) * maxOpacity;
      }
      lastTick = 0;
    };

    const draw = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.fillStyle = resolvedColor;
      for (let i = 0; i < cols; i++) {
        for (let j = 0; j < rows; j++) {
          ctx.globalAlpha = squares[i * rows + j];
          ctx.fillRect(
            i * (squareSize + gridGap) * dpr,
            j * (squareSize + gridGap) * dpr,
            squareSize * dpr,
            squareSize * dpr,
          );
        }
      }
      ctx.globalAlpha = 1;
    };

    const animate = (time: number) => {
      frameId = null;
      if (!inView) return;
      if (startTime === null) startTime = time;
      const tick = Math.floor(((time - startTime) / 1000) * TICKS_PER_SECOND);
      // Replay every missed tick so the state at tick N is the same on every
      // machine, whatever the frame rate did in between.
      for (let t = lastTick + 1; t <= tick; t++) {
        for (let i = 0; i < squares.length; i++) {
          if (hash01(i, t) < perTickChance) {
            squares[i] = hash01(i ^ 0x517cc1b7, t) * maxOpacity;
          }
        }
      }
      lastTick = Math.max(lastTick, tick);
      draw();
      frameId = requestAnimationFrame(animate);
    };

    setup();
    draw();

    const resizeObserver = new ResizeObserver(() => {
      setup();
      draw();
    });
    resizeObserver.observe(container);

    const intersectionObserver = new IntersectionObserver(([entry]) => {
      inView = entry.isIntersecting;
      if (safe && inView && frameId === null) {
        frameId = requestAnimationFrame(animate);
      }
    });
    intersectionObserver.observe(canvas);

    return () => {
      if (frameId !== null) cancelAnimationFrame(frameId);
      resizeObserver.disconnect();
      intersectionObserver.disconnect();
    };
  }, [safe, squareSize, gridGap, flickerChance, color, maxOpacity]);

  return (
    <div
      ref={containerRef}
      aria-hidden
      className={cn('pointer-events-none h-full w-full', className)}
      style={{ color }}
    >
      <canvas ref={canvasRef} />
    </div>
  );
}
