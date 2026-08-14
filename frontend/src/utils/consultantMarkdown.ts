/** Parsers for the consultant-service deliverable documents.
 *
 * The consultant-service prompts (blueprint.j2 / technical_plan.j2) mandate a
 * fixed `## Heading` skeleton, so the result page can parse sections
 * deterministically and render bespoke layouts. Every accessor degrades to
 * undefined/empty when a section is missing — callers fall back gracefully.
 */

export interface MdSection {
  title: string;
  body: string;
}

export interface MdItem {
  title: string;
  text: string;
  /** Un-stripped body, for callers that want to re-parse nested lists (e.g. parseListItems). */
  raw?: string;
}

export function splitH2Sections(markdown: string): MdSection[] {
  const sections: MdSection[] = [];
  const parts = markdown.split(/^##\s+(?!#)/m).filter(Boolean);
  for (const part of parts) {
    const newline = part.indexOf('\n');
    if (newline === -1) continue;
    sections.push({
      title: part.slice(0, newline).trim().replace(/#+$/, '').trim(),
      body: part.slice(newline + 1).trim(),
    });
  }
  return sections;
}

export function findSection(sections: MdSection[], pattern: RegExp): MdSection | undefined {
  return sections.find((s) => pattern.test(s.title.toLowerCase()));
}

/** Sub-sections introduced with `### Name`. */
export function splitH3Subsections(body: string): MdItem[] {
  const items: MdItem[] = [];
  const parts = body.split(/^###\s+/m).filter(Boolean);
  for (const part of parts) {
    const newline = part.indexOf('\n');
    if (newline === -1) continue;
    const rawBody = part.slice(newline + 1).trim();
    items.push({
      title: stripInlineMarkdown(part.slice(0, newline).trim()),
      text: stripInlineMarkdown(rawBody),
      raw: rawBody,
    });
  }
  return items;
}

/** List items (`- x`, `* x`, `1. x`), with a leading `**Bold**` promoted to title. */
export function parseListItems(body: string): MdItem[] {
  const items: MdItem[] = [];
  // Join wrapped lines: a list item runs until the next marker or blank line.
  const lines = body.split('\n');
  let current: string | null = null;
  const flush = () => {
    if (!current) return;
    const raw = current.trim();
    current = null;
    if (!raw) return;
    const bold = raw.match(/^\*\*(.+?)\*\*[:\s—–-]*\s*(.*)$/s);
    if (bold) {
      items.push({
        title: stripInlineMarkdown(bold[1]).replace(/:+$/, ''),
        text: stripInlineMarkdown(bold[2]),
      });
    } else {
      items.push({ title: '', text: stripInlineMarkdown(raw) });
    }
  };
  for (const line of lines) {
    const marker = line.match(/^\s*(?:[-*+]|\d+[.)])\s+(.*)$/);
    if (marker) {
      flush();
      current = marker[1];
    } else if (current !== null && line.trim()) {
      current += ' ' + line.trim();
    } else {
      flush();
    }
  }
  flush();
  return items;
}

/** First paragraph of a body (text before the first blank line or list). */
export function firstParagraph(body: string): string {
  const beforeList = body.split(/^\s*(?:[-*+]|\d+[.)])\s+/m)[0] ?? body;
  const para = beforeList.split(/\n\s*\n/)[0] ?? beforeList;
  return stripInlineMarkdown(para.replace(/\n/g, ' ').trim());
}

export function firstSentence(text: string): string {
  const match = text.match(/^.+?[.!?](?:\s|$)/);
  return (match ? match[0] : text).trim();
}

export function stripInlineMarkdown(text: string): string {
  return text
    .replace(/\*\*(.+?)\*\*/g, '$1')
    .replace(/\*(.+?)\*/g, '$1')
    .replace(/`(.+?)`/g, '$1')
    .trim();
}

export interface MdPhase {
  title: string;
  fields: { label: string; text: string }[];
}

/** A two-level bullet list — top-level items (e.g. "Phase 1: ...") each
 *  followed by indented child bullets (e.g. "**Delivers:** ..."). Grouped by
 *  indentation rather than `parseListItems`' flat marker scan, so a phase and
 *  its detail lines stay together as one card instead of separate rows. */
export function parseNestedPhases(body: string): MdPhase[] {
  const phases: MdPhase[] = [];
  let current: MdPhase | null = null;
  for (const raw of body.split(/\r\n|\n/)) {
    if (!raw.trim()) continue;
    const marker = raw.match(/^(\s*)(?:[-*+]|\d+[.)])\s+(.*)$/);
    if (!marker) continue;
    const indent = marker[1].length;
    const content = marker[2].trim();
    const bold = content.match(/^\*\*(.+?)\*\*[:\s—–-]*\s*(.*)$/s);
    if (indent === 0) {
      current = { title: stripInlineMarkdown(bold ? bold[1] : content), fields: [] };
      phases.push(current);
    } else if (current) {
      if (bold) {
        current.fields.push({
          label: stripInlineMarkdown(bold[1]).replace(/:+$/, ''),
          text: stripInlineMarkdown(bold[2]),
        });
      } else {
        current.fields.push({ label: '', text: stripInlineMarkdown(content) });
      }
    }
  }
  return phases;
}

/** "Online Booking System (integrated with X)" → { title, sub } for card layouts. */
export function splitFeatureLabel(feature: string): { title: string; sub: string } {
  const paren = feature.match(/^(.*?)\s*\((.+)\)\s*$/);
  if (paren) return { title: paren[1].trim(), sub: paren[2].trim() };
  for (const joiner of [' for ', ' with ', ' — ', ' - ']) {
    const at = feature.indexOf(joiner);
    if (at > 8) {
      return { title: feature.slice(0, at).trim(), sub: feature.slice(at + 1).trim() };
    }
  }
  return { title: feature.trim(), sub: '' };
}
