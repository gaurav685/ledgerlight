"use client";

import { useEffect, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
import Link from "next/link";
import { RequireAuth } from "@/components/RequireAuth";
import { EventTierDisclaimer } from "@/components/Disclaimer";
import { TierBadge } from "@/components/TierBadge";
import { apiFetch, ApiError } from "@/lib/api";
import type { TimelineEntry } from "@/lib/types";

function Timeline() {
  const params = useParams<{ id: string }>();
  const searchParams = useSearchParams();
  const asOf = searchParams.get("as_of") ?? new Date().toISOString().slice(0, 10);

  const [entries, setEntries] = useState<TimelineEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiFetch<TimelineEntry[]>(`/companies/${params.id}/timeline?as_of=${asOf}`)
      .then(setEntries)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Failed to load timeline"));
  }, [params.id, asOf]);

  return (
    <div>
      <h1>Event timeline</h1>
      <p>
        As of <strong>{asOf}</strong>. <Link href={`/companies/${params.id}`}>Back to overview</Link>
      </p>
      <EventTierDisclaimer />
      {error && <div className="error-banner">{error}</div>}
      {entries && (
        <table>
          <thead>
            <tr>
              <th>Event time</th>
              <th>Known at</th>
              <th>Kind</th>
              <th>Label</th>
              <th>Tier</th>
              <th>Evidence</th>
            </tr>
          </thead>
          <tbody>
            {entries.length === 0 && (
              <tr>
                <td colSpan={6}>No real events or filings known as of this date.</td>
              </tr>
            )}
            {entries.map((entry, idx) => (
              <tr key={idx}>
                <td>{entry.event_time ?? "unknown"}</td>
                <td>{entry.known_at}</td>
                <td>{entry.kind}</td>
                <td>{entry.label}</td>
                <td>
                  <TierBadge tier={entry.tier} />
                </td>
                <td>
                  {entry.version_id ? (
                    <Link href={`/documents/${entry.version_id}?page=1`}>View document</Link>
                  ) : (
                    "--"
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

export default function TimelinePage() {
  return (
    <RequireAuth>
      <Timeline />
    </RequireAuth>
  );
}
