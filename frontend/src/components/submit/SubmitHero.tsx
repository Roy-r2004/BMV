export default function SubmitHero() {
  return (
    <div className="submit-hero text-center mb-6 sm:mb-10 relative">
      <span className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-white border border-blue-200/70 text-blue-700 text-[10px] sm:text-xs font-semibold uppercase tracking-[0.16em] mb-3.5 sm:mb-5 shadow-sm">
        <span className="inline-flex rounded-full h-2 w-2 bg-cyan-500" />
        Free AI preview
      </span>

      <h1 className="text-3xl sm:text-4xl lg:text-[2.75rem] font-bold text-navy mb-2.5 sm:mb-3 leading-[1.1] tracking-tight">
        Build your <span className="gradient-text">business version</span>
      </h1>

      <p className="submit-hero__sub text-slate-600 max-w-xl mx-auto text-sm sm:text-base leading-relaxed px-1">
        Five quick steps — then a custom preview built for your business.
      </p>

      <div className="submit-hero__meta flex flex-wrap items-center justify-center gap-x-5 gap-y-1.5 mt-4 sm:mt-6 text-[11px] sm:text-xs text-slate-500">
        {['No card', 'Preview free'].map((item) => (
          <span key={item} className="flex items-center gap-1.5">
            <span className="w-1 h-1 rounded-full bg-cyan-500" />
            {item}
          </span>
        ))}
      </div>
    </div>
  );
}
