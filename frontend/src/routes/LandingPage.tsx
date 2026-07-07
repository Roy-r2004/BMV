import Hero from '../components/Hero';
import LandingHighlights from '../components/landing/LandingHighlights';
import HowItWorks from '../components/HowItWorks';
import ExamplesTeaser from '../components/ExamplesTeaser';
import UseCases from '../components/UseCases';
import Packages from '../components/Packages';
import FAQ from '../components/FAQ';
import CTASection from '../components/CTASection';
import SiteNav from '../components/SiteNav';
import SiteFooter from '../components/SiteFooter';
import LandingGuide from '../components/landing/LandingGuide';

export default function LandingPage() {
  return (
    <div className="bg-white overflow-x-hidden">
      <SiteNav />
      <div id="hero">
        <Hero />
      </div>
      <div id="consultancy">
        <LandingHighlights />
      </div>
      <HowItWorks />
      <div id="examples">
        <ExamplesTeaser />
      </div>
      <div id="use-cases">
        <UseCases />
      </div>
      <div id="packages">
        <Packages />
      </div>
      <div id="faq">
        <FAQ />
      </div>
      <div id="get-started">
        <CTASection />
      </div>
      <SiteFooter />
      <LandingGuide />
    </div>
  );
}
