interface Props {
  content: string;
  variant?: 'default' | 'proposal' | 'technical';
  emptyLabel?: string;
}

function preprocess(content: string): string {
  return content
    .replace(/^[-=]{3,}\s*$/gm, '')
    .replace(/^\*\*(.+?)\*\*\s*$/gm, '## $1')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

export default function MarkdownProse({ content, variant = 'default', emptyLabel }: Props) {
  const cleaned = preprocess(content);

  if (!cleaned) {
    if (emptyLabel) return <p className="text-slate-400 italic text-sm">{emptyLabel}</p>;
    return null;
  }

  const html = cleaned
    .replace(/^### (.+)$/gm, '<h4 class="text-base font-semibold text-slate-900 mt-5 mb-2">$1</h4>')
    .replace(/^## (.+)$/gm, '<h3 class="text-lg font-bold text-slate-900 mt-6 mb-3">$1</h3>')
    .replace(/^# (.+)$/gm, '<h2 class="text-xl font-bold text-slate-900 mt-6 mb-4">$1</h2>')
    .replace(/^\d+\.\s+(.+)$/gm, '<li class="ml-5 mb-2 pl-1 text-slate-600 leading-relaxed">$1</li>')
    .replace(/^[-*]\s+(.+)$/gm, '<li class="ml-5 mb-2 pl-1 list-disc text-slate-600 leading-relaxed">$1</li>')
    .replace(/\*\*(.+?)\*\*/g, '<strong class="text-slate-900 font-semibold">$1</strong>')
    .replace(/`([^`]+)`/g, '<code class="px-1.5 py-0.5 rounded bg-slate-100 text-indigo-700 text-xs font-mono border border-slate-200">$1</code>')
    .replace(/\n\n/g, '</p><p class="mb-4 text-sm text-slate-600 leading-relaxed">')
    .replace(/\n/g, '<br/>');

  const variantClass =
    variant === 'proposal'
      ? 'delivery-prose delivery-prose--proposal'
      : variant === 'technical'
        ? 'delivery-prose delivery-prose--technical'
        : 'delivery-prose';

  return (
    <div
      className={variantClass}
      dangerouslySetInnerHTML={{
        __html: `<p class="mb-4 text-sm text-slate-600 leading-relaxed">${html}</p>`,
      }}
    />
  );
}
