import SiteNav from '../components/SiteNav';
import SiteFooter from '../components/SiteFooter';
import AboutHero from '../components/about/AboutHero';
import AboutManifesto from '../components/about/AboutManifesto';
import AboutStats from '../components/about/AboutStats';
import AboutStory from '../components/about/AboutStory';
import AboutPrinciples from '../components/about/AboutPrinciples';
import AboutEngineering from '../components/about/AboutEngineering';
import AboutFinale from '../components/about/AboutFinale';

export default function AboutPage() {
  return (
    <div className="min-h-screen bg-white overflow-x-hidden">
      <SiteNav />
      <AboutHero />
      <AboutManifesto />
      <AboutStats />
      <AboutStory />
      <AboutPrinciples />
      <AboutEngineering />
      <AboutFinale />
      <SiteFooter />
    </div>
  );
}
