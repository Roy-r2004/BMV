const items = [
  { icon: '✦', label: 'Free AI preview', accent: true },
  { icon: '◎', label: 'Built for your business' },
  { icon: '→', label: 'Our team builds it' },
];

export default function HeroTrustBar() {
  return (
    <div className="flex flex-wrap gap-2 justify-center lg:justify-start mt-4">
      {items.map((item) => (
        <span
          key={item.label}
          className={`hero-trust-chip ${item.accent ? 'hero-trust-chip--accent' : ''}`}
        >
          <span className="hero-trust-chip__icon">{item.icon}</span>
          {item.label}
        </span>
      ))}
    </div>
  );
}
