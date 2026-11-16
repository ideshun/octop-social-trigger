import { createRequire } from "node:module";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const root = dirname(fileURLToPath(import.meta.url));
const deps = process.argv[2] ? resolve(process.argv[2], "package.json") : import.meta.url;
const { build } = createRequire(deps)("esbuild");
await build({
  entryPoints: [resolve(root, "src/settings.tsx")],
  outfile: resolve(root, "dist/settings.js"),
  bundle: true, format: "esm", platform: "browser", target: "es2022",
  jsx: "transform", jsxFactory: "React.createElement", jsxFragment: "React.Fragment",
  loader: { ".css": "text" }, minify: true,
});
