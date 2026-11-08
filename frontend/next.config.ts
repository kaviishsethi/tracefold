import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  devIndicators: false,
  output: "standalone", // self-contained server build for deployment
};

export default nextConfig;
