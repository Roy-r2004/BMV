import SiteNav from '../components/SiteNav';
import SiteFooter from '../components/SiteFooter';
import AboutHero from '../components/about/AboutHero';
import AboutManifesto from '../components/about/AboutManifesto';
import AboutStats from '../components/about/AboutStats';
import AboutStory from '../components/about/AboutStory';
import AboutPrinciples from '../components/about/AboutPrinciples';
import AboutEngineering from '../components/about/AboutEngineering';
import AboutFinale from '../components/about/AboutFinale';
import '../styles/about-boom.css';

export default function AboutPage() {
  return (
    <div className="about-boom min-h-screen overflow-x-hidden">
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
