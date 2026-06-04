"use client";

import type React from "react";
import Image from "next/image";

export interface LogoMarqueeProps {
  title?: string;
  description?: string;
  logos?: Array<{
    name: string;
    src: string;
  }>;
  speed?: "slow" | "normal" | "fast";
  direction?: "left" | "right";
  pauseOnHover?: boolean;
}

const DEFAULT_LOGOS = [
  { name: "Next.js", src: "/nextJS.svg" },
  { name: "FastAPI", src: "/fastAPI.svg" },
  { name: "Redis", src: "/redis.svg" },
  { name: "Supabase", src: "/supabase.svg" },
  { name: "Vercel", src: "/vercel.svg" },
];

const SPEED_MAP = {
  slow: "60s",
  normal: "40s",
  fast: "20s",
};

export function LogoMarquee({
  title = "Built with forward-thinking teams",
  description = "Best-in-class AI and cloud infrastructure",
  logos = DEFAULT_LOGOS,
  speed = "normal",
  direction = "left",
  pauseOnHover = true,
}: LogoMarqueeProps) {
  const animationDuration = SPEED_MAP[speed];
  const animationDirection = direction === "right" ? "reverse" : "normal";

  return (
    <section className="overflow-hidden bg-black pt-4 pb-20 lg:pb-32">
      <style>
        {`
          @keyframes marquee-scroll {
            from {
              transform: translateX(0);
            }
            to {
              transform: translateX(-50%);
            }
          }
          .marquee-track {
            animation: marquee-scroll var(--marquee-duration, 40s) linear infinite;
            animation-direction: var(--marquee-direction, normal);
          }
          .marquee-container:hover .marquee-track {
            animation-play-state: var(--marquee-pause-on-hover, running);
          }
          @media (prefers-reduced-motion: reduce) {
            .marquee-track {
              animation: none;
            }
          }
        `}
      </style>
      <div className="mx-auto max-w-8xl px-12 lg:px-20">
        <div className="mb-12 text-center">
          <h2 className="mb-4 font-bold text-md text-white lg:text-3xl">
            {title}
          </h2>
          <p className="text-white/70 text-sm">{description}</p>
        </div>
        <div
          className="marquee-container relative overflow-hidden"
          style={{
            maskImage:
              "linear-gradient(to right, transparent, black 10%, black 90%, transparent)",
            WebkitMaskImage:
              "linear-gradient(to right, transparent, black 10%, black 90%, transparent)",
          }}
        >
          <div
            className="marquee-track flex w-max"
            style={
              {
                "--marquee-duration": animationDuration,
                "--marquee-direction": animationDirection,
                "--marquee-pause-on-hover": pauseOnHover ? "paused" : "running",
              } as React.CSSProperties
            }
          >
            {/* First set of logos */}
            {logos.map((logo, index) => (
              <div
                className="flex shrink-0 items-center justify-center px-8 py-4 opacity-70 transition-opacity duration-200 hover:opacity-100 cursor-pointer"
                key={`first-${logo.name}-${index}`}
              >
                <Image
                  src={logo.src}
                  alt={logo.name}
                  width={60}
                  height={20}
                  className="h-5 w-auto object-contain lg:h-6"
                />
              </div>
            ))}
            {/* Second set of logos for seamless loop */}
            {logos.map((logo, index) => (
              <div
                className="flex shrink-0 items-center justify-center px-8 py-4 opacity-70 transition-opacity duration-200 hover:opacity-100 cursor-pointer"
                key={`second-${logo.name}-${index}`}
              >
                <Image
                  src={logo.src}
                  alt={logo.name}
                  width={60}
                  height={20}
                  className="h-5 w-auto object-contain lg:h-6"
                />
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

export default LogoMarquee;
