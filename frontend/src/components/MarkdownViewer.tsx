interface Props {
  content: string;
}

export default function MarkdownViewer({ content }: Props) {
  if (!content) return <p className="text-slate-400 italic">Not generated yet.</p>;

  const html = content
    .replace(/^### (.+)$/gm, '<h3 class="text-lg font-bold mt-4 mb-2">$1</h3>')
    .replace(/^## (.+)$/gm, '<h2 class="text-xl font-bold mt-6 mb-3">$1</h2>')
    .replace(/^# (.+)$/gm, '<h1 class="text-2xl font-bold mt-6 mb-4">$1</h1>')
    .replace(/^\d+\.\s+(.+)$/gm, '<li class="ml-4 mb-1">$1</li>')
    .replace(/^[-*]\s+(.+)$/gm, '<li class="ml-4 mb-1 list-disc">$1</li>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\n\n/g, '</p><p class="mb-3 text-sm text-slate-700 leading-relaxed">')
    .replace(/\n/g, '<br/>');

  return (
    <div
      className="prose-sm max-w-none"
      dangerouslySetInnerHTML={{ __html: `<p class="mb-3 text-sm text-slate-700 leading-relaxed">${html}</p>` }}
    />
  );
}
