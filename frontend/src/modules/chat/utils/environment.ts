export function buildEnvironmentContext() {
  return {
    time: {
      now: new Date().toISOString(),
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    },
  };
}
