import { useShowcaseOverlay } from '../../../../context/ShowcaseOverlayContext';
import { buildOverlayThemeCss } from '../../../../utils/overlayThemeConfig';

interface Props {
  solutionId: string;
}

/** Injects live CSS so overlay colors repaint buttons, accents, and backgrounds */
export default function OverlayThemeStyle({ solutionId }: Props) {
  const { primaryColor, secondaryColor, backgroundColor, accentColor } = useShowcaseOverlay();

  const css = buildOverlayThemeCss(solutionId, {
    primary: primaryColor,
    secondary: secondaryColor,
    background: backgroundColor,
    accent: accentColor ?? secondaryColor,
  });

  if (!css) return null;
  return <style data-overlay-theme={solutionId}>{css}</style>;
}
