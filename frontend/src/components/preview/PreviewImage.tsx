import { useState, type CSSProperties } from 'react';

interface Props {
  src: string;
  alt: string;
  className?: string;
  fallbackClassName?: string;
  style?: CSSProperties;
}

/** Image with gradient fallback if the file fails to load. */
export default function PreviewImage({ src, alt, className = '', fallbackClassName = '', style }: Props) {
  const [failed, setFailed] = useState(false);

  if (failed) {
    return (
      <div
        className={`preview-image-fallback ${fallbackClassName || className}`}
        style={style}
        role="img"
        aria-label={alt}
      />
    );
  }

  return (
    <img
      src={src}
      alt={alt}
      className={className}
      style={style}
      loading="lazy"
      decoding="async"
      onError={() => setFailed(true)}
    />
  );
}
