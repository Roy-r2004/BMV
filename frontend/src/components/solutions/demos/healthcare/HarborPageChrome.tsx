/** Role-aware page headers — keeps patient vs staff vs admin visually distinct. */

export function SitePageHeader({
  eyebrow,
  title,
  subtitle,
}: {
  eyebrow?: string;
  title: string;
  subtitle?: string;
}) {
  return (
    <header className="hc-page-head hc-page-head--patient">
      <span className="hc-page-head__role">Patient website</span>
      {eyebrow && <p className="hc-page-head__eyebrow">{eyebrow}</p>}
      <h1 className="hc-page-head__title">{title}</h1>
      {subtitle && <p className="hc-page-head__sub">{subtitle}</p>}
    </header>
  );
}

export function StaffPageHeader({
  role,
  title,
  subtitle,
}: {
  role: 'intake' | 'schedule' | 'admin';
  title: string;
  subtitle?: string;
}) {
  const labels = {
    intake: 'Staff · AI intake console',
    schedule: 'Front desk · Clinic calendar',
    admin: 'Practice manager · Admin',
  };
  return (
    <header className={`hc-page-head hc-page-head--${role}`}>
      <span className="hc-page-head__role">{labels[role]}</span>
      <h1 className="hc-page-head__title">{title}</h1>
      {subtitle && <p className="hc-page-head__sub">{subtitle}</p>}
    </header>
  );
}
