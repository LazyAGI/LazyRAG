import fs from "fs";
import {
  getOpenApiApis,
  getOpenApiCacheFilePath,
  hashFile,
} from "./openapi-manifest.mjs";

const cwdPath = process.cwd();
const apis = getOpenApiApis(cwdPath);
const cacheFilePath = getOpenApiCacheFilePath(cwdPath);
const args = new Set(process.argv.slice(2));
const jsonOutput = args.has("--json");
const quiet = args.has("--quiet");

let cache = {};
if (fs.existsSync(cacheFilePath)) {
  try {
    const raw = fs.readFileSync(cacheFilePath, "utf-8").trim();
    cache = raw ? JSON.parse(raw) : {};
  } catch {
    cache = {};
  }
}

const statuses = apis.map((api) => {
  const exists = fs.existsSync(api.input);
  const currentHash = exists ? hashFile(api.input) : "";
  const cachedHash = cache[api.name] || "";

  return {
    name: api.name,
    input: api.input,
    exists,
    currentHash,
    cachedHash,
    stale: exists && currentHash !== cachedHash,
  };
});

if (jsonOutput) {
  process.stdout.write(`${JSON.stringify(statuses, null, 2)}\n`);
} else if (!quiet) {
  statuses.forEach((status) => {
    const state = !status.exists
      ? "missing"
      : status.stale
        ? "stale"
        : "fresh";
    process.stdout.write(`${status.name}: ${state}\n`);
  });
}

if (statuses.some((status) => status.stale || !status.exists)) {
  process.exit(1);
}
