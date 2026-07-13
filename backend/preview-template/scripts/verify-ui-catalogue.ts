import { existsSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { CATALOGUE_COMPONENTS, SKELETONS, getCatalogueComponentNames } from '../src/ui/registry.ts';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const uiRoot = join(root, 'src', 'ui');
const errors: string[] = [];
const opsShellSource = readFileSync(join(uiRoot, 'ops', 'OpsShell.tsx'), 'utf8');
if (
  !/return\s*\(\)\s*=>\s*\{[\s\S]*dragging\.current = false;[\s\S]*document\.body\.style\.cursor = '';[\s\S]*document\.body\.style\.userSelect = '';/.test(
    opsShellSource
  )
) {
  errors.push('OpsShell must restore body drag styles during effect cleanup');
}

const cataloguePath = join(uiRoot, 'catalogue.json');
if (!existsSync(cataloguePath)) {
  errors.push('catalogue.json missing — run npm run sync:ui');
} else {
  const catalogue = JSON.parse(readFileSync(cataloguePath, 'utf8')) as {
    components: Array<{ name: string }>;
    skeletons: Array<{ id: string; allowedComponents: string[] }>;
  };
  const jsonNames = catalogue.components.map((c) => c.name).sort().join(',');
  const regNames = CATALOGUE_COMPONENTS.map((c) => c.name).sort().join(',');
  if (jsonNames !== regNames) {
    errors.push('catalogue.json components drifted from registry.ts — run npm run sync:ui');
  }
  if (catalogue.skeletons.length !== SKELETONS.length) {
    errors.push('catalogue.json skeletons drifted from registry.ts');
  }
}

const barrel = readFileSync(join(uiRoot, 'index.ts'), 'utf8');
for (const component of CATALOGUE_COMPONENTS) {
  const filePath = join(uiRoot, component.path);
  if (!existsSync(filePath)) {
    errors.push(`Missing component file: ${component.path}`);
  }
  if (!new RegExp(`\\b${component.name}\\b`).test(barrel)) {
    errors.push(`Barrel index.ts missing export for ${component.name}`);
  }
}

const names = new Set(getCatalogueComponentNames());
for (const skeleton of SKELETONS) {
  for (const allowed of skeleton.allowedComponents) {
    if (!names.has(allowed)) {
      errors.push(`Skeleton ${skeleton.id} references unknown component ${allowed}`);
    }
  }
}

const pageFiles = [
  join(uiRoot, 'examples', 'PublicReferencePage.tsx'),
  join(uiRoot, 'examples', 'OpsReferencePage.tsx'),
];

const forbidden = [
  '@radix-ui/',
  'recharts',
  '@tanstack/react-table',
  'magicui',
  '@tremor',
  'framer-motion',
  'motion/react',
  'lucide-react',
  'sonner',
  'date-fns',
];

for (const page of pageFiles) {
  if (!existsSync(page)) {
    errors.push(`Missing reference page: ${page}`);
    continue;
  }
  const source = readFileSync(page, 'utf8');
  if (!source.includes("from '@/ui'") && !source.includes('from "@/ui"')) {
    errors.push(`${page} must import from @/ui`);
  }
  if (!source.includes('getSkeleton') && !source.includes('SkeletonComposer')) {
    errors.push(`${page} must consume skeleton registry (getSkeleton / SkeletonComposer)`);
  }
  for (const needle of forbidden) {
    if (source.includes(`from '${needle}`) || source.includes(`from "${needle}`)) {
      errors.push(`${page} must not import ${needle}`);
    }
  }
}

const pkg = JSON.parse(readFileSync(join(root, 'package.json'), 'utf8')) as {
  dependencies: Record<string, string>;
};
const allowedDeps = new Set([
  'react',
  'react-dom',
  'react-router-dom',
  'clsx',
  'tailwind-merge',
  'class-variance-authority',
  'recharts',
  '@tanstack/react-table',
  '@radix-ui/react-dialog',
  '@radix-ui/react-select',
  '@radix-ui/react-tabs',
  '@radix-ui/react-tooltip',
  'motion',
  'lucide-react',
  'sonner',
  'date-fns',
]);
for (const dep of Object.keys(pkg.dependencies)) {
  if (!allowedDeps.has(dep)) {
    errors.push(`Unapproved dependency: ${dep}`);
  }
}

if (errors.length) {
  console.error('UI catalogue verification failed:');
  for (const error of errors) console.error(` - ${error}`);
  process.exit(1);
}

console.log(
  `UI catalogue OK: ${CATALOGUE_COMPONENTS.length} components, ${SKELETONS.length} skeletons, barrel + skeleton-driven references.`
);
