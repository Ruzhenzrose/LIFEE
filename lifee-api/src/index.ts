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
	prompt?: string | { en: string; zh: string }; // persona-specific style/behavior instruction (optional)
  };
  
  type Body = {
	situation?: string;
	question?: string;
	userInput?: string; // 前端每一轮用户输入（可选）
	personas?: Persona[];
	birthDate?: string; // YYYY-MM-DD (Gregorian)
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
  
  export default {
	async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
	  // ---- CORS preflight ----
	  if (request.method === "OPTIONS") {
		return new Response(null, { headers: corsHeaders });
	  }
  
	  const url = new URL(request.url);
	  const stream = url.searchParams.get("stream") === "1";
  
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
		  };
		});
  
		const userInput = body.userInput?.trim() || "";
		const targetLang = decideTargetLang(userInput, situation);
		const TARGET_LANGUAGE = langName(targetLang);
		const stageExample = targetLang === "zh" ? "（皱眉）" : "(frowns)";

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

				  const personaPrompt = `
You are not an assistant. You are one inner voice in an internal debate.
You speak ONLY as this persona: ${p.name} (${p.id}).

TARGET_LANGUAGE: ${TARGET_LANGUAGE}

Context:
${situation}
${birthDate ? `\nUser birth date (YYYY-MM-DD, optional reference): ${birthDate}` : ""}

Persona instruction:
${personaInstruction}

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
	  return `- ${p.id}: ${p.name}${style}`;
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