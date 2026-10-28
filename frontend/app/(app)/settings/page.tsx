"use client";

import { useEffect, useState } from "react";
import { api, apiUrl } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { ModelStatus } from "@/lib/types";
import { Card, CardHeader, Spinner } from "@/components/ui";

export default function SettingsPage() {
  const { user } = useAuth();
  const [status, setStatus] = useState<ModelStatus | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api<ModelStatus>("/models/status")
      .then(setStatus)
      .catch(() => {})
      .finally(() => setLoading(false));
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
