# Sign Static Check Report

## Contract

- Official formula fields must use signed accumulation: buy is positive, sell is negative.
- Official signed fields: `CH_rule_t`, `Q_rule_t`, `R_seed_t`, `signed_large_active_amount`, `signed_mix_qr_amount`, `signed_amount`.
- Gross display fields may remain non-negative and must not be treated as the formula source of truth.

## Results

- `PASS` trade side sign maps sell to negative (src\scheduler.py)
- `PASS` trade signed amount uses side sign (src\scheduler.py)
- `PASS` active large signed amount uses active sign (src\scheduler.py)
- `PASS` rule event stores signed amount (src\capital_rule_engine.py)
- `PASS` rule window accumulates signed amount (src\capital_rule_engine.py)
- `PASS` legacy signed buckets keep signed amount (src\capital_rule_engine.py)
- `PASS` pid reads official signed rule fields (src\pid_decomposer.py)
- `PASS` capital model rule flow intention uses signed direction (src\capital_model.py)

## Gross Display Fields

These fields are intentionally gross/display counters and can be positive for sell-side volume:

- `signal_deal_buy_amount`
- `signal_deal_sell_amount`
- `large_active_buy_amount`
- `large_active_sell_amount`
- `small_passive_buy_amount`
- `small_passive_sell_amount`

## Summary

- total_checks: `8`
- failed_checks: `0`
