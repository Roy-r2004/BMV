import { getShowcaseDemoComponent } from './demos/showcaseRegistry';
import OverlayThemeStyle from './demos/shared/OverlayThemeStyle';
import OverlayGeneratedFiles from './demos/shared/OverlayGeneratedFiles';
import OverlayElementEdits from './demos/shared/OverlayElementEdits';
import UserVersionBar from './UserVersionBar';
import { ShowcaseOverlayProvider } from '../../context/ShowcaseOverlayContext';
import type { SolutionShowcase } from '../../data/showcaseDemos';
import type { SolutionOverlay } from '../../types/auth';
import type { MouseEvent } from 'react';

export interface PreviewEditSelection {
  id: number;
  prompt: string;
}

interface Props {
  showcase: SolutionShowcase;
  solutionName: string;
  onRequestClick: () => void;
  overlay?: SolutionOverlay;
  /** Logged-in user is viewing their private workspace */
  isOwnerView?: boolean;
  ownerUserId?: number;
  onEditWithAi?: () => void;
  onResetWorkspace?: () => void;
  resetting?: boolean;
  selectionEnabled?: boolean;
  onPreviewElementSelect?: (selection: PreviewEditSelection) => void;
}

const SELECTABLE_SELECTOR = [
  'h1',
  'h2',
  'h3',
  'h4',
  'p',
  'label',
  'button',
  'a',
  'input',
  'select',
  'textarea',
  '[data-overlay-target]',
  '.overlay-feature-widget',
  'section',
  'article',
].join(',');

function cleanText(value: string): string {
  return value.replace(/\s+/g, ' ').trim().slice(0, 180);
}

function classifyElement(el: HTMLElement): string {
  const tag = el.tagName.toLowerCase();
  if (/^h[1-4]$/.test(tag)) return 'title';
  if (tag === 'p') return 'text';
  if (tag === 'button' || tag === 'a') return 'button/link';
  if (tag === 'input' || tag === 'select' || tag === 'textarea' || tag === 'label') return 'form field';
  if (el.classList.contains('overlay-feature-widget')) return 'AI feature widget';
  if (tag === 'section' || tag === 'article') return 'section/layout';
  return tag;
}

function cssEscape(value: string): string {
  return value.replace(/[^a-zA-Z0-9_-]/g, (char) => `\\${char}`);
}

function stableClassName(el: HTMLElement): string | undefined {
  return Array.from(el.classList).find((cls) => {
    if (cls.startsWith('preview-edit-')) return false;
    if (!/^[a-zA-Z][a-zA-Z0-9_-]*$/.test(cls)) return false;
    return cls.includes('__') || cls.endsWith('-widget') || cls.startsWith('overlay-') || cls.startsWith('lh-');
  });
}

function nthOfType(el: HTMLElement): number {
  let index = 1;
  let sibling = el.previousElementSibling;
  while (sibling) {
    if (sibling.tagName === el.tagName) index += 1;
    sibling = sibling.previousElementSibling;
  }
  return index;
}

function selectorHint(el: HTMLElement, root: HTMLElement): string {
  const overlayTarget = el.getAttribute('data-overlay-target');
  if (overlayTarget) return `[data-overlay-target="${overlayTarget}"]`;
  const stableClass = stableClassName(el);
  if (stableClass) return `.${cssEscape(stableClass)}`;

  const parts: string[] = [];
  let node: HTMLElement | null = el;
  while (node && node !== root && parts.length < 4) {
    const tag = node.tagName.toLowerCase();
    const cls = stableClassName(node);
    parts.unshift(cls ? `.${cssEscape(cls)}` : `${tag}:nth-of-type(${nthOfType(node)})`);
    node = node.parentElement;
    if (node) {
      const parentClass = stableClassName(node);
      if (parentClass) {
        parts.unshift(`.${cssEscape(parentClass)}`);
        break;
      }
    }
  }
  return parts.join(' > ') || el.tagName.toLowerCase();
}

