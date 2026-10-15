/** Placeholder blocks shown while a page's data loads. */
export function Bar({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse rounded-md bg-surface-2 ${className}`} />;
}

export function TilesSkeleton() {
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {[0, 1, 2, 3].map((i) => (
        <div key={i} className="card p-5">
          <Bar className="h-4 w-28" />
          <Bar className="mt-3 h-7 w-24" />
          <Bar className="mt-3 h-4 w-36" />
        </div>
      ))}
    </div>
  );
}

export function TableSkeleton({ rows = 8 }: { rows?: number }) {
  return (
    <div className="card p-4">
      {Array.from({ length: rows }, (_, i) => (
        <Bar key={i} className={`h-5 ${i ? "mt-4" : ""}`} />
      ))}
    </div>
  );
}
