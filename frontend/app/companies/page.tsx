"use client";

import { useState, type FormEvent } from "react";
import Link from "next/link";
import { RequireAuth } from "@/components/RequireAuth";
import { apiFetch, ApiError } from "@/lib/api";
import type { CompanyOut } from "@/lib/types";

function CompanySearch() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<CompanyOut[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [searching, setSearching] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setSearching(true);
    try {
      const rows = await apiFetch<CompanyOut[]>(`/companies/search?q=${encodeURIComponent(query)}`);
      setResults(rows);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Search failed");
      setResults(null);
    } finally {
      setSearching(false);
    }
  }

  return (
    <div>
      <h1>Company search</h1>
      {error && <div className="error-banner">{error}</div>}
      <form onSubmit={handleSubmit}>
        <div className="field">
          <label htmlFor="q">Company name</label>
          <input
            id="q"
            name="q"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="e.g. Jet Airways"
            required
          />
        </div>
        <button type="submit" className="btn" disabled={searching}>
          Search
        </button>
      </form>
      {results !== null && (
        <table>
          <thead>
            <tr>
              <th>Name</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {results.length === 0 && (
              <tr>
                <td colSpan={2}>No real matches found.</td>
              </tr>
            )}
            {results.map((company) => (
              <tr key={company.id}>
                <td>{company.name}</td>
                <td>
                  <Link href={`/companies/${company.id}`}>View overview</Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

export default function CompaniesPage() {
  return (
    <RequireAuth>
      <CompanySearch />
    </RequireAuth>
  );
}
