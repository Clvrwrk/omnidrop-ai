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
import type { Organization, OrgUser, Location } from "@/lib/types";

const statusColor: Record<string, string> = {
  active: "green",
  invalid: "red",
  untested: "gray",
};

interface SlackFormState {
  webhookUrl: string;
  channel: string;
  saving: boolean;
  testing: boolean;
  saveMessage: string | null;
  saveError: boolean;
  testMessage: string | null;
  testSuccess: boolean | null;
}

function defaultSlackState(loc: Location): SlackFormState {
  return {
    webhookUrl: loc.notification_channels?.slack?.webhook_url ?? "",
    channel: loc.notification_channels?.slack?.channel ?? "",
    saving: false,
    testing: false,
    saveMessage: null,
    saveError: false,
    testMessage: null,
    testSuccess: null,
  };
}

export default function SettingsPage() {
  const [org, setOrg] = useState<Organization | null>(null);
  const [users, setUsers] = useState<OrgUser[]>([]);
  const [maxUsers, setMaxUsers] = useState(5);
  const [locations, setLocations] = useState<Location[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [name, setName] = useState("");
  const [apiKey, setApiKey] = useState("");
  // Per-location Slack notification form state keyed by location_id
  const [slackForms, setSlackForms] = useState<
    Record<string, SlackFormState>
  >({});

  const loadOrg = useCallback(async () => {
    try {
      const [orgRes, usersRes] = await Promise.all([
        api.getOrganization(),
        api.getOrgUsers(),
      ]);
      setOrg(orgRes);
      setUsers(usersRes.users);
      setMaxUsers(usersRes.max_users);
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
    }
  }, []);

  const loadLocations = useCallback(async () => {
    try {
      const res = await api.getLocations();
      setLocations(res.locations);
      // Initialise Slack form state for any new locations
      setSlackForms((prev) => {
        const next = { ...prev };
        for (const loc of res.locations) {
          if (!next[loc.location_id]) {
            next[loc.location_id] = defaultSlackState(loc);
          }
        }
        return next;
      });
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
    }
  }, []);

  function updateSlackField(
    locationId: string,
    field: keyof Pick<SlackFormState, "webhookUrl" | "channel">,
    value: string,
  ) {
    setSlackForms((prev) => ({
      ...prev,
      [locationId]: { ...prev[locationId], [field]: value },
    }));
  }

  async function handleSaveNotifications(locationId: string) {
    const form = slackForms[locationId];
    if (!form) return;
    setSlackForms((prev) => ({
      ...prev,
      [locationId]: {
        ...prev[locationId],
        saving: true,
        saveMessage: null,
        saveError: false,
      },
    }));
    try {
      await api.updateLocationNotifications(locationId, {
        slack_webhook_url: form.webhookUrl.trim() || null,
        slack_channel: form.channel.trim() || null,
      });
      setSlackForms((prev) => ({
        ...prev,
        [locationId]: {
          ...prev[locationId],
          saving: false,
          saveMessage: "Saved.",
          saveError: false,
        },
      }));
    } catch (e) {
      setSlackForms((prev) => ({
        ...prev,
        [locationId]: {
          ...prev[locationId],
          saving: false,
          saveMessage:
            e instanceof ApiError ? e.message : "Failed to save settings.",
          saveError: true,
        },
      }));
    }
  }

  async function handleTestNotifications(locationId: string) {
    setSlackForms((prev) => ({
      ...prev,
      [locationId]: {
        ...prev[locationId],
        testing: true,
        testMessage: null,
        testSuccess: null,
      },
    }));
    try {
      const res = await api.testLocationNotifications(locationId);
      setSlackForms((prev) => ({
        ...prev,
        [locationId]: {
          ...prev[locationId],
          testing: false,
          testMessage: res.success
            ? "Test message sent to Slack ✓"
            : res.message || "Failed — check your webhook URL",
          testSuccess: res.success,
        },
      }));
    } catch {
      setSlackForms((prev) => ({
        ...prev,
        [locationId]: {
          ...prev[locationId],
          testing: false,
          testMessage: "Failed — check your webhook URL",
          testSuccess: false,
        },
      }));
    }
  }

  useEffect(() => {
    loadOrg();
    loadLocations();
  }, [loadOrg, loadLocations]);

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim() || !apiKey.trim() || !org) return;

    setAdding(true);
    setError(null);
    try {
      await api.createLocation({
        name: name.trim(),
        acculynx_api_key: apiKey.trim(),
        organization_id: org.organization_id,
      });
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
    <div className="space-y-8">
      <Title>Settings</Title>

      {error && (
        <Card className="border-red-200 bg-red-50">
          <Text className="text-red-700">{error}</Text>
        </Card>
      )}

      {/* ─── Company Section ──────────────────────────────────────────── */}
      <div className="space-y-4">
        <Title>Company</Title>

        <Card>
          <Text className="text-sm font-medium text-gray-500">Organization Name</Text>
          <Text className="mt-1 text-lg font-semibold">
            {org?.name ?? "Loading..."}
          </Text>
        </Card>

        <Card>
          <div className="flex items-center justify-between">
            <Title>Users</Title>
            <button
              disabled={users.length >= maxUsers}
              className="rounded bg-blue-600 px-3 py-1.5 text-sm text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
              title={
                users.length >= maxUsers
                  ? `Maximum of ${maxUsers} users reached`
                  : "Invite a new user"
              }
            >
              Invite User
            </button>
          </div>
          {users.length >= maxUsers && (
            <Text className="mt-1 text-xs text-amber-600">
              Maximum of {maxUsers} users reached.
            </Text>
          )}
          <Table className="mt-4">
            <TableHead>
              <TableRow>
                <TableHeaderCell>Name</TableHeaderCell>
                <TableHeaderCell>Added</TableHeaderCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {users.map((user) => (
                <TableRow key={user.user_id}>
                  <TableCell>{user.name || "—"}</TableCell>
                  <TableCell>
                    {new Date(user.created_at).toLocaleDateString()}
                  </TableCell>
                </TableRow>
              ))}
              {users.length === 0 && (
                <TableRow>
                  <TableCell colSpan={2} className="text-center text-gray-400">
                    No users found
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </Card>
      </div>

      {/* ─── AccuLynx Integrations Section ────────────────────────────── */}
      <div className="space-y-4">
        <Title>AccuLynx Integrations</Title>
        <Card className="border-blue-100 bg-blue-50">
          <Text className="text-sm text-blue-800">
            AccuLynx integration is optional. You can process documents without it.
          </Text>
        </Card>

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
              disabled={adding || !org}
              className="rounded bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700 disabled:opacity-50"
            >
              {adding ? "Adding..." : "Add Location"}
            </button>
          </form>
        </Card>

        {/* Locations List */}
        {locations.length === 0 ? (
          <Card>
            <Text className="text-center text-gray-400">
              No locations registered
            </Text>
          </Card>
        ) : (
          <div className="space-y-4">
            {locations.map((loc) => {
              const form = slackForms[loc.location_id];
              return (
                <Card key={loc.location_id}>
                  {/* Location header row */}
                  <div className="flex items-center justify-between">
                    <div>
                      <Title>{loc.name}</Title>
                      <Text className="text-xs text-gray-500">
                        API key: ****{loc.api_key_last4} &nbsp;·&nbsp; Added{" "}
                        {new Date(loc.created_at).toLocaleDateString()}
                      </Text>
                    </div>
                    <div className="flex items-center gap-3">
                      <Badge
                        color={
                          (statusColor[loc.connection_status] as
                            | "green"
                            | "red"
                            | "gray") ?? "gray"
                        }
                      >
                        {loc.connection_status}
                      </Badge>
                      <button
                        onClick={() => handleDelete(loc.location_id)}
                        className="text-sm text-red-600 hover:text-red-800"
                      >
                        Remove
                      </button>
                    </div>
                  </div>

                  {/* ── Notifications section ──────────────────────────── */}
                  <div className="mt-5 border-t pt-5 space-y-4">
                    <Title>Notifications</Title>

                    <div>
                      <label
                        htmlFor={`slack-url-${loc.location_id}`}
                        className="block text-sm font-medium text-gray-700"
                      >
                        Slack Webhook URL
                      </label>
                      <input
                        id={`slack-url-${loc.location_id}`}
                        type="text"
                        value={form?.webhookUrl ?? ""}
                        onChange={(e) =>
                          updateSlackField(
                            loc.location_id,
                            "webhookUrl",
                            e.target.value,
                          )
                        }
                        placeholder="https://hooks.slack.com/services/..."
                        className="mt-1 block w-full rounded border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
                      />
                      <Text className="mt-1 text-xs text-gray-500">
                        Paste your Slack Incoming Webhook URL. We&apos;ll send
                        document clarification alerts here when AI can&apos;t
                        process a file.
                      </Text>
                    </div>

                    <div>
                      <label
                        htmlFor={`slack-channel-${loc.location_id}`}
                        className="block text-sm font-medium text-gray-700"
                      >
                        Channel (optional)
                      </label>
                      <input
                        id={`slack-channel-${loc.location_id}`}
                        type="text"
                        value={form?.channel ?? ""}
                        onChange={(e) =>
                          updateSlackField(
                            loc.location_id,
                            "channel",
                            e.target.value,
                          )
                        }
                        placeholder="#field-ops"
                        className="mt-1 block w-full rounded border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
                      />
                    </div>

                    <div className="flex items-center gap-3 flex-wrap">
                      <button
                        onClick={() =>
                          handleSaveNotifications(loc.location_id)
                        }
                        disabled={form?.saving}
                        className="rounded bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700 disabled:opacity-50"
                      >
                        {form?.saving ? "Saving..." : "Save"}
                      </button>
                      <button
                        onClick={() =>
                          handleTestNotifications(loc.location_id)
                        }
                        disabled={
                          form?.testing || !form?.webhookUrl?.trim()
                        }
                        className="rounded border border-gray-300 px-4 py-2 text-sm text-gray-700 hover:bg-gray-50 disabled:opacity-50"
                      >
                        {form?.testing ? "Sending..." : "Test"}
                      </button>

                      {form?.saveMessage && (
                        <Text
                          className={`text-sm ${
                            form.saveError
                              ? "text-red-600"
                              : "text-green-600"
                          }`}
                        >
                          {form.saveMessage}
                        </Text>
                      )}
                      {form?.testMessage && (
                        <Text
                          className={`text-sm ${
                            form.testSuccess === false
                              ? "text-red-600"
                              : "text-green-600"
                          }`}
                        >
                          {form.testMessage}
                        </Text>
                      )}
                    </div>
                  </div>
                </Card>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
