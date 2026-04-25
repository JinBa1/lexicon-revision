import { Link } from "react-router-dom";

export function NotFoundRoute() {
  return (
    <main className="mx-auto max-w-2xl px-6 py-16 text-center font-body text-ink">
      <h1 className="font-display text-3xl font-semibold">Not found</h1>
      <Link to="/" className="mt-4 inline-block text-claret underline">
        Back to home
      </Link>
    </main>
  );
}
