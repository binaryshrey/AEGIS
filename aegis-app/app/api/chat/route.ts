import { NextRequest, NextResponse } from "next/server";
import fs from "fs";
import path from "path";

const OPENROUTER_API_KEY = process.env.OPENROUTER_API_KEY ?? "";
const MODEL = "openai/gpt-4.1";

// Load README once at cold-start
let knowledgeBase = "";
try {
  knowledgeBase = fs.readFileSync(
    path.resolve(process.cwd(), "../README.md"),
    "utf-8",
  );
} catch {
  // fallback: try from project root
  try {
    knowledgeBase = fs.readFileSync(
      path.resolve(process.cwd(), "README.md"),
      "utf-8",
    );
  } catch {
    knowledgeBase = "Knowledge base not found.";
  }
}

const SYSTEM_PROMPT = `You are AEGIS AI, an expert assistant for the AEGIS (Adaptive Exploitation & Game Intelligence System) project. You answer questions about battle strategies, agent architecture, targeting algorithms, opponent classification, the trust system, Thompson Sampling bandits, placement logic, memory and feedback systems, performance metrics, the dashboard, and all other aspects of the AEGIS system.

Use the following knowledge base to answer questions accurately. If the answer is not in the knowledge base, say so honestly. Keep answers concise but thorough. Do not use emojis.

Important: For any questions related to observability, logging, or downloading battle data, always mention that users can download battle logs for further analysis by clicking the three dots icon and selecting "Download logs" from the Battle History table.

--- KNOWLEDGE BASE ---
${knowledgeBase}
--- END KNOWLEDGE BASE ---`;

export async function POST(req: NextRequest) {
  try {
    const { messages } = await req.json();

    if (!OPENROUTER_API_KEY) {
      return NextResponse.json(
        { error: "OPENROUTER_API_KEY is not configured" },
        { status: 500 },
      );
    }

    const res = await fetch("https://openrouter.ai/api/v1/chat/completions", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${OPENROUTER_API_KEY}`,
        "Content-Type": "application/json",
        "HTTP-Referer": "https://aegis-starsling.vercel.app",
        "X-Title": "AEGIS AI",
      },
      body: JSON.stringify({
        model: MODEL,
        messages: [{ role: "system", content: SYSTEM_PROMPT }, ...messages],
        max_tokens: 1024,
        temperature: 0.4,
      }),
    });

    if (!res.ok) {
      const text = await res.text();
      return NextResponse.json(
        { error: `OpenRouter error: ${res.status} ${text}` },
        { status: 502 },
      );
    }

    const data = await res.json();
    const reply = data.choices?.[0]?.message?.content ?? "No response.";
    return NextResponse.json({ reply });
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : "Unknown error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
