"use client";

import { useEffect, useRef, useState } from "react";
import { api, apiUrl, getToken } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { ModelStatus } from "@/lib/types";
import { Button, Card, CardHeader, ErrorNote, Spinner } from "@/components/ui";

export default function SettingsPage() {
  const { user } = useAuth();
  const [status, setStatus] = useState<ModelStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [backupBusy, setBackupBusy] = useState(false);
  const [backupError, setBackupError] = useState("");
  const [backupMessage, setBackupMessage] = useState("");
  const [driveStatus, setDriveStatus] = useState<{ configured: boolean; connected: boolean; email: string; last_sync: string }>({ configured: false, connected: false, email: "", last_sync: "" });
  const [driveBusy, setDriveBusy] = useState(false);
  const [driveMessage, setDriveMessage] = useState("");
  const backupFileRef = useRef<HTMLInputElement>(null);

  async function downloadBackup() {
    setBackupBusy(true);
    setBackupError("");
    setBackupMessage("");
    try {
      const response = await fetch(`${apiUrl}/api/v1/documents/backup/export`, {
        headers: { Authorization: `Bearer ${getToken()}` },
      });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.detail || `Backup failed (${response.status})`);
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "secbrain-library-backup.zip";
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      setBackupMessage("Backup downloaded. Save this ZIP in your Google Drive folder.");
    } catch (cause) {
      setBackupError(cause instanceof Error ? cause.message : "Could not create the backup.");
    } finally {
      setBackupBusy(false);
    }
  }

  async function restoreBackup() {
    const file = backupFileRef.current?.files?.[0];
    if (!file) {
      setBackupError("Choose a SecBrain backup ZIP to restore.");
      return;
    }
    setBackupBusy(true);
    setBackupError("");
    setBackupMessage("");
    try {
      const form = new FormData();
      form.append("file", file);
      const response = await fetch(`${apiUrl}/api/v1/documents/backup/import`, {
        method: "POST",
        headers: { Authorization: `Bearer ${getToken()}` },
        body: form,
      });
      const result = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(result.detail || `Restore failed (${response.status})`);
      setBackupMessage(`Restore queued: ${result.imported} document(s) to re-index; ${result.skipped} duplicate or unsupported item(s) skipped.`);
      if (backupFileRef.current) backupFileRef.current.value = "";
    } catch (cause) {
      setBackupError(cause instanceof Error ? cause.message : "Could not restore this backup.");
    } finally {
      setBackupBusy(false);
    }
  }

  async function connectDrive() {
    setDriveBusy(true);
    setDriveMessage("");
    try {
      const result = await api<{ authorization_url: string }>("/drive-sync/connect");
      window.location.assign(result.authorization_url);
    } catch (cause) {
      setDriveMessage(cause instanceof Error ? cause.message : "Could not connect Google Drive.");
      setDriveBusy(false);
    }
  }

  async function syncDrive() {
    setDriveBusy(true);
    try {
      const result = await api<{ busy?: boolean; pushed: number; pulled: number; skipped: number; last_sync: string }>("/drive-sync/sync", { method: "POST" });
      if (result.busy) {
        setDriveMessage("A sync is already running. It will continue automatically.");
        return;
      }
      setDriveStatus((current) => ({ ...current, connected: true, last_sync: result.last_sync }));
      setDriveMessage(`Synced ${result.pushed} to Drive and ${result.pulled} from Drive.`);
    } catch (cause) {
      setDriveMessage(cause instanceof Error ? cause.message : "Google Drive sync failed.");
    } finally {
      setDriveBusy(false);
    }
  }

  async function disconnectDrive() {
    setDriveBusy(true);
    try {
      await api<void>("/drive-sync/disconnect", { method: "POST" });
      setDriveStatus((current) => ({ ...current, connected: false, email: "", last_sync: "" }));
      setDriveMessage("Google Drive disconnected from this SecBrain account.");
    } catch (cause) {
      setDriveMessage(cause instanceof Error ? cause.message : "Could not disconnect Google Drive.");
    } finally {
      setDriveBusy(false);
    }
  }

  useEffect(() => {
    api<ModelStatus>("/models/status")
      .then(setStatus)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    let active = true;
    const check = async () => {
      try {
        const result = await api<typeof driveStatus>("/drive-sync/status");
        if (!active) return;
        setDriveStatus(result);
      } catch { /* Drive sync is optional and must not block settings. */ }
    };
    void check();
    return () => { active = false; };
  }, []);

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Settings</h1>

      <Card className="p-4">
        <CardHeader title="Account" />
        <dl className="space-y-2 pt-3 text-sm">
          <Row k="Email" v={user?.email || "—"} />
          <Row k="Role" v={user?.role || "—"} />
          <Row k="Organization" v={user?.organization_id || "—"} />
        </dl>
      </Card>

      <Card className="p-4">
        <CardHeader title="Library backup & restore" />
        <div className="space-y-4 pt-3 text-sm">
          <p className="max-w-3xl text-muted">
            Move your knowledge library between PCs without hosting SecBrain online. The backup contains only
            extracted text and knowledge metadata—never the original PDFs or source files. Restore rebuilds the search index on this PC.
            Conversations, accounts, API keys, and model settings are not included.
          </p>
          <div className="grid gap-3 md:grid-cols-2">
            <div className="rounded-lg border border-border bg-surface-2/50 p-4">
              <h2 className="font-medium text-fg">Back up this library</h2>
              <p className="mt-1 min-h-10 text-xs text-muted">
                Download a portable ZIP of extracted knowledge, then save it in your Drive.
              </p>
              <Button className="mt-3" onClick={downloadBackup} disabled={backupBusy}>
                {backupBusy ? "Working…" : "Download backup ZIP"}
              </Button>
            </div>
            <div className="rounded-lg border border-border bg-surface-2/50 p-4">
              <h2 className="font-medium text-fg">Restore on this PC</h2>
              <p className="mt-1 min-h-10 text-xs text-muted">
                Download the ZIP from Drive, select it here, and SecBrain will re-index its documents.
              </p>
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <input
                  ref={backupFileRef}
                  type="file"
                  accept=".zip,application/zip"
                  className="block min-w-0 flex-1 text-xs text-muted file:mr-2 file:rounded-md file:border-0 file:bg-surface-2 file:px-2 file:py-1.5 file:text-fg"
                />
                <Button onClick={restoreBackup} disabled={backupBusy}>
                  {backupBusy ? "Working…" : "Restore backup"}
                </Button>
              </div>
            </div>
          </div>
          {backupError && <ErrorNote message={backupError} />}
          {backupMessage && <p role="status" className="text-xs text-success">{backupMessage}</p>}
          <p className="text-xs text-muted">
            Restored collections are private to your account. Re-importing a backup skips documents already
            indexed in your accessible library. ZIPs may be up to 512 MB; each document may be up to 25 MB.
          </p>
        </div>
      </Card>

      <Card className="p-4">
        <CardHeader title="Google Drive live knowledge sync" />
        <div className="space-y-3 pt-3 text-sm">
          <p className="max-w-3xl text-muted">
            Keep the extracted knowledge pool in your Google Drive and sync it across SecBrain installations using the same Google account. Only normalized text and metadata are synced; original PDFs, conversations, credentials, and settings stay local.
          </p>
          {!driveStatus.configured ? (
            <p className="rounded-lg border border-border bg-surface-2/50 p-3 text-xs text-muted">
              Google Drive sync needs OAuth credentials in the backend environment. Set <code>SECBRAIN_GOOGLE_DRIVE_CLIENT_ID</code> and <code>SECBRAIN_GOOGLE_DRIVE_CLIENT_SECRET</code>, then restart SecBrain.
            </p>
          ) : driveStatus.connected ? (
            <>
              <p className="text-xs text-muted">Connected as {driveStatus.email || "Google account"}. Automatic sync runs about every minute while SecBrain is open.</p>
              {driveStatus.last_sync && <p className="text-xs text-muted">Last sync: {new Date(driveStatus.last_sync).toLocaleString()}</p>}
              <div className="flex flex-wrap gap-2">
                <Button onClick={() => void syncDrive()} disabled={driveBusy}>{driveBusy ? "Syncing…" : "Sync now"}</Button>
                <Button onClick={() => void disconnectDrive()} disabled={driveBusy}>Disconnect</Button>
              </div>
            </>
          ) : (
            <Button onClick={() => void connectDrive()} disabled={driveBusy}>{driveBusy ? "Connecting…" : "Connect Google Drive"}</Button>
          )}
          {driveMessage && <p role="status" className="text-xs text-muted">{driveMessage}</p>}
        </div>
      </Card>

      <Card className="p-4">
        <CardHeader title="Privacy & Data Governance" />
        {loading ? (
          <Spinner />
        ) : (
          <div className="space-y-2 pt-3 text-sm">
            <Row k="API base URL" v={apiUrl} />
            <Row k="Inference provider" v={status?.generation.provider || "—"} />
            <Row
              k="Outbound LLM calls"
              v={status?.generation.outbound_disabled ? "Disabled (air-gapped)" : "Enabled"}
            />
            <Row k="Vector store" v={status?.vector_store || "—"} />
            <p className="pt-2 text-xs text-muted">
              Collections and documents are isolated per organization. Private collections are visible only
              to their owner and explicit members. Document contents are not sent to a hosted model unless an
              outbound provider is explicitly configured. Set SECBRAIN_DISABLE_OUTBOUND_LLM=true to forbid all
              outbound model calls. Deleting a document removes its chunks and vectors.
            </p>
          </div>
        )}
      </Card>
    </div>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex items-center justify-between gap-4">
      <dt className="text-muted">{k}</dt>
      <dd className="break-all text-right text-fg">{v}</dd>
    </div>
  );
}
