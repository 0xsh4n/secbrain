"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { CollectionOut } from "@/lib/types";
import { Card, CardHeader, Button, Input, Select, Textarea, Badge, Spinner, Empty, ErrorNote } from "@/components/ui";

export default function CollectionsPage() {
  const [collections, setCollections] = useState<CollectionOut[]>([]);
  const [categories, setCategories] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [category, setCategory] = useState("");
  const [visibility, setVisibility] = useState("private");

  function load() {
    api<CollectionOut[]>("/collections")
      .then(setCollections)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }
  useEffect(() => {
    load();
    api<{ categories: string[] }>("/collections/categories").then((r) => setCategories(r.categories)).catch(() => {});
  }, []);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    try {
      await api("/collections", { method: "POST", body: { name, description, category, visibility } });
      setShowForm(false);
      setName("");
      setDescription("");
      setCategory("");
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed");
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Collections</h1>
        <Button onClick={() => setShowForm(!showForm)}>{showForm ? "Cancel" : "+ New Collection"}</Button>
      </div>
      {error && <ErrorNote message={error} />}

      {showForm && (
        <Card className="p-4">
          <form onSubmit={create} className="space-y-3">
            <Input placeholder="Name" value={name} onChange={(e) => setName(e.target.value)} required />
            <Textarea placeholder="Description" value={description} onChange={(e) => setDescription(e.target.value)} />
            <div className="grid grid-cols-2 gap-3">
              <Select value={category} onChange={(e) => setCategory(e.target.value)}>
                <option value="">(no category)</option>
                {categories.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </Select>
              <Select value={visibility} onChange={(e) => setVisibility(e.target.value)}>
                <option value="private">Private</option>
                <option value="organization">Organization</option>
              </Select>
            </div>
            <Button type="submit">Create</Button>
          </form>
        </Card>
      )}

      {loading ? (
        <Spinner />
      ) : collections.length === 0 ? (
        <Empty message="No collections yet. Create one to organize knowledge." />
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
          {collections.map((c) => (
            <Card key={c.id} className="p-4">
              <div className="flex items-center justify-between">
                <h3 className="font-medium">{c.name}</h3>
                <Badge>{c.visibility}</Badge>
              </div>
              {c.category && <div className="mt-1 font-mono text-xs text-accent">{c.category}</div>}
              <p className="mt-2 text-sm text-muted">{c.description || "No description"}</p>
              <div className="mt-3 text-xs text-muted">{c.document_count} documents</div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
