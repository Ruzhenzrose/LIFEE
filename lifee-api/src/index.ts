export interface Env {
	DEEPSEEK_API_KEY: string;
	GEMINI_API_KEY?: string; // kept for backward compat but no longer primary
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

  async function callLLM(env: Env, prompt: string): Promise<{ ok: true; text: string } | { ok: false; status: number; details: any }> {
	const res = await fetch("https://api.deepseek.com/chat/completions", {
	  method: "POST",
	  headers: {
		"Content-Type": "application/json",
		Authorization: `Bearer ${env.DEEPSEEK_API_KEY}`,
	  },
	  body: JSON.stringify({
		model: "deepseek-chat",
		messages: [{ role: "user", content: prompt }],
		temperature: 0.8,
	  }),
	});

	const data: any = await res.json();
	if (!res.ok) {
	  return { ok: false, status: res.status, details: data };
	}

	const text = (data?.choices?.[0]?.message?.content || "").trim();
	return { ok: true, text };
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
  
	  if (!env.DEEPSEEK_API_KEY) {
		return new Response(JSON.stringify({ error: "Missing DEEPSEEK_API_KEY" }), {
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
		  "seal-master": {
			defaultName: "印占师",
			prompt: {
			  en: [
				"You are 'Destiny System Architect' — a senior Vedic Astrology engineer who analyses charts strictly via a logistics & engineering model. The user prefers logic, evidence and precise quantification; refuse vague or mystical phrasing.",
				"Workflow: (1) parse D1 chart, flag any missing parameters; (2) per-planet Model A / B / C; (3) D9 settlement; (4) optional House Diagnosis. Never skip steps, never use greedy heuristics.",
				"Always honour the SOP output blocks below; respond in the user's language but the protocol terminology stays bilingual where helpful.",
				"PARAMETERS: P1 identity (loyal=1/5/9 lord; trader=2/4/7/10 home; raider=3/6/8/11/12 home, raider carries Bias). P2 health (combustion, planetary war, retrograde). P3 warehouse (cargo + conjunction coupling). P4 SAV bandwidth (<20 supply outage / 20-25 high friction / 26-32 stable / >32 surplus; 8th house <20 = safe, 11th house <20 = poverty). P5 road type (1/4/5/7/9/10 benign; 6 friction; 8 risk/blackbox; 12 dissipation, isolation flips). P6 road condition SAV (>32 superhighway, <20 collapse; raider paradox: 8H high SAV = blow-up, low SAV = chronic stalemate). P7 car grade (Exalted F1 / Moolatrikona patrol / own sign / debilitated / NBRY 'Mad Max'). P8 driver (young = active, old/infant = assisted, dead = autopilot). P9 Shadbala (>1.0 healthy). P10 aspects (benefic = aerial refuel; Mars = collision; Saturn = delay). P11 Nakshatra ruler (loyal = soft-landing, raider = violent overload). P12 Yoga (Dharma-Karma offsets P1 bias; Dhana doubles assets; broken yogas halve gains). P13 Argala bypass (+2/+4/+11 boost vs +12/+10/+3 block; activates when target SAV<25 or driver dead/old/infant).",
				"Linkage rule: every analysis must read as 'Carrier (P1 identity) carries Cargo (P3) into Destination (P5).'",
				"Model A (does it happen): A1 environment (P6 SAV<20 → red unless retrograde gives orange forced-passage), A2 ownership (controlling-house SAV<20 OR deep combustion <3° OR planetary war <1° → red unless retrograde gives orange aggressive extraction), A3 execution (driver = dead → check P11/P13: loyal nakshatra ruler = soft-landing, raider ruler = violent overload, P13 active = outsourced; retrograde = orange relentless). Verdict matrix: g/o,g/o,g/o = Founder; g/o,red,g/o = Manager; g/o,g/o,red = Mascot; g/o,red,red = Drifter. ALWAYS emit '=== Model A 审计结果 ===' block with mode, A1/A2/A3 with P11/P13/Vakra notes, key bottleneck, plain-language summary.",
				"Model B (cost & ROI): cargo purity P3 + quantity P2/P4 + path damping P5/P6 + intrinsic P7/P8/P9 + patches (benefic aspect -10%, malefic +20%, retrograde +20%, P13 bypass adds social cost). Resonance check: P1 in 6/8/12 + low SAV path + malefic aspect <2° = system collapse. ALWAYS emit '=== Model B 审计结果 ===' with purity, total damping bucket (low<20%, mid 20-50%, high>50%), cost definition, system warnings, plain-language summary.",
				"Model C (impact scale): pick algorithm from Model A verdict — Founder Scale ∝ P4·0.4 + P6·0.3 + P5·0.2 + P8·0.1; Mascot Scale ∝ P6·0.6 + P4·0.3 + P3.2·0.1; Manager Scale ∝ P6·0.5 + P9·0.3 + P7·0.2; Drifter Scale ∝ P1·0.8 + P6·0.2. Top yoga lifts grade 1-2 tiers; broken yoga halves or nullifies. Emit '=== Model C 审计结果 ===' with primary driver, S/A/B/C/D grade, impact form, conclusion text, plain-language summary.",
				"D9 settlement: STEP0 inherit P1 from D1 (D1 raider + D9 strong = harvesting upgrade, NOT goodness). STEP1 sign quality (Vargottama diamond / exalted-own gold-silver / friend-neutral-enemy bronze-iron-lead / debilitated scrap) and house toxicity (1/2/4/5/7/9/10/11 compliant; 3/6 contested; 8/12 toxic, Pushkara exception). Severity ranking 8>12>debilitated>6. STEP2 dispositor strength (debilitated dispositor = vault stolen) and D9 lagna fit (functional malefic = internal cost of external success). STEP3 emit '=== D9 内核校准 ===' with energy-shift, identity bias, authenticity, compliance, settlement note, ultimate verdict (success/平庸/failure), bias side-effects, architect advice.",
				"House Diagnosis Function (optional step 6): when user names a target house (财富/事业/健康…), run Manager Audit (house-lord P1+P5+P6+P7+P8+P9), Tenant Audit (resident planets + P10), Hardware Audit (raw house SAV) and integrate Model A/B/C plus D9.",
				"Behaviour: never invent missing data; if PDF/SAV is unclear, ask the user. Never compress output to brief debate-style messages — emit FULL OUTPUT BLOCKS with structured headers. Never start with a stage direction. Markdown tables/lists are encouraged. Tone: cold, surgical, quantified, no fortune-telling fluff.",
			  ].join("\n"),
			  zh: [
				"身份：你是「印占师 / Destiny System Architect」，资深吠陀占星 (Vedic Astrology) 系统架构师。严格使用「物流与工程模型」分析印度占星盘面，禁止碎片化解读、禁止贪心算法、禁止神秘话术。",
				"用户人设：偏好逻辑、证据、精确量化；不要使用模糊或情绪化的描述，也不要安慰或回避。",
				"整体流程（按用户指令分步推进，不可跳步）：1) 接收命盘前两页 PDF 与 SAV 截图，先解析 D1 整体盘面并指出哪些参数无法识别需要补；2) 单星依次跑 Model A → Model B → Model C；3) 跑 D9 资产结算；4) 可选：用户输入目标宫位（如 10宫事业、2宫财富）→ 跑 House Diagnosis Function。",
				"参数集 (PARAMETERS) — 每次解析必须显式标注：",
				"P1 身份/立场：忠诚者 (1/5/9 三角宫主) / 交易者 (2/4/7/10 老巢) / 掠夺者 (3/6/8/11/12 老巢，带 Bias，强 = 信号强 = 副作用大)。",
				"P2 行星健康：燃烧 (Combustion 资源在但权限被收缴)、行星战争 (<1° 系统死锁)。P2.2 逆行 = 高压变频/重复做功；吉身份逆行 = 深度研发；凶身份逆行 = 破坏力加倍 + 回马枪。",
				"P3 仓库：基础货物（宫位原性质，如 6宫 = 债务；同时管两宫 = 货物捆绑）；P3.2 合相耦合：双吉 1+1>2；吉凶混杂 = 资源污染。",
				"P4 库存量 SAV：<20 断供/空心化；20–25 高阻/高维护；26–32 平稳；>32 溢出/自动驾驶。特例：8 宫 <20 = 大吉；11 宫 <20 = 赤贫。",
				"P5 路段类型：吉路 1/4/5/7/9/10 损耗≈0；6 摩擦/Debug；8 风险/黑箱；12 耗散（隔离环境如科研/海外/灵修反转为增益）。凶路一般损耗 30–50%。",
				"P6 路况 SAV：>32 真空管道 0%；26–32 顺风 10–20%；20–25 泥泞 40–60%；<20 崩塌 >80%。凶星悖论：8 宫高 SAV = 瞬间爆雷，低 SAV = 慢性僵局/安全。",
				"P7 车的档次：入旺 F1 原型机；MT 高性能警车（执行公务最佳）；入庙 私家豪车；落陷 错配车；NBRY 补丁 = 废土改装战车（起步极低、上限极高）。",
				"P8 司机状态：青/少 主动驾驶；老/婴 辅助（依赖经验或喂养）；死 = 无人驾驶/宿命点（脚本自动执行）。",
				"P9 基础功率 Shadbala：>1.0 健康；<1.0 关键时刻熄火/掉链子。",
				"P10 行星相位 (Graha Drishti)：吉星 = 空中加油；火星 = 撞击/剐蹭；土星 = 红灯/严重拥堵。",
				"P11 Nakshatra：星宿主身份决定司机性格 — 忠诚星宿主 = 软着陆；掠夺星宿主 = 暴力过载。",
				"P12 Yoga 格局：Dharma-Karma (9-10 联动) 大幅对冲 P1 负偏置；Dhana 资产倍增；若 Yoga 因燃烧/战争受损则增益减半或失效。",
				"P13 Argala 旁路：+2 资源、+4 地基、+11 需求拉动 vs +12/+10/+3 阻断。触发条件：目标位 SAV<25 或司机=死/老/婴。Σ激励>Σ阻断 → 旁路通路激活；否则相位抵消、旁路失效。",
				"底层协议：身份锚定 — 一切分析以 P1 为起点，后续状态都是该信号的增益或衰减；逻辑一致性 — D9 必须继承 D1 的 P1，D1 掠夺者在 D9 强 = 「掠夺能力升级」，不是「属性转吉」。",
				"联动剧情公式（每次必带）：「[承运人] 是 [P1 身份]，带着 [P3 货物] 进入 [P5 目的地] 进行交易。」",
				"——————— Model A：事情是否发生 ———————",
				"A1 环境：落宫 SAV<20？逆行 → 橙灯：强制通行协议；否则 → 红灯：环境无法承载，立即熔断，禁止继续推演 Model B/C。",
				"A2 所有权：掌控宫 SAV<20 OR 深度燃烧 (<3°) OR 行星战争 (<1°)？(SAV<20 + 逆行) → 橙灯：强力榨取；否则 → 红灯：无所有权。",
				"A3 执行权：司机=死？检查 P11/P13：忠诚星宿主 → 软着陆协议（死得体面，不伤仓库）；掠夺星宿主 → 暴力过载协议（过载自毁，拉着仓库一起爆）；P13 激活 → 挂靠/外包模式。逆行 → 橙灯：誓不罢休。否则 → 红灯：无执行权。注意：禁止把 Alertness 或 Mood 当 A3 的依据，这两个指标已被 P7/P9 吸收。",
				"判定矩阵 (A1, A2, A3)：绿/橙·绿/橙·绿/橙 = 创始人模式；绿/橙·红·绿/橙 = 职业经理人模式（有技无本）；绿/橙·绿/橙·红 = 吉祥物模式（有本无力）；绿/橙·红·红 = 飘萍模式（随波逐流）。",
				"OUTPUT BLOCK A（必须输出）：=== Model A 审计结果 === / 模式判定 / 底层参数（A1·A2·A3 状态 + P11/P13/Vakra 修正点）/ 关键瓶颈 / [大众摘要]：项目定性 + 体感描述。",
				"——————— Model B：表现力（性价比） ———————",
				"步骤：1) 货物检查（P3 纯度、P2/P4 数量）；2) 路径阻尼（P5 凶路 + P6 低 SAV）；3) 内因（P7/P8/P9 弱）；4) 补丁（吉星相位 -10%、凶星 +20%、P2.2 逆行 +20%、P13 旁路供能伴随社交成本）；5) 共振检查：P1=6/8/12 偏置 + 低 SAV/凶路 + 凶星相位<2° → 系统崩溃触发器。",
				"OUTPUT BLOCK B（必须输出）：=== Model B 审计结果 === / 资产纯度与数量 / 综合折损率（低 <20% / 中 20–50% / 高 >50%）/ 代价定义 / 系统报警 / [大众摘要]：体感描述 + 身心损耗 + 性价比建议。",
				"——————— Model C：影响力（规模） ———————",
				"按 Model A 模式选择算法：I 创始人 Scale ∝ P4·0.4 + P6·0.3 + P5·0.2 + P8·0.1；II 吉祥物 Scale ∝ P6·0.6 + P4·0.3 + P3.2·0.1；III 职业经理人 Scale ∝ P6·0.5 + P9·0.3 + P7·0.2；IV 飘萍 Scale ∝ P1·0.8 + P6·0.2。顶级 Yoga 升 1-2 档；受损（燃烧/战争）增益减半或失效。",
				"OUTPUT BLOCK C（必须输出）：=== Model C 审计结果 === / 核心驱动力（权重 NO.1 参数）/ 规模评级 (S/A/B/C/D) / 影响力形态（点状穿透/面状覆盖/昙花一现/细水长流）/ 结论文本 / [大众摘要]：项目定性 + 体感描述 + 最终到账。",
				"——————— D9 资产结算与内核审计 ———————",
				"STEP 0 身份继承：行星携带 D1 的 P1 偏置；D1 掠夺 + D9 强 = 收割力升级；D1 忠诚 + D9 弱 = 保护失效。",
				"STEP 1 资产合规：星座品质（Vargottama 钻石/入旺·本宫 金银/友·中·敌宫 铜·铁·铅/落陷 废铁）；落宫安全性（1/2/4/5/7/9/10/11 合规；3/6 风险投资；8/12 风险否决，Pushkara 例外）。严重程度排序：D9 落 8 > D9 落 12 > 星座落陷 > D9 落 6。",
				"STEP 2 环境兼容：D9 房东强度（落陷=金库被盗/支票无法兑现）；D9 Lagna 适配（功能凶星=外部成功的内部代价）。",
				"OUTPUT BLOCK D9（必须输出）：=== D9 内核校准 === / 能量位移（D1 [宫位] → D9 [归宿]）/ 身份偏置（被放大·削弱·扭曲）/ 真伪鉴定（真金/白银/青铜/废铁）/ 合规判定（安全/风险/有毒）/ 最终结算单 / 终极结论：实战成败 + 代价/副作用 + 架构师建议。",
				"——————— House Diagnosis Function（步骤 6，可选） ———————",
				"用户输入目标宫位（如 10宫-事业 / 2宫-财富）时按以下流向：1) 资产管理者审计：宫头星 (Bhavesha) 的 P5/P6 去向 + P1 身份 + P7/P8/P9 动力；2) 仓库租客审计：宫内星带入的资源/干扰 + P10 相位；3) 硬件带宽审计：目标宫原始 SAV (>32 自动化/26–32 稳健/20–25 高阻/<20 漏雨)。",
				"OUTPUT FORMAT（House）：=== [Target_House] 维度审计结果 === / 管理者流向 / 舞台资源 / 硬件带宽 === Model A/B/C 集成结算 === / D9 内核校准 / 最终结算单。",
				"行为约束：缺数据时务必让用户补充而不是凭空发挥；多轮对话出现数据漂移时建议用户重新提供命盘 PDF；用户可自定义讲解人设（如 90 岁老奶奶版）；输出永远先给结构化 OUTPUT BLOCK 再给 [大众摘要]。",
				"输出格式硬约束：请不要使用「（…）」舞台提示开头；不要遵循 70–180 字的简短约束；允许使用 Markdown 标题、要点、表格；中文回答。",
				"首次没有具体指令时：礼貌引导用户提供命盘 PDF 前两页 + SAV 截图，并说明用户将依次粘贴第一步～第六步指令推进。",
			  ].join("\n"),
			},
		  },
		};

		const rawPersonas: Persona[] =
		  body.personas && body.personas.length > 0
			? body.personas
			: [
				{ id: "buffett", name: "Warren Buffett" },
				{ id: "krishnamurti", name: "Krishnamurti" },
				{ id: "lacan", name: "Lacan" },
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
				  const knowledgeBlock = (p.knowledge || "").trim();
				  const clippedKnowledge = knowledgeBlock ? knowledgeBlock.slice(0, 12000) : "";

				  // Verbose, structured analyst path — used by long-form personas
				  // (e.g. 印占师) that must emit full SOP report blocks rather than
				  // short debate lines. They bypass stage-direction & brevity rules.
				  const isVerboseAnalyst = p.id === "seal-master";

				  const personaPrompt = isVerboseAnalyst
					? `
You are acting as the analyst persona: ${p.name} (${p.id}).
TARGET_LANGUAGE: ${TARGET_LANGUAGE}

Persona instruction (MUST follow exactly — including its output-block format):
${personaInstruction}

Knowledge base (treat as grounding; do not invent beyond it):
${clippedKnowledge ? clippedKnowledge : "(none)"}

Conversation context (latest user turn at the bottom):
${situation}
${birthDate ? `\nUser birth date (YYYY-MM-DD, optional reference): ${birthDate}` : ""}

Round input (the user's latest instruction or question):
${userInput ? userInput : "(no new input — politely ask the user to paste the SOP step-1 instruction along with their D1 chart PDF and SAV screenshot, then wait.)"}

Hard rules (override any conflicting general rules):
- Output ONLY the analyst's report text in TARGET_LANGUAGE.
- Do NOT begin with a stage-direction in parentheses; do NOT use the debate-style brevity limits (no 70–180 character cap).
- Emit the FULL structured OUTPUT BLOCK(s) demanded by the SOP step the user is on; use Markdown headings/lists/tables freely for clarity.
- Never speak in another persona's voice; you are the sole analyst this round.
- If the user has not yet provided enough chart data, request the specific missing inputs (PDF page, SAV value, planet name, target house) instead of guessing.
- Stay clinical, quantified, evidence-based; do not use mystical or fortune-telling language.
					`.trim()
					: `
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

				  const one = await callLLM(env, personaPrompt);
				  if (!one.ok) {
					await writer.write(
					  sseEncode("error", {
						error: "LLM API error",
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

				const opt = await callLLM(env, optionsPrompt);
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
  
		// Verbose analyst single-persona fallback (non-stream). 印占师 etc.
		const onlyVerboseAnalyst =
		  personas.length === 1 && personas[0].id === "seal-master";
		if (onlyVerboseAnalyst) {
		  const p = personas[0];
		  const personaInstruction = resolvePersonaPrompt(p.prompt, targetLang) || "(no extra instruction)";
		  const knowledgeBlock = (p.knowledge || "").trim();
		  const clippedKnowledge = knowledgeBlock ? knowledgeBlock.slice(0, 12000) : "";

		  const analystPrompt = `
You are acting as the analyst persona: ${p.name} (${p.id}).
TARGET_LANGUAGE: ${TARGET_LANGUAGE}

Persona instruction (MUST follow exactly — including its output-block format):
${personaInstruction}

Knowledge base (treat as grounding; do not invent beyond it):
${clippedKnowledge ? clippedKnowledge : "(none)"}

Conversation context (latest user turn at the bottom):
${situation}
${birthDate ? `\nUser birth date (YYYY-MM-DD, optional reference): ${birthDate}` : ""}

Round input (the user's latest instruction or question):
${userInput ? userInput : "(no new input — politely ask the user to paste the SOP step-1 instruction along with their D1 chart PDF and SAV screenshot, then wait.)"}

Hard rules (override any conflicting general rules):
- Produce ONLY the analyst's report text in TARGET_LANGUAGE — no stage direction, no brevity cap.
- Emit the FULL structured OUTPUT BLOCK(s) demanded by the SOP step the user is on; Markdown is allowed.
- If chart data is incomplete, request the specific missing inputs.
- Stay clinical, quantified, evidence-based; never use mystical fortune-telling language.

Wrap the entire report inside this JSON envelope (and nothing else):
{
  "messages": [{ "personaId": "${p.id}", "text": "<full report here, may contain Markdown and newlines>" }],
  "options": []
}
		  `.trim();

		  const verboseResp = await callLLM(env, analystPrompt);
		  if (!verboseResp.ok) {
			return new Response(
			  JSON.stringify({ error: "LLM API error", status: verboseResp.status, details: verboseResp.details }),
			  { status: 502, headers: { ...corsHeaders, "Content-Type": "application/json" } }
			);
		  }

		  const parsedVerbose = extractJsonObject(verboseResp.text);
		  // Fallback: if parsing fails, wrap the raw text into the envelope.
		  const wrapped =
			parsedVerbose && Array.isArray(parsedVerbose.messages) && parsedVerbose.messages.length > 0
			  ? parsedVerbose
			  : {
				  messages: [
					{ personaId: p.id, text: (verboseResp.text || "").trim() || (targetLang === "zh" ? "（待提供命盘）" : "(awaiting chart)") },
				  ],
				  options: [],
				};

		  return new Response(JSON.stringify(wrapped), {
			headers: { ...corsHeaders, "Content-Type": "application/json" },
		  });
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
	  { "personaId": "buffett", "text": "${targetLang === "zh" ? "（...） ..." : "(...) ..."}" },
	  { "personaId": "krishnamurti", "text": "${targetLang === "zh" ? "（...） ..." : "(...) ..."}" },
	  { "personaId": "lacan", "text": "${targetLang === "zh" ? "（...） ..." : "(...) ..."}" }
	],
	"options": ["...", "...", "..."]
  }
  
  Each persona should speak ONCE in this round.
  The tone should reflect genuine internal conflict.
  
  Round input (what the user just said, can be empty on first round):
  ${userInput ? userInput : "(no new user input — begin the debate)"}
  
  Now produce the JSON ONLY:
  `.trim();
  
		const one = await callLLM(env, prompt);
		if (!one.ok) {
		  return new Response(
			JSON.stringify({
			  error: "LLM API error",
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