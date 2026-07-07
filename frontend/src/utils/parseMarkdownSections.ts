export interface MarkdownSection {
  title: string;
  body: string;
  kind: SectionKind;
}

export type SectionKind =
  | 'summary'
  | 'score'
  | 'concept'
  | 'journey'
  | 'features'
  | 'technical'
  | 'questions'
  | 'timeline'
  | 'general';

/** Remove inline markdown emphasis markers for plain-text display. */
export function stripMarkdownFormatting(text: string): string {
  return text
    .replace(/\*\*(.+?)\*\*/g, '$1')
    .replace(/\*(.+?)\*/g, '$1')
    .replace(/__(.+?)__/g, '$1')
    .replace(/_(.+?)_/g, '$1')
    .trim();
}

/** Strip underline dividers and normalize whitespace. */
export function cleanMarkdownText(text: string): string {
  return stripMarkdownFormatting(
    text
      .replace(/^[-=]{3,}\s*$/gm, '')
      .replace(/\n{3,}/g, '\n\n')
      .trim(),
  );
}

function classifySection(title: string): SectionKind {
  const t = title.toLowerCase();
  if (t.includes('score') || t.includes('fit')) return 'score';
  if (t.includes('concept name') || t.includes('product promise')) return 'concept';
  if (t.includes('journey')) return 'journey';
  if (t.includes('feature') || t.includes('screens') || t.includes('integration')) return 'features';
  if (t.includes('question') || t.includes('assumption') || t.includes('risk')) return 'questions';
  if (t.includes('timeline') || t.includes('complexity') || t.includes('pricing')) return 'timeline';
  if (t.includes('summary') || t.includes('why this')) return 'summary';
  if (t.includes('data') || t.includes('stack') || t.includes('api')) return 'technical';
  return 'general';
}

function cleanTitle(title: string): string {
  return title.replace(/\*\*/g, '').trim();
}

/**
 * Parse AI blueprint markdown — supports **Title** + underline, ## headings, and numbered titles.
 * Numbered list items inside a section stay in the body (not split into cards).
 */
export function parseMarkdownSections(content: string): MarkdownSection[] {
  if (!content?.trim()) return [];

  const sections: MarkdownSection[] = [];
  const lines = content.split('\n');
  let current: { title: string; lines: string[] } | null = null;

  const push = () => {
    if (!current) return;
    const body = cleanMarkdownText(current.lines.join('\n'));
    const title = cleanTitle(current.title);
    if (body.length >= 2 && title) {
      sections.push({ title, body, kind: classifySection(title) });
    }
    current = null;
  };

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const trimmed = line.trim();

    const boldTitle = trimmed.match(/^\*\*(.+?)\*\*$/);
    const nextLine = i + 1 < lines.length ? lines[i + 1].trim() : '';
    const nextIsUnderline = /^[-=]{3,}$/.test(nextLine);

    if (boldTitle && nextIsUnderline) {
      push();
      current = { title: boldTitle[1], lines: [] };
      i++;
      continue;
    }

    const heading = trimmed.match(/^#{1,4}\s+(.+)$/);
    if (heading) {
      push();
      current = { title: heading[1], lines: [] };
      continue;
    }

    if (/^[-=]{3,}$/.test(trimmed)) continue;

    // Only top-level numbered titles when not inside a section (rare)
    if (!current) {
      const numberedTitle = trimmed.match(/^(\d+)\.\s+(.+)$/);
      if (numberedTitle && trimmed.length < 80 && !trimmed.endsWith('.')) {
        push();
        current = { title: numberedTitle[2], lines: [] };
        continue;
      }
    }

    if (current) {
      current.lines.push(line);
    } else if (trimmed) {
      current = { title: 'Overview', lines: [line] };
    }
  }
  push();

  if (!sections.length) {
    const body = cleanMarkdownText(content);
    if (body) return [{ title: 'Blueprint', body, kind: 'general' }];
  }

  return sections;
}

export function highlightSections(sections: MarkdownSection[], keywords: string[]): MarkdownSection[] {
  const lower = keywords.map((k) => k.toLowerCase());
  const matched = sections.filter((s) =>
    lower.some((k) => s.title.toLowerCase().includes(k)),
  );
  return matched.length ? matched : sections.slice(0, 8);
}

/** Extract list items from body text. */
export function extractListItems(body: string): string[] {
  return body
    .split('\n')
    .map((l) => l.trim())
    .filter((l) => /^\d+\.\s+/.test(l) || /^[-*]\s+/.test(l))
    .map((l) => stripMarkdownFormatting(l.replace(/^\d+\.\s+/, '').replace(/^[-*]\s+/, '')))
    .filter(Boolean);
}

/** Single-line value sections (score, concept name, etc.) */
export function extractScalar(body: string): string {
  const cleaned = cleanMarkdownText(body).replace(/\*\*/g, '');
  const lines = cleaned.split('\n').map((l) => l.trim()).filter(Boolean);
  return lines.join(' ').slice(0, 200);
}
