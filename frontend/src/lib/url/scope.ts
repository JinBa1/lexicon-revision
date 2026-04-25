import type { FilterCondition } from "@/lib/api/types";

import { serializeFiltersToSearchParams } from "./filters";

type CollectionHrefOptions = {
  query?: string;
};

export function buildCollectionHref(collection: string, opts: CollectionHrefOptions = {}): string {
  const base = `/c/${encodeURIComponent(collection)}`;
  const query = opts.query?.trim() ?? "";

  if (query === "") {
    return base;
  }

  const searchParams = new URLSearchParams({ q: query });
  return `${base}?${searchParams.toString()}`;
}

type PageHrefOptions = {
  collection: string;
  query: string;
  filters: readonly FilterCondition[];
};

export function buildQuestionsHref(opts: PageHrefOptions): string {
  return buildPageHref("questions", opts);
}

export function buildAnswerHref(opts: PageHrefOptions): string {
  return buildPageHref("answer", opts);
}

function buildPageHref(page: "questions" | "answer", opts: PageHrefOptions): string {
  const base = `/c/${encodeURIComponent(opts.collection)}/${page}`;
  const filterParams = serializeFiltersToSearchParams(opts.filters);
  const searchParams = new URLSearchParams();

  if (opts.query !== "") {
    searchParams.set("q", opts.query);
  }

  for (const filter of filterParams.getAll("filter")) {
    searchParams.append("filter", filter);
  }

  const qs = searchParams.toString();
  return qs === "" ? base : `${base}?${qs}`;
}

export function buildSourceHref(collection: string, chunkId: string): string {
  return `/c/${encodeURIComponent(collection)}/source/${encodeURIComponent(chunkId)}`;
}

export function buildUnlockHref(collection: string, returnTo?: string): string {
  const base = `/unlock/${encodeURIComponent(collection)}`;

  if (!returnTo) {
    return base;
  }

  const params = new URLSearchParams({ returnTo });
  return `${base}?${params.toString()}`;
}

export function parseQueryFromSearchParams(params: URLSearchParams): string {
  return params.get("q") ?? "";
}
