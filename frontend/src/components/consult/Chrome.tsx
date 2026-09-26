/**
 * The consultation's own top bar: the BMV logo, five stages, and where they are.
 *
 * The site's navigation is for browsing; this is one engagement from a brief
 * to a set of plans, and a menu of other pages in the middle of it is an exit
 * sign. Each stage is named under its bar: the current one in blue, the ones
 * behind them in ink. The logo is the site's own component.
 */
import Logo from '../Logo';

const STEP_NAMES = ['The brief', 'Fact-finding', 'Analysis', 'The answer', 'Your plans'] as const;

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
      <ol className="cx-steps" aria-label={`Stage ${Math.min(step + 1, 5)} of 5: ${STEP_NAMES[Math.min(step, 4)]}`}>
        {STEP_NAMES.map((name, i) => (
          <li
            key={name}
            className={`cx-step${i < step ? ' done' : i === step ? ' now' : ''}`}
            aria-current={i === step ? 'step' : undefined}
          >
            <i />
            <span>{name}</span>
          </li>
        ))}
      </ol>
      <p className="cx-where">
        {right}
        <span>{where}</span>
      </p>
    </header>
  );
}
