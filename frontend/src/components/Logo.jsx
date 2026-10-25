// The RentSafe MY mark + wordmark. `dark` is the Guide page's variant.
export default function Logo({ dark = false }) {
  return (
    <span className="flex flex-none items-center gap-2.5 whitespace-nowrap">
      <span
        className={`flex h-[30px] w-[30px] flex-none items-center justify-center rounded-lg ${
          dark ? "border border-teal/40 bg-teal/[.16]" : "bg-navy"
        }`}
      >
        <span className="h-[13px] w-[13px] rotate-45 rounded-full border-[2.5px] border-teal border-t-transparent" />
      </span>
      <span className={`font-serif text-lg font-bold tracking-[-.2px] ${dark ? "text-white" : "text-navy"}`}>
        RentSafe <span className="text-teal">MY</span>
      </span>
    </span>
  );
}
