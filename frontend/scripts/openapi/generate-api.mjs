/**
 * Generate API clients from OpenAPI specs.
 * Local specs live in scripts/openapi/specs, external specs come from tieyiyuan.
 * Output: src/api/generated/<name>-client
 */
import { execSync } from "child_process";
import path from "path";
import fs from "fs";
import { createHash } from "crypto";
import { fileURLToPath } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const cwdPath = process.cwd();
// From lazyRag/LazyRAG/frontend go up to workspace root then into tieyiyuan api
const inputDirname = path.resolve(
  cwdPath,
  "../../../tieyiyuan/neutrino/api/public/appplatform/api",
);
const outputDirname = path.resolve(cwdPath, "src/api/generated");
const localSpecsDir = path.resolve(cwdPath, "scripts/openapi/specs");

const apis = [
  {
    name: "auth",
    input: path.resolve(localSpecsDir, "auth-openapi.yaml"),
    output: path.resolve(outputDirname, "auth-client"),
  },
  {
    name: "core",
    input: path.resolve(localSpecsDir, "core.yaml"),
    output: path.resolve(outputDirname, "core-client"),
  },
  {
    name: "authservice",
    input: path.resolve(inputDirname, "authservice/v1/openapi.yaml"),
    output: path.resolve(outputDirname, "authservice-client"),
  },
  {
    name: "chatbot",
    input: path.resolve(inputDirname, "chatbot/openapi.yaml"),
    output: path.resolve(outputDirname, "chatbot-client"),
  },
  {
    name: "knowledge",
    input: path.resolve(inputDirname, "rag/openapi.yaml"),
    output: path.resolve(outputDirname, "knowledge-client"),
  },
  {
    name: "file",
    input: path.resolve(inputDirname, "fileservice/openapi.yaml"),
    output: path.resolve(outputDirname, "file-client"),
  },
];

const args = process.argv.slice(2);
const flags = new Set(args.filter((arg) => arg.startsWith("--")));
const positional = args.filter((arg) => !arg.startsWith("--"));
const skipCache = flags.has("--skip-cache");
const target = positional[0];

const selectedApis = target ? apis.filter((api) => api.name === target) : apis;

if (target && selectedApis.length === 0) {
  console.error(
    `❌ API "${target}" not found. Available: ${apis.map((a) => a.name).join(", ")}`,
  );
  process.exit(1);
}

const cacheFilePath = path.resolve(
  cwdPath,
  "scripts/openapi/.openapi-cache.json",
);
let cache = {};
if (!skipCache && fs.existsSync(cacheFilePath)) {
  cache = JSON.parse(fs.readFileSync(cacheFilePath, "utf-8"));
}

function hashFile(filePath) {
  if (!fs.existsSync(filePath)) return "";
  const content = fs.readFileSync(filePath);
  return createHash("sha256").update(content).digest("hex");
}

let updated = false;
for (const api of selectedApis) {
  if (!fs.existsSync(api.input)) {
    console.warn(
      `⚠️ ${api.name}: Input not found at ${api.input}, skipping. Run from workspace or copy specs to api/specs/`,
    );
    continue;
  }
  const currentHash = hashFile(api.input);
  const prevHash = cache[api.name];

  if (!skipCache && currentHash === prevHash) {
    console.log(`✅ ${api.name}: No changes detected.`);
    continue;
  }

  console.log(`🔁 ${api.name}: Regenerating...`);
  fs.mkdirSync(api.output, { recursive: true });

  try {
    execSync(
      `pnpm exec openapi-generator-cli generate --skip-validate-spec -c scripts/openapi/openapi-generator-config.json -i "${api.input}" -o "${api.output}"`,
      { stdio: "inherit", cwd: cwdPath },
    );
    cache[api.name] = currentHash;
    updated = true;
  } catch (error) {
    console.error(`❌ Failed to generate API "${api.name}":`, error);
    process.exit(1);
  }
}

if (!skipCache && updated) {
  fs.writeFileSync(cacheFilePath, JSON.stringify(cache, null, 2));
  console.log("💾 Cache updated");
}
