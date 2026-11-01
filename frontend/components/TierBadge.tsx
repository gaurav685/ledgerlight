export function TierBadge({ tier }: { tier: string | null }) {
  if (!tier) {
    return null;
  }
  const cls = tier.toUpperCase() === "VERIFIED" ? "verified" : "candidate";
  return <span className={`badge ${cls}`}>{tier.toUpperCase()}</span>;
}
