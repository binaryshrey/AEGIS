"use client";

import Link from "next/link";

const GITHUB_URI = "https://github.com/binaryshrey/AEGIS";
const LINKEDIN_URI = "https://in.linkedin.com/in/shreyanshsaurabh";
const BETTERSTACK_URI = "";

const Footer = () => {
  return (
    <footer className="bg-[#c69205] py-20 border-t border-white/10">
      <div className="mx-auto max-w-7xl px-6 lg:px-8">
        {/* Navigation Links */}
        <nav className="flex justify-center gap-8 mb-8">
          <Link
            href={GITHUB_URI}
            target="_blank"
            className="text-white hover:text-white/70 text-sm font-medium transition-colors"
          >
            Github
          </Link>
          <Link
            href={BETTERSTACK_URI}
            target="_blank"
            className="text-white hover:text-white/70 text-sm font-medium transition-colors"
          >
            Status
          </Link>

          <Link
            href={LINKEDIN_URI}
            target="_blank"
            className="text-white hover:text-white/70 text-sm font-medium transition-colors"
          >
            Contact
          </Link>
        </nav>

        {/* Copyright */}
        <div className="text-center">
          <p className="text-white text-sm">© 2026 AEGIS</p>
        </div>
      </div>
    </footer>
  );
};

export default Footer;
