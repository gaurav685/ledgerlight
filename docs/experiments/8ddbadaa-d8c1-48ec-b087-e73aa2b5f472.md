# Experiment 8ddbadaa-d8c1-48ec-b087-e73aa2b5f472 (generated)

git SHA: `707fb229be33e0480732ae84a14f52a17958a911`

## Config

```json
{
  "command": "backtest",
  "seed": 42,
  "data_snapshot_hash": "cce45ab1b1342582192d76308b8b5d93605f3924b1a5b382bcf1c8bab55eb17a"
}
```

## Data snapshot hashes

```json
{
  "dataset": "cce45ab1b1342582192d76308b8b5d93605f3924b1a5b382bcf1c8bab55eb17a"
}
```

## Metrics

```json
{
  "B0_base_rate": {
    "pr_auc": 0.275,
    "roc_auc": 0.5459104938271605,
    "brier_skill_score": -0.2131525424258307,
    "n": 144
  },
  "B1_rating_rule": {
    "pr_auc": 0.3544238683127572,
    "roc_auc": 0.6342592592592593,
    "brier_skill_score": -0.2962962962962963,
    "n": 144
  },
  "B2_price_liquidity": {
    "pr_auc": 0.44444444444444453,
    "roc_auc": 0.5744598765432098,
    "brier_skill_score": -0.18666868569061723,
    "n": 144
  },
  "B3_structured_rule_verified": {
    "pr_auc": 0.23727513864839656,
    "roc_auc": 0.5230195473251028,
    "brier_skill_score": -0.8548215077327361,
    "n": 144
  },
  "LightGBM": {
    "pr_auc": 0.26666666666666666,
    "roc_auc": 0.5420524691358024,
    "brier_skill_score": -0.2207377758831226,
    "n": 144
  },
  "positive_counts": {
    "company_month_rows": 36,
    "distinct_positive_companies": 4,
    "distinct_positive_events": 5,
    "is_inconclusive": true
  }
}
```