function readableElementText(el: HTMLElement): string {
  if (el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement) {
    return cleanText(el.value || el.placeholder || el.getAttribute('aria-label') || '');
  }
  if (el instanceof HTMLSelectElement) {
    return cleanText(el.selectedOptions[0]?.textContent || el.getAttribute('aria-label') || '');
  }
  return cleanText(el.innerText || el.textContent || el.getAttribute('aria-label') || '');
}

function getSelectableElement(target: EventTarget | null, root: HTMLElement): HTMLElement | null {
  if (!(target instanceof HTMLElement)) return null;
  const el = target.closest<HTMLElement>(SELECTABLE_SELECTOR);
  if (!el || !root.contains(el)) return null;
  return el;
}

function buildSelectionPrompt(el: HTMLElement, root: HTMLElement): string {
  const type = classifyElement(el);
  const selector = selectorHint(el, root);
  const text = readableElementText(el);
  return [
    `Change this selected ${type} in the live preview.`,
    `Element selector: ${selector}`,
    text ? `Current text/value: "${text}"` : '',
    '',
    'Requested change: ',
  ].filter(Boolean).join('\n');
}

export default function SolutionShowcaseDemo({
  showcase,
  solutionName,
  onRequestClick,
  overlay,
  isOwnerView,
  ownerUserId,
  onEditWithAi,
  onResetWorkspace,
  resetting,
  selectionEnabled,
  onPreviewElementSelect,
}: Props) {
  const DemoComponent = getShowcaseDemoComponent(showcase.solutionId);
  const activeOverlay = isOwnerView ? overlay : undefined;

  const clearPreviewSelection = (root: HTMLElement) => {
    root.querySelectorAll('.preview-edit-hover, .preview-edit-selected').forEach((el) => {
      el.classList.remove('preview-edit-hover', 'preview-edit-selected');
    });
  };

  const handlePreviewClick = (e: MouseEvent<HTMLDivElement>) => {
    if (!selectionEnabled || !onPreviewElementSelect) return;
    const root = e.currentTarget;
    const el = getSelectableElement(e.target, root);
    if (!el) return;

    e.preventDefault();
    e.stopPropagation();
    clearPreviewSelection(root);
    el.classList.add('preview-edit-selected');
    onPreviewElementSelect({ id: Date.now(), prompt: buildSelectionPrompt(el, root) });
  };

  const handlePreviewMouseOver = (e: MouseEvent<HTMLDivElement>) => {
    if (!selectionEnabled) return;
    const root = e.currentTarget;
    root.querySelectorAll('.preview-edit-hover').forEach((el) => el.classList.remove('preview-edit-hover'));
    const el = getSelectableElement(e.target, root);
    if (el && !el.classList.contains('preview-edit-selected')) el.classList.add('preview-edit-hover');
  };

  const handlePreviewMouseLeave = (e: MouseEvent<HTMLDivElement>) => {
    e.currentTarget.querySelectorAll('.preview-edit-hover').forEach((el) => el.classList.remove('preview-edit-hover'));
  };

  return (
    <div
      key={ownerUserId ? `owner-${ownerUserId}` : 'guest'}
      className={
        isOwnerView
          ? `user-version-demo user-codegen user-codegen-${showcase.solutionId}${selectionEnabled ? ' preview-select-mode' : ''}`
          : undefined
      }
      onClickCapture={handlePreviewClick}
      onMouseOverCapture={handlePreviewMouseOver}
      onMouseLeave={handlePreviewMouseLeave}
    >
      {isOwnerView && onEditWithAi && onResetWorkspace && (
        <UserVersionBar
          solutionName={solutionName}
          overlay={overlay ?? {}}
          onEdit={onEditWithAi}
          onReset={onResetWorkspace}
          resetting={resetting}
        />
      )}
      <ShowcaseOverlayProvider
        overlay={activeOverlay}
        solutionId={showcase.solutionId}
        defaultBusinessName={showcase.businessName}
      >
        <OverlayThemeStyle solutionId={showcase.solutionId} />
        <OverlayGeneratedFiles solutionId={showcase.solutionId} />
        <DemoComponent
          showcase={showcase}
          onRequestClick={onRequestClick}
          overlay={activeOverlay}
        />
        <OverlayElementEdits solutionId={showcase.solutionId} />
      </ShowcaseOverlayProvider>
    </div>
  );
}
