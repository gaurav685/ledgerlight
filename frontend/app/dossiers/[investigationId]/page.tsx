"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { RequireAuth } from "@/components/RequireAuth";
import { apiFetch, ApiError } from "@/lib/api";
import type { DossierOut, InvestigationOut } from "@/lib/types";

const SECTION_HEADINGS: Record<string, string> = {
  summary: "Summary",
  chronology: "Chronology",
  findings: "Findings",
  risk_signals: "Risk signals",
  conflicting_evidence: "Conflicting evidence",
  limitations: "Limitations and data gaps",
  sources: "Sources",
  disclaimer: "Disclaimer",
};
const SECTION_ORDER = Object.keys(SECTION_HEADINGS);

const TERMINAL_STATES = new Set(["FINALISE"]);

function InvestigationDetail() {
  const params = useParams<{ investigationId: string }>();
  const [investigation, setInvestigation] = useState<InvestigationOut | null>(null);
  const [dossier, setDossier] = useState<DossierOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [exportContent, setExportContent] = useState<string | null>(null);

  const reload = useCallback(() => {
    apiFetch<InvestigationOut>(`/dossiers/investigations/${params.investigationId}`)
      .then(setInvestigation)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Failed to load"));
    apiFetch<DossierOut>(`/dossiers/investigations/${params.investigationId}/dossier`)
      .then(setDossier)
      .catch(() => setDossier(null));
  }, [params.investigationId]);

  useEffect(() => {
    reload();
  }, [reload]);

  // A real investigation's own async job may still be running -- poll
  // its real state every 3s until it reaches a real terminal state.
  useEffect(() => {
    if (!investigation || TERMINAL_STATES.has(investigation.state)) {
      return;
    }
    const timer = setTimeout(reload, 3000);
    return () => clearTimeout(timer);
  }, [investigation, reload]);

  async function handleExport(fmt: "markdown" | "json") {
    try {
      const result = await apiFetch<{ format: string; content: string }>(
        `/dossiers/investigations/${params.investigationId}/export?fmt=${fmt}`,
      );
      setExportContent(result.content);
    } catch (err) {
      setExportContent(err instanceof ApiError ? err.message : "Export failed");
    }
  }

  if (error) {
    return <div className="error-banner">{error}</div>;
  }
  if (!investigation) {
    return <p>Loading...</p>;
  }

  return (
    <div>
      <h1>Investigation</h1>
      <p>
        As of <strong>{investigation.as_of}</strong> -- state{" "}
        <strong>{investigation.state}</strong>
        {investigation.final_status && <> -- {investigation.final_status}</>}
      </p>
      {!TERMINAL_STATES.has(investigation.state) && <p>Running... this page refreshes itself.</p>}

      {dossier && (
        <>
          <h2>Dossier (version {dossier.version}, {dossier.status})</h2>
          {SECTION_ORDER.map((key) => (
            <section key={key}>
              <h3>{SECTION_HEADINGS[key]}</h3>
              {dossier.sections[key] && dossier.sections[key].length > 0 ? (
                <ul>
                  {dossier.sections[key].map((sentence, idx) => (
                    <li key={idx}>{sentence}</li>
                  ))}
                </ul>
              ) : (
                <p>None found.</p>
              )}
            </section>
          ))}
          <button type="button" className="btn secondary" onClick={() => handleExport("markdown")}>
            Export Markdown
          </button>{" "}
          <button type="button" className="btn secondary" onClick={() => handleExport("json")}>
            Export JSON
          </button>
          {exportContent && <pre className="page-text">{exportContent}</pre>}
        </>
      )}
    </div>
  );
}

export default function InvestigationDetailPage() {
  return (
    <RequireAuth>
      <InvestigationDetail />
    </RequireAuth>
  );
}
