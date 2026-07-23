============================================================
Failure Pattern Analysis
Model   : qwen/qwen3.5-9b
Dataset : Spider Hard+Extra Hard (n=224)
============================================================

### Overall
  Single-shot   (max_retries=1): 141/224 = 62.9%
  Blind         (max_retries=3): 151/224 = 67.4%  delta +4.5%
  Feedback loop (max_retries=3): 158/224 = 70.5%  delta +7.6%
  Blind vs feedback: -3.1%

### By hardness
  hard    1-shot 95/148 (64.2%)   blind 97/148 (65.5%)   feedback 102/148 (68.9%)
  extra   1-shot 46/76 (60.5%)   blind 54/76 (71.1%)   feedback 56/76 (73.7%)

### Accuracy by SQL pattern (gold SQL)
Pattern               n   1-shot    blind   feedback   fb-delta
-----------------------------------------------------------------
Nested SELECT       157   63.7%   67.5%     72.6%  +8.9%
JOIN                105   52.4%   59.0%     62.9%  +10.5%
NOT IN               46   82.6%   80.4%     91.3%  +8.7%
GROUP BY             39   30.8%   43.6%     38.5%  +7.7%
INTERSECT            38   57.9%   81.6%     76.3%  +18.4%
EXCEPT               31   71.0%   71.0%     77.4%  +6.5%
ORDER BY             29   65.5%   65.5%     69.0%  +3.4%
HAVING               15   26.7%   40.0%     40.0%  +13.3%
UNION                11   45.5%   36.4%     54.5%  +9.1%

### Failure reasons
  1-shot      correct: 141  execution_error: 32  wrong_result: 51
  blind       correct: 151  execution_error: 14  wrong_result: 59
  feedback    correct: 158  wrong_result: 66

### Hardest patterns (single-shot EX < 50%)
  HAVING              n= 15  1-shot 26.7%  blind 40.0%  feedback 40.0%
  GROUP BY            n= 39  1-shot 30.8%  blind 43.6%  feedback 38.5%
  UNION               n= 11  1-shot 45.5%  blind 36.4%  feedback 54.5%
