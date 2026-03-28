import type { NextConfig } from "next";
import { withSentryConfig } from "@sentry/nextjs";

const nextConfig: NextConfig = {
  reactStrictMode: true,
};

export default withSentryConfig(nextConfig, {
  // Sentry webpack plugin options
  org: process.env.SENTRY_ORG,
  project: process.env.SENTRY_PROJECT,

  // Suppress Sentry CLI output during builds
  silent: !process.env.CI,

  // Upload source maps in CI only
  widenClientFileUpload: true,
  hideSourceMaps: true,
  disableLogger: true,

  // Automatically instrument Next.js App Router
  autoInstrumentServerFunctions: true,
});
