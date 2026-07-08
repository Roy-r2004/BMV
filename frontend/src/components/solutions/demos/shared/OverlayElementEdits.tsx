import { useEffect } from 'react';
import { useShowcaseOverlay } from '../../../../context/ShowcaseOverlayContext';
import type { OverlayElementEdit } from '../../../../types/auth';

function applyEdit(el: Element, edit: OverlayElementEdit) {
  if (!(el instanceof HTMLElement)) return;

  if (edit.placeholder != null && el instanceof HTMLInputElement) {
    el.placeholder = edit.placeholder;
    el.setAttribute('placeholder', edit.placeholder);
  }

  if (edit.placeholder != null && el instanceof HTMLTextAreaElement) {
    el.placeholder = edit.placeholder;
    el.setAttribute('placeholder', edit.placeholder);
  }

  if (edit.value != null && (el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement)) {
    el.value = edit.value;
    el.setAttribute('value', edit.value);
  }

  if (edit.ariaLabel != null) {
    el.setAttribute('aria-label', edit.ariaLabel);
  }

  if (edit.text != null) {
    if (el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement) {
      el.placeholder = edit.text;
      el.setAttribute('placeholder', edit.text);
    } else if (el instanceof HTMLSelectElement) {
      el.setAttribute('aria-label', edit.text);
    } else {
      el.textContent = edit.text;
    }
  }
}

function applyElementEdits(scope: HTMLElement, edits: OverlayElementEdit[]) {
  for (const edit of edits) {
    if (!edit.selector) continue;
    try {
      scope.querySelectorAll(edit.selector).forEach((el) => applyEdit(el, edit));
    } catch {
      // Ignore invalid model-generated selectors instead of breaking the preview.
    }
  }
}

export default function OverlayElementEdits({ solutionId }: { solutionId: string }) {
  const { overlay } = useShowcaseOverlay();
  const edits = overlay.elementEdits;

  useEffect(() => {
    if (!edits?.length) return;
    const scope = document.querySelector<HTMLElement>(`.user-codegen-${solutionId}`);
    if (!scope) return;

    let frame = 0;
    const apply = () => {
      window.cancelAnimationFrame(frame);
      frame = window.requestAnimationFrame(() => applyElementEdits(scope, edits));
    };

    apply();
    const observer = new MutationObserver(apply);
    observer.observe(scope, { childList: true, subtree: true });

    return () => {
      window.cancelAnimationFrame(frame);
      observer.disconnect();
    };
  }, [edits, solutionId]);

  return null;
}
