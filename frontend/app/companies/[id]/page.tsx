"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { RequireAuth } from "@/components/RequireAuth";
import { ModelLimitationsBanner } from "@/components/Disclaimer";
import { apiFetch, ApiError } from "@/lib/api";
import type { CompanyOut, CredibilityOut, ScoreOut } from "@/lib/types";

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

function CompanyOverview() {
  const params = useParams<{ id: string }>();
  const companyId = params.id;

  const [asOf, setAsOf] = useState(todayIso());
  const [company, setCompany] = useState<CompanyOut | null>(null);
  const [score, setScore] = useState<ScoreOut | null>(null);
  const [scoreError, setScoreError] = useState<string | null>(null);
  const [credibility, setCredibility] = useState<CredibilityOut | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiFetch<CompanyOut>(`/companies/${companyId}`)
      .then(setCompany)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Failed to load company"));
  }, [companyId]);

  useEffect(() => {
    let active = true;
    apiFetch<ScoreOut>(`/companies/${companyId}/scores?as_of=${asOf}`)
      .then((result) => {
        if (active) {
          setScore(result);
          setScoreError(null);
        }
      })
      .catch((err) => {
        if (active) {
          setScore(null);
          setScoreError(err instanceof ApiError ? err.message : "Failed to load score");
        }
      });
    apiFetch<CredibilityOut>(`/companies/${companyId}/credibility?as_of=${asOf}`)
      .then((result) => active && setCredibility(result))
      .catch(() => active && setCredibility(null));
    return () => {
      active = false;
    };
  }, [companyId, asOf]);

  if (error) {
    return <div className="error-banner">{error}</div>;
  }
  if (!company) {
    return <p>Loading...</p>;
  }

  return (
    <div>
      <h1>{company.name}</h1>
      <div className="field">
        <label htmlFor="as_of">As of</label>
        <input
          id="as_of"
          type="date"
          value={asOf}
          max={todayIso()}
          onChange={(e) => setAsOf(e.target.value)}
        />
      </div>

      <p>
        <Link href={`/companies/${companyId}/timeline?as_of=${asOf}`}>View event timeline</Link>
      </p>

      <h2>Risk score</h2>
      {scoreError && <p>{scoreError}</p>}
      {score && (
        <>
          <p>
            Calibrated score as of <strong>{score.as_of}</strong>:{" "}
            <strong>{score.score.toFixed(4)}</strong> ({score.model_version})
          </p>
          {score.shap_contributors && score.shap_contributors.length > 0 && (
            <table>
              <thead>
                <tr>
                  <th>Feature</th>
                  <th>Contribution</th>
                </tr>
              </thead>
              <tbody>
                {score.shap_contributors.map(([feature, value]) => (
                  <tr key={feature}>
                    <td>{feature}</td>
                    <td>{value.toFixed(4)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <ModelLimitationsBanner text={score.model_limitations} />
        </>
      )}

      <h2>Management credibility</h2>
      {credibility && (
        <p>
          {credibility.available
            ? `Value: ${credibility.value}`
            : `Insufficient data -- ${credibility.reason}`}
        </p>
      )}
    </div>
  );
}

export default function CompanyOverviewPage() {
  return (
    <RequireAuth>
      <CompanyOverview />
    </RequireAuth>
  );
}
