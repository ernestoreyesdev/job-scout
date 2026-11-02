import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Extra hostnames the dev server accepts (comma separated), e.g. a Tailscale name for testing on a phone.
  allowedDevOrigins: (process.env.DEV_ORIGINS ?? "")
    .split(",")
    .map((origin) => origin.trim())
    .filter(Boolean),
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  async redirects() {
    return [{ source: "/", destination: "/tracker", permanent: false }];
  },
};

export default nextConfig;
