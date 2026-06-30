export function Logo({ size = 34 }: { size?: number }) {
  return (
    <svg viewBox="0 0 44 44" width={size} height={size} aria-hidden>
      <circle cx="22" cy="22" r="18" fill="none" stroke="var(--gilt)" strokeWidth="1.4" strokeDasharray="92 16" strokeLinecap="round" />
      <circle cx="22" cy="22" r="12.5" fill="none" stroke="var(--oxblood)" strokeWidth="1" opacity="0.7" />
      <circle cx="6.5" cy="22" r="2.1" fill="var(--gilt-2)" />
    </svg>
  );
}
