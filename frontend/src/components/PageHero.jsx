// The centred opening of the Guide and About pages: a badge, the title and a
// lead paragraph, with anything else (the Guide's jump links) underneath.
// props: { badge, title, lead, children }
export default function PageHero({ badge, title, lead, children }) {
  return (
    <div className="mb-11 text-center">
      <div className="mb-5 inline-flex items-center gap-2 rounded-full border border-teal/30 bg-teal/[.12] px-3.5 py-1.5 text-[12.5px] font-bold tracking-[.4px] text-teal-dark">
        <span className="h-1.5 w-1.5 rounded-full bg-teal shadow-[0_0_10px_#2A9D8F]" /> {badge}
      </div>
      <h1 className="mb-3.5 mt-0 font-serif text-[40px] font-bold leading-[1.05] tracking-[-1.2px] text-navy sm:text-[56px] sm:tracking-[-1.6px]">
        {title}
      </h1>
      <p className="mx-auto my-0 max-w-[560px] text-[17px] leading-[1.55] text-gray-500 [text-wrap:pretty]">{lead}</p>
      {children}
    </div>
  );
}
