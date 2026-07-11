# 100 Stock Replay Report

## Batch Summary

- trade_date: `20260708`
- sample_count: `75`
- output_count: `100`
- imputed_output_count: `25`
- stock_universe_size: `100`
- stock_list_file: `C:\level-2-ana\data\百只股票样本.csv`
- stock_offset: `0`
- stock_limit: `None`

## Missing And Imputed Symbols

- missing_symbol_count: `25`
- missing_symbols: `603773.SH, 605006.SH, 603779.SH, 605287.SH, 605389.SH, 605366.SH, 605299.SH, 605162.SH, 605069.SH, 603717.SH, 603721.SH, 603937.SH, 688496.SH, 688509.SH, 605066.SH, 603918.SH, 603679.SH, 603936.SH, 603686.SH, 603700.SH, 688560.SH, 603893.SH, 688082.SH, 688008.SH, 688169.SH`
- incomplete_stock_dir_count: `4`

## Warnings

- Missing raw data for requested symbols: 603773.SH, 605006.SH, 603779.SH, 605287.SH, 605389.SH, 605366.SH, 605299.SH, 605162.SH, 605069.SH, 603717.SH, 603721.SH, 603937.SH, 688496.SH, 688509.SH, 605066.SH, 603918.SH, 603679.SH, 603936.SH, 603686.SH, 603700.SH, 688560.SH, 603893.SH, 688082.SH, 688008.SH, 688169.SH
- Skipped incomplete stock dirs: 688169.SH(trades,orders,snapshots); 688496.SH(trades,orders,snapshots); 688509.SH(trades,orders,snapshots); 688560.SH(trades,orders,snapshots)
- Imputed missing symbols with market-average defaults: 603773.SH, 605006.SH, 603779.SH, 605287.SH, 605389.SH, 605366.SH, 605299.SH, 605162.SH, 605069.SH, 603717.SH, 603721.SH, 603937.SH, 688496.SH, 688509.SH, 605066.SH, 603918.SH, 603679.SH, 603936.SH, 603686.SH, 603700.SH, 688560.SH, 603893.SH, 688082.SH, 688008.SH, 688169.SH

## Performance

- total_seconds: `274.622711`
- sample_build_seconds: `272.415492`
- pattern_seconds: `0.129583`
- capital_seconds: `0.960771`
- market_seconds: `0.002122`
- export_seconds: `0.036146`

## Order Lifecycle Recovery

- order_age_total_count: `3883779`
- order_age_recovered_count: `3697597`
- order_age_missing_count: `186182`
- order_age_direct_count: `3299571`
- order_age_fifo_count: `398026`
- order_age_unresolved_count: `186182`
- order_age_recovery_ratio: `0.9520616389346561`

## Output Files

- market_snapshot_path: `E:\2026OPC大赛\自动化交易\比赛系统\output\20260708_20260710_023945\market_pid_snapshot.csv`
- market_report_path: `E:\2026OPC大赛\自动化交易\比赛系统\output\20260708_20260710_023945\market_regime_report.md`
- diagnostics_json_path: `E:\2026OPC大赛\自动化交易\比赛系统\output\20260708_20260710_023945\batch_diagnostics.json`
- distribution_csv_path: `E:\2026OPC大赛\自动化交易\比赛系统\output\20260708_20260710_023945\label_distribution.csv`
- submit_zip: `E:\2026OPC大赛\自动化交易\比赛系统\output\20260708_20260710_023945\submit.zip`
