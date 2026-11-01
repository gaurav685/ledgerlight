"use client";

import { useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { RequireAuth } from "@/components/RequireAuth";
import { apiFetch, ApiError } from "@/lib/api";
import type { CompanyOut, InvestigationOut } from "@/lib/types";

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

function Dossiers() {
  const [investigations, setInvestigations] = useState<InvestigationOut[]>([]);
  const [listError, setListError] = useState<string | null>(null);

  const [query, setQuery] = useState("");
  const [results, setResults] = useState<CompanyOut[]>([]);
  const [selectedCompany, setSelectedCompany] = useState<CompanyOut | null>(null);
  const [asOf, setAsOf] = useState(todayIso());
  const [createError, setCreateError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  function reloadInvestigations() {
    apiFetch<InvestigationOut[]>("/dossiers/investigations")
      .then(setInvestigations)
      .catch((err) => setListError(err instanceof ApiError ? err.message : "Failed to load"));
  }

  useEffect(reloadInvestigations, []);

  async function handleSearch(event: FormEvent) {
    event.preventDefault();
    try {
      const rows = await apiFetch<CompanyOut[]>(`/companies/search?q=${encodeURIComponent(query)}`);
      setResults(rows);
    } catch {
      setResults([]);
    }
  }

  async function handleCreate(event: FormEvent) {
    event.preventDefault();
    if (!selectedCompany) {
      return;
    }
    setCreateError(null);
    setCreating(true);
    try {
      await apiFetch<InvestigationOut>("/dossiers/investigations", {
        method: "POST",
        body: { company_id: selectedCompany.id, as_of: asOf },
      });
      setSelectedCompany(null);
      setResults([]);
      setQuery("");
      reloadInvestigations();
    } catch (err) {
      setCreateError(err instanceof ApiError ? err.message : "Failed to start investigation");
    } finally {
      setCreating(false);
    }
  }

  return (
    <div>
      <h1>Dossiers</h1>

      <h2>Start a new investigation</h2>
      {createError && <div className="error-banner">{createError}</div>}
      {!selectedCompany ? (
        <form onSubmit={handleSearch}>
          <div className="field">
            <label htmlFor="company_query">Company name</label>
            <input id="company_query" value={query} onChange={(e) => setQuery(e.target.value)} />
          </div>
          <button type="submit" className="btn secondary">
            Search
          </button>
          {results.length > 0 && (
            <ul>
              {results.map((company) => (
                <li key={company.id}>
                  <button
                    type="button"
                    className="btn secondary"
                    onClick={() => setSelectedCompany(company)}
                  >
                    Select {company.name}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </form>
      ) : (
        <form onSubmit={handleCreate}>
          <p>
            Company: <strong>{selectedCompany.name}</strong>{" "}
            <button type="button" className="btn secondary" onClick={() => setSelectedCompany(null)}>
              Change
            </button>
          </p>
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
          <button type="submit" className="btn" disabled={creating}>
            {creating ? "Starting..." : "Start investigation"}
          </button>
        </form>
      )}

      <h2>Recent investigations</h2>
      {listError && <div className="error-banner">{listError}</div>}
      <table>
        <thead>
          <tr>
            <th>As of</th>
            <th>State</th>
            <th>Final status</th>
            <th>Started</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {investigations.length === 0 && (
            <tr>
              <td colSpan={5}>No real investigations yet.</td>
            </tr>
          )}
          {investigations.map((investigation) => (
            <tr key={investigation.id}>
              <td>{investigation.as_of}</td>
              <td>{investigation.state}</td>
              <td>{investigation.final_status ?? "--"}</td>
              <td>{investigation.started_at}</td>
              <td>
                <Link href={`/dossiers/${investigation.id}`}>View</Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function DossiersPage() {
  return (
    <RequireAuth>
      <Dossiers />
    </RequireAuth>
  );
}
