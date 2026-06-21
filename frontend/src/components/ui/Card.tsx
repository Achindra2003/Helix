interface Props {
  className?: string;
  children: React.ReactNode;
}

export function Card({ className = "", children }: Props) {
  return (
    <div
      className={
        "rounded-xl border border-line bg-surface p-5 " + className
      }
    >
      {children}
    </div>
  );
}
