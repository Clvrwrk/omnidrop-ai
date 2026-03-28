"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Badge,
  Card,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeaderCell,
  TableRow,
  Text,
  Title,
} from "@tremor/react";
import { api, ApiError } from "@/lib/api-client";
import type { Location } from "@/lib/types";

const statusColor: Record<string, string> = {
  active: "green",
  invalid: "red",
  untested: "gray",
};

export default function SettingsPage() {
  const [locations, setLocations] = useState<Location[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [name, setName] = useState("");
  const [apiKey, setApiKey] = useState("");

  const loadLocations = useCallback(async () => {
    try {
      const res = await api.getLocations();
      setLocations(res.locations);
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
    }
  }, []);

  useEffect(() => {
    loadLocations();
  }, [loadLocations]);

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim() || !apiKey.trim()) return;

    setAdding(true);
    setError(null);
    try {
      await api.createLocation({ name: name.trim(), acculynx_api_key: apiKey.trim() });
      setName("");
      setApiKey("");
      await loadLocations();
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
    } finally {
      setAdding(false);
    }
  }

  async function handleDelete(locationId: string) {
    setError(null);
    try {
      await api.deleteLocation(locationId);
      await loadLocations();
    } catch (e) {
      if (e instanceof ApiError) {
        if (e.status === 409) {
          setError("Cannot delete location with unprocessed jobs.");
        } else {
          setError(e.message);
        }
      }
    }
  }

  return (
    <div className="space-y-6">
      <Title>Settings</Title>

      {error && (
        <Card className="border-red-200 bg-red-50">
          <Text className="text-red-700">{error}</Text>
        </Card>
      )}

      {/* Add Location Form */}
      <Card>
        <Title>Add Roofing Location</Title>
        <Text>Register a new AccuLynx location and API key</Text>
        <form onSubmit={handleAdd} className="mt-4 space-y-4">
          <div>
            <label htmlFor="location-name" className="block text-sm font-medium text-gray-700">
              Location Name
            </label>
            <input
              id="location-name"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Dallas North"
              className="mt-1 block w-full rounded border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
              required
            />
          </div>
          <div>
            <label htmlFor="api-key" className="block text-sm font-medium text-gray-700">
              AccuLynx API Key
            </label>
            <input
              id="api-key"
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder="Enter your AccuLynx API key"
              className="mt-1 block w-full rounded border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
              required
            />
          </div>
          <button
            type="submit"
            disabled={adding}
            className="rounded bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {adding ? "Adding..." : "Add Location"}
          </button>
        </form>
      </Card>

      {/* Locations List */}
      <Card>
        <Title>Registered Locations</Title>
        <Table className="mt-4">
          <TableHead>
            <TableRow>
              <TableHeaderCell>Name</TableHeaderCell>
              <TableHeaderCell>API Key</TableHeaderCell>
              <TableHeaderCell>Status</TableHeaderCell>
              <TableHeaderCell>Added</TableHeaderCell>
              <TableHeaderCell>Actions</TableHeaderCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {locations.map((loc) => (
              <TableRow key={loc.location_id}>
                <TableCell>{loc.name}</TableCell>
                <TableCell className="font-mono text-xs">
                  ****{loc.api_key_last4}
                </TableCell>
                <TableCell>
                  <Badge color={statusColor[loc.connection_status] ?? "gray"}>
                    {loc.connection_status}
                  </Badge>
                </TableCell>
                <TableCell>
                  {new Date(loc.created_at).toLocaleDateString()}
                </TableCell>
                <TableCell>
                  <button
                    onClick={() => handleDelete(loc.location_id)}
                    className="text-sm text-red-600 hover:text-red-800"
                  >
                    Remove
                  </button>
                </TableCell>
              </TableRow>
            ))}
            {locations.length === 0 && (
              <TableRow>
                <TableCell colSpan={5} className="text-center text-gray-400">
                  No locations registered
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </Card>
    </div>
  );
}
