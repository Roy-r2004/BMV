import type { ComponentType } from 'react';
import type { SolutionShowcase } from '../../../data/showcaseDemos';
import HealthcareShowcaseDemo from './healthcare/HealthcareShowcaseDemo';
import StudioNineShowcaseDemo from './personal-care/StudioNineShowcaseDemo';
import EmberShowcaseDemo from './food/EmberShowcaseDemo';
import NorthlineShowcaseDemo from './real-estate/NorthlineShowcaseDemo';
import PeakFormShowcaseDemo from './fitness/PeakFormShowcaseDemo';
import ApexShowcaseDemo from './professional-services/ApexShowcaseDemo';
import LumenShowcaseDemo from './ecommerce/LumenShowcaseDemo';
import SummitShowcaseDemo from './education/SummitShowcaseDemo';
import BrightFixShowcaseDemo from './home-services/BrightFixShowcaseDemo';
import HarborFundShowcaseDemo from './nonprofit/HarborFundShowcaseDemo';
import RowShowcaseDemo from './hospitality/RowShowcaseDemo';
import MetroShowcaseDemo from './automotive/MetroShowcaseDemo';
import GenericShowcaseDemo from './GenericShowcaseDemo';

export interface ShowcaseDemoProps {
  showcase: SolutionShowcase;
  onRequestClick: () => void;
}

/** Bespoke cinematic demos — all 12 industries */
const CUSTOM_DEMOS: Partial<Record<string, ComponentType<ShowcaseDemoProps>>> = {
  healthcare: HealthcareShowcaseDemo,
  'personal-care': StudioNineShowcaseDemo,
  food: EmberShowcaseDemo,
  'real-estate': NorthlineShowcaseDemo,
  fitness: PeakFormShowcaseDemo,
  'professional-services': ApexShowcaseDemo,
  ecommerce: LumenShowcaseDemo,
  education: SummitShowcaseDemo,
  'home-services': BrightFixShowcaseDemo,
  nonprofit: HarborFundShowcaseDemo,
  hospitality: RowShowcaseDemo,
  automotive: MetroShowcaseDemo,
};

export function getShowcaseDemoComponent(solutionId: string): ComponentType<ShowcaseDemoProps> {
  return CUSTOM_DEMOS[solutionId] ?? GenericShowcaseDemo;
}

export function hasCustomShowcaseDemo(solutionId: string): boolean {
  return Boolean(CUSTOM_DEMOS[solutionId]);
}
