// FAQ accordion built on <details>, so it works without JS and is keyboard accessible.
import { Plus } from "lucide-react";

export function Accordion({ items }: { items: [string, string][] }) {
  return (
    <div className="divide-y divide-line border-y border-line">
      {items.map(([q, a]) => (
        <details key={q} className="group">
          <summary className="flex cursor-pointer list-none items-center justify-between gap-6 py-6 text-[18px] font-medium tracking-[-0.02em] text-ink transition-colors hover:text-white [&::-webkit-details-marker]:hidden">
            {q}
            <Plus className="size-5 shrink-0 text-mute transition-transform duration-300 ease-out-expo group-open:rotate-45" aria-hidden />
          </summary>
          <p className="max-w-3xl pb-7 text-[16px] leading-[1.65] text-mute">{a}</p>
        </details>
      ))}
    </div>
  );
}
