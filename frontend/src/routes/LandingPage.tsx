import Hero from '../components/Hero';
import HowItWorks from '../components/HowItWorks';
import ExamplesTeaser from '../components/ExamplesTeaser';
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
      <HowItWorks />
      <ExamplesTeaser />
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
