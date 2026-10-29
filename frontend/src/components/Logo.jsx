// The RentSafe MY mark + wordmark.
export default function Logo() {
  return (
    <span className="flex flex-none items-center gap-2.5 whitespace-nowrap">
      <span className="flex h-[30px] w-[30px] flex-none items-center justify-center rounded-lg bg-navy">
        <span className="h-[13px] w-[13px] rotate-45 rounded-full border-[2.5px] border-teal border-t-transparent" />
      </span>
      <span className="font-serif text-lg font-bold tracking-[-.2px] text-navy">
        RentSafe <span className="text-teal">MY</span>
      </span>
    </span>
  );
}
