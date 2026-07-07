import type { ImageTheme } from './demoContent';



interface Props {

  theme: ImageTheme;

  primary: string;

  secondary: string;

  label?: string;

  className?: string;

  aspect?: string;

}



function FitnessMock({ secondary }: { secondary: string }) {

  return (

    <div className="absolute inset-0 flex flex-col justify-between p-6 sm:p-8 text-white">

      <div className="flex items-center justify-between">

        <span className="text-xs font-bold uppercase tracking-widest opacity-90">Client portal</span>

        <span className="text-xs px-2 py-1 rounded-full bg-white/20">Week 4</span>

      </div>

      <div className="grid grid-cols-2 gap-3">

        <div className="rounded-2xl bg-white/15 backdrop-blur-sm border border-white/20 p-4">

          <p className="text-[10px] uppercase tracking-wide opacity-80">Today&apos;s meals</p>

          <p className="text-sm font-bold mt-1">1,840 kcal</p>

          <div className="mt-2 h-1.5 rounded-full bg-white/20 overflow-hidden">

            <div className="h-full rounded-full" style={{ width: '72%', backgroundColor: secondary }} />

          </div>

        </div>

        <div className="rounded-2xl bg-white/15 backdrop-blur-sm border border-white/20 p-4">

          <p className="text-[10px] uppercase tracking-wide opacity-80">Workout</p>

          <p className="text-sm font-bold mt-1">Upper body</p>

          <p className="text-[10px] mt-1 opacity-80">45 min · 6 exercises</p>

        </div>

        <div className="col-span-2 rounded-2xl bg-white/10 border border-white/15 p-4 flex items-center gap-4">

          <div

            className="w-14 h-14 rounded-full border-4 flex items-center justify-center text-xs font-bold shrink-0"

            style={{ borderColor: `${secondary}cc`, color: 'white' }}

          >

            87%

          </div>

          <div>

            <p className="text-xs font-semibold">Habit streak · 12 days</p>

            <p className="text-[10px] opacity-75 mt-0.5">Meals logged · Progress photo due Fri</p>

          </div>

        </div>

      </div>

    </div>

  );

}



function DefaultMock({ theme }: { theme: ImageTheme }) {

  const icons: Record<ImageTheme, string> = {

    wellness: '✦',

    fitness: '◆',

    saas: '▣',

    generic: '●',

  };

  return (

    <div className="absolute inset-0 flex flex-col justify-between p-6 sm:p-8 text-white">

      <div className="flex items-center gap-2">

        <span className="text-2xl opacity-90">{icons[theme]}</span>

        <span className="text-xs font-semibold uppercase tracking-widest opacity-80">

          {theme === 'saas' ? 'Live preview' : theme === 'wellness' ? 'Your experience' : 'Preview'}

        </span>

      </div>

      <div className="space-y-3">

        <div className="h-2 w-3/4 rounded-full bg-white/30" />

        <div className="h-2 w-1/2 rounded-full bg-white/20" />

        <div className="grid grid-cols-3 gap-2 mt-4">

          {[1, 2, 3].map((n) => (

            <div key={n} className="h-14 rounded-xl bg-white/15 backdrop-blur-sm border border-white/10" />

          ))}

        </div>

      </div>

    </div>

  );

}



/** Industry-themed hero visual — avoids wrong stock photos for non-clinic businesses. */

export default function IndustryVisual({

  theme,

  primary,

  secondary,

  label,

  className = '',

  aspect = 'aspect-[4/5]',

}: Props) {

  return (

    <div

      className={`relative overflow-hidden rounded-3xl shadow-2xl shadow-slate-300/50 ${aspect} w-full ${className}`}

      style={{ background: `linear-gradient(145deg, ${primary} 0%, ${secondary} 55%, ${primary}dd 100%)` }}

    >

      <div className="absolute inset-0 opacity-20 bg-[radial-gradient(circle_at_30%_20%,white,transparent_50%)]" />

      {theme === 'fitness' ? (

        <FitnessMock secondary={secondary} />

      ) : (

        <DefaultMock theme={theme} />

      )}

      {label && (

        <div className="absolute bottom-6 left-6 right-6 rounded-2xl bg-white/95 backdrop-blur p-4 shadow-xl text-slate-900">

          <p className="text-xs text-slate-500">{label}</p>

        </div>

      )}

    </div>

  );

}



/** Smaller card thumbnail for service grids */

export function ServiceVisual({

  theme,

  primary,

  secondary,

  className = 'h-32',

}: {

  theme?: ImageTheme;

  primary: string;

  secondary: string;

  className?: string;

}) {

  const isFitness = theme === 'fitness';

  return (

    <div

      className={`w-full ${className} relative overflow-hidden flex items-end p-3`}

      style={{ background: `linear-gradient(135deg, ${primary}cc, ${secondary}ee)` }}

    >

      <div className="absolute inset-0 bg-[linear-gradient(45deg,transparent_40%,rgba(255,255,255,0.12)_50%,transparent_60%)]" />

      {isFitness && (

        <div className="relative z-10 text-white text-[10px] font-semibold uppercase tracking-wide opacity-90">

          Program

        </div>

      )}

    </div>

  );

}


