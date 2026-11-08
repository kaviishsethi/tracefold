import { Suspense } from "react";
import { ContactForm } from "@/components/contact-form";
import { EDGE } from "@/components/marketing";
import { SiteFooter, SiteHeader } from "@/components/site";
import { cx } from "@/components/ui";

export const metadata = { title: "Contact · Tracefold" };

export default function Contact() {
  return (
    <div className="bg-bg">
      <SiteHeader />
      <section className={cx("pb-[clamp(80px,9vw,128px)] pt-[clamp(140px,16vw,200px)]", EDGE)}>
        <div className="mx-auto grid max-w-[1400px] gap-12 lg:grid-cols-[0.8fr_1.2fr]">
          <div>
            <h1 className="rise text-[clamp(44px,6vw,88px)] font-semibold leading-[1] tracking-[-0.05em] text-white">Contact</h1>
            <p className="rise mt-6 max-w-md text-[clamp(17px,1.4vw,20px)] leading-[1.55] text-[#c2c3c7]" style={{ animationDelay: "100ms" }}>
              Talk to the team that builds Tracefold about deployments, pricing, support or security.
            </p>
            <p className="rise mt-8 max-w-md text-[15px] leading-[1.6] text-mute" style={{ animationDelay: "150ms" }}>
              We reply within one business day.
            </p>
          </div>
          <div className="rise" style={{ animationDelay: "200ms" }}>
            <Suspense>
              <ContactForm />
            </Suspense>
          </div>
        </div>
      </section>
      <SiteFooter />
    </div>
  );
}
