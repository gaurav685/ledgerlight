"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { RequireAuth } from "@/components/RequireAuth";
import { apiFetch, ApiError } from "@/lib/api";
import type {
  AlertOut,
  AlertRuleOut,
  CompanyOut,
  WatchlistItemOut,
  WatchlistOut,
} from "@/lib/types";

const RULE_TYPES = ["new_event_type", "score_percentile_threshold"] as const;

function WatchlistDetail({ watchlist }: { watchlist: WatchlistOut }) {
  const [items, setItems] = useState<WatchlistItemOut[]>([]);
  const [rules, setRules] = useState<AlertRuleOut[]>([]);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<CompanyOut[]>([]);
  const [ruleType, setRuleType] = useState<string>(RULE_TYPES[0]);
  const [ruleConfig, setRuleConfig] = useState("{}");
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(() => {
    apiFetch<WatchlistItemOut[]>(`/watchlists/${watchlist.id}/items`).then(setItems).catch(() => {});
    apiFetch<AlertRuleOut[]>("/alerts/rules")
      .then((all) => setRules(all.filter((r) => r.watchlist_id === watchlist.id)))
      .catch(() => {});
  }, [watchlist.id]);

  useEffect(reload, [reload]);

  async function handleSearch(event: FormEvent) {
    event.preventDefault();
    try {
      const rows = await apiFetch<CompanyOut[]>(`/companies/search?q=${encodeURIComponent(query)}`);
      setResults(rows);
    } catch {
      setResults([]);
    }
  }

  async function handleAddItem(companyId: string) {
    try {
      await apiFetch(`/watchlists/${watchlist.id}/items`, {
        method: "POST",
        body: { company_id: companyId },
      });
      reload();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to add company");
    }
  }

  async function handleRemoveItem(itemId: string) {
    try {
      await apiFetch(`/watchlists/${watchlist.id}/items/${itemId}`, { method: "DELETE" });
      reload();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to remove company");
    }
  }

  async function handleCreateRule(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      const config = JSON.parse(ruleConfig) as Record<string, unknown>;
      await apiFetch("/alerts/rules", {
        method: "POST",
        body: { watchlist_id: watchlist.id, rule_type: ruleType, config },
      });
      reload();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to create rule (check config JSON)");
    }
  }

  async function handleDeleteRule(ruleId: string) {
    try {
      await apiFetch(`/alerts/rules/${ruleId}`, { method: "DELETE" });
      reload();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to delete rule");
    }
  }

  return (
    <div style={{ border: "1px solid var(--border)", padding: 12, marginBottom: 16 }}>
      <h3>{watchlist.name}</h3>
      {error && <div className="error-banner">{error}</div>}

      <h4>Companies</h4>
      <ul>
        {items.map((item) => (
          <li key={item.id}>
            {item.company_id}{" "}
            <button type="button" className="btn secondary" onClick={() => handleRemoveItem(item.id)}>
              Remove
            </button>
          </li>
        ))}
      </ul>
      <form onSubmit={handleSearch}>
        <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Company name" />
        <button type="submit" className="btn secondary">
          Search
        </button>
      </form>
      {results.map((company) => (
        <div key={company.id}>
          {company.name}{" "}
          <button type="button" className="btn secondary" onClick={() => handleAddItem(company.id)}>
            Add
          </button>
        </div>
      ))}

      <h4>Alert rules</h4>
      <ul>
        {rules.map((rule) => (
          <li key={rule.id}>
            {rule.rule_type}: {JSON.stringify(rule.config)}{" "}
            <button type="button" className="btn secondary" onClick={() => handleDeleteRule(rule.id)}>
              Delete
            </button>
          </li>
        ))}
      </ul>
      <form onSubmit={handleCreateRule}>
        <select value={ruleType} onChange={(e) => setRuleType(e.target.value)}>
          {RULE_TYPES.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
        <input
          value={ruleConfig}
          onChange={(e) => setRuleConfig(e.target.value)}
          placeholder='{"event_type_code":"ANY"}'
          style={{ width: 260 }}
        />
        <button type="submit" className="btn secondary">
          Add rule
        </button>
      </form>
    </div>
  );
}

function AlertsList() {
  const [alerts, setAlerts] = useState<AlertOut[]>([]);

  const reload = useCallback(() => {
    apiFetch<AlertOut[]>("/alerts").then(setAlerts).catch(() => {});
  }, []);

  useEffect(reload, [reload]);

  async function handleAcknowledge(alertId: string) {
    await apiFetch(`/alerts/${alertId}/acknowledge`, { method: "POST" });
    reload();
  }

  return (
    <div>
      <h2>Alerts</h2>
      <table>
        <thead>
          <tr>
            <th>Triggered</th>
            <th>Payload</th>
            <th>Acknowledged</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {alerts.length === 0 && (
            <tr>
              <td colSpan={4}>No real alerts yet.</td>
            </tr>
          )}
          {alerts.map((alert) => (
            <tr key={alert.id}>
              <td>{alert.triggered_at}</td>
              <td>{JSON.stringify(alert.payload)}</td>
              <td>{alert.acknowledged_at ?? "no"}</td>
              <td>
                {!alert.acknowledged_at && (
                  <button
                    type="button"
                    className="btn secondary"
                    onClick={() => handleAcknowledge(alert.id)}
                  >
                    Acknowledge
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Watchlists() {
  const [watchlists, setWatchlists] = useState<WatchlistOut[]>([]);
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(() => {
    apiFetch<WatchlistOut[]>("/watchlists")
      .then(setWatchlists)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Failed to load"));
  }, []);

  useEffect(reload, [reload]);

  async function handleCreate(event: FormEvent) {
    event.preventDefault();
    try {
      await apiFetch("/watchlists", { method: "POST", body: { name } });
      setName("");
      reload();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to create watchlist");
    }
  }

  return (
    <div>
      <h1>Watchlists</h1>
      {error && <div className="error-banner">{error}</div>}
      <form onSubmit={handleCreate}>
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Watchlist name" />
        <button type="submit" className="btn">
          Create
        </button>
      </form>
      {watchlists.map((watchlist) => (
        <WatchlistDetail key={watchlist.id} watchlist={watchlist} />
      ))}
      <AlertsList />
    </div>
  );
}

export default function WatchlistsPage() {
  return (
    <RequireAuth>
      <Watchlists />
    </RequireAuth>
  );
}
