import SubmitWizard from '../components/SubmitWizard';
import SiteNav from '../components/SiteNav';
import SiteFooter from '../components/SiteFooter';
import SubmitHero from '../components/submit/SubmitHero';
import SubmitTips from '../components/submit/SubmitTips';

export default function SubmitPage() {
  return (
    <div className="min-h-screen hero-surface relative overflow-hidden">
      <div className="absolute inset-0 hero-mesh pointer-events-none opacity-80" />
      <div className="absolute inset-0 cinematic-grid opacity-35 pointer-events-none" />
      <div className="hero-blob w-[480px] h-[280px] bg-blue-400/25 -top-20 -right-24" />
      <div className="hero-blob w-[420px] h-[260px] bg-cyan-400/20 -bottom-24 -left-28" />
      <div className="hero-blob w-[320px] h-[200px] bg-indigo-400/15 top-1/3 left-1/2 -translate-x-1/2" />

      <SiteNav />

      <div className="relative z-10 section-padding pb-20 pt-24">
        <div className="container-max max-w-6xl">
          <SubmitHero />

          <div className="grid lg:grid-cols-[1fr_300px] gap-8 xl:gap-10 items-start">
            <div className="order-2 lg:order-1">
              <SubmitWizard />
            </div>
            <div className="order-1 lg:order-2">
              <SubmitTips />
            </div>
          </div>
        </div>
      </div>

      <SiteFooter />
    </div>
  );
}
