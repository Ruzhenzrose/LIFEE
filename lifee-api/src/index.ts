export interface Env {
	GEMINI_API_KEY: string;
  }
  
  const corsHeaders: Record<string, string> = {
	"Access-Control-Allow-Origin": "*",
	"Access-Control-Allow-Methods": "POST, OPTIONS",
	"Access-Control-Allow-Headers": "Content-Type",
  };
  
  type Persona = {
	id: string;
	name: string;
  };
  
  type Body = {
	situation?: string;
	question?: string;
	userInput?: string; // 前端每一轮用户输入（可选）
	personas?: Persona[];
  };
  
  function extractJsonObject(text: string): any | null {
	// 尝试从模型输出中“抠出”第一个完整 JSON 对象
	const first = text.indexOf("{");
	const last = text.lastIndexOf("}");
	if (first === -1 || last === -1 || last <= first) return null;
  
	const maybe = text.slice(first, last + 1).trim();
	try {
	  return JSON.parse(maybe);
	} catch {
	  return null;
	}
  }
  
  export default {
	async fetch(request: Request, env: Env): Promise<Response> {
	  // ---- CORS preflight ----
	  if (request.method === "OPTIONS") {
		return new Response(null, { headers: corsHeaders });
	  }
  
	  const url = new URL(request.url);
  
	  // 只允许 POST /decision
	  if (url.pathname !== "/decision" || request.method !== "POST") {
		return new Response("Not Found", { status: 404, headers: corsHeaders });
	  }
  
	  if (!env.GEMINI_API_KEY) {
		return new Response(JSON.stringify({ error: "Missing GEMINI_API_KEY" }), {
		  status: 500,
		  headers: { ...corsHeaders, "Content-Type": "application/json" },
		});
	  }
  
	  try {
		const body = (await request.json()) as Body;
  
		const situation =
		  body.situation?.trim() ||
		  body.question?.trim() ||
		  "Start the internal debate.";
  
		const personas: Persona[] =
		  body.personas && body.personas.length > 0
			? body.personas
			: [
				{ id: "serene", name: "SERENE" },
				{ id: "architect", name: "The Architect" },
				{ id: "rebel", name: "The Outlier" },
				{ id: "caretaker", name: "The Soft Anchor" },
			  ];
  
		const userInput = body.userInput?.trim() || "";
  
		// ✅ 核心：把 system prompt 直接塞进 user 内容里（v1 最稳，不用 systemInstruction 字段）
		const prompt = `
  You are NOT an assistant.
  You are NOT a coach.
  You are NOT a therapist.
  You are NOT a summarizer.
  
  You are an internal debate engine.
  
  Your task is to simulate an internal argument between multiple personas.
  Each persona speaks independently.
  They may interrupt, contradict, or challenge each other.
  
  Context:
  ${situation}
  
  Personas:
  ${personas.map((p) => `- ${p.id}: ${p.name}`).join("\n")}
  
  Rules (ABSOLUTE):
  - DO NOT give advice
  - DO NOT summarize
  - DO NOT conclude
  - DO NOT explain the debate
  - DO NOT address the user directly
  - DO NOT use markdown
  - DO NOT add meta commentary
  
  You MUST output JSON ONLY in the following format:
  
  {
	"messages": [
	  { "personaId": "serene", "text": "..." },
	  { "personaId": "architect", "text": "..." },
	  { "personaId": "rebel", "text": "..." }
	],
	"options": ["...", "...", "..."]
  }
  
  Each persona should speak ONCE in this round.
  The tone should reflect genuine internal conflict.
  
  Round input (what the user just said, can be empty on first round):
  ${userInput ? userInput : "(no new user input — begin the debate)"}
  
  Now produce the JSON ONLY:
  `.trim();
  
		// ---- Gemini v1 call ----
		const geminiRes = await fetch(
		  `https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash:generateContent?key=${env.GEMINI_API_KEY}`,
		  {
			method: "POST",
			headers: { "Content-Type": "application/json" },
			body: JSON.stringify({
			  contents: [
				{
				  role: "user",
				  parts: [{ text: prompt }],
				},
			  ],
			}),
		  }
		);
  
		const geminiData: any = await geminiRes.json();
  
		if (!geminiRes.ok) {
		  return new Response(
			JSON.stringify({
			  error: "Gemini API error",
			  status: geminiRes.status,
			  details: geminiData,
			}),
			{
			  status: 502,
			  headers: { ...corsHeaders, "Content-Type": "application/json" },
			}
		  );
		}
  
		const rawText =
		  geminiData?.candidates?.[0]?.content?.parts
			?.map((p: any) => p?.text)
			.filter(Boolean)
			.join("") || "";
  
		// ---- 尽量保证返回一定是 JSON ----
		const parsed = extractJsonObject(rawText);
		if (!parsed || !parsed.messages || !parsed.options) {
		  return new Response(
			JSON.stringify({
			  error: "Model did not return valid debate JSON",
			  raw: rawText,
			}),
			{
			  status: 502,
			  headers: { ...corsHeaders, "Content-Type": "application/json" },
			}
		  );
		}
  
		return new Response(JSON.stringify(parsed), {
		  headers: { ...corsHeaders, "Content-Type": "application/json" },
		});
	  } catch (err: any) {
		return new Response(
		  JSON.stringify({
			error: "Invalid request",
			details: String(err?.message || err),
		  }),
		  {
			status: 400,
			headers: { ...corsHeaders, "Content-Type": "application/json" },
		  }
		);
	  }
	},
  };