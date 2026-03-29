"""
AI prompt for quantitative decision analysis.

The AI is asked to output structured JSON with multi-dimensional scoring
for each option the user faces.
"""

# The 6 analysis dimensions
DIMENSIONS = [
    {"key": "financial",  "label": "💰 财务影响",  "label_en": "Financial Impact"},
    {"key": "risk",       "label": "⚠️ 风险水平",  "label_en": "Risk Level"},
    {"key": "growth",     "label": "📈 成长潜力",  "label_en": "Growth Potential"},
    {"key": "time_cost",  "label": "⏰ 时间成本",  "label_en": "Time Cost"},
    {"key": "wellbeing",  "label": "😊 幸福感",    "label_en": "Wellbeing"},
    {"key": "feasibility","label": "✅ 可行性",    "label_en": "Feasibility"},
]

DECISION_ANALYSIS_PROMPT = """\
你是一位精通量化决策的分析师。用户面临一个人生抉择，请用数学模型与数据帮助他分析。

要求：
1. 提炼出 2-4 个可选方案（options）。
2. 对每个方案，在以下 6 个维度上打分（0-100）：
   - financial: 财务影响（越高获益越大）
   - risk: 风险水平（越高风险越大，注意：这里高分=高风险）
   - growth: 成长潜力（越高越好）
   - time_cost: 时间成本（越高消耗越大，高分=更费时间）
   - wellbeing: 幸福感/生活质量（越高越好）
   - feasibility: 可行性（越高越易达成）
3. 对每个方案给出 expected_value（期望值，0-100，综合评估）。
4. 对每个方案给出三种情景分析：
   - best_case: 最佳情景（一句话描述）
   - worst_case: 最差情景（一句话描述）
   - most_likely: 最可能情景（一句话描述）
5. 最后给出 recommendation：一段详细、有深度的综合分析与建议（至少200字）。

请严格以如下 JSON 格式输出（不要有其它内容）：
{
  "options": [
    {
      "name": "方案名称",
      "description": "一句话简介",
      "scores": {
        "financial": 70,
        "risk": 40,
        "growth": 85,
        "time_cost": 60,
        "wellbeing": 75,
        "feasibility": 65
      },
      "expected_value": 72,
      "scenarios": {
        "best_case": "...",
        "worst_case": "...",
        "most_likely": "..."
      }
    }
  ],
  "recommendation": "详细的综合分析与建议..."
}
"""
