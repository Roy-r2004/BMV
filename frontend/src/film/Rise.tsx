import type { CSSProperties, JSX } from 'react';

/**
 * A headline that rises word by word when its shot comes on screen, like a
 * film title. Words between asterisks are set in the italic accent:
 * "Your idea, *tested* and built".
 */
export default function Rise({
  as: Tag = 'h2',
  className,
  children,
  id,
}: {
  as?: keyof JSX.IntrinsicElements;
  className?: string;
  children: string;
  id?: string;
}) {
  let i = 0;
  const parts = children.split('*');
  const word = (w: string) => (
    <span className="w" key={`w${i}`}>
      <span style={{ '--i': i++ } as CSSProperties}>{w}</span>
    </span>
  );
  const run = (text: string) =>
    text.split(/(\s+)/).map((p, k) => (!p ? null : /^\s+$/.test(p) ? <span key={`s${i}-${k}`}>{p}</span> : word(p)));

  return (
    <Tag className={className} id={id}>
      {parts.map((p, k) => (k % 2 ? <em key={`e${k}`}>{run(p)}</em> : <span key={`t${k}`}>{run(p)}</span>))}
    </Tag>
  );
}
