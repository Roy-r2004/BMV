import { motion, type MotionProps, type Variants } from 'framer-motion';

const ease: [number, number, number, number] = [0.22, 1, 0.36, 1];

export const fadeUp = {
  hidden: { opacity: 0, y: 16 },
  show: {
    opacity: 1,
    y: 0,
    transition: {
      duration: 0.32,
      ease,
    },
  },
} satisfies Variants;

export const staggerChildren = {
  initial: 'hidden',
  animate: 'show',
  variants: {
    hidden: {},
    show: {},
  },
  transition: {
    staggerChildren: 0.08,
    delayChildren: 0.04,
  },
} satisfies MotionProps;

export const pageFade = {
  initial: { opacity: 0, y: 8 },
  animate: {
    opacity: 1,
    y: 0,
    transition: {
      duration: 0.36,
      ease,
    },
  },
  exit: {
    opacity: 0,
    y: -6,
    transition: {
      duration: 0.18,
      ease: 'easeOut',
    },
  },
} satisfies MotionProps;

export const MotionDiv = motion.div;
