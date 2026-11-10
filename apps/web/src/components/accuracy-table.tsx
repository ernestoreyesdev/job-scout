import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { DEFAULT_CUT, type CutAccuracy } from "@/lib/insights";
import { cn } from "@/lib/utils";

const PERCENT = new Intl.NumberFormat("en-US", { style: "percent", maximumFractionDigits: 0 });

/** Precision and recall of each score cut against good or bad labels; the default cut is highlighted. */
export function AccuracyTable({ rows }: { rows: CutAccuracy[] }) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Score at or above</TableHead>
          <TableHead className="text-right">Precision</TableHead>
          <TableHead className="text-right">Recall</TableHead>
          <TableHead className="text-right">Good above</TableHead>
          <TableHead className="text-right">Bad above</TableHead>
          <TableHead className="text-right">Good below</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((row) => (
          <TableRow key={row.cut} className={cn(row.cut === DEFAULT_CUT && "bg-muted/50 font-medium")}>
            <TableCell>{row.cut}</TableCell>
            <TableCell className="text-right tabular-nums">{row.precision === null ? "–" : PERCENT.format(row.precision)}</TableCell>
            <TableCell className="text-right tabular-nums">{row.recall === null ? "–" : PERCENT.format(row.recall)}</TableCell>
            <TableCell className="text-right tabular-nums">{row.truePositives}</TableCell>
            <TableCell className="text-right tabular-nums">{row.falsePositives}</TableCell>
            <TableCell className="text-right tabular-nums">{row.falseNegatives}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
