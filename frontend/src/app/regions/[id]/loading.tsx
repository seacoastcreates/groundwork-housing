import { Bar, TableSkeleton, TilesSkeleton } from "@/components/Skeleton";

export default function Loading() {
  return (
    <div role="status" aria-label="Loading">
      <Bar className="h-4 w-40" />
      <Bar className="mt-5 h-4 w-28" />
      <Bar className="mt-2 h-10 w-80" />
      <div className="mt-6"><TilesSkeleton /></div>
      <div className="card mt-6 p-5">
        <Bar className="h-5 w-72" />
        <Bar className="mt-4 h-72" />
      </div>
      <div className="mt-10"><TableSkeleton rows={6} /></div>
    </div>
  );
}
