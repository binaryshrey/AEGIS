import { NextRequest, NextResponse } from "next/server";
import fs from "fs";
import path from "path";

const ENGINE_SERVER_URL = process.env.ENGINE_SERVER_URL || "http://localhost:5001";
const isLocal = ENGINE_SERVER_URL.includes("localhost");

export async function GET(req: NextRequest) {
  const battleId = req.nextUrl.searchParams.get("id");

  if (!battleId) {
    return NextResponse.json({ error: "Missing id" }, { status: 400 });
  }

  if (!/^[0-9a-f-]{36}$/i.test(battleId)) {
    return NextResponse.json({ error: "Invalid id" }, { status: 400 });
  }

  // Production: proxy from Render backend
  if (!isLocal) {
    const res = await fetch(`${ENGINE_SERVER_URL}/engine/download?id=${battleId}`);
    if (!res.ok) {
      return NextResponse.json({ error: "Log file not found" }, { status: res.status });
    }
    const text = await res.text();
    return new NextResponse(text, {
      headers: {
        "Content-Type": "text/plain; charset=utf-8",
        "Content-Disposition": `attachment; filename="battle-logs-${battleId}.txt"`,
      },
    });
  }

  // Local dev: read file directly
  const logPath = path.resolve(process.cwd(), `../data/battles/${battleId}.jsonl`);

  if (!fs.existsSync(logPath)) {
    return NextResponse.json({ error: "Log file not found" }, { status: 404 });
  }

  const content = fs.readFileSync(logPath, "utf-8");

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
