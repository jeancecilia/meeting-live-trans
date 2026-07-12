import Link from "next/link";

export default function Home() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center p-8">
      <h1 className="text-3xl font-bold mb-4 text-slate-100">Meeting Live Trans</h1>
      <p className="text-slate-400 text-lg mb-8">
        Private English ↔ Thai meeting platform
      </p>
      <Link
        href="/login"
        className="px-6 py-3 bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-lg transition-colors"
      >
        Sign In
      </Link>
    </main>
  );
}
