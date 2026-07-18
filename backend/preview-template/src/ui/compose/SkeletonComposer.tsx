import * as React from 'react';

import { getSkeleton, type SkeletonId } from '../registry';

export type SkeletonSlots = Record<string, React.ReactNode>;

export interface SkeletonComposerProps {
  skeletonId: SkeletonId;
  /** Map of section id → rendered catalogue subtree. Composer decides order. */
  slots: SkeletonSlots;
  /** Optional recipe/template-driven order; falls back to skeleton.recommendedOrder. */
  order?: readonly string[];
}

export interface ComposedSkeletonLayout {
  main: React.ReactNode;
  /** Pass to OpsShell `rail` for ops-dashboard activity column. */
  rail?: React.ReactNode;
}

function assertRequiredSections(skeletonId: SkeletonId, slots: SkeletonSlots) {
  const skeleton = getSkeleton(skeletonId);
  const missingRequired = skeleton.requiredSections.filter((section) => {
    if (section === 'shell') return false;
    return slots[section] == null;
  });
  if (missingRequired.length > 0) {
    throw new Error(`Skeleton "${skeletonId}" missing required sections: ${missingRequired.join(', ')}`);
  }
  return skeleton;
}

function resolveOrder(
  skeleton: ReturnType<typeof getSkeleton>,
  slots: SkeletonSlots,
  order?: readonly string[],
): string[] {
  const sequence = (order && order.length > 0 ? order : skeleton.recommendedOrder).filter(
    (section) => section !== 'shell' && slots[section] != null,
  );
  // When a recipe/template order is provided, it owns the page face —
  // do not append leftover AI slots (features/spotlight/etc.) or every
  // business collapses back into the same long marketing stack.
  if (order && order.length > 0) {
    const requiredMissing = skeleton.requiredSections.filter(
      (section) =>
        section !== 'shell' &&
        slots[section] != null &&
        !sequence.includes(section),
    );
    return [...sequence, ...requiredMissing];
  }
  for (const section of Object.keys(slots)) {
    if (section !== 'shell' && slots[section] != null && !sequence.includes(section)) {
      sequence.push(section);
    }
  }
  return sequence;
}

/**
 * Drives page structure from the skeleton registry.
 * Pages supply content slots; section order prefers recipe/template `order`.
 */
export function SkeletonComposer({ skeletonId, slots, order }: SkeletonComposerProps) {
  const skeleton = assertRequiredSections(skeletonId, slots);
  const ordered = resolveOrder(skeleton, slots, order);

  return (
    <>
      {ordered.map((section) => (
        <React.Fragment key={section}>{slots[section]}</React.Fragment>
      ))}
    </>
  );
}

/**
 * Split ops-dashboard slots into main column + right rail (activity).
 * Other skeletons return a flat main tree (no rail).
 */
export function composeSkeletonLayout(
  skeletonId: SkeletonId,
  slots: SkeletonSlots,
  order?: readonly string[],
): ComposedSkeletonLayout {
  const skeleton = assertRequiredSections(skeletonId, slots);

  if (skeletonId === 'ops-dashboard' && slots.activity != null) {
    const mainOrder = resolveOrder(skeleton, slots, order).filter(
      (section) => section !== 'activity',
    );
    return {
      main: (
        <div className="space-y-5">
          {mainOrder.map((section) => (
            <React.Fragment key={section}>{slots[section]}</React.Fragment>
          ))}
        </div>
      ),
      rail: <div className="space-y-4 xl:sticky xl:top-5">{slots.activity}</div>,
    };
  }

  return {
    main: <SkeletonComposer skeletonId={skeletonId} slots={slots} order={order} />,
  };
}

export { getSkeleton };
export type { SkeletonId };
