import assert from 'node:assert/strict';
import test from 'node:test';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

import {
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
  Input,
  MotionDiv,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  Toaster,
  fadeUp,
  pageFade,
  staggerChildren,
  toast,
} from '../.tmp-ui-tests/ui/index.js';
import { UiIcon } from '../.tmp-ui-tests/components/UiIcons.js';

test('button, badge, card, and input render with expected primitives', () => {
  const markup = renderToStaticMarkup(
    React.createElement(
      Card,
      null,
      React.createElement(
        CardHeader,
        null,
        React.createElement(CardTitle, null, 'Preview 2026'),
        React.createElement(CardDescription, null, 'Shared primitives')
      ),
      React.createElement(
        CardContent,
        null,
        React.createElement(Badge, { children: 'Ready' }),
        React.createElement(Input, { value: 'hello', readOnly: true, 'aria-label': 'Greeting' }),
        React.createElement(Button, null, 'Save')
      )
    )
  );

  assert.match(markup, /Preview 2026/);
  assert.match(markup, /Shared primitives/);
  assert.match(markup, /Ready/);
  assert.match(markup, /aria-label="Greeting"/);
  assert.match(markup, /Save/);
});

test('button supports asChild links', () => {
  const markup = renderToStaticMarkup(
    React.createElement(
      Button,
      { asChild: true, variant: 'secondary' },
      React.createElement('a', { href: '/demo' }, 'Open')
    )
  );

  assert.match(markup, /^<a /);
  assert.match(markup, /href="\/demo"/);
  assert.match(markup, /Open/);
});

test('motion presets expose stable animation defaults', () => {
  assert.equal(typeof MotionDiv, 'object');
  assert.equal(fadeUp.hidden.opacity, 0);
  assert.equal(fadeUp.hidden.y, 16);
  assert.equal(fadeUp.show.opacity, 1);
  assert.equal(pageFade.initial.opacity, 0);
  assert.equal(pageFade.animate.opacity, 1);
  assert.equal(staggerChildren.transition.staggerChildren, 0.08);
});

test('toast helpers remain thin sonner re-exports', () => {
  assert.equal(typeof Toaster, 'function');
  assert.equal(typeof toast, 'function');
  assert.equal(typeof toast.success, 'function');
  assert.equal(typeof toast.error, 'function');
  assert.equal(typeof toast.message, 'function');
});

test('dialog and tabs wrappers are exported', () => {
  assert.ok(Dialog);
  assert.equal(typeof DialogContent, 'object');
  assert.equal(typeof DialogTitle, 'object');
  assert.equal(typeof DialogDescription, 'object');
  assert.ok(Tabs);
  assert.equal(typeof TabsList, 'object');
  assert.equal(typeof TabsTrigger, 'object');
  assert.equal(typeof TabsContent, 'object');
});

test('UiIcon keeps the string name API with a safe svg fallback', () => {
  const chart = renderToStaticMarkup(React.createElement(UiIcon, { name: 'chart', className: 'h-4 w-4' }));
  const fallback = renderToStaticMarkup(React.createElement(UiIcon, { name: 'unknown-name', className: 'h-4 w-4' }));

  assert.match(chart, /<svg/);
  assert.match(fallback, /<svg/);
  assert.doesNotMatch(fallback, /😀|✨|⭐|🔥/u);
});
