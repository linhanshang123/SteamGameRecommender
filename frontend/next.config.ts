import path from "node:path";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  outputFileTracingRoot: path.join(process.cwd(), ".."),
  outputFileTracingExcludes: {
    "/*": ["../backend/.cache/**/*"],
  },
};

export default nextConfig;
