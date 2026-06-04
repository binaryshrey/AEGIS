"use client";

import Image from "next/image";

export interface FeatureOneProps {
  title?: string;
  description?: string;
  imageSrc?: string;
}

export function FeatureOne({
  title = "Dissect Battles and Expose Opponent Weaknesses at Depth",
  description = "View per-opponent win rates, strategy breakdowns and move efficiency charts, powered by AEGIS AI and comprehensive JSONL event analytics.",
  imageSrc = "/analytics.webp",
}: FeatureOneProps) {
  return (
    <section className="overflow-hidden bg-black pb-20">
      <div className="mx-auto max-w-8xl px-12 lg:px-20">
        <div className="mb-12 text-center">
          <h2 className="mb-4 font-bold text-md text-white lg:text-3xl">
            {title}
          </h2>
          <p className="text-white/70 text-sm">{description}</p>
        </div>
        <div className="flex justify-center">
          <Image
            src={imageSrc}
            alt="Feature"
            width={1200}
            height={600}
            className="w-full max-w-8xl rounded-xl"
          />
        </div>
      </div>
    </section>
  );
}

export default FeatureOne;
