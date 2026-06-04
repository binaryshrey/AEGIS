import { NextRequest, NextResponse } from "next/server";
import { spawn } from "child_process";
import path from "path";
import fs from "fs";

export async function POST(req: NextRequest) {
  const { battleId } = await req.json();

  if (!battleId) {
    return NextResponse.json({ error: "battleId is required" }, { status: 400 });
  }

  const engineDir = path.resolve(process.cwd(), "..");
  const serverUrl = process.env.ENGINE_SERVER_URL || "http://localhost:5001";
  const competition = process.env.ENGINE_COMPETITION || "mock-competition";
  const logDir = path.join(engineDir, "data", "battles");
  const logFile = path.join(logDir, `${battleId}.jsonl`);

  // Ensure log directory exists
  fs.mkdirSync(logDir, { recursive: true });

  const child = spawn(
    "python",
    [
      "-m", "engine.main",
      "--url", serverUrl,
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
