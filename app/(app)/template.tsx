"use client";

import { motion, useReducedMotion } from "motion/react";
import type { ReactNode } from "react";

/** A short fade-and-rise between pages so the change of screen is noticed, not dramatic. */
export default function AppTemplate({ children }: { children: ReactNode }) {
  const reduce = useReducedMotion();
  if (reduce) return <>{children}</>;
  return (
    <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}>
      {children}
    </motion.div>
  );
}
