/**
 * The consultant's narrated trail, reshaped into something a screen can lay out.
 *
 * The server appends one line at a time and never edits: "here is an
 * explanation", later "here is what its test found", later "this one leads".
 * That is the right shape to store and the wrong one to draw — a log renders
 * as a column that grows off the bottom of the screen, and the verdict for an
 * explanation ends up nowhere near the explanation.
 *
 * So this folds the log back into passes, each a board: the explanations, the
 * verdict each one earned, which leads, and how the two reviewers did. A
 * re-diagnosis is a second pass. Pure and side-effect free, so the same trail
 * always draws the same screen — including one reloaded halfway through.
 */
import type { ThinkingStep } from '../api/consultant';

export type Verdict = 'supported' | 'refuted' | 'untestable';

export interface BoardHypothesis {
  text: string;
  area?: string;
  /** false = software cannot fix this cause. Undefined means we were not told. */
  software?: boolean;
  /** This is the explanation the client walked in with. */
  theirs?: boolean;
  verdict?: Verdict;
  because?: string;
  cites: string[];
  leading: boolean;
}

export interface BoardReviewer {
  angle: 'alternative' | 'confirmation';
  kills: boolean;
  because: string;
}

export type PassStage = 'considering' | 'testing' | 'challenging' | 'settled';

export interface BoardPass {
  /** This pass ran because the one before it lost its leading explanation. */
  retry: boolean;
  hypotheses: BoardHypothesis[];
  testing: boolean;
  challenging: boolean;
  reviewers: BoardReviewer[];
  settled?: 'survived' | 'killed' | 'unchallenged';
}

export function derivePasses(steps: ThinkingStep[]): BoardPass[] {
  const passes: BoardPass[] = [];
  let cur: BoardPass | null = null;

  for (const s of steps) {
    // A header opens a pass. Lines before the first header belong to a pass we
    // only have the tail of (the server keeps the most recent lines), so they
    // are dropped rather than invented a home.
    if (s.kind === 'considering' && s.count != null) {
      cur = {
        retry: Boolean(s.retry),
        hypotheses: [],
        testing: false,
        challenging: false,
        reviewers: [],
      };
      passes.push(cur);
      continue;
    }
    if (!cur) continue;

    switch (s.kind) {
      case 'considering':
        cur.hypotheses.push({
          text: s.text,
          area: s.area,
          software: s.software,
          theirs: s.theirs,
          cites: [],
          leading: false,
        });
        break;

      case 'testing': {
        if (s.leading) {
          // Matched on the statement, not position: the verdicts arrive in a
          // burst after the parallel tests finish and the order is not a
          // contract worth leaning on.
          const h = cur.hypotheses.find((x) => x.text === s.text);
          if (h) h.leading = true;
        } else {
          cur.testing = true;
        }
        break;
      }

      case 'verdict': {
        const h = cur.hypotheses.find((x) => x.text === s.text);
        if (h) {
          h.verdict = s.verdict;
          h.because = s.because;
          h.cites = s.cites ?? [];
        }
        break;
      }

      case 'challenge':
        if (s.angle) {
          cur.reviewers.push({ angle: s.angle, kills: Boolean(s.kills), because: s.text });
        } else {
          cur.challenging = true;
        }
        break;

      case 'settled':
        cur.settled = s.status;
        break;
    }
  }
  return passes;
}

export function stageOf(pass: BoardPass): PassStage {
  if (pass.settled) return 'settled';
  if (pass.challenging) return 'challenging';
  if (pass.testing) return 'testing';
  return 'considering';
}
