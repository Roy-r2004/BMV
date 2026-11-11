import { Link } from 'react-router-dom';
import { COMPANY } from '../data/company';
import '../styles/footer.css';

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

/**
 * The footer every page ends on: black, the firm and its address, the link
 * columns, and the line the firm stands on, set as large as the page allows.
 */
export default function SiteFooter() {
  const year = new Date().getFullYear();

  return (
    <footer className="sf">
      <div className="sf-top">
        <div className="sf-firm">
          <Link to="/" className="sf-brand">
            <img src="/logo-160.png" alt="" width={40} height={40} />
            <span>{COMPANY.name}</span>
          </Link>
          <p>
            An AI consultancy. We test business decisions against the client's own figures, and design and build the systems
            that carry them out.
          </p>
          <a className="sf-mail" href={`mailto:${COMPANY.email}`}>
            {COMPANY.email}
          </a>
        </div>
        {COLUMNS.map((c) => (
          <div className="sf-col" key={c.title}>
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

      <p className="sf-line" aria-hidden="true">
        Your idea, tested and built.
      </p>

      <div className="sf-base">
        <p>
          © {year} {COMPANY.name}. {COMPANY.registered}.
        </p>
        {/* the server photograph is CC BY-SA and must be credited where it is shown; the Dubai photograph is CC0 */}
        <p>
          Server photo:{' '}
          <a href="https://commons.wikimedia.org/wiki/File:Wikimedia_Foundation_Servers-8055_14.jpg" target="_blank" rel="noopener noreferrer">
            Victor Grigas
          </a>
          , Wikimedia Commons, CC BY-SA 3.0
        </p>
        <Link to="/login">Client sign in</Link>
      </div>
    </footer>
  );
}
