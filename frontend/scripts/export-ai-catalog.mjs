import { writeFileSync } from 'fs';
import { fileURLToPath, pathToFileURL } from 'url';
import { dirname, join } from 'path';

const root = dirname(fileURLToPath(import.meta.url));
const catalogUrl = pathToFileURL(join(root, '../src/data/aiFeatureCatalog.ts')).href;
const { AI_FEATURE_CATALOG } = await import(catalogUrl);

const out = join(root, '../src/data/aiFeatureCatalog.json');
writeFileSync(out, JSON.stringify(AI_FEATURE_CATALOG, null, 2), 'utf8');
console.log('Wrote', out);
