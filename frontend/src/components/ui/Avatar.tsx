function initials(email: string): string {
  const name = email.split("@")[0];
  const parts = name.split(/[.\-_]/).filter(Boolean);
  const letters = parts.length >= 2 ? parts[0][0] + parts[1][0] : name.slice(0, 2);
  return letters.toUpperCase();
}

export function Avatar({ email, size = 32 }: { email: string; size?: number }) {
  return (
    <div
      title={email}
      className="grid place-items-center rounded-full gradient-helix text-[#0A0A12] font-semibold"
      style={{ width: size, height: size, fontSize: size * 0.4 }}
    >
      {initials(email)}
    </div>
  );
}
