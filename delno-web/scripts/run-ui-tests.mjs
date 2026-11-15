/**
 * Run the cabinet UI state tests with the TypeScript already installed
 * in delno-web. No extra test runner.
 */
import { spawnSync } from "node:child_process";
import { createRequire } from "node:module";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const require = createRequire(join(root, "package.json"));
const ts = require("typescript");

const sources = ["lib/sttErrors.ts", "lib/hermesUiStates.ts", "lib/hermesUiStates.test.ts"];
const outDir = join(root, ".ui-test-dist");
mkdirSync(outDir, { recursive: true });

for (const rel of sources) {
  const src = readFileSync(join(root, rel), "utf8");
  const js = ts.transpileModule(src, {
    compilerOptions: {
      module: ts.ModuleKind.ES2022,
      target: ts.ScriptTarget.ES2022,
      esModuleInterop: true,
    },
  }).outputText.replaceAll(/from\s+["'](\.\/[^"']+)["']/g, (_match, spec) => {
    const file = spec.endsWith(".js") ? spec : `${spec}.js`;
    return `from "${file}"`;
  });
  const outName = rel.replace(/^lib\//, "").replace(/\.ts$/, ".mjs");
  writeFileSync(join(outDir, outName), js.replaceAll(/from\s+"(\.\/[^"]+)\.js"/g, 'from "$1.mjs"'));
}

const result = spawnSync(process.execPath, ["--test", join(outDir, "hermesUiStates.test.mjs")], {
  stdio: "inherit",
});
process.exit(result.status ?? 1);
