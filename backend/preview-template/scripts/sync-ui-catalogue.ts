import { writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { CATALOGUE_COMPONENTS, SKELETONS } from '../src/ui/registry.ts';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const outPath = join(root, 'src', 'ui', 'catalogue.json');

const catalogue = {
  version: 1,
  import: '@/ui',
  generatedFrom: 'src/ui/registry.ts',
  rule: 'Generated pages must import UI only from @/ui. Do not invent props or import Radix/Recharts/TanStack directly.',
  components: CATALOGUE_COMPONENTS,
  skeletons: SKELETONS,
};

writeFileSync(outPath, `${JSON.stringify(catalogue, null, 2)}\n`, 'utf8');
console.log(`Wrote ${outPath} (${CATALOGUE_COMPONENTS.length} components, ${SKELETONS.length} skeletons)`);
