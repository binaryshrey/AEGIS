import { NextRequest } from "next/server";
import path from "path";
import fs from "fs";

export const dynamic = "force-dynamic";

export async function GET(req: NextRequest) {
  const battleId = req.nextUrl.searchParams.get("id");

  if (!battleId) {
    return new Response("Missing id", { status: 400 });
  }

  // Sanitize battleId to prevent path traversal
  if (!/^[a-f0-9-]+$/i.test(battleId)) {
    return new Response("Invalid id", { status: 400 });
  }

  const engineDir = path.resolve(process.cwd(), "..");
  const logFile = path.join(engineDir, "data", "battles", `${battleId}.jsonl`);

  const encoder = new TextEncoder();
  let cancelled = false;

  const stream = new ReadableStream({
    async start(controller) {
      let offset = 0;
      let doneEventSeen = false;
      let waitingTicks = 0;
      const MAX_WAIT = 300; // ~5 minutes at 1s intervals

      const poll = () => {
        if (cancelled || doneEventSeen) {
          controller.close();
          return;
        }

        try {
          if (!fs.existsSync(logFile)) {
            waitingTicks++;
            if (waitingTicks > MAX_WAIT) {
              controller.enqueue(
                encoder.encode(
                  `data: ${JSON.stringify({ event: "error", data: { message: "Log file never appeared" } })}\n\n`
                )
              );
              controller.close();
              return;
            }
            setTimeout(poll, 1000);
            return;
          }

          const stat = fs.statSync(logFile);
          if (stat.size > offset) {
            const fd = fs.openSync(logFile, "r");
            const buf = Buffer.alloc(stat.size - offset);
            fs.readSync(fd, buf, 0, buf.length, offset);
            fs.closeSync(fd);
            offset = stat.size;

            const chunk = buf.toString("utf-8");
            const lines = chunk.split("\n").filter((l) => l.trim());

            for (const line of lines) {
              try {
                const parsed = JSON.parse(line);
                controller.enqueue(
                  encoder.encode(`data: ${JSON.stringify(parsed)}\n\n`)
                );
                if (parsed.event === "run_ended") {
                  doneEventSeen = true;
                }
              } catch {
                // Skip malformed lines
              }
            }

            if (doneEventSeen) {
              controller.close();
              return;
            }
          }

          setTimeout(poll, 500);
        } catch (err) {
          if (!cancelled) {
            controller.enqueue(
              encoder.encode(
                `data: ${JSON.stringify({ event: "error", data: { message: String(err) } })}\n\n`
              )
            );
            controller.close();
          }
        }
      };

      poll();
    },
    cancel() {
      cancelled = true;
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
    },
  });
}
