import * as Sentry from "@sentry/nextjs";

export async function register() {
  // Runtime-specific configs are loaded for their respective environments.
  // The direct init below covers the browser bundle (NEXT_RUNTIME is undefined
  // client-side) and acts as a fallback with the task-specified sample rate.
  if (!process.env.NEXT_RUNTIME && process.env.NEXT_PUBLIC_SENTRY_DSN) {
    Sentry.init({
      dsn: process.env.NEXT_PUBLIC_SENTRY_DSN,
      tracesSampleRate: 0.2,
      environment: process.env.NEXT_PUBLIC_APP_ENV ?? "development",
    });
  }

  if (process.env.NEXT_RUNTIME === "nodejs") {
    await import("./sentry.server.config");
  }

  if (process.env.NEXT_RUNTIME === "edge") {
    await import("./sentry.edge.config");
  }
}
