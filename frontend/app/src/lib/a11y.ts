// Making a div behave like the button it already looks like.
//
// The app's two most-used lists — conversations and branches — were clickable
// `div`s with no role, no tab stop and no key handler, which meant the primary
// navigation of the product could not be reached without a mouse at all. Not a
// rough edge: a keyboard-only user could not switch threads.
//
// The honest fix is usually a real `<button>`, and where that is possible it is
// better than this. These rows are flex layouts carrying their own controls,
// and a button inside a button is invalid HTML that browsers restructure.
//
// **Where to put it matters more than that it is there.** `role="button"` is
// children-presentational in ARIA: assistive tech may prune everything inside
// it. So put it on the whole row only when the row is *just* content — the
// conversation list — and on the row's label when the row also holds real
// controls — the branch tree, whose rows carry resolve/rename/delete buttons
// and a verdict mark with its own `aria-label`. Taking the row wholesale there
// would hide four things to fix one.
import type { KeyboardEvent, MouseEvent } from "react";

/**
 * Props that make a non-button element operable by keyboard.
 *
 * Enter and Space both activate, matching a real button — Space is the one
 * people forget, and its default (scrolling the page) has to be prevented or
 * the list jumps as it activates.
 *
 * The click is taken from here rather than declared alongside, so the pointer
 * and keyboard paths cannot drift apart. It stops propagating because the
 * label-inside-a-clickable-row case would otherwise select twice — once from
 * the label, once from the row it bubbled into.
 */
export function activatable(onActivate: () => void) {
  return {
    role: "button",
    tabIndex: 0,
    onClick: (e: MouseEvent) => {
      e.stopPropagation();
      onActivate();
    },
    onKeyDown: (e: KeyboardEvent) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        e.stopPropagation();
        onActivate();
      }
    },
  } as const;
}
