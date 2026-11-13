"use client";

import { useEffect, useState } from "react";
import { RequireAuth } from "@/components/RequireAuth";
import { EventStudyDisclaimer } from "@/components/Disclaimer";
import { apiFetch, ApiError } from "@/lib/api";
import type { EventStudyRunSummaryOut } from "@/lib/types";

interface WindowMetric {
  n: number;
  mean_car: number | null;
  median_car: number | null;
  t_stat: number;
  t_p: number;
  t_p_holm: number;
  bmp_stat: number;
  bmp_p: number;
  bmp_p_holm: number;
  rank_stat: number;
  rank_p: number;
  rank_p_holm: number;
}

function fmt(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "n/a";
  return v.toFixed(4);
}

function EventTypeTable({
  eventType,
  windows,
}: {
  eventType: string;
  windows: Record<string, WindowMetric>;
}) {
  return (
    <div>
      <h3>{eventType}</h3>
      <table>
        <thead>
          <tr>
            <th>Window</th>
            <th>N</th>
            <th>Mean CAR</th>
            <th>Median CAR</th>
            <th>t</th>
            <th>BMP</th>
            <th>Rank p</th>
            <th>Holm p (rank)</th>
          </tr>
        </thead>
        <tbody>
          {Object.entries(windows).map(([windowName, m]) => (
            <tr key={windowName}>
              <td>{windowName}</td>
              <td>{m.n}</td>
              <td>{fmt(m.mean_car)}</td>
              <td>{fmt(m.median_car)}</td>
              <td>{fmt(m.t_stat)}</td>
              <td>{fmt(m.bmp_stat)}</td>
              <td>{fmt(m.rank_p)}</td>
              <td>{fmt(m.rank_p_holm)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <img
        src={`/api/research/event-study/caar/${eventType.toLowerCase()}.png`}
        alt={`${eventType} real CAAR, day -30 to +60`}
        style={{ maxWidth: "100%" }}
      />
    </div>
  );
}

function EventStudyPageInner() {
  const [summary, setSummary] = useState<EventStudyRunSummaryOut | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiFetch<EventStudyRunSummaryOut>("/research/event-study")
      .then(setSummary)
      .catch((err) =>
        setError(
          err instanceof ApiError && err.status === 404
            ? "No real governance event-study run has been performed yet."
            : "Failed to load the event study."
        )
      );
  }, []);

  if (error) {
    return (
      <div>
        <h1>Governance event study</h1>
        <p>{error}</p>
      </div>
    );
  }
  if (!summary) {
    return <p>Loading...</p>;
  }

  const eventTypes = Object.keys(summary.metrics).filter((k) => k !== "_robustness");

  return (
    <div>
      <h1>Governance event study</h1>
      <EventStudyDisclaimer />
      <p>
        Run <code>{summary.run_id}</code> -- spec <code>{summary.spec_version}</code> (sha256{" "}
        <code>{summary.spec_sha256.slice(0, 16)}&hellip;</code>), git{" "}
        <code>{summary.git_sha.slice(0, 10)}</code>, {summary.created_at}
      </p>

      <h2>Event counts per filter stage</h2>
      <table>
        <thead>
          <tr>
            <th>Stage</th>
            <th>Real count</th>
          </tr>
        </thead>
        <tbody>
          {Object.entries(summary.event_counts).map(([stage, count]) => (
            <tr key={stage}>
              <td>{stage}</td>
              <td>{String(count)}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {eventTypes.map((eventType) => (
        <EventTypeTable
          key={eventType}
          eventType={eventType}
          windows={summary.metrics[eventType] as Record<string, WindowMetric>}
        />
      ))}
    </div>
  );
}

export default function EventStudyPage() {
  return (
    <RequireAuth>
      <EventStudyPageInner />
    </RequireAuth>
  );
}
