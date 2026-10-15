import Search from "@/components/Search";

export default function NotFound() {
  return (
    <section className="mx-auto max-w-xl py-6 text-center">
      <div className="eyebrow">Not found</div>
      <h1 className="display mt-2 text-3xl font-semibold">We don&apos;t have that area</h1>
      <p className="mt-3 text-ink-2">The link may be out of date. Search for a ZIP, city or metro instead.</p>
      <div className="mt-6 flex justify-center"><Search /></div>
    </section>
  );
}
