export function SitePageHeader({ eyebrow, title, subtitle }: { eyebrow?: string; title: string; subtitle?: string }) {
  return (
    <header className="sn-page-head sn-page-head--patient">
      <span className="sn-page-head__role">Client website</span>
      {eyebrow && <p className="sn-page-head__eyebrow">{eyebrow}</p>}
      <h1 className="sn-page-head__title">{title}</h1>
      {subtitle && <p className="sn-page-head__sub">{subtitle}</p>}
    </header>
  );
}

export function StaffPageHeader({
  role,
  title,
  subtitle,
}: {
  role: 'inbox' | 'schedule' | 'admin'; // inbox maps to intake styles
  title: string;
  subtitle?: string;
}) {
  const labels = {
    inbox: 'Staff · Client DM console',
    schedule: 'Front desk · Chair calendar',
    admin: 'Owner · Studio hub',
  };
  const roleClass = role === 'inbox' ? 'intake' : role;
  return (
    <header className={`sn-page-head sn-page-head--${roleClass}`}>
      <span className="sn-page-head__role">{labels[role]}</span>
      <h1 className="sn-page-head__title">{title}</h1>
      {subtitle && <p className="sn-page-head__sub">{subtitle}</p>}
    </header>
  );
}
