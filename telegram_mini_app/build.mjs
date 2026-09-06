import { build } from 'esbuild';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const root = path.dirname(fileURLToPath(import.meta.url));
const outdir = path.resolve(process.argv[2] || path.join(root, 'dist'));
await mkdir(outdir, { recursive: true });
const result = await build({
  absWorkingDir: root,
  entryPoints: { app: 'app.js', styles: 'styles.css' },
  outdir, bundle: true, splitting: true, format: 'esm', minify: true,
  target: ['es2022'], charset: 'utf8', metafile: true,
  entryNames: 'assets/[name]-[hash]', chunkNames: 'assets/[name]-[hash]',
  assetNames: 'assets/[name]-[hash]', loader: { '.woff2': 'file' },
});
const entries = {};
for (const [file, meta] of Object.entries(result.metafile.outputs)) {
  if (meta.entryPoint === 'app.js' || meta.entryPoint === 'styles.css') {
    entries[meta.entryPoint] = path.relative(outdir, path.resolve(root, file)).replaceAll('\\', '/');
  }
}
if (!entries['app.js'] || !entries['styles.css']) throw new Error('Missing application bundle');
let html = await readFile(path.join(root, 'index.html'), 'utf8');
for (const [source, destination] of Object.entries(entries)) html = html.replace(`./${source}`, `./${destination}`);
await writeFile(path.join(outdir, 'index.html'), html);
await writeFile(path.join(outdir, 'bundle-meta.json'), JSON.stringify(result.metafile, null, 2));
await writeFile(path.join(outdir, 'asset-manifest.json'), JSON.stringify(entries, null, 2));
console.log(`Built Mini App: ${Object.keys(result.metafile.outputs).length} assets`);
