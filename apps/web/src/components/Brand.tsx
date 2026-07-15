import Link from "next/link";

export function Brand({ href = "/" }: { href?: string }) {
  return (
    <Link href={href} className="group inline-flex items-center gap-3" aria-label="LumaMeet home / หน้าหลัก LumaMeet">
      <span className="relative grid h-10 w-10 place-items-center overflow-hidden rounded-2xl bg-gradient-to-br from-cyan-300 via-sky-400 to-violet-500 shadow-[0_12px_32px_rgba(56,189,248,0.24)] transition-transform group-hover:scale-[1.03]">
        <span className="absolute inset-[1px] rounded-[15px] bg-slate-950/30" />
        <span className="relative text-[11px] font-black tracking-[-0.08em] text-white">A/ก</span>
      </span>
      <span>
        <span className="block text-[15px] font-semibold tracking-[-0.02em] text-white">LumaMeet</span>
        <span className="block text-[10px] font-medium uppercase tracking-[0.2em] text-slate-500">English · ไทย</span>
      </span>
    </Link>
  );
}
