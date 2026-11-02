import Link from "next/link";
import { Suspense } from "react";

import { CompanyRow } from "@/components/company-row";
import { FindCareersPages } from "@/components/find-careers-pages";
import { ImportCompanies } from "@/components/import-companies";
import { Pager } from "@/components/pager";
import { RunStatus } from "@/components/run-status";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { getSignedInSource } from "@/lib/repository";

const CHECKED = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric" });

export default function CompaniesPage({ searchParams }: PageProps<"/companies">) {
  return (
    <main className="mx-auto w-full max-w-4xl flex-1 px-6 py-10">
      <h1 className="text-2xl font-semibold tracking-tight">Companies</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Every company the app has found. Searches with no company check all of them; hide one to leave it out of your
        searches. Jobs already in your Tracker stay there.
      </p>
      <Suspense fallback={<p className="mt-8 text-sm text-muted-foreground">Loading…</p>}>
        <CompaniesData searchParams={searchParams} />
      </Suspense>
    </main>
  );
}

async function CompaniesData({ searchParams }: Pick<PageProps<"/companies">, "searchParams">) {
  const params = await searchParams;
  const search = (Array.isArray(params.q) ? params.q[0] : params.q)?.trim().slice(0, 100) ?? "";
  const { repository } = await getSignedInSource();
  const [companies, runs, withoutCareersPage] = await Promise.all([
    repository.listCompanies(Number(params.page) || 1, search),
    repository.listRuns(1),
    repository.countCompaniesWithoutCareersPage(),
  ]);
  const companyRun = runs[0]?.kind === "import" || runs[0]?.kind === "careers_pages" ? runs[0] : null;

  if (companies.total === 0 && !search) {
    return (
      <>
        <ImportCompanies />
        {companyRun && <RunStatus run={companyRun} />}
        <p className="mt-8 text-sm text-muted-foreground">
          No companies yet. Add some above, or run a search with no company and the app finds some.
        </p>
      </>
    );
  }

  return (
    <>
      <ImportCompanies />
      {companyRun && <RunStatus run={companyRun} />}
      <section className="mt-8">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <form method="get" action="/companies" className="flex flex-wrap items-center gap-3 text-sm">
            <Input name="q" defaultValue={search} placeholder="Search companies" aria-label="Search companies" className="w-64" />
            <Button type="submit" size="sm" variant="outline">
              Search
            </Button>
            {search && (
              <Link href="/companies" className="text-muted-foreground hover:text-foreground">
                Clear
              </Link>
            )}
          </form>
          {withoutCareersPage > 0 && <FindCareersPages count={withoutCareersPage} />}
        </div>
        {companies.total === 0 && <p className="text-sm text-muted-foreground">No companies match “{search}”.</p>}
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Company</TableHead>
              <TableHead className="w-28 text-right">Open jobs</TableHead>
              <TableHead className="w-36">Last checked</TableHead>
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
        <Pager
          basePath="/companies"
          page={companies.page}
          pageCount={companies.pageCount}
          total={companies.total}
          params={search ? { q: search } : {}}
        />
      </section>
    </>
  );
}
