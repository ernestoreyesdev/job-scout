import { ArrowDown, ArrowUp, Search } from "lucide-react";
import Link from "next/link";
import { Suspense } from "react";

import { CompanyRow } from "@/components/company-row";
import { ImportCompanies } from "@/components/import-companies";
import { Pager } from "@/components/pager";
import { RunStatus } from "@/components/run-status";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { COMPANY_SORTS, type CompanySort } from "@/lib/db";
import { jobListHref } from "@/lib/job-query";
import { getSignedInSource } from "@/lib/repository";

const CHECKED = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric" });

export default function CompaniesPage({ searchParams }: PageProps<"/companies">) {
  return (
    <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-8 sm:px-6 sm:py-10">
      <h1 className="text-2xl font-semibold tracking-tight">Companies</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Every company the app has found. Searches with no company check all of them; hide one to leave it out of your
        searches. Jobs already in your Tracker stay there.
      </p>
      <Suspense fallback={<div className="mt-8 h-64 animate-pulse rounded-xl border bg-card" />}>
        <CompaniesData searchParams={searchParams} />
      </Suspense>
    </main>
  );
}

async function CompaniesData({ searchParams }: Pick<PageProps<"/companies">, "searchParams">) {
  const params = await searchParams;
  const first = (value: string | string[] | undefined) => (Array.isArray(value) ? value[0] : value)?.trim() ?? "";
  const search = first(params.q).slice(0, 100);
  const sortValue = first(params.sort);
  const sort: CompanySort = sortValue in COMPANY_SORTS ? (sortValue as CompanySort) : "jobs";
  const order = first(params.order) === "asc" || first(params.order) === "desc" ? first(params.order) : COMPANY_SORTS[sort];
  const listParams: Record<string, string> = {
    ...(search && { q: search }),
    ...(sort !== "jobs" && { sort }),
    ...(order !== COMPANY_SORTS[sort] && { order }),
  };
  const { repository } = await getSignedInSource();
  const [companies, runs] = await Promise.all([
    repository.listCompanies(Number(params.page) || 1, search, sort, order === "asc"),
    repository.listRuns(1),
  ]);
  const importRun = runs[0]?.kind === "import" ? runs[0] : null;

  if (companies.total === 0 && !search) {
    return (
      <>
        <ImportCompanies />
        {importRun && <RunStatus run={importRun} />}
        <div className="mt-8 rounded-xl border border-dashed px-6 py-12 text-center">
          <p className="font-medium">No companies yet</p>
          <p className="mt-1 text-sm text-muted-foreground">
            Add some above, or run a search with no company and the app finds some.
          </p>
        </div>
      </>
    );
  }

  return (
    <>
      <ImportCompanies />
      {importRun && <RunStatus run={importRun} />}
      <section className="mt-6">
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border bg-card p-3 shadow-xs">
          <span className="pl-1 text-sm font-medium">
            {companies.total.toLocaleString()} {companies.total === 1 ? "company" : "companies"}
          </span>
          <form method="get" action="/companies" className="flex flex-wrap items-center gap-2 text-sm">
            <div className="relative">
              <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                name="q"
                defaultValue={search}
                placeholder="Search companies"
                aria-label="Search companies"
                className="h-8 w-64 rounded-full pl-9"
              />
            </div>
            {listParams.sort && <input type="hidden" name="sort" value={listParams.sort} />}
            {listParams.order && <input type="hidden" name="order" value={listParams.order} />}
            <Button type="submit" size="sm" variant="outline" className="rounded-full">
              Search
            </Button>
            {search && (
              <Link href={jobListHref("/companies", { ...listParams, q: "" })} className="text-muted-foreground hover:text-foreground">
                Clear
              </Link>
            )}
          </form>
        </div>
        {companies.total === 0 && <p className="mt-4 text-sm text-muted-foreground">No companies match “{search}”.</p>}
        <div className="mt-3 rounded-xl border bg-card px-2 shadow-xs">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>
                  <SortLink column="name" label="Company" sort={sort} order={order} params={listParams} />
                </TableHead>
                <TableHead className="w-28 text-right">
                  <SortLink column="jobs" label="Open jobs" sort={sort} order={order} params={listParams} />
                </TableHead>
                <TableHead className="w-36">
                  <SortLink column="checked" label="Last checked" sort={sort} order={order} params={listParams} />
                </TableHead>
                <TableHead className="w-24">
                  <span className="sr-only">Actions</span>
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {companies.items.map((company) => (
                <CompanyRow key={company.id} company={company} checked={CHECKED.format(new Date(company.checked_at))} />
              ))}
            </TableBody>
          </Table>
        </div>
        <Pager
          basePath="/companies"
          page={companies.page}
          pageCount={companies.pageCount}
          total={companies.total}
          params={listParams}
        />
      </section>
    </>
  );
}

/** A column header that sorts by its column, or flips the direction when it already does; the arrow shows the active one. */
function SortLink({
  column,
  label,
  sort,
  order,
  params,
}: {
  column: CompanySort;
  label: string;
  sort: CompanySort;
  order: string;
  params: Record<string, string>;
}) {
  const active = sort === column;
  const next = active ? (order === "asc" ? "desc" : "asc") : COMPANY_SORTS[column];
  const href = jobListHref("/companies", {
    ...params,
    sort: column === "jobs" ? "" : column,
    order: next === COMPANY_SORTS[column] ? "" : next,
  });
  const Arrow = order === "asc" ? ArrowUp : ArrowDown;
  return (
    <Link href={href} className="inline-flex items-center gap-1 hover:text-foreground" aria-label={`Sort by ${label.toLowerCase()}`}>
      {label}
      {active && <Arrow className="size-3.5" />}
    </Link>
  );
}
