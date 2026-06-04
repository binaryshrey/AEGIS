import { NextRequest, NextResponse } from "next/server";
import { spawn } from "child_process";
import path from "path";
import fs from "fs";

const ENGINE_SERVER_URL = process.env.ENGINE_SERVER_URL || "http://localhost:5001";
const isLocal = ENGINE_SERVER_URL.includes("localhost");

export async function POST(req: NextRequest) {
  const { battleId } = await req.json();

  if (!battleId) {
    return NextResponse.json({ error: "battleId is required" }, { status: 400 });
  }

  // Production: proxy to Render backend
  if (!isLocal) {
    const res = await fetch(`${ENGINE_SERVER_URL}/engine/start`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ battleId }),
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  }

  // Local dev: spawn subprocess directly
  const engineDir = path.resolve(process.cwd(), "..");
  const competition = process.env.ENGINE_COMPETITION || "mock-competition";
  const logDir = path.join(engineDir, "data", "battles");
  const logFile = path.join(logDir, `${battleId}.jsonl`);

  fs.mkdirSync(logDir, { recursive: true });

  const child = spawn(
    "python",
    [
      "-m", "engine.main",
      "--url", ENGINE_SERVER_URL,
      "--competition", competition,
      "--rounds", "1",
      "--battle-id", battleId,
      "--log", logFile,
    ],
    {
      cwd: engineDir,
      detached: true,
      stdio: "ignore",
    }
  );

  child.unref();

  return NextResponse.json({ ok: true, battleId, pid: child.pid });
}
