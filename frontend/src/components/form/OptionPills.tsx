import type { ReactNode } from 'react';

interface Props {
  name: string;
  options: string[];
  value: string;
  onChange: (value: string) => void;
  icons?: Record<string, ReactNode>;
}

export default function OptionPills({ name, options, value, onChange, icons }: Props) {
  return (
    <div className="flex flex-wrap gap-2.5">
      {options.map((opt) => {
        const selected = value === opt;
        const icon = icons?.[opt];
        return (
          <label key={opt} className="cursor-pointer group">
            <input
              type="radio"
              name={name}
              value={opt}
              checked={selected}
              onChange={() => onChange(opt)}
              className="sr-only"
            />
            <span
              className={`inline-flex items-center gap-2 px-4 py-3 sm:py-2.5 rounded-xl text-sm font-medium border min-h-[2.75rem] transition-colors duration-200 ${
                selected
                  ? 'border-blue-500/50 bg-gradient-to-r from-blue-600 to-cyan-500 text-white shadow-md shadow-blue-500/20'
                  : 'border-slate-200 bg-white text-slate-600'
              }`}
            >
              {icon && (
                <span
                  className={`shrink-0 w-7 h-7 rounded-lg flex items-center justify-center transition-colors ${
                    selected ? 'bg-white/20 text-white' : 'bg-blue-50 text-blue-600 group-hover:bg-blue-100'
                  }`}
                >
                  {icon}
                </span>
              )}
              <span>{opt}</span>
            </span>
          </label>
        );
      })}
    </div>
  );
}
