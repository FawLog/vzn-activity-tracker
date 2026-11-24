export function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <a className={`brand${compact ? " brand--compact" : ""}`} href="/" data-nav>
      <svg className="brand__mark" viewBox="0 0 64 48" aria-hidden="true">
        <path d="M3 42 20 12l11 17 9-14 21 27H48l-8-11-9 14-11-17-8 14Z" fill="currentColor" />
      </svg>
      <span className="brand__copy">
        <strong>VZN //</strong>
        <span>Arctic Intelligence</span>
        {!compact && <small>Alliance Intelligence Platform</small>}
      </span>
    </a>
  );
}
