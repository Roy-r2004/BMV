/**
 * Lightweight stand-ins for @headlessui/react + framer-motion.
 * Preview apps only allow react / react-dom / react-router-dom — models still
 * emit Headless UI / Framer APIs. Guards rewrite those imports here so the
 * demo renders instead of crashing with "Transition is not defined".
 */
import {
  createElement,
  Fragment as ReactFragment,
  type CSSProperties,
  type ElementType,
  type ReactNode,
} from 'react';

type AnyProps = Record<string, unknown> & {
  children?: ReactNode;
  as?: ElementType;
  className?: string;
  style?: CSSProperties;
  show?: boolean;
  open?: boolean;
  appear?: boolean;
  static?: boolean;
  unmount?: boolean;
  onClose?: (...args: unknown[]) => void;
};

function resolveTag(as: ElementType | undefined, fallback: ElementType = 'div'): ElementType {
  return as || fallback;
}

function visible(props: AnyProps): boolean {
  if (props.show === false || props.open === false) return false;
  return true;
}

function Pass({ as, children, show, open, appear, static: _s, unmount, onClose, enter, enterFrom, enterTo, leave, leaveFrom, leaveTo, ...rest }: AnyProps) {
  if (!visible({ show, open })) return null;
  return createElement(resolveTag(as), rest, children);
}

function TransitionRoot(props: AnyProps) {
  return Pass(props);
}
function TransitionChild(props: AnyProps) {
  return Pass({ ...props, show: props.show !== false });
}
export const Transition = Object.assign(TransitionRoot, { Child: TransitionChild });

function DialogRoot({ children, onClose, open, show, as, ...rest }: AnyProps) {
  if (open === false || show === false) return null;
  return createElement(resolveTag(as), { role: 'dialog', ...rest }, children);
}
function DialogPanel(props: AnyProps) {
  return Pass(props);
}
function DialogTitle(props: AnyProps) {
  return Pass({ ...props, as: props.as || 'h3' });
}
function DialogDescription(props: AnyProps) {
  return Pass({ ...props, as: props.as || 'p' });
}
export const Dialog = Object.assign(DialogRoot, {
  Panel: DialogPanel,
  Title: DialogTitle,
  Description: DialogDescription,
});

function MenuRoot(props: AnyProps) {
  return Pass({ ...props, as: props.as || 'div' });
}
function MenuButton(props: AnyProps) {
  return Pass({ ...props, as: props.as || 'button' });
}
function MenuItems(props: AnyProps) {
  return Pass(props);
}
function MenuItem({ children, ...rest }: AnyProps & { children?: ReactNode | ((args: { active: boolean; close: () => void }) => ReactNode) }) {
  const close = () => undefined;
  const body = typeof children === 'function' ? children({ active: false, close }) : children;
  return Pass({ ...rest, children: body });
}
export const Menu = Object.assign(MenuRoot, {
  Button: MenuButton,
  Items: MenuItems,
  Item: MenuItem,
});

function DisclosureRoot({ children, ...rest }: AnyProps & { children?: ReactNode | ((args: { open: boolean }) => ReactNode) }) {
  const body = typeof children === 'function' ? children({ open: true }) : children;
  return Pass({ ...rest, children: body });
}
function DisclosureButton(props: AnyProps) {
  return Pass({ ...props, as: props.as || 'button' });
}
function DisclosurePanel(props: AnyProps) {
  return Pass(props);
}
export const Disclosure = Object.assign(DisclosureRoot, {
  Button: DisclosureButton,
  Panel: DisclosurePanel,
});

function ListboxRoot({ children, ...rest }: AnyProps & { children?: ReactNode | ((args: { open: boolean; value: unknown }) => ReactNode) }) {
  const value = rest.value;
  const body = typeof children === 'function' ? children({ open: true, value }) : children;
  return Pass({ ...rest, children: body });
}
function ListboxButton(props: AnyProps) {
  return Pass({ ...props, as: props.as || 'button' });
}
function ListboxOptions(props: AnyProps) {
  return Pass(props);
}
function ListboxOption({ children, ...rest }: AnyProps & { children?: ReactNode | ((args: { active: boolean; selected: boolean }) => ReactNode) }) {
  const body = typeof children === 'function' ? children({ active: false, selected: Boolean(rest.selected) }) : children;
  return Pass({ ...rest, children: body });
}
export const Listbox = Object.assign(ListboxRoot, {
  Button: ListboxButton,
  Options: ListboxOptions,
  Option: ListboxOption,
});

export const Combobox = Listbox;
export const Popover = Disclosure;
export const Tab = Object.assign(Pass, {
  Group: Pass,
  List: Pass,
  Panels: Pass,
  Panel: Pass,
});
export const Switch = (props: AnyProps) => Pass({ ...props, as: props.as || 'button', role: 'switch' });
export const RadioGroup = Object.assign(Pass, { Label: Pass, Option: Pass, Description: Pass });
export const Portal = ({ children }: { children?: ReactNode }) => createElement(ReactFragment, null, children);

/** Framer-motion-compatible motion.* tags — no animation, just DOM. */
function motionTag(tag: string) {
  return function MotionEl(props: AnyProps) {
    const {
      initial: _i,
      animate: _a,
      exit: _e,
      transition: _t,
      variants: _v,
      whileHover: _wh,
      whileTap: _wt,
      whileInView: _wiv,
      layout: _l,
      layoutId: _lid,
      drag: _d,
      ...rest
    } = props;
    return Pass({ ...rest, as: tag as ElementType });
  };
}

export const motion = new Proxy(
  {} as Record<string, ReturnType<typeof motionTag>>,
  {
    get: (_t, prop: string) => motionTag(prop),
  },
);

export function AnimatePresence({ children }: { children?: ReactNode; mode?: string; initial?: boolean }) {
  return createElement(ReactFragment, null, children);
}

export function useAnimation() {
  return { start: async () => undefined, stop: () => undefined, set: () => undefined };
}

export default {
  Transition,
  Dialog,
  Menu,
  Disclosure,
  Listbox,
  Combobox,
  Popover,
  Tab,
  Switch,
  RadioGroup,
  Portal,
  motion,
  AnimatePresence,
  useAnimation,
};
