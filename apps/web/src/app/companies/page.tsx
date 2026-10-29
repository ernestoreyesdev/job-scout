import { Suspense } from "react";

import { CompanyRow } from "@/components/company-row";
import { Pager } from "@/components/pager";
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
  const { repository } = await getSignedInSource();
  const companies = await repository.listCompanies(Number((await searchParams).page) || 1);

  if (companies.total === 0) {
    return (
      <p className="mt-8 text-sm text-muted-foreground">
        No companies yet. Run a search with no company and the app finds some.
      </p>
    );
  }

  return (
    <section className="mt-8">
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
      <Pager basePath="/companies" page={companies.page} pageCount={companies.pageCount} total={companies.total} />
    </section>
  );
}
