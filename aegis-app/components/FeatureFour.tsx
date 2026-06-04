"use client";

import Image from "next/image";
import Link from "next/link";

export interface FeatureFourProps {
  title?: string;
  description?: string;
  imageSrc?: string;
  linkText?: string;
  linkHref?: string;
}

export function FeatureFour({
  title = "Ask Questions, Get Strategy & Observability Insights",
  description = "Interrogate every aspect of your battle results in real time, from Thompson Sampling bandit selections to trust score breakdowns, all answered by one intelligent chatbot.",
  imageSrc = "/chat.webp",
  linkText = "Learn more",
  linkHref = "https://github.com/binaryshrey/",
}: FeatureFourProps) {
  return (
    <section className="overflow-hidden bg-black py-20">
      <div className="mx-auto max-w-8xl px-12 lg:px-20">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-12 lg:gap-0 items-center">
          {/* Left side - Image */}
          <div className="relative lg:pr-8">
            <Image
              src={imageSrc}
              alt={title}
              width={800}
              height={600}
              className="w-full h-auto rounded-xl"
            />
          </div>

          {/* Right side - Text content */}
          <div className="flex flex-col justify-center lg:pl-8">
            <h2 className="text-3xl lg:text-4xl font-bold text-white mb-6">
              {title}
            </h2>
            <p className="text-lg text-gray-300 mb-8 leading-relaxed">
              {description}
            </p>
            <div>
              <Link
                href={linkHref}
                className="inline-flex items-center text-white hover:text-blue-300 transition-colors text-lg font-medium"
              >
                {linkText}
                <svg
                  className="ml-2 w-5 h-5"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M9 5l7 7-7 7"
                  />
                </svg>
              </Link>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

export default FeatureFour;
