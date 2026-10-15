"use client"; // Error boundaries must be Client Components

import Link from "next/link";
import { useEffect } from "react";

export default function Error({ error, retry }: { error: Error & { digest?: string }; retry: () => void }) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <section className="card mx-auto max-w-xl p-8 text-center">
      <div className="eyebrow">Something went wrong</div>
      <h1 className="display mt-2 text-3xl font-semibold">The data is temporarily unavailable</h1>
      <p className="mt-3 text-ink-2">
        We couldn&apos;t load home values just now. This is usually brief, so try again in a moment.
      </p>
      <div className="mt-6 flex justify-center gap-3">
        <button onClick={() => retry()} className="segment segment-active">Try again</button>
        <Link href="/" className="segment">Back to markets</Link>
      </div>
    </section>
  );
}
