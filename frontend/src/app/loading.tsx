import { Bar, TableSkeleton, TilesSkeleton } from "@/components/Skeleton";

export default function Loading() {
  return (
    <div role="status" aria-label="Loading">
      <Bar className="h-4 w-56" />
      <Bar className="mt-4 h-12 w-full max-w-2xl" />
      <Bar className="mt-4 h-5 w-full max-w-xl" />
      <div className="mt-10"><TilesSkeleton /></div>
      <div className="mt-10"><TableSkeleton /></div>
    </div>
  );
}
