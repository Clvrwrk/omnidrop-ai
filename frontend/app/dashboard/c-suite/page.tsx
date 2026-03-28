"use client";

import { useCallback, useEffect, useState } from "react";
import {
  BarList,
  Card,
  Metric,
  ProgressBar,
  Text,
  Title,
} from "@tremor/react";
import { api, ApiError } from "@/lib/api-client";
import type { AnalyticsPeriod, LeakageSummary, Organization } from "@/lib/types";

const periods: { label: string; value: AnalyticsPeriod }[] = [
  { label: "7 Days", value: "7d" },
  { label: "30 Days", value: "30d" },
  { label: "90 Days", value: "90d" },
  { label: "Year to Date", value: "ytd" },
];

function formatCurrency(val: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 0,
  }).format(val);
}

function usageBarColor(used: number, max: number): string {
  const pct = max > 0 ? (used / max) * 100 : 0;
  if (pct >= 95) return "red";
  if (pct >= 80) return "amber";
  return "gray";
}

export default function CSuitePage() {
  const [period, setPeriod] = useState<AnalyticsPeriod>("30d");
  const [leakage, setLeakage] = useState<LeakageSummary | null>(null);
  const [org, setOrg] = useState<Organization | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const loadData = useCallback(async () => {
    setError(null);
    setLoading(true);
    try {
      const [leakageRes, orgRes] = await Promise.all([
        api.getLeakageSummary({ period }),
        api.getOrganization(),
      ]);
      setLeakage(leakageRes);
      setOrg(orgRes);
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [period]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const locationBarData = (leakage?.by_location ?? [])
    .slice()
    .sort((a, b) => b.total_leakage - a.total_leakage)
    .map((l) => ({ name: l.location_name, value: l.total_leakage }));

  const vendorBarData = (leakage?.by_vendor ?? [])
    .slice()
    .sort((a, b) => b.total_leakage - a.total_leakage)
    .map((v) => ({ name: v.vendor_name, value: v.total_leakage }));

  const docUsed = org?.documents_processed ?? 0;
  const docMax = org?.max_documents ?? 500;
  const docPct = docMax > 0 ? Math.round((docUsed / docMax) * 100) : 0;

  return (
    <div className="space-y-6">
      {/* Header + period selector */}
      <div className="flex items-center justify-between">
        <div>
          <Title>Revenue Recovery</Title>
          <Text className="mt-1 text-gray-500">
            Cross-branch leakage findings — {org?.name ?? "Loading..."}
          </Text>
        </div>
        <div className="flex gap-2">
          {periods.map((p) => (
            <button
              key={p.value}
              onClick={() => setPeriod(p.value)}
              className={`rounded px-3 py-1 text-sm ${
                period === p.value
                  ? "bg-blue-600 text-white"
                  : "bg-gray-100 text-gray-600 hover:bg-gray-200"
              }`}
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>

      {error && (
        <Card className="border-red-200 bg-red-50">
          <Text className="text-red-700">{error}</Text>
        </Card>
      )}

      {/* Freemium usage bar */}
      {org?.plan_tier === "free" && (
        <Card className="border-amber-200 bg-amber-50">
          <div className="flex items-center justify-between mb-2">
            <Text className="text-sm font-medium text-gray-700">
              {docUsed.toLocaleString()} / {docMax.toLocaleString()} documents used
            </Text>
            <a
              href="/settings"
              className="text-xs font-medium text-blue-600 hover:text-blue-800"
            >
              Upgrade for unlimited
            </a>
          </div>
          <ProgressBar
            value={docPct}
            color={usageBarColor(docUsed, docMax)}
            className="mt-1"
          />
        </Card>
      )}

      {/* Hero metric row */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <Card>
          <Text>Total Revenue Leakage</Text>
          <Metric>
            {loading ? "—" : formatCurrency(leakage?.total_leakage ?? 0)}
          </Metric>
          <Text className="mt-1 text-xs text-gray-400">
            {leakage?.finding_count ?? 0} finding
            {(leakage?.finding_count ?? 0) !== 1 ? "s" : ""} this period
          </Text>
        </Card>

        <Card>
          <Text>Documents Processed</Text>
          <Metric>
            {loading ? "—" : (org?.documents_processed ?? 0).toLocaleString()}
          </Metric>
          {org?.plan_tier === "free" && (
            <div className="mt-2">
              <ProgressBar
                value={docPct}
                color={usageBarColor(docUsed, docMax)}
                className="mt-1"
              />
              <Text className="mt-1 text-xs text-gray-400">
                {docPct}% of {docMax.toLocaleString()} free-tier limit
              </Text>
            </div>
          )}
        </Card>

        <Card>
          <Text>Active Locations</Text>
          <Metric>
            {loading
              ? "—"
              : (leakage?.by_location ?? []).length.toLocaleString()}
          </Metric>
          <Text className="mt-1 text-xs text-gray-400">
            Branches with findings this period
          </Text>
        </Card>
      </div>

      {/* Leakage by Location + Vendor */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <Title>Leakage by Location</Title>
          <Text className="mt-1 text-xs text-gray-500">
            Branches paying above contracted rates this period
          </Text>
          {locationBarData.length > 0 ? (
            <BarList
              data={locationBarData}
              color="red"
              valueFormatter={formatCurrency}
              className="mt-4"
            />
          ) : (
            <Text className="mt-6 text-center text-gray-400">
              {loading ? "Loading..." : "No leakage findings for this period."}
            </Text>
          )}
        </Card>

        <Card>
          <Title>Leakage by Vendor</Title>
          <Text className="mt-1 text-xs text-gray-500">
            Vendors with highest overcharge amounts this period
          </Text>
          {vendorBarData.length > 0 ? (
            <BarList
              data={vendorBarData}
              color="orange"
              valueFormatter={formatCurrency}
              className="mt-4"
            />
          ) : (
            <Text className="mt-6 text-center text-gray-400">
              {loading ? "Loading..." : "No vendor leakage data for this period."}
            </Text>
          )}
        </Card>
      </div>
    </div>
  );
}
