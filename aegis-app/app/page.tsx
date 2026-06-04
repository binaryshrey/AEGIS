import HeroSection from "@/components/hero-section";
import LogoMarquee from "@/components/LogoMarquee";
import FeatureOne from "@/components/FeatureOne";
import FeatureTwo from "@/components/FeatureTwo";
import FeatureThree from "@/components/FeatureThree";
import FeatureFour from "@/components/FeatureFour";
import FeatureFive from "@/components/FeatureFive";
import Footer from "@/components/Footer";
import CTA from "@/components/CTA";

export default function Home() {
  return (
    <>
      <HeroSection />
      <LogoMarquee />
      <FeatureOne />
      <FeatureTwo />
      <FeatureThree />
      <FeatureFour />
      <FeatureFive />
      <CTA />
      <Footer />
    </>
  );
}
