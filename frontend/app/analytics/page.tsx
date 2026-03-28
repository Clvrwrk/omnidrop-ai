"use client";

import { useCallback, useEffect, useState } from "react";
import {
  AreaChart,
  Badge,
  BarList,
  Card,
  Metric,
  Text,
  Title,
} from "@tremor/react";
import { api, ApiError } from "@/lib/api-client";
import type {
  AnalyticsPeriod,
  KpiResponse,
  VendorSpendResponse,
} from "@/lib/types";

const periods: { label: string; value: AnalyticsPeriod }[] = [
  { label: "7 Days", value: "7d" },
  { label: "30 Days", value: "30d" },
  { label: "90 Days", value: "90d" },
  { label: "Year to Date", value: "ytd" },
];

function formatDelta(delta: number): string {
  const sign = delta >= 0 ? "+" : "";
  return `${sign}${delta.toFixed(1)}%`;
}

function formatCurrency(val: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 0,
  }).format(val);
}

export default function AnalyticsPage() {
  const [period, setPeriod] = useState<AnalyticsPeriod>("30d");
  const [kpis, setKpis] = useState<KpiResponse | null>(null);
  const [vendorSpend, setVendorSpend] = useState<VendorSpendResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    setError(null);
    try {
      const [kpiRes, spendRes] = await Promise.all([
        api.getKpis({ period }),
        api.getVendorSpend({ period, group_by: "vendor" }),
      ]);
      setKpis(kpiRes);
      setVendorSpend(spendRes);
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
    }
  }, [period]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <Title>Analytics</Title>
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

      {/* KPI Cards */}
      {kpis && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Card>
            <Text>Documents Processed</Text>
            <Metric>{kpis.volume_processed.value.toLocaleString()}</Metric>
            <Badge color={kpis.volume_processed.delta_pct >= 0 ? "green" : "red"} className="mt-2">
              {formatDelta(kpis.volume_processed.delta_pct)}
            </Badge>
          </Card>
          <Card>
            <Text>Accuracy Rate</Text>
            <Metric>{(kpis.accuracy_rate.value * 100).toFixed(1)}%</Metric>
            <Badge color={kpis.accuracy_rate.delta_pct >= 0 ? "green" : "red"} className="mt-2">
              {formatDelta(kpis.accuracy_rate.delta_pct)}
            </Badge>
          </Card>
          <Card>
            <Text>Avg Processing Time</Text>
            <Metric>{kpis.avg_processing_time_seconds.value.toFixed(1)}s</Metric>
            <Badge color={kpis.avg_processing_time_seconds.delta_pct <= 0 ? "green" : "red"} className="mt-2">
              {formatDelta(kpis.avg_processing_time_seconds.delta_pct)}
            </Badge>
          </Card>
          <Card>
            <Text>Total Invoice Value</Text>
            <Metric>{formatCurrency(kpis.total_invoice_value.value)}</Metric>
            <Badge color={kpis.total_invoice_value.delta_pct >= 0 ? "green" : "red"} className="mt-2">
              {formatDelta(kpis.total_invoice_value.delta_pct)}
            </Badge>
          </Card>
        </div>
      )}

      {/* Pending Triage */}
      {kpis && kpis.pending_triage_count > 0 && (
        <Card className="border-yellow-200 bg-yellow-50">
          <div className="flex items-center justify-between">
            <Text>Documents awaiting triage review</Text>
            <Badge color="yellow">{kpis.pending_triage_count} pending</Badge>
          </div>
        </Card>
      )}

      {/* Vendor Spend BarList + Trend */}
      {vendorSpend && (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <Card>
            <Title>Vendor Spend</Title>
            <BarList
              data={vendorSpend.items.map((v) => ({
                name: v.name,
                value: v.value,
              }))}
              color="blue"
              className="mt-4"
              valueFormatter={formatCurrency}
            />
          </Card>
          <Card>
            <Title>Spend Trend</Title>
            <AreaChart
              data={vendorSpend.trend}
              index="date"
              categories={["total"]}
              colors={["blue"]}
              yAxisWidth={60}
              valueFormatter={formatCurrency}
              className="mt-4 h-64"
            />
          </Card>
        </div>
      )}
    </div>
  );
}
