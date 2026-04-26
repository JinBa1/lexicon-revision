import type { TableBlock as TableBlockType } from "@/lib/api/types";

export function TableBlock({ block }: { block: TableBlockType }) {
  return (
    <div className="overflow-x-auto">
      <table>
        <tbody>
          {block.rows.map((row, rowIndex) => (
            <tr key={rowIndex}>
              {row.map((cell, cellIndex) => (
                <td key={cellIndex}>{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
