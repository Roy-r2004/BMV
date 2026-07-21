import SubmitWizard from '../components/SubmitWizard';
import SiteNav from '../components/SiteNav';
import SiteFooter from '../components/SiteFooter';
import SubmitHero from '../components/submit/SubmitHero';
import SubmitTips from '../components/submit/SubmitTips';

export default function SubmitPage() {
  return (
    <div className="submit-page min-h-screen">
      <SiteNav />

      <div className="relative z-10 section-padding pb-10 pt-24">
        <div className="container-max max-w-6xl">
          <SubmitHero />
          <SubmitTips />

          <div className="grid lg:grid-cols-[1fr_300px] gap-6 lg:gap-10 items-start">
            <div className="min-w-0">
              <SubmitWizard />
            </div>
            <div className="hidden lg:block">
              <SubmitTips desktopOnly />
            </div>
          </div>
        </div>
      </div>

      <div className="hidden sm:block">
        <SiteFooter />
      </div>
    </div>
  );
}
