/**
 * The consultation's own top bar: the BMV logo, five steps, and where they are.
 *
 * The site's navigation is for browsing; this is one conversation from a
 * question to a package, and a menu of other pages in the middle of it is an
 * exit sign. The five marks say how far along they are without a word. The
 * logo is the site's own component — the same mark as everywhere else.
 */
import Logo from '../Logo';

const STEP_NAMES = ['Your situation', 'Questions', 'Diagnosis', 'Your answer', 'Your package'] as const;

export default function Chrome({ step, where, right }: {
  /** 0-4, which of the five is current. 5 marks all five done. */
  step: number;
  where: string;
  right?: React.ReactNode;
}) {
  return (
    <header className="cx-top">
      <div className="cx-brand">
        <span className="sm:hidden"><Logo /></span>
        <span className="hidden sm:block"><Logo showName /></span>
      </div>
      <div className="cx-steps" aria-label={`Step ${Math.min(step + 1, 5)} of 5: ${where}`}>
        {STEP_NAMES.map((name, i) => (
          <i key={name} className={i < step ? 'on' : i === step ? 'now' : ''} title={name} />
        ))}
      </div>
      <p className="cx-where">
        {right}
        <span>{where}</span>
      </p>
    </header>
  );
}
