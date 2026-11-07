import { Link } from 'react-router-dom';
import { COMPANY } from '../data/company';

const COLUMNS = [
  {
    title: 'Services',
    links: [
      { to: '/services#consultation', label: 'Consultation' },
      { to: '/services#build', label: 'System build' },
      { to: '/private-ai', label: 'Private AI' },
      { to: '/solutions', label: 'Example systems' },
    ],
  },
  {
    title: 'Firm',
    links: [
      { to: '/about', label: 'About' },
      { to: '/approach', label: 'Approach' },
      { to: '/contact', label: 'Contact' },
      { to: '/demo', label: 'Start a consultation' },
    ],
  },
  {
    title: 'Legal',
    links: [
      { to: '/privacy', label: 'Privacy notice' },
      { to: '/terms', label: 'Terms of engagement' },
    ],
  },
] as const;

export default function SiteFooter() {
  const year = new Date().getFullYear();

  return (
    <footer className="fm-foot">
      <div className="fm-wrap">
        <div className="fm-foot-top">
          <div className="fm-foot-brand">
            <Link to="/" className="fm-brand">
              <img src="/logo-160.png" alt="" width={36} height={36} />
              <span>{COMPANY.name}</span>
            </Link>
            <p>
              An AI consultancy. We test business decisions against the client's own figures, and design and build the
              systems that carry them out.
            </p>
            <a className="fm-foot-mail" href={`mailto:${COMPANY.email}`}>
              {COMPANY.email}
            </a>
          </div>

          <div className="fm-foot-cols">
            {COLUMNS.map((c) => (
              <div key={c.title}>
                <h2>{c.title}</h2>
                <ul>
                  {c.links.map((l) => (
                    <li key={l.label}>
                      <Link to={l.to}>{l.label}</Link>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </div>

        <div className="fm-foot-base">
          <p>
            © {year} {COMPANY.name}. {COMPANY.registered}.
          </p>
          <Link to="/login">Client sign in</Link>
        </div>
      </div>
    </footer>
  );
}
