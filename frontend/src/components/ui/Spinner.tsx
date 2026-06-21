export function Spinner({ size = 20 }: { size?: number }) {
  return (
    <span
      className="inline-block animate-spin rounded-full border-2 border-line border-t-violet"
      style={{ width: size, height: size }}
    />
  );
}

export function FullPageSpinner() {
  return (
    <div className="grid h-full place-items-center app-glow">
      <Spinner size={28} />
    </div>
  );
}
