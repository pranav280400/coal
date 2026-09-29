import type { Metadata } from "next";
import { Landing } from "./landing";

export const metadata: Metadata = {
  title: "Smarter Monitoring for Safer Mines",
  description:
    "Lumen is an AI-driven governance and compliance platform for Indian coal mines — statutory tracking, geo-tagged inspections, automated escalation and a tamper-evident audit trail.",
};

export default function LandingPage() {
  return <Landing />;
}
