====================================================
Failure Pattern Analysis
Model   : qwen/qwen3.5-9b
Dataset : Spider Hard+Extra Hard (n=224)
====================================================

### Overall
  Single-shot  (max_retries=1): 138/224 = 61.6%
  Feedback loop (max_retries=3): 154/224 = 68.8%
  Delta: +7.1%

### By hardness
  hard    1-shot 92/148 (62.2%)   3-retry 99/148 (66.9%)   delta +4.7%
  extra   1-shot 46/76 (60.5%)   3-retry 55/76 (72.4%)   delta +11.8%

### Accuracy by SQL pattern (gold SQL)
Pattern               n   1-shot  3-retry    delta
----------------------------------------------------
Nested SELECT       157   61.1%   70.1%  +8.9%
JOIN                105   50.5%   59.0%  +8.6%
NOT IN               46   73.9%   87.0%  +13.0%
GROUP BY             39   35.9%   43.6%  +7.7%
INTERSECT            38   55.3%   71.1%  +15.8%
EXCEPT               31   71.0%   83.9%  +12.9%
ORDER BY             29   65.5%   69.0%  +3.4%
HAVING               15   40.0%   46.7%  +6.7%
UNION                11   54.5%   45.5%  -9.1%

### Failure reasons
  1-shot    correct: 138  execution_error: 32  wrong_result: 54
  3-retry   correct: 154  wrong_result: 70

### Hardest patterns (single-shot EX < 50%)
  GROUP BY            n= 39  1-shot 35.9%  →  3-retry 43.6%
  HAVING              n= 15  1-shot 40.0%  →  3-retry 46.7%
