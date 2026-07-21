// One motion voice for the whole app — the Framer-Motion counterpart of the
// CSS `--ease-quill` / `.folio` language. Import these instead of re-declaring
// easings and variants per component, so every surface settles the same way.
import type { Variants } from "framer-motion";

/** The quill lands, then settles. Matches --ease-quill in tokens.css. */
export const EASE = [0.22, 0.61, 0.21, 1] as const;

/** A list container that deals its children in one after another. */
export const stagger: Variants = {
  hidden: {},
  show: { transition: { staggerChildren: 0.045, delayChildren: 0.02 } },
};

/** A single item rising into place. Pairs with `stagger`. */
export const rise: Variants = {
  hidden: { opacity: 0, y: 8 },
  show: { opacity: 1, y: 0, transition: { duration: 0.34, ease: EASE } },
};
