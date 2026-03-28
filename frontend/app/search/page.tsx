"use client";

import { useState } from "react";
import { Badge, Card, Text, Title } from "@tremor/react";
import { api, ApiError } from "@/lib/api-client";
import type { SearchResult } from "@/lib/types";

export default function SearchPage() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [searched, setSearched] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    if (!query.trim()) return;

    setSearching(true);
    setError(null);
    try {
      const res = await api.search(query.trim());
      setResults(res.results);
      setSearched(true);
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
    } finally {
      setSearching(false);
    }
  }

  return (
    <div className="space-y-6">
      <Title>Document Search</Title>
      <Text>Semantic search across all ingested documents using AI</Text>

      {/* Search Input */}
      <form onSubmit={handleSearch} className="flex gap-3">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="e.g. What is the warranty period for Timberline shingles?"
          className="flex-1 rounded border border-gray-300 px-4 py-2 text-sm focus:border-blue-500 focus:outline-none"
        />
        <button
          type="submit"
          disabled={searching || !query.trim()}
          className="rounded bg-blue-600 px-6 py-2 text-sm text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {searching ? "Searching..." : "Search"}
        </button>
      </form>

      {error && (
        <Card className="border-red-200 bg-red-50">
          <Text className="text-red-700">{error}</Text>
        </Card>
      )}

      {/* Results */}
      {searched && results.length === 0 && (
        <Card>
          <Text className="text-center text-gray-400">
            No results found for &ldquo;{query}&rdquo;
          </Text>
        </Card>
      )}

      <div className="space-y-4">
        {results.map((result) => (
          <Card key={`${result.document_id}-${result.chunk_text.slice(0, 20)}`}>
            <div className="flex items-start justify-between">
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <Text className="font-semibold">{result.file_name}</Text>
                  <Badge color="blue">{result.document_type}</Badge>
                  <Badge color="gray">{result.location_name}</Badge>
                </div>
                <p className="mt-2 text-sm text-gray-700 leading-relaxed">
                  {result.chunk_text}
                </p>
                <Text className="mt-2 text-xs text-gray-400">
                  {new Date(result.created_at).toLocaleDateString()}
                </Text>
              </div>
              <div className="ml-4 text-right">
                <Badge
                  color={
                    result.similarity_score > 0.8
                      ? "green"
                      : result.similarity_score > 0.6
                        ? "yellow"
                        : "gray"
                  }
                >
                  {(result.similarity_score * 100).toFixed(0)}% match
                </Badge>
              </div>
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}
