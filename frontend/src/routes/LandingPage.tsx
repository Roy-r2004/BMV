import Hero from '../components/Hero';
import WhatYoullGet from '../components/WhatYoullGet';
import TheMachine from '../components/TheMachine';
import UseCases from '../components/UseCases';
import Packages from '../components/Packages';
import FAQ from '../components/FAQ';
import CTASection from '../components/CTASection';
import SiteNav from '../components/SiteNav';
import SiteFooter from '../components/SiteFooter';

export default function LandingPage() {
  return (
    <div className="bg-white overflow-x-hidden">
      <SiteNav />
      <div id="hero">
        <Hero />
      </div>
      <WhatYoullGet />
      <TheMachine />
      <div id="use-cases">
        <UseCases />
      </div>
      <div id="packages">
        <Packages />
      </div>
      <FAQ />
      <div id="get-started">
        <CTASection />
      </div>
      <SiteFooter />
    </div>
  );
}
