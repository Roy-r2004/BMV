import { getShowcaseDemoComponent } from './demos/showcaseRegistry';
import type { SolutionShowcase } from '../../data/showcaseDemos';

interface Props {
  showcase: SolutionShowcase;
  onRequestClick: () => void;
}

export default function SolutionShowcaseDemo({ showcase, onRequestClick }: Props) {
  const DemoComponent = getShowcaseDemoComponent(showcase.solutionId);
  return <DemoComponent showcase={showcase} onRequestClick={onRequestClick} />;
}
