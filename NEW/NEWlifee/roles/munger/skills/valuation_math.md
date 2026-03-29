---
name: valuation-math
description: Munger's valuation and decision math
trigger: [valuation, DCF, discount, earnings ratio, PE, PB, return, compound, rule of 72, margin of safety, intrinsic value, expensive, cheap, price, multiple]
---

## Munger's Valuation and Decision Math

Precise nonsense is worse than rough correctness. Valuation is not about calculating an exact number — that's self-deception. Valuation is about judging: is this price roughly reasonable.

### DCF: Discounted Cash Flow (the Intuitive Version)

Core logic: A dollar today is worth a dollar. A dollar one year from now is worth only about ninety cents — because you could take today's dollar and earn interest on it.

```
Intrinsic value = Sum of all future years' free cash flow, discounted to today
```

You don't need exact calculations. You just need to answer three questions:
1. How much cash can this business generate in the future? (The more predictable, the better)
2. How long can these cash flows last? (The moat determines this)
3. What discount rate? (Usually 10% — your minimum expected return)

If you need an Excel spreadsheet calculated to two decimal places to prove something is cheap, it's not cheap enough. Truly great opportunities are obvious from mental math alone.

### Reverse-Engineering Returns

Don't ask "what is this stock worth" — flip it and ask "at this price, what is the market assuming?"

```
Implied growth rate ≈ 1/PE × 100% + growth rate
```

Example: A company trading at PE = 50
- At zero growth, annual return = 1/50 = 2% (worse than a savings account)
- To achieve a 10% annual return, you need 8% annual growth
- Growing at 8% for ten consecutive years → earnings multiply by 2.16×. Can this company do that?

Most high-PE stocks embed unrealistic growth assumptions. The moment growth slows, valuation and earnings get hammered simultaneously.

### Margin of Safety: Buying Insurance

Margin of safety = Intrinsic value − Purchase price

```
Margin of safety % = (Intrinsic value − Price) / Intrinsic value
```

- Margin of safety ≥ 30%: Worth considering
- Margin of safety ≥ 50%: A good opportunity
- No margin of safety: No matter how great the company, if the price isn't right, don't buy

Why do you need a margin of safety? Because:
1. Your valuation might be wrong
2. The unexpected can happen
3. Humans are inherently overconfident

### Probability-Weighted Expected Value

Every decision is a bet. Smart bettors don't ask "will I win?" — they ask "are the odds worth it?"

```
Expected value = (good outcome × probability) − (bad outcome × probability)
```

Example: An investment
- 60% chance of gaining 50% → contributes +30%
- 40% chance of losing 30% → contributes −12%
- Expected value = +18% → worth doing

But also consider:
- Can you survive the bad outcome? (Never bet what you can't afford to lose)
- How reliable is your probability estimate? (Usually less reliable than you think)

### Rule of 72

Quick mental math for how long it takes to double your money:

```
Years to double ≈ 72 ÷ Annual return rate
```

- 8% annual return → 72/8 = 9 years to double
- 12% annual return → 72/12 = 6 years to double
- 24% annual return → 72/24 = 3 years to double

Works in reverse too:
- Someone promises 10× in 10 years → ~26% annualized (Buffett's long-term rate is barely over 20% — do you believe them?)
- Someone promises doubling in 3 years → ~26% annualized (same question)

When you see "high return" promises, run the Rule of 72 first — most unrealistic promises fall apart under this simple test.

### Valuation Sanity Check

No matter what method you used, always finish with a sanity check:
- What does this valuation imply about the company's profits in a few years? Is that realistic?
- Has any company in the same industry ever achieved this historically?
- If this assumption doesn't hold, how much do I lose?
- Am I concluding the valuation is reasonable because I like the story?
