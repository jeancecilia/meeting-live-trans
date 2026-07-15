import Link from "next/link";

export function LawMark({ className = "h-10 w-10" }: { className?: string }) {
  return (
    <span className={`law-mark grid shrink-0 place-items-center ${className}`} aria-hidden>
      <svg viewBox="0 0 48 48" className="h-[72%] w-[72%]" fill="none">
        <path d="M7 18 24 7l17 11H7Z" fill="currentColor" />
        <path d="M10 21h28M12 36h24M8 41h32" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
        <path d="M14 22v13M21 22v13M27 22v13M34 22v13" stroke="currentColor" strokeWidth="3" />
      </svg>
    </span>
  );
}

export function Brand({ href = "/" }: { href?: string }) {
  return (
    <Link href={href} className="group inline-flex items-center gap-3" aria-label="UdonLaw home / หน้าหลักอุดรลอว์">
      <LawMark />
      <span>
        <span className="law-brand-name block text-[17px] font-semibold tracking-[-0.02em]">UdonLaw</span>
        <span className="law-brand-subtitle block text-[9px] font-semibold uppercase tracking-[0.16em]">สำนักงานกฎหมาย · Law Office</span>
      </span>
    </Link>
  );
}
