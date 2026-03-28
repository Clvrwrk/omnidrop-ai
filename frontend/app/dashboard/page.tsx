"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  AreaChart,
  Badge,
  Card,
  Metric,
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
import type {
  Job,
  IntakeEvent,
  HealthResponse,
  UploadResponse,
} from "@/lib/types";

const statusColor: Record<string, string> = {
  queued: "gray",
  processing: "yellow",
  complete: "green",
  failed: "red",
};

export default function DashboardPage() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [events, setEvents] = useState<IntakeEvent[]>([]);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState<UploadResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const loadData = useCallback(async () => {
    try {
      const [jobsRes, eventsRes, healthRes] = await Promise.all([
        api.getJobs({ limit: 25 }),
        api.getEvents({ limit: 25 }),
        api.getHealth(),
      ]);
      setJobs(jobsRes.jobs);
      setEvents(eventsRes.events);
      setHealth(healthRes);
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  async function handleUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;

    setUploading(true);
    setUploadResult(null);
    setError(null);

    try {
      // Use the first available location — in production, user selects location
      const locRes = await api.getLocations();
      const locationId = locRes.locations[0]?.location_id;
      if (!locationId) {
        setError("No location configured. Add one in Settings first.");
        return;
      }
      const result = await api.uploadDocument(file, locationId);
      setUploadResult(result);
      await loadData();
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    const file = e.dataTransfer.files[0];
    if (!file) return;
    // Simulate a file input change
    const dt = new DataTransfer();
    dt.items.add(file);
    if (fileInputRef.current) {
      fileInputRef.current.files = dt.files;
      fileInputRef.current.dispatchEvent(new Event("change", { bubbles: true }));
    }
  }

  // Build a simple trend from events (group by date)
  const eventTrend = events.reduce<Record<string, number>>((acc, ev) => {
    const date = ev.received_at.slice(0, 10);
    acc[date] = (acc[date] ?? 0) + 1;
    return acc;
  }, {});
  const chartData = Object.entries(eventTrend)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([date, count]) => ({ date, Events: count }));

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <Title>Dashboard</Title>
        {health && (
          <Badge color={health.status === "healthy" ? "green" : health.status === "degraded" ? "yellow" : "red"}>
            System: {health.status}
          </Badge>
        )}
      </div>

      {error && (
        <Card className="border-red-200 bg-red-50">
          <Text className="text-red-700">{error}</Text>
        </Card>
      )}

      {/* Omni-Drop Upload Zone */}
      <Card>
        <Title>Omni-Drop</Title>
        <Text>Drag and drop any file to start AI processing</Text>
        <div
          onDragOver={(e) => e.preventDefault()}
          onDrop={handleDrop}
          className="mt-4 flex flex-col items-center justify-center rounded-lg border-2 border-dashed border-gray-300 p-12 text-center hover:border-blue-400 transition-colors"
        >
          <Text className="text-gray-500">
            {uploading ? "Uploading..." : "Drop files here or click to browse"}
          </Text>
          <input
            ref={fileInputRef}
            type="file"
            onChange={handleUpload}
            className="mt-4"
            accept=".pdf,.png,.jpg,.jpeg,.xlsx,.xls,.csv"
          />
        </div>
        {uploadResult && (
          <div className="mt-3">
            <Badge color="blue">Job queued: {uploadResult.job_id.slice(0, 8)}...</Badge>
          </div>
        )}
      </Card>

      {/* KPI Summary Row */}
      {health && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <Card>
            <Text>Celery Workers</Text>
            <Metric>{health.checks.celery_workers.active_count}</Metric>
          </Card>
          <Card>
            <Text>Queue Depth</Text>
            <Metric>{health.checks.celery_workers.queue_depth}</Metric>
          </Card>
          <Card>
            <Text>Supabase</Text>
            <Metric>{health.checks.supabase.latency_ms}ms</Metric>
          </Card>
        </div>
      )}

      {/* Intake Volume Chart */}
      {chartData.length > 0 && (
        <Card>
          <Title>Intake Volume</Title>
          <AreaChart
            data={chartData}
            index="date"
            categories={["Events"]}
            colors={["blue"]}
            yAxisWidth={40}
            className="mt-4 h-48"
          />
        </Card>
      )}

      {/* Recent Jobs Table */}
      <Card>
        <Title>Recent Jobs</Title>
        <Table className="mt-4">
          <TableHead>
            <TableRow>
              <TableHeaderCell>Job ID</TableHeaderCell>
              <TableHeaderCell>Location</TableHeaderCell>
              <TableHeaderCell>Type</TableHeaderCell>
              <TableHeaderCell>Status</TableHeaderCell>
              <TableHeaderCell>Created</TableHeaderCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {jobs.map((job) => (
              <TableRow key={job.job_id}>
                <TableCell className="font-mono text-xs">
                  {job.job_id.slice(0, 8)}...
                </TableCell>
                <TableCell>{job.location_name}</TableCell>
                <TableCell>{job.document_type ?? "—"}</TableCell>
                <TableCell>
                  <Badge color={statusColor[job.status] ?? "gray"}>
                    {job.status}
                  </Badge>
                </TableCell>
                <TableCell>
                  {new Date(job.created_at).toLocaleString()}
                </TableCell>
              </TableRow>
            ))}
            {jobs.length === 0 && (
              <TableRow>
                <TableCell colSpan={5} className="text-center text-gray-400">
                  No jobs yet
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </Card>

      {/* Recent Events */}
      <Card>
        <Title>Recent Intake Events</Title>
        <Table className="mt-4">
          <TableHead>
            <TableRow>
              <TableHeaderCell>Event ID</TableHeaderCell>
              <TableHeaderCell>Type</TableHeaderCell>
              <TableHeaderCell>Status</TableHeaderCell>
              <TableHeaderCell>Received</TableHeaderCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {events.map((ev) => (
              <TableRow key={ev.event_id}>
                <TableCell className="font-mono text-xs">
                  {ev.event_id.slice(0, 8)}...
                </TableCell>
                <TableCell>{ev.event_type}</TableCell>
                <TableCell>
                  <Badge
                    color={
                      ev.status === "accepted"
                        ? "green"
                        : ev.status === "rejected"
                          ? "red"
                          : "gray"
                    }
                  >
                    {ev.status}
                  </Badge>
                </TableCell>
                <TableCell>
                  {new Date(ev.received_at).toLocaleString()}
                </TableCell>
              </TableRow>
            ))}
            {events.length === 0 && (
              <TableRow>
                <TableCell colSpan={4} className="text-center text-gray-400">
                  No events yet
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </Card>
    </div>
  );
}
