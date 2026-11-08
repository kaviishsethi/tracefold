import { ArrowRight } from "lucide-react";
import { EDGE } from "@/components/marketing";
import { Reveal, SiteFooter, SiteHeader } from "@/components/site";
import { LinkButton, cx } from "@/components/ui";

export const metadata = { title: "Manifesto · Tracefold" };

const CHAPTERS: [string, string[]][] = [
  [
    "Company text ends up public quietly.",
    [
      "A roadmap gets pasted into a forum post. A design doc is shared with a public link. A config file goes into a Gist to debug a deploy. None of it is unusual. It is what happens when teams move quickly.",
      "When someone does notice, the hard questions are which of your files it came from, and whether the copy is still up.",
    ],
  ],
  [
    "Checking shouldn't create a second copy.",
    [
      "The usual answer is to send your documents to a vendor so they can look for them. The most sensitive material you own now has a second home you don't control.",
      "We think the check should run where your files already live, and only the public side of the search should touch the network.",
    ],
  ],
  [
    "So Tracefold runs in your environment.",
    [
      "The scan engine and its local model run on your machine or in your trusted environment. A separate worker fetches the public pages you approve, and it never sees your files.",
      "Tracefold compares the text locally and shows the evidence: your file and lines, the public URL, the matching passage and when it was retrieved. Every outbound request goes into a ledger you can read.",
    ],
  ],
  [
    "It also looks at what hasn't leaked yet.",
    [
      "Even when nothing matches publicly, Tracefold reviews your files for secrets written into code, sensitive values sent to logs, confidential markers and personal data, and suggests a change for each one.",
      "After you edit the file, it checks again and tells you whether the issue is still detected.",
    ],
  ],
  [
    "And it says where its answers stop.",
    [
      "Tracefold reports matching content found publicly, or no match in the sources it checked. It only finds exact passages, and it can't prove a copy doesn't exist somewhere else.",
      "When it drafts a takedown request or an action to disable a leaked AWS key, nothing is sent or changed until a named person approves it. A submitted request isn't a removal: removal only shows once a fresh scan no longer finds the text.",
    ],
  ],
];

export default function Manifesto() {
  return (
    <div className="bg-bg">
      <SiteHeader />

      <section className={cx("pb-[clamp(64px,7vw,104px)] pt-[clamp(140px,16vw,200px)]", EDGE)}>
        <div className="mx-auto max-w-[1400px]">
          <h1 className="rise max-w-[18ch] text-[clamp(44px,6vw,88px)] font-semibold leading-[1] tracking-[-0.05em] text-white">
            Checking for leaks shouldn&apos;t need another copy of your files.
          </h1>
        </div>
      </section>

      <section className={cx("pb-[clamp(72px,8vw,120px)]", EDGE)}>
        <div className="mx-auto max-w-[1400px] divide-y divide-line border-y border-line">
          {CHAPTERS.map(([h, ps]) => (
            <Reveal key={h}>
              <div className="grid gap-6 py-[clamp(40px,5vw,64px)] lg:grid-cols-[1fr_1.5fr] lg:gap-16">
                <h2 className="text-[clamp(26px,2.6vw,38px)] font-medium leading-[1.12] tracking-[-0.035em] text-ink">{h}</h2>
                <div className="space-y-5">
                  {ps.map((p) => (
                    <p key={p.slice(0, 20)} className="text-[clamp(17px,1.35vw,19px)] leading-[1.65] text-ink-2">
                      {p}
                    </p>
                  ))}
                </div>
              </div>
            </Reveal>
          ))}
        </div>
      </section>

      <section className={cx("pb-[clamp(80px,9vw,128px)]", EDGE)}>
        <Reveal className="mx-auto max-w-[1400px]">
          <div className="flex flex-wrap items-center justify-between gap-6 rounded-[24px] border border-line bg-[#111216] px-[clamp(24px,4vw,56px)] py-10">
            <p className="text-[clamp(22px,2.2vw,30px)] font-medium tracking-[-0.03em] text-ink">Find the copy. See the evidence. Approve the next step.</p>
            <div className="flex flex-wrap gap-3">
              <LinkButton href="/security" variant="secondary">
                Read the security model
              </LinkButton>
              <LinkButton href="/scan">
                Get started <ArrowRight className="size-4" aria-hidden />
              </LinkButton>
            </div>
          </div>
        </Reveal>
      </section>

      <SiteFooter />
    </div>
  );
}
