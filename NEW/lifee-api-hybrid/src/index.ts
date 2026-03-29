export interface Env {
	GEMINI_API_KEY: string;
	SUPABASE_URL?: string;
	SUPABASE_SERVICE_ROLE_KEY?: string;
	SUPABASE_HYBRID_RPC?: string; // default: hybrid_knowledge_search
  }
  
  const corsHeaders: Record<string, string> = {
	"Access-Control-Allow-Origin": "*",
	"Access-Control-Allow-Methods": "POST, OPTIONS",
	"Access-Control-Allow-Headers": "Content-Type",
  };
  
  type Persona = {
	id: string;
	name: string;
	prompt?: string | { en: string; zh: string }; // persona-specific style/behavior instruction (optional)
	knowledge?: string; // optional grounding notes passed from client (e.g. markdown)
  };
  
  type Body = {
	situation?: string;
	question?: string;
	userInput?: string; // 前端每一轮用户输入（可选）
	personas?: Persona[];
	birthDate?: string; // YYYY-MM-DD (Gregorian)
  };

  type LifeSimDeepenRequest = {
	situation?: string;
	landingPeriods?: string[];
  };

  type LifeSimClarifyRequest = {
	situation?: string;
	landingPeriods?: string[];
  };

  type LifeSimAnswers = {
	value_priority?: string;
	risk_preference?: string;
	time_horizon?: string;
	constraints?: string;
	[key: string]: string | undefined;
  };

  type LifeSimRoutesRequest = {
	situation?: string;
	landingPeriods?: string[];
	answers?: LifeSimAnswers;
  };

  type LifeSimRefineRequest = {
	situation?: string;
	landingPeriods?: string[];
	answers?: LifeSimAnswers;
	selectedPath?: unknown;
	refinePrompt?: string;
  };

  type LifeSimConclusionRequest = {
	situation?: string;
	landingPeriods?: string[];
	answers?: LifeSimAnswers;
	selectedPath?: unknown;
	refinementNotes?: string[];
  };

  type LifeSimQuestion = {
	id: string;
	label: string;
	question: string;
	placeholder: string;
	kind: "text" | "single";
	options?: string[];
  };

  type LifeSimTimelinePoint = {
	phase: string;
	focus: string;
	risk: string;
	signal: string;
  };

  type LifeSimPath = {
	id: string;
	name: string;
	tagline: string;
	narrative: string;
	timeline: LifeSimTimelinePoint[];
	scores: {
	  growth: number;
	  stability: number;
	  happiness: number;
	  risk: number;
	  feasibility: number;
	};
	pros: string[];
	cons: string[];
	first_action: string;
  };

  type LifeSimClarifyResponse = {
	needs_clarification: boolean;
	reason: string;
	question: string;
	options: string[];
  };

  type HybridSearchRow = {
	chunk_text?: string;
	text?: string;
	source?: string;
	score?: number;
	vector_score?: number;
	keyword_score?: number;
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

  function sseEncode(event: string, data: unknown): Uint8Array {
	const payload = typeof data === "string" ? data : JSON.stringify(data);
	const chunk = `event: ${event}\ndata: ${payload}\n\n`;
	return new TextEncoder().encode(chunk);
  }

  function normalizeGeminiText(geminiData: any): string {
	return (
	  geminiData?.candidates?.[0]?.content?.parts
		?.map((p: any) => p?.text)
		.filter(Boolean)
		.join("") || ""
	).trim();
  }

  async function callGeminiText(env: Env, prompt: string): Promise<{ ok: true; text: string } | { ok: false; status: number; details: any }> {
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
	  return { ok: false, status: geminiRes.status, details: geminiData };
	}

	return { ok: true, text: normalizeGeminiText(geminiData) };
  }

  async function callGeminiEmbedding(env: Env, text: string): Promise<number[] | null> {
	try {
	  const res = await fetch(
		`https://generativelanguage.googleapis.com/v1beta/models/text-embedding-004:embedContent?key=${env.GEMINI_API_KEY}`,
		{
		  method: "POST",
		  headers: { "Content-Type": "application/json" },
		  body: JSON.stringify({
			model: "models/text-embedding-004",
			content: {
			  parts: [{ text }],
			},
		  }),
		}
	  );
	  const data: any = await res.json();
	  if (!res.ok) return null;
	  const values = data?.embedding?.values;
	  if (!Array.isArray(values) || !values.length) return null;
	  return values.map((v: any) => Number(v)).filter((v: number) => Number.isFinite(v));
	} catch {
	  return null;
	}
  }

  function hasHybridConfig(env: Env): boolean {
	return !!(env.SUPABASE_URL && env.SUPABASE_SERVICE_ROLE_KEY);
  }

  async function fetchHybridRows(
	env: Env,
	{
	  queryText,
	  personaId,
	  queryEmbedding,
	  matchCount = 4,
	  vectorWeight = 0.7,
	  keywordWeight = 0.3,
	}: {
	  queryText: string;
	  personaId: string;
	  queryEmbedding?: number[] | null;
	  matchCount?: number;
	  vectorWeight?: number;
	  keywordWeight?: number;
	}
  ): Promise<HybridSearchRow[]> {
	if (!hasHybridConfig(env)) return [];
	const rpc = (env.SUPABASE_HYBRID_RPC || "hybrid_knowledge_search").trim();
	const url = `${env.SUPABASE_URL}/rest/v1/rpc/${rpc}`;
	const hasEmbedding = Array.isArray(queryEmbedding) && queryEmbedding.length > 0;
	const embeddingLiteral = hasEmbedding ? `[${queryEmbedding.map((v) => Number(v).toString()).join(",")}]` : null;
	const vw = hasEmbedding ? vectorWeight : 0;
	const kw = hasEmbedding ? keywordWeight : 1;
	try {
	  const res = await fetch(url, {
		method: "POST",
		headers: {
		  "Content-Type": "application/json",
		  apikey: env.SUPABASE_SERVICE_ROLE_KEY as string,
		  Authorization: `Bearer ${env.SUPABASE_SERVICE_ROLE_KEY}`,
		  Prefer: "return=representation",
		},
		body: JSON.stringify({
		  p_query_text: queryText,
		  p_query_embedding: embeddingLiteral,
		  p_persona_id: personaId,
		  p_match_count: matchCount,
		  p_vector_weight: vw,
		  p_keyword_weight: kw,
		}),
	  });
	  if (!res.ok) return [];
	  const data: any = await res.json();
	  if (!Array.isArray(data)) return [];
	  return data as HybridSearchRow[];
	} catch {
	  return [];
	}
  }

  type TargetLang = "en" | "zh";

  function detectLangFromText(text: string): TargetLang {
	// Naive but effective: any CJK ideograph => Chinese
	return /[\u4E00-\u9FFF]/.test(text) ? "zh" : "en";
  }

  function decideTargetLang(userInput: string, situation: string): TargetLang {
	// IMPORTANT: prioritize the user's latest input to avoid old context (e.g. earlier Chinese rounds)
	// forcing the model back into Chinese even when the user now types English.
	if (userInput?.trim()) return detectLangFromText(userInput);
	return detectLangFromText(situation || "");
  }

  function langName(lang: TargetLang): string {
	return lang === "zh" ? "Simplified Chinese" : "English";
  }

  function resolvePersonaPrompt(prompt: Persona["prompt"] | undefined, lang: TargetLang): string {
	if (!prompt) return "";
	if (typeof prompt === "string") return prompt;
	return prompt[lang] || prompt.en || prompt.zh || "";
  }

  function jsonResponse(data: unknown, status = 200): Response {
	return new Response(JSON.stringify(data), {
	  status,
	  headers: { ...corsHeaders, "Content-Type": "application/json" },
	});
  }

  function clampScore(v: number): number {
	if (!Number.isFinite(v)) return 0;
	return Math.max(0, Math.min(100, Math.round(v)));
  }

  function asString(v: unknown, fallback = ""): string {
	return typeof v === "string" ? v.trim() : fallback;
  }

  function asStringArray(v: unknown, fallback: string[] = []): string[] {
	if (!Array.isArray(v)) return fallback;
	return v.map((x) => (typeof x === "string" ? x.trim() : "")).filter(Boolean);
  }

  function formatHybridContext(rows: HybridSearchRow[], maxChars = 2400): string {
	if (!rows.length) return "";
	const lines = rows
	  .slice(0, 6)
	  .map((r, i) => {
		const t = asString(r.chunk_text || r.text || "", "").replace(/\s+/g, " ").trim();
		if (!t) return "";
		const src = asString(r.source, "knowledge");
		const score = Number.isFinite(Number(r.score)) ? Number(r.score).toFixed(3) : "";
		return `[${i + 1}] (${src}${score ? ` | score=${score}` : ""}) ${t}`;
	  })
	  .filter(Boolean);
	const text = lines.join("\n");
	return text.length > maxChars ? `${text.slice(0, maxChars)}...` : text;
  }

  function isLikelyAmbiguousInput(situation: string): boolean {
	const text = (situation || "").trim();
	if (!text) return true;
	const compact = text.replace(/\s+/g, "");
	if (compact.length < 18) return true;
	const vagueSignals = [
	  "怎么办",
	  "好纠结",
	  "很迷茫",
	  "不知道",
	  "help",
	  "confused",
	  "not sure",
	  "what should i do",
	];
	const lower = text.toLowerCase();
	return vagueSignals.some((k) => lower.includes(k));
  }

  function normalizeQuestion(input: any, idx: number, lang: TargetLang): LifeSimQuestion {
	const defaults: LifeSimQuestion[] = lang === "zh"
	  ? [
		  {
			id: "value_priority",
			label: "价值取向",
			question: "这次决策你最想守住的是什么？",
			placeholder: "例如：长期成长、稳定现金流、家庭关系、个人自由",
			kind: "text",
		  },
		  {
			id: "risk_preference",
			label: "风险偏好",
			question: "你当前可接受的风险级别是？",
			placeholder: "请选择最接近你的状态",
			kind: "single",
			options: ["低风险稳步推进", "中风险可控试错", "高风险快速突破"],
		  },
		  {
			id: "time_horizon",
			label: "时间边界",
			question: "你希望多久看到明显结果？",
			placeholder: "例如：3个月、半年、1年",
			kind: "text",
		  },
		  {
			id: "constraints",
			label: "不可妥协",
			question: "这件事里你绝对不能失去的条件是什么？",
			placeholder: "例如：不能裸辞、必须保留周末时间、现金流不能断",
			kind: "text",
		  },
		]
	  : [
		  {
			id: "value_priority",
			label: "Value Priority",
			question: "What matters most in this decision right now?",
			placeholder: "e.g. growth, stability, freedom, relationships",
			kind: "text",
		  },
		  {
			id: "risk_preference",
			label: "Risk Preference",
			question: "What level of risk is acceptable right now?",
			placeholder: "Pick the closest option",
			kind: "single",
			options: ["Low risk", "Balanced risk", "High risk"],
		  },
		  {
			id: "time_horizon",
			label: "Time Horizon",
			question: "When do you want visible progress?",
			placeholder: "e.g. 3 months / 6 months / 1 year",
			kind: "text",
		  },
		  {
			id: "constraints",
			label: "Non-negotiables",
			question: "What must not be sacrificed in this path?",
			placeholder: "e.g. minimum cashflow, health baseline, family time",
			kind: "text",
		  },
		];

	const base = defaults[idx] || defaults[defaults.length - 1];
	return {
	  id: asString(input?.id, base.id),
	  label: asString(input?.label, base.label),
	  question: asString(input?.question, base.question),
	  placeholder: asString(input?.placeholder, base.placeholder),
	  kind: input?.kind === "single" ? "single" : base.kind,
	  options: input?.kind === "single" ? asStringArray(input?.options, base.options || []) : undefined,
	};
  }

  function normalizePath(input: any, idx: number, lang: TargetLang): LifeSimPath {
	const fallbackNames = lang === "zh"
	  ? ["稳定路径", "冒险路径", "新生路径"]
	  : ["Stable Path", "Adventure Path", "Reinvention Path"];
	const fallbackId = ["stable", "adventure", "new-life"][idx] || `path-${idx + 1}`;
	const timelineFallback: LifeSimTimelinePoint[] = lang === "zh"
	  ? [
		  { phase: "0-3个月", focus: "先做最低成本试验", risk: "方向模糊", signal: "每周有可追踪进展" },
		  { phase: "3-6个月", focus: "放大有效动作", risk: "执行疲劳", signal: "关键指标持续改善" },
		  { phase: "6-12个月", focus: "形成稳定节奏", risk: "外部变量冲击", signal: "可复制的成果出现" },
		]
	  : [
		  { phase: "0-3 months", focus: "Run low-cost validation", risk: "Unclear direction", signal: "Weekly measurable progress" },
		  { phase: "3-6 months", focus: "Scale what works", risk: "Execution fatigue", signal: "Core metrics improve steadily" },
		  { phase: "6-12 months", focus: "Lock operating rhythm", risk: "External shocks", signal: "Repeatable outcomes emerge" },
		];

	const timelineRaw = Array.isArray(input?.timeline) ? input.timeline : [];
	const timeline = timelineRaw.length
	  ? timelineRaw.slice(0, 5).map((t: any, i: number) => ({
		  phase: asString(t?.phase, timelineFallback[Math.min(i, timelineFallback.length - 1)].phase),
		  focus: asString(t?.focus, timelineFallback[Math.min(i, timelineFallback.length - 1)].focus),
		  risk: asString(t?.risk, timelineFallback[Math.min(i, timelineFallback.length - 1)].risk),
		  signal: asString(t?.signal, timelineFallback[Math.min(i, timelineFallback.length - 1)].signal),
		}))
	  : timelineFallback;

	const scores = input?.scores || {};
	return {
	  id: asString(input?.id, fallbackId),
	  name: asString(input?.name, fallbackNames[idx] || fallbackNames[0]),
	  tagline: asString(input?.tagline, lang === "zh" ? "在现实约束下推进" : "Move under real constraints"),
	  narrative: asString(
		input?.narrative,
		lang === "zh"
		  ? "这条路径以阶段化推进为核心：先验证、再加码、再固化，减少一次性押注。"
		  : "This path prioritizes staged progress: validate, scale, then stabilize."
	  ),
	  timeline,
	  scores: {
		growth: clampScore(Number(scores?.growth ?? (60 + idx * 8))),
		stability: clampScore(Number(scores?.stability ?? (74 - idx * 10))),
		happiness: clampScore(Number(scores?.happiness ?? (62 + idx * 6))),
		risk: clampScore(Number(scores?.risk ?? (38 + idx * 20))),
		feasibility: clampScore(Number(scores?.feasibility ?? (76 - idx * 8))),
	  },
	  pros: asStringArray(input?.pros, lang === "zh" ? ["节奏清晰", "可逐步验证"] : ["Clear cadence", "Stepwise validation"]),
	  cons: asStringArray(input?.cons, lang === "zh" ? ["需要持续复盘", "短期可能看起来慢"] : ["Needs steady review", "May feel slow early"]),
	  first_action: asString(
		input?.first_action,
		lang === "zh" ? "今天先定义一个一周内可验证的最小实验。" : "Define one 7-day test you can run today."
	  ),
	};
  }

  async function callGeminiJson<T>(env: Env, prompt: string, fallback: T): Promise<T> {
	const res = await callGeminiText(env, prompt);
	if (!res.ok) return fallback;
	const parsed = extractJsonObject(res.text);
	if (!parsed || typeof parsed !== "object") return fallback;
	return parsed as T;
  }

  async function handleLifeSimulator(request: Request, url: URL, env: Env): Promise<Response> {
	const path = url.pathname;
	const rawBody = await request.json();
	const body = (rawBody || {}) as Record<string, unknown>;
	const situation = asString(body.situation, "");
	const landingPeriods = asStringArray(body.landingPeriods, []);
	const lang = detectLangFromText(`${situation}\n${landingPeriods.join(" ")}`);
	const lifeSimEmbedding = situation ? await callGeminiEmbedding(env, situation) : null;
	const lifeSimRows = await fetchHybridRows(env, {
	  queryText: `${situation}\n${landingPeriods.join(", ")}`,
	  personaId: "life-simulator",
	  queryEmbedding: lifeSimEmbedding,
	  matchCount: 5,
	});
	const lifeSimHybridContext = formatHybridContext(lifeSimRows);

	if (!situation && path !== "/simulator/conclusion") {
	  return jsonResponse({ error: "Missing situation" }, 400);
	}

	if (path === "/simulator/clarify") {
	  const _req = body as LifeSimClarifyRequest;
	  const heuristic = isLikelyAmbiguousInput(situation);
	  const fallback: LifeSimClarifyResponse = lang === "zh"
		? {
			needs_clarification: heuristic,
			reason: heuristic ? "场景描述偏抽象，关键约束和目标尚不明确。" : "信息已基本清楚，可进入深挖阶段。",
			question: "为了更准确推演，你当前更接近下面哪一种？",
			options: [
			  "我在两个明确选项之间犹豫",
			  "我知道方向但受现实约束卡住",
			  "我连目标本身都还没想清楚",
			],
		  }
		: {
			needs_clarification: heuristic,
			reason: heuristic ? "Your scenario is still broad and lacks a key constraint." : "Your input is specific enough to proceed.",
			question: "To simulate accurately, which one is closest to your current state?",
			options: [
			  "I'm stuck between two concrete options",
			  "I know the direction but constraints block me",
			  "I still don't know the real goal yet",
			],
		  };

	  const prompt = `
You are a product intake classifier for a life simulator.
Language: ${lang === "zh" ? "Simplified Chinese" : "English"}.
User situation:
${situation}
Landing periods: ${landingPeriods.join(", ") || "(none)"}
Knowledge snippets (optional):
${lifeSimHybridContext || "(none)"}

Task:
1) Decide if clarification is needed before deeper analysis.
2) Provide one short reason.
3) Provide one disambiguation question.
4) Provide exactly 3 concise multiple-choice options (mutually exclusive).

Return JSON only:
{
  "needs_clarification": true/false,
  "reason": "...",
  "question": "...",
  "options": ["...", "...", "..."]
}
`.trim();

	  const raw = await callGeminiJson(env, prompt, fallback as any);
	  let options = asStringArray((raw as any)?.options, fallback.options).slice(0, 3);
	  while (options.length < 3) options.push(fallback.options[options.length] || fallback.options[0]);
	  return jsonResponse({
		needs_clarification: typeof (raw as any)?.needs_clarification === "boolean"
		  ? (raw as any).needs_clarification
		  : fallback.needs_clarification,
		reason: asString((raw as any)?.reason, fallback.reason),
		question: asString((raw as any)?.question, fallback.question),
		options,
	  });
	}

	if (path === "/simulator/deepen") {
	  const fallback = {
		situation_brief: lang === "zh" ? `当前议题：${situation}` : `Current topic: ${situation}`,
		assumptions: lang === "zh"
		  ? ["你希望降低决策焦虑", "你需要可执行的路径而不只是观点", "你愿意在现实约束下做阶段推进"]
		  : ["You want less decision anxiety", "You need actionable paths, not just opinions", "You can move in staged steps under constraints"],
		questions: [
		  normalizeQuestion({}, 0, lang),
		  normalizeQuestion({}, 1, lang),
		  normalizeQuestion({}, 2, lang),
		  normalizeQuestion({}, 3, lang),
		],
		initial_hypotheses: lang === "zh"
		  ? ["先明确底线，再放大机会，避免一次性押注。"]
		  : ["Define non-negotiables first, then scale upside with controlled risk."],
	  };

	  const prompt = `
You are a product-grade life-simulation intake analyst.
Language: ${lang === "zh" ? "Simplified Chinese" : "English"}.
User situation: ${situation}
Landing periods: ${landingPeriods.join(", ") || "(none)"}
Knowledge snippets (optional):
${lifeSimHybridContext || "(none)"}

Task:
1) Summarize the situation in one sentence.
2) Provide 2-4 key assumptions.
3) Generate exactly 4 clarifying questions: value_priority, risk_preference, time_horizon, constraints.
4) Each question must include: id, label, question, placeholder, kind ("text" or "single"), and options if kind is single.
5) Add 1-2 initial hypotheses.

Return JSON only:
{
  "situation_brief": "...",
  "assumptions": ["..."],
  "questions": [
    { "id": "value_priority", "label": "...", "question": "...", "placeholder": "...", "kind": "text" },
    { "id": "risk_preference", "label": "...", "question": "...", "placeholder": "...", "kind": "single", "options": ["..."] },
    { "id": "time_horizon", "label": "...", "question": "...", "placeholder": "...", "kind": "text" },
    { "id": "constraints", "label": "...", "question": "...", "placeholder": "...", "kind": "text" }
  ],
  "initial_hypotheses": ["..."]
}
`.trim();

	  const raw = await callGeminiJson(env, prompt, fallback as any);
	  return jsonResponse({
		situation_brief: asString((raw as any)?.situation_brief, fallback.situation_brief),
		assumptions: asStringArray((raw as any)?.assumptions, fallback.assumptions),
		questions: Array.isArray((raw as any)?.questions)
		  ? (raw as any).questions.slice(0, 4).map((q: any, i: number) => normalizeQuestion(q, i, lang))
		  : fallback.questions,
		initial_hypotheses: asStringArray((raw as any)?.initial_hypotheses, fallback.initial_hypotheses),
	  });
	}

	if (path === "/simulator/routes") {
	  const req = body as LifeSimRoutesRequest;
	  const answers = req.answers || {};
	  const answerText = Object.entries(answers)
		.map(([k, v]) => `${k}: ${asString(v, "")}`)
		.filter((line) => !line.endsWith(": "))
		.join("\n");

	  const fallbackPaths = [
		normalizePath({ id: "stable", name: lang === "zh" ? "稳定路径" : "Stable Path" }, 0, lang),
		normalizePath({ id: "adventure", name: lang === "zh" ? "冒险路径" : "Adventure Path" }, 1, lang),
		normalizePath({ id: "new-life", name: lang === "zh" ? "新生路径" : "Reinvention Path" }, 2, lang),
	  ];

	  const prompt = `
You are a strategic foresight analyst. Build multiple future routes for one life decision.
Language: ${lang === "zh" ? "Simplified Chinese" : "English"}.
Situation: ${situation}
Landing periods: ${landingPeriods.join(", ") || "(none)"}
Knowledge snippets (optional):
${lifeSimHybridContext || "(none)"}
Answers:
${answerText || "(none)"}

Generate exactly 3 distinct routes:
1) Stable path (lower risk, compounding)
2) Adventure path (higher upside + volatility)
3) Reinvention path (identity shift / new context)

For each route provide id,name,tagline,narrative,timeline(3-5 steps with phase/focus/risk/signal),scores(growth,stability,happiness,risk,feasibility 0-100),pros,cons,first_action.

Return JSON only:
{
  "paths": [ ... ],
  "comparison_summary": "...",
  "suggested_path_id": "stable|adventure|new-life"
}
`.trim();

	  const raw = await callGeminiJson(env, prompt, {
		paths: fallbackPaths,
		comparison_summary: lang === "zh" ? "三条路径分别优化稳定性、增速和人生重构。" : "The three paths optimize stability, acceleration, and reinvention.",
		suggested_path_id: "stable",
	  } as any);

	  const rawPaths = Array.isArray((raw as any)?.paths) ? (raw as any).paths : fallbackPaths;
	  const paths = rawPaths.slice(0, 3).map((p: any, idx: number) => normalizePath(p, idx, lang));
	  const suggestedPathId = asString((raw as any)?.suggested_path_id, paths[0]?.id || "stable");
	  return jsonResponse({
		paths,
		comparison_summary: asString(
		  (raw as any)?.comparison_summary,
		  lang === "zh" ? "建议先选一条主路径做两周验证，再根据信号迭代。" : "Pick one primary path, run a 2-week test, then iterate by signals."
		),
		suggested_path_id: paths.some((p: LifeSimPath) => p.id === suggestedPathId) ? suggestedPathId : paths[0]?.id || "stable",
	  });
	}

	if (path === "/simulator/refine") {
	  const req = body as LifeSimRefineRequest;
	  const selectedPath = normalizePath(req.selectedPath || {}, 0, lang);
	  const refinePrompt = asString(req.refinePrompt, "");
	  const answersText = Object.entries(req.answers || {})
		.map(([k, v]) => `${k}: ${asString(v, "")}`)
		.filter((line) => !line.endsWith(": "))
		.join("\n");

	  if (!refinePrompt) {
		return jsonResponse({ error: "Missing refinePrompt" }, 400);
	  }

	  const prompt = `
You are refining an existing life route with user feedback.
Language: ${lang === "zh" ? "Simplified Chinese" : "English"}.
Situation: ${situation}
User refinement request: ${refinePrompt}
Knowledge snippets (optional):
${lifeSimHybridContext || "(none)"}
Context answers:
${answersText || "(none)"}

Current selected path JSON:
${JSON.stringify(selectedPath, null, 2)}

Return JSON only:
{
  "updated_path": { ...same schema as input path... },
  "delta": ["what changed"],
  "follow_up_questions": ["question 1", "question 2"]
}
`.trim();

	  const raw = await callGeminiJson(env, prompt, {
		updated_path: selectedPath,
		delta: [lang === "zh" ? "已根据新约束调整推进节奏。" : "Adjusted cadence based on new constraints."],
		follow_up_questions: [lang === "zh" ? "如果资源再减少 20%，你还会坚持这条路径吗？" : "If resources drop by 20%, would you still keep this path?"],
	  } as any);

	  return jsonResponse({
		updated_path: normalizePath((raw as any)?.updated_path || selectedPath, 0, lang),
		delta: asStringArray((raw as any)?.delta, lang === "zh" ? ["已完成一次路径迭代。"] : ["Path iteration completed."]),
		follow_up_questions: asStringArray((raw as any)?.follow_up_questions, []),
	  });
	}

	if (path === "/simulator/conclusion") {
	  const req = body as LifeSimConclusionRequest;
	  const selectedPath = normalizePath(req.selectedPath || {}, 0, lang);
	  const notes = asStringArray(req.refinementNotes, []);
	  const answersText = Object.entries(req.answers || {})
		.map(([k, v]) => `${k}: ${asString(v, "")}`)
		.filter((line) => !line.endsWith(": "))
		.join("\n");

	  const prompt = `
You are a product strategist + behavioral coach writing a final execution memo.
Language: ${lang === "zh" ? "Simplified Chinese" : "English"}.
Situation: ${situation}
Knowledge snippets (optional):
${lifeSimHybridContext || "(none)"}
Selected path:
${JSON.stringify(selectedPath, null, 2)}
User answers:
${answersText || "(none)"}
Refinement notes:
${notes.join("\n") || "(none)"}

Return JSON only:
{
  "decision_statement": "...",
  "why_now": "...",
  "next_7_days": ["..."],
  "next_30_days": ["..."],
  "watchouts": ["..."],
  "fallback_plan": ["..."],
  "confidence": 0-100
}
`.trim();

	  const raw = await callGeminiJson(env, prompt, {
		decision_statement: lang === "zh" ? "选择主路径并用短周期验证，避免情绪化摇摆。" : "Commit to one primary path and validate in short cycles.",
		why_now: lang === "zh" ? "当前窗口期最需要的是执行闭环，而不是继续信息囤积。" : "This window rewards execution loops more than additional information hoarding.",
		next_7_days: lang === "zh" ? ["定义一个可量化目标", "安排两次复盘", "完成第一轮最小实验"] : ["Define one measurable target", "Schedule two reviews", "Run first minimum experiment"],
		next_30_days: lang === "zh" ? ["固化每周节奏", "淘汰低效动作", "加码高回报动作"] : ["Lock weekly cadence", "Cut low-leverage actions", "Scale high-return actions"],
		watchouts: lang === "zh" ? ["避免同时推进三条路径", "不要忽视现金流和精力边界"] : ["Avoid running three paths in parallel", "Protect cashflow and energy limits"],
		fallback_plan: lang === "zh" ? ["若关键指标连续两周下滑，降级到保守版本", "保留可逆选项，避免不可逆大赌注"] : ["If core metrics decline for 2 weeks, downgrade to conservative mode", "Keep reversible options; avoid irreversible big bets"],
		confidence: 72,
	  } as any);

	  return jsonResponse({
		decision_statement: asString((raw as any)?.decision_statement, ""),
		why_now: asString((raw as any)?.why_now, ""),
		next_7_days: asStringArray((raw as any)?.next_7_days, []),
		next_30_days: asStringArray((raw as any)?.next_30_days, []),
		watchouts: asStringArray((raw as any)?.watchouts, []),
		fallback_plan: asStringArray((raw as any)?.fallback_plan, []),
		confidence: clampScore(Number((raw as any)?.confidence ?? 70)),
	  });
	}

	return jsonResponse({ error: "Not Found" }, 404);
  }
  
	  export default {
		async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
		  // ---- CORS preflight ----
		  if (request.method === "OPTIONS") {
			return new Response(null, { headers: corsHeaders });
		  }
	  
		  const url = new URL(request.url);
		  const stream = url.searchParams.get("stream") === "1";

		  if (request.method === "POST" && url.pathname.startsWith("/simulator/")) {
			if (!env.GEMINI_API_KEY) {
			  return new Response(JSON.stringify({ error: "Missing GEMINI_API_KEY" }), {
				status: 500,
				headers: { ...corsHeaders, "Content-Type": "application/json" },
			  });
			}
			try {
			  return await handleLifeSimulator(request, url, env);
			} catch (err: any) {
			  return jsonResponse(
				{
				  error: "Invalid simulator request",
				  details: String(err?.message || err),
				},
				400
			  );
			}
		  }

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

		const birthDate = body.birthDate?.trim() || "";
  
		// Persona templates (default 4 voices)
		const PERSONA_TEMPLATES: Record<string, { defaultName: string; prompt: Persona["prompt"] }> = {
		  serene: {
			defaultName: "SERENE",
			prompt: {
			  en: [
				"Core: warm, steady comforter. Soothe without denying reality; name feelings; lower intensity while keeping boundaries.",
				"Method: validate emotion → accept/ground → recognize effort/courage → offer 1–2 tiny next steps as possibilities.",
				"Avoid: platitudes, absolutist claims, shaming, commands, forced positivity.",
				"Safety: if self-harm/danger signals appear, prioritize immediate safety and suggest real-world support (no method details).",
			  ].join("\n"),
			  zh: [
				"你是 Seren：温暖、幸福、胸怀宽广的安慰者，总能给人带来快乐与安稳。",
				"在这场“内部辩论”里，你的职责是为焦虑、委屈、迷茫、紧绷的部分提供安抚与希望，同时保持清醒与边界；你也会温柔地化解冲突，让讨论回到可承受的节奏。",
				"气质：柔和稳定、真诚、包容；不说教、不评判、不讽刺；不强行正能量，但会点亮希望。",
				"表达原则：先看见处境与感受（命名情绪）→再接纳与安放→再指出已付出的努力/勇气→最后给 1-2 个很小、可落地的下一步。",
				"你避免：‘想开点/别难过’式否定情绪；空泛鸡汤；绝对化结论；把责任全部推给当事人；任何羞辱或指责。",
				"安全：若出现自伤/轻生或现实危险信号，你会优先关心当下安全，并建议寻求现实支持（亲友/当地紧急电话/医院/心理援助），但不提供任何自伤方法细节。",
			  ].join("\n"),
			},
		  },
		  // Entrepreneur / Founder voice (user requested "lifecoach" -> entrepreneur style)
		  architect: {
			defaultName: "The Entrepreneur",
			prompt: [
			  "Voice: battle-tested entrepreneur / operator. High stress tolerance, calm under pressure, allergic to vague thinking.",
			  "Style: blunt, a little sharp-tongued, but NEVER insulting; critique ideas and excuses, not the person.",
			  "Focus: identify the real constraint, the leverage point, and the fastest feedback loop. Name trade-offs, opportunity costs, and risks clearly.",
			  "Behavior: loves challenges; will push for clarity, commitments, and measurable next steps. Calls out self-deception in one sentence when needed.",
			  "Language: concrete, specific, decisive tone. Prefer short sentences. Avoid therapy talk.",
			].join(" "),
		  },
		  // Backward-compatible alias if caller sends id "lifecoach"
		  lifecoach: {
			defaultName: "The Entrepreneur",
			prompt: [
			  "Voice: battle-tested entrepreneur / operator. High stress tolerance, calm under pressure, allergic to vague thinking.",
			  "Style: blunt, a little sharp-tongued, but NEVER insulting; critique ideas and excuses, not the person.",
			  "Focus: identify the real constraint, the leverage point, and the fastest feedback loop. Name trade-offs, opportunity costs, and risks clearly.",
			  "Behavior: loves challenges; will push for clarity, commitments, and measurable next steps. Calls out self-deception in one sentence when needed.",
			  "Language: concrete, specific, decisive tone. Prefer short sentences. Avoid therapy talk.",
			].join(" "),
		  },
		  rebel: {
			defaultName: "The Outlier",
			prompt:
			  "Voice: disruptive challenger. Attack the status quo, expose self-deception, name the avoided truth. Be edgy but not cruel; punch up at excuses, not at the person. Prefer bold reframes and uncomfortable questions.",
		  },
		  caretaker: {
			defaultName: "The Positive Psychologist",
			prompt:
			  [
				"You are a gentle, emotionally steady Positive Psychologist (positive psychology).",
				"Goal: when the user faces life confusion, provide emotional validation + evidence-based insight (without diagnosing).",
				"Method: name feelings, normalize uncertainty, reframe with PERMA/values/strengths, highlight agency and small experiments, encourage self-compassion.",
				"Boundaries: do not moralize, do not shame, do not overpromise, do not claim clinical certainty; if there are signs of crisis/self-harm, suggest reaching out to trusted people or professionals (as an internal note).",
				"Tone: warm, grounded, kind, specific. Use simple language; avoid jargon unless briefly explained.",
			  ].join(" "),
		  },
		  "audrey-hepburn": {
			defaultName: "Audrey Hepburn",
			prompt: {
			  en: [
				"Identity: Audrey Hepburn — an elegant muse: gentle, poised, quietly brave, humane. Warmth with impeccable taste.",
				"Style: concise, lyrical, cinematic; subtle wit; use simple vivid images (morning light, a tidy room, a well-chosen dress).",
				"Focus: dignity, kindness, restraint, and the smallest next step that restores grace and self-respect.",
				"Method: soften the panic → name what matters (values) → choose the simplest honest action → one concrete next step (10–20 minutes).",
				"Avoid: harshness, cynicism, therapy jargon, moralizing, grand plans, or commanding language.",
				"Constraint: speak as inner self-talk (not addressing the user directly).",
			  ].join("\n"),
			  zh: [
				"身份：奥黛丽·赫本——优雅的缪斯，温柔、克制、体面、安静但不软弱；善良里有锋利的边界。",
				"语气：简洁、含蓄、带一点轻盈的幽默；用清晰的画面感（清晨的光、整理好的衣领、干净的桌面）来落地情绪与选择。",
				"关注点：尊严、善意、节制，以及“最小但诚实”的下一步，让人重新站稳。",
				"方法：先把慌乱放慢→点出真正珍视的价值→选择最简单、最体面的行动→给出 10–20 分钟可完成的下一步。",
				"你避免：刻薄、犬儒、心理学术语堆砌、说教、宏大计划、命令式口吻。",
				"约束：以内部独白方式表达（不要直接对用户下指令）。",
			  ].join("\n"),
			},
		  },
		  mystic: {
			defaultName: "东方玄学大师",
			prompt: {
			  en: [
				"You are an Eastern metaphysics advisor using BaZi (Four Pillars), five elements, and timing cycles as a symbolic decision lens (not science).",
				"If only a birth date (YYYY-MM-DD) is provided, note it's simplified; for precision, ask for birth time and birthplace (optional).",
				"Output: calm, structured; give tendencies/cycles/risk points/fit strategies. Avoid fatalism and absolutes.",
				"Boundaries: no medical/legal/investment certainty. Use metaphysics as a framing tool to clarify trade-offs and timing.",
			  ].join(" "),
			  zh: [
				"你是一位东方玄学大师，擅长以八字（四柱）、五行气机与运势节律来做“决策参考”。",
				"重要前提：用户需要提供八字信息。若只给了出生日期（YYYY-MM-DD），你必须明确这是简化版推演；如需更精确，请提示补充出生时辰与出生地（可选）。",
				"输出要求：用简体中文、克制且有条理，不要神神叨叨。给出“倾向/节律/风险点/适配策略”，避免宿命论与绝对断言。",
				"边界：不要把玄学当成科学结论；不做医疗/法律/投资的确定性结论。把玄学当作一种象征性框架，帮助用户看见取舍与时机。",
				"风格：沉稳、洞察、一针见血但不吓人；可以用少量术语（如五行、喜忌、节律）但要配一句通俗解释。",
			  ].join(" "),
			},
		  },
		};

		const rawPersonas: Persona[] =
		  body.personas && body.personas.length > 0
			? body.personas
			: [
				{ id: "serene", name: PERSONA_TEMPLATES.serene.defaultName },
				{ id: "architect", name: PERSONA_TEMPLATES.architect.defaultName },
				{ id: "rebel", name: PERSONA_TEMPLATES.rebel.defaultName },
				{ id: "caretaker", name: PERSONA_TEMPLATES.caretaker.defaultName },
			  ];

		// Attach template prompts by id (even for user-supplied personas)
		const personas: Persona[] = rawPersonas.map((p) => {
		  const t = PERSONA_TEMPLATES[p.id];
		  return {
			id: p.id,
			name: p.name || t?.defaultName || p.id,
			// Allow caller to override prompt; otherwise use template prompt.
			prompt: p.prompt ?? t?.prompt,
			knowledge: typeof p.knowledge === "string" ? p.knowledge : "",
		  };
		});
  
			const userInput = body.userInput?.trim() || "";
			const targetLang = decideTargetLang(userInput, situation);
			const TARGET_LANGUAGE = langName(targetLang);
			const stageExample = targetLang === "zh" ? "（皱眉）" : "(frowns)";
			const decisionQueryText = `${situation}\n${userInput}`.trim();
			const decisionEmbedding = decisionQueryText ? await callGeminiEmbedding(env, decisionQueryText) : null;
			const hybridKnowledgeByPersona = new Map<string, string>();
			for (const p of personas) {
			  const rows = await fetchHybridRows(env, {
				queryText: decisionQueryText,
				personaId: p.id,
				queryEmbedding: decisionEmbedding,
				matchCount: 4,
			  });
			  hybridKnowledgeByPersona.set(p.id, formatHybridContext(rows, 1800));
			}

			// ---- Stream mode: emit one persona at a time (SSE) ----
			if (stream) {
		  const { readable, writable } = new TransformStream();
		  const writer = writable.getWriter();

		  const headers = {
			...corsHeaders,
			"Content-Type": "text/event-stream; charset=utf-8",
			"Cache-Control": "no-cache, no-transform",
		  };

		  ctx.waitUntil(
			(async () => {
			  try {
				// Kickoff comment (helps some proxies/browsers flush early)
				await writer.write(new TextEncoder().encode(":ok\n\n"));

				const earlier: Array<{ personaId: string; name: string; text: string }> = [];

					for (const p of personas) {
				  const earlierBlock = earlier.length
					? earlier.map((m) => `- ${m.personaId} (${m.name}): ${m.text}`).join("\n")
					: "(none)";
				  const personaInstruction = resolvePersonaPrompt(p.prompt, targetLang) || "(no extra instruction)";
					  const hybridBlock = (hybridKnowledgeByPersona.get(p.id) || "").trim();
					  const knowledgeBlock = [asString(p.knowledge, ""), hybridBlock].filter(Boolean).join("\n\n");
					  const clippedKnowledge = knowledgeBlock ? knowledgeBlock.slice(0, 12000) : "";

				  const personaPrompt = `
You are not an assistant. You are one inner voice in an internal debate.
You speak ONLY as this persona: ${p.name} (${p.id}).

TARGET_LANGUAGE: ${TARGET_LANGUAGE}

Context:
${situation}
${birthDate ? `\nUser birth date (YYYY-MM-DD, optional reference): ${birthDate}` : ""}

Persona instruction:
${personaInstruction}

Knowledge base (optional; treat as grounding facts, do not invent beyond it):
${clippedKnowledge ? clippedKnowledge : "(none)"}

Earlier voices (react to at least one point if any exist):
${earlierBlock}

Rules (absolute):
- Output MUST be in TARGET_LANGUAGE (follow the user's latest input language).
- If earlier voices are in a different language, interpret/translate them and still respond in TARGET_LANGUAGE.
- Output ONLY the message text for your persona (no JSON, no markdown, no meta).
- The text MUST start with a short stage direction, e.g. "${stageExample}", then a space, then the message.
- If TARGET_LANGUAGE is Simplified Chinese, the stage direction must be in Chinese parentheses with 2–8 Chinese characters.
- If TARGET_LANGUAGE is English, the stage direction should be 1–3 English words in parentheses.
- If earlier voices exist, respond to at least one of them (rebut, question, or build).
- If a knowledge base is provided, use it to ground factual claims. If a detail is not in the knowledge base and you are unsure, say you are unsure rather than making it up.
- Do NOT address the user directly (avoid "you should/you need"); speak as inner self-talk.
- Keep it concise. (English: ~50–120 words; Chinese: ~70–180 characters.)

Round input (may be empty on the first round):
${userInput ? userInput : "(no new input — begin the debate)"}
				  `.trim();

				  const one = await callGeminiText(env, personaPrompt);
				  if (!one.ok) {
					await writer.write(
					  sseEncode("error", {
						error: "Gemini API error",
						status: one.status,
						details: one.details,
					  })
					);
					await writer.close();
					return;
				  }

				  const text = one.text || (targetLang === "zh" ? "（沉默） ……" : "(silence) ...");
				  const msg = { personaId: p.id, text };
				  earlier.push({ personaId: p.id, name: p.name, text });
				  await writer.write(sseEncode("message", msg));
				}

				// Generate options after all persona messages (small, actionable choices)
				const debateBlock = earlier.map((m) => `${m.name} (${m.personaId}): ${m.text}`).join("\n");
				const optionsPrompt = `
You are an option generator for an internal debate (not an assistant).

TARGET_LANGUAGE: ${TARGET_LANGUAGE}

Context:
${situation}
${birthDate ? `\nUser birth date (YYYY-MM-DD, optional reference): ${birthDate}` : ""}

Round input:
${userInput ? userInput : "(no new input)"}

Persona messages this round:
${debateBlock}

Task: produce 3–5 distinct "next-step options" that are short, specific, and doable.
Rules:
- Output MUST be in TARGET_LANGUAGE.
- Do not command; do not claim certainty; present options only.
- Each option length: English 4–10 words; Chinese 8–24 characters.

Output JSON ONLY exactly in this format:
{ "options": ["...", "...", "..."] }
				`.trim();

				const opt = await callGeminiText(env, optionsPrompt);
				if (opt.ok) {
				  const parsedOpt = extractJsonObject(opt.text);
				  const options = Array.isArray(parsedOpt?.options) ? parsedOpt.options : [];
				  await writer.write(sseEncode("options", { options }));
				} else {
				  await writer.write(sseEncode("options", { options: [] }));
				}

				await writer.write(sseEncode("done", { ok: true }));
				await writer.close();
			  } catch (err: any) {
				try {
				  await writer.write(
					sseEncode("error", {
					  error: "Stream failed",
					  details: String(err?.message || err),
					})
				  );
				} catch (_) {}
				try {
				  await writer.close();
				} catch (_) {}
			  }
			})()
		  );

		  return new Response(readable, { headers });
		}
  
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
  ${birthDate ? `\nUser birth date (Gregorian, YYYY-MM-DD): ${birthDate}` : ""}
  
  Personas (each persona MUST follow its own voice instruction):
	  ${personas
		.map((p) => {
		  const resolved = resolvePersonaPrompt(p.prompt, targetLang);
		  const style = resolved ? `\n    Voice instruction: ${resolved}` : "";
			  const mergedKnowledge = [asString(p.knowledge, ""), asString(hybridKnowledgeByPersona.get(p.id), "")]
				.filter(Boolean)
				.join("\n\n")
				.slice(0, 1600);
		  const kb = mergedKnowledge ? `\n    Knowledge snippets: ${mergedKnowledge}` : "";
		  return `- ${p.id}: ${p.name}${style}${kb}`;
		})
		.join("\n")}
  
  Rules (ABSOLUTE):
  - DO NOT give definitive advice or commands; present perspectives, questions, and trade-offs (options belong in the options array)
  - DO NOT summarize
  - DO NOT conclude
  - DO NOT explain the debate
  - DO NOT address the user directly
  - DO NOT use markdown
  - DO NOT add meta commentary
  - TARGET_LANGUAGE is ${TARGET_LANGUAGE}. Output MUST be in TARGET_LANGUAGE.
  - IMPORTANT: Determine language from the user's latest input (Round input). If it is English, output English even if earlier context contains Chinese, and vice versa.
  - The output "messages" MUST contain exactly ONE message per persona listed above (personaId must match the ids in Personas)
  - Generate messages SEQUENTIALLY in the same order as Personas listed above. Later personas MUST react to earlier personas (rebut, question, or build on at least one earlier point).
  - Each message "text" MUST start with a short stage direction, e.g. "${stageExample}", then a space, then the message.
  - If TARGET_LANGUAGE is Simplified Chinese, the stage direction must be in Chinese parentheses with 2–8 Chinese characters.
  - If TARGET_LANGUAGE is English, the stage direction should be 1–3 English words in parentheses.
  
  You MUST output JSON ONLY in the following format:
  
  {
	"messages": [
	  { "personaId": "serene", "text": "${targetLang === "zh" ? "（...） ..." : "(...) ..."}" },
	  { "personaId": "architect", "text": "${targetLang === "zh" ? "（...） ..." : "(...) ..."}" },
	  { "personaId": "rebel", "text": "${targetLang === "zh" ? "（...） ..." : "(...) ..."}" },
	  { "personaId": "caretaker", "text": "${targetLang === "zh" ? "（...） ..." : "(...) ..."}" }
	],
	"options": ["...", "...", "..."]
  }
  
  Each persona should speak ONCE in this round.
  The tone should reflect genuine internal conflict.
  
  Round input (what the user just said, can be empty on first round):
  ${userInput ? userInput : "(no new user input — begin the debate)"}
  
  Now produce the JSON ONLY:
  `.trim();
  
		const one = await callGeminiText(env, prompt);
		if (!one.ok) {
		  return new Response(
			JSON.stringify({
			  error: "Gemini API error",
			  status: one.status,
			  details: one.details,
			}),
			{
			  status: 502,
			  headers: { ...corsHeaders, "Content-Type": "application/json" },
			}
		  );
		}
  
		const rawText = one.text;
  
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
