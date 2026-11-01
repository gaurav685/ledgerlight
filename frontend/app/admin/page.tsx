"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { RequireAuth } from "@/components/RequireAuth";
import { useAuth } from "@/lib/auth";
import { apiFetch, ApiError } from "@/lib/api";
import {
  ROLES,
  type ApiKeyCreateResponse,
  type ApiKeyOut,
  type AuditLogOut,
  type UserOut,
  type WebhookCreateResponse,
  type WebhookDeliveryOut,
  type WebhookOut,
} from "@/lib/types";

function UsersSection() {
  const [users, setUsers] = useState<UserOut[]>([]);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<string>(ROLES[0]);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(() => {
    apiFetch<UserOut[]>("/admin/users").then(setUsers).catch(() => {});
  }, []);
  useEffect(reload, [reload]);

  async function handleCreate(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      await apiFetch("/admin/users", { method: "POST", body: { email, password, role } });
      setEmail("");
      setPassword("");
      reload();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to create user");
    }
  }

  async function handleRoleChange(userId: string, newRole: string) {
    await apiFetch(`/admin/users/${userId}/role`, { method: "PATCH", body: { role: newRole } });
    reload();
  }

  async function handleRevoke(userId: string) {
    await apiFetch(`/admin/users/${userId}`, { method: "DELETE" });
    reload();
  }

  return (
    <section>
      <h2>Users and roles</h2>
      {error && <div className="error-banner">{error}</div>}
      <table>
        <thead>
          <tr>
            <th>Email</th>
            <th>Role</th>
            <th>Membership</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {users.map((user) => (
            <tr key={user.user_id}>
              <td>{user.email}</td>
              <td>
                <select
                  value={user.role}
                  onChange={(e) => handleRoleChange(user.user_id, e.target.value)}
                  disabled={user.membership_status === "revoked"}
                >
                  {ROLES.map((r) => (
                    <option key={r} value={r}>
                      {r}
                    </option>
                  ))}
                </select>
              </td>
              <td>{user.membership_status}</td>
              <td>
                {user.membership_status !== "revoked" && (
                  <button
                    type="button"
                    className="btn danger"
                    onClick={() => handleRevoke(user.user_id)}
                  >
                    Revoke
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <form onSubmit={handleCreate}>
        <input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="Email" />
        <input
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="Password"
          type="password"
        />
        <select value={role} onChange={(e) => setRole(e.target.value)}>
          {ROLES.map((r) => (
            <option key={r} value={r}>
              {r}
            </option>
          ))}
        </select>
        <button type="submit" className="btn">
          Create user
        </button>
      </form>
    </section>
  );
}

function ApiKeysSection() {
  const [keys, setKeys] = useState<ApiKeyOut[]>([]);
  const [name, setName] = useState("");
  const [rawKey, setRawKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(() => {
    apiFetch<ApiKeyOut[]>("/api-keys").then(setKeys).catch(() => {});
  }, []);
  useEffect(reload, [reload]);

  async function handleCreate(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      const result = await apiFetch<ApiKeyCreateResponse>("/api-keys", {
        method: "POST",
        body: { name, scopes: [] },
      });
      setRawKey(result.raw_key);
      setName("");
      reload();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to create key");
    }
  }

  async function handleRevoke(id: string) {
    await apiFetch(`/api-keys/${id}`, { method: "DELETE" });
    reload();
  }

  return (
    <section>
      <h2>API keys</h2>
      {error && <div className="error-banner">{error}</div>}
      {rawKey && (
        <div className="disclaimer-banner">
          Real key, shown once -- copy it now, it cannot be shown again: <code>{rawKey}</code>
        </div>
      )}
      <table>
        <thead>
          <tr>
            <th>Name</th>
            <th>Prefix</th>
            <th>Revoked</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {keys.map((key) => (
            <tr key={key.id}>
              <td>{key.name}</td>
              <td>{key.key_prefix}</td>
              <td>{key.revoked_at ?? "no"}</td>
              <td>
                {!key.revoked_at && (
                  <button type="button" className="btn danger" onClick={() => handleRevoke(key.id)}>
                    Revoke
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <form onSubmit={handleCreate}>
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Key name" />
        <button type="submit" className="btn">
          Create key
        </button>
      </form>
    </section>
  );
}

function WebhooksSection() {
  const [webhooks, setWebhooks] = useState<WebhookOut[]>([]);
  const [url, setUrl] = useState("");
  const [rawSecret, setRawSecret] = useState<string | null>(null);
  const [deliveries, setDeliveries] = useState<Record<string, WebhookDeliveryOut[]>>({});
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(() => {
    apiFetch<WebhookOut[]>("/webhooks").then(setWebhooks).catch(() => {});
  }, []);
  useEffect(reload, [reload]);

  async function handleCreate(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      const result = await apiFetch<WebhookCreateResponse>("/webhooks", {
        method: "POST",
        body: { url },
      });
      setRawSecret(result.raw_secret);
      setUrl("");
      reload();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to register webhook");
    }
  }

  async function handleTest(id: string) {
    try {
      await apiFetch(`/webhooks/${id}/test`, { method: "POST" });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Test delivery failed");
    }
  }

  async function handleDelete(id: string) {
    await apiFetch(`/webhooks/${id}`, { method: "DELETE" });
    reload();
  }

  async function handleShowDeliveries(id: string) {
    const rows = await apiFetch<WebhookDeliveryOut[]>(`/webhooks/${id}/deliveries`);
    setDeliveries((prev) => ({ ...prev, [id]: rows }));
  }

  return (
    <section>
      <h2>Webhooks</h2>
      {error && <div className="error-banner">{error}</div>}
      {rawSecret && (
        <div className="disclaimer-banner">
          Real signing secret, shown once: <code>{rawSecret}</code>
        </div>
      )}
      {webhooks.map((webhook) => (
        <div key={webhook.id} style={{ marginBottom: 8 }}>
          {webhook.url} ({webhook.is_active ? "active" : "inactive"}){" "}
          <button type="button" className="btn secondary" onClick={() => handleTest(webhook.id)}>
            Send test
          </button>{" "}
          <button
            type="button"
            className="btn secondary"
            onClick={() => handleShowDeliveries(webhook.id)}
          >
            Show deliveries
          </button>{" "}
          <button type="button" className="btn danger" onClick={() => handleDelete(webhook.id)}>
            Delete
          </button>
          {deliveries[webhook.id] && (
            <ul>
              {deliveries[webhook.id].map((delivery) => (
                <li key={delivery.id}>
                  {delivery.created_at}: {delivery.status} (attempt {delivery.attempt_count})
                </li>
              ))}
            </ul>
          )}
        </div>
      ))}
      <form onSubmit={handleCreate}>
        <input
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://example.com/hook"
          style={{ width: 300 }}
        />
        <button type="submit" className="btn">
          Register webhook
        </button>
      </form>
    </section>
  );
}

function AuditLogSection() {
  const [rows, setRows] = useState<AuditLogOut[]>([]);

  useEffect(() => {
    apiFetch<AuditLogOut[]>("/admin/audit-log").then(setRows).catch(() => {});
  }, []);

  return (
    <section>
      <h2>Audit log</h2>
      <table>
        <thead>
          <tr>
            <th>When</th>
            <th>Action</th>
            <th>Target</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id}>
              <td>{row.created_at}</td>
              <td>{row.action}</td>
              <td>
                {row.target_type} {row.target_id}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function AdminConsole() {
  const { identity } = useAuth();
  if (identity?.role !== "tenant_admin") {
    return <p>This page is restricted to tenant admins.</p>;
  }
  return (
    <div>
      <h1>Tenant admin</h1>
      <UsersSection />
      <ApiKeysSection />
      <WebhooksSection />
      <AuditLogSection />
    </div>
  );
}

export default function AdminPage() {
  return (
    <RequireAuth>
      <AdminConsole />
    </RequireAuth>
  );
}
