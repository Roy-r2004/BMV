import type { ComponentType } from 'react';
import type { SolutionShowcase } from '../../../data/showcaseDemos';
import HealthcareShowcaseDemo from './healthcare/HealthcareShowcaseDemo';
import GenericShowcaseDemo from './GenericShowcaseDemo';

export interface ShowcaseDemoProps {
  showcase: SolutionShowcase;
  onRequestClick: () => void;
}

/** Custom demos — one industry at a time until approved */
const CUSTOM_DEMOS: Partial<Record<string, ComponentType<ShowcaseDemoProps>>> = {
  healthcare: HealthcareShowcaseDemo,
};

export function getShowcaseDemoComponent(solutionId: string): ComponentType<ShowcaseDemoProps> {
  return CUSTOM_DEMOS[solutionId] ?? GenericShowcaseDemo;
}

export function hasCustomShowcaseDemo(solutionId: string): boolean {
  return Boolean(CUSTOM_DEMOS[solutionId]);
}
