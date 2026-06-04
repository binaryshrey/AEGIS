import { NextRequest, NextResponse } from "next/server";
import fs from "fs";
import path from "path";

export async function GET(req: NextRequest) {
  const battleId = req.nextUrl.searchParams.get("id");

  if (!battleId) {
    return NextResponse.json({ error: "Missing id" }, { status: 400 });
  }

  // Sanitize: only allow uuid-shaped ids
  if (!/^[0-9a-f-]{36}$/i.test(battleId)) {
    return NextResponse.json({ error: "Invalid id" }, { status: 400 });
  }

  const logPath = path.resolve(process.cwd(), `../data/battles/${battleId}.jsonl`);

  if (!fs.existsSync(logPath)) {
    return NextResponse.json({ error: "Log file not found" }, { status: 404 });
  }

  const content = fs.readFileSync(logPath, "utf-8");

  // Format each JSON line for readability
  const lines = content.trim().split("\n");
  const formatted = lines
    .map((line) => {
      try {
        const obj = JSON.parse(line);
        return JSON.stringify(obj, null, 2);
      } catch {
        return line;
      }
    })
    .join("\n\n---\n\n");

  return new NextResponse(formatted, {
    headers: {
      "Content-Type": "text/plain; charset=utf-8",
      "Content-Disposition": `attachment; filename="battle-logs-${battleId}.txt"`,
    },
  });
}
