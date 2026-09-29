"use client";

import dynamic from "next/dynamic";
import { Spinner } from "@/components/ui";

// Leaflet touches `window` at import time, so the map is rendered on the client only.
export const MineMap = dynamic(() => import("./mine-map"), {
  ssr: false,
  loading: () => (
    <div className="grid h-full w-full place-items-center bg-copper-50">
      <Spinner />
    </div>
  ),
});
