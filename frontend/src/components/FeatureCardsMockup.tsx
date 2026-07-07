import { getIcon } from './ProductHeroMockup';

interface FeatureCard {
  title: string;
  description: string;
  icon: string;
}

interface Props {
  cards: FeatureCard[];
  primaryColor?: string;
}

export default function FeatureCardsMockup({ cards, primaryColor = '#2563eb' }: Props) {
  return (
    <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
      {cards.map((card, i) => (
        <div key={i} className="card p-5 hover:shadow-md transition-shadow">
          <div className="w-10 h-10 rounded-xl flex items-center justify-center text-xl mb-3" style={{ backgroundColor: `${primaryColor}15` }}>
            {getIcon(card.icon)}
          </div>
          <h4 className="font-semibold mb-1">{card.title}</h4>
          <p className="text-sm text-slate-600">{card.description}</p>
        </div>
      ))}
    </div>
  );
}
