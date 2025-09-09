### 목적
`ChartManager` 메소드 전체를 훑어 의미가 같은 인수를 한 눈에 통일할 수 있도록 규칙과 메소드별 권장 시그니처를 표로 정리했습니다. 코드는 수정하지 않았습니다.

## 표 1) 인수 표기 통일 규칙(권장안)

| 의미 | 현재 표기 예 | 제안 통일 표기 | 설명/규칙 |
|---|---|---|---|
| 현재봉으로부터의 오프셋(0=현재봉, 1=1봉전) | n, before, m(일부) | offset | 봉 인덱스는 항상 `offset`으로 통일 |
| 조회 길이/윈도우(몇 개 봉을 대상으로 계산) | n | length | 집계·검색 대상 개수 |
| 시작 기준 오프셋(어디서부터 length를 잡는가) | m | start_offset | `length`와 같이 쓰일 때 시작점은 `start_offset` |
| 이동평균 등 기간 수(윈도우 크기) | period, k, m | period | 지표 “기간”은 `period`; 특수한 경우 접두어 사용 |
| MA 기간(특화) | k, m | ma_period | 이동평균과 직결된 기간은 `ma_period`로 명시 |
| MACD 빠름/느림/시그널 기간 | fast, slow, signal | fast_period, slow_period, signal_period | 의미를 정확히 드러내도록 접두어 추가 |
| 상위 N개(탑 K) | cnt | top_k | 예: 거래량 상위 N개의 평균 |
| 비교 윈도우 크기(자신 포함 N봉 중 최대/최소 등) | cnt | window | “상위 N개”가 아니라 “N봉 비교 범위”일 때는 `window` |
| 최대 확인할 봉 수(루프 안전) | max_check | max_bars | 안전 상한은 `max_bars` |
| n번째 발생 | nth | nth | 그대로 사용(충분히 명확) |
| 퍼센트 임계치 | threshold, length(%) | threshold_pct, …_pct | 단위가 %면 이름에 `_pct` 접미사 사용 |
| 비율(배수) | up, down, k | …_ratio | 배수/비율은 `_ratio` 접미사, min/max 접두어로 방향 명시 |
| 날짜(YYYYMMDD) | dt | date | 포맷은 YYYYMMDD로 명시 |
| 변화율 임계치(%) | p | min_change_pct | “현재가 대비 몇 % 이상” 등의 임계치 |

규칙 예:
- 퍼센트: `…_pct`, 비율/배수: `…_ratio`
- 같은 의미가 복수로 동시에 필요할 때는 `start_offset`(시작점) + `length`(개수)를 함께 사용
- MA 전용 기간은 `ma_period`, 그 외 지표는 `period`

## 표 2) 메소드별 권장 시그니처(이름만 통일) — `ChartManager`

- 단일 `offset`만 받는 메소드 → `offset=0`으로 통일  
  대상: `c, o, h, l, v, a, red, blue, doji, body, body_top, body_bottom, body_center, up_tail, down_tail, length, body_pct, up_tail_pct, down_tail_pct, length_pct, gap_up, gap_down, is_doji, is_hammer, bar_time, bar_date, up_start, down_start, bar`

| 메소드 | 현행 시그니처 | 제안 시그니처 |
|---|---|---|
| c | (n=0) | (offset=0) |
| o | (n=0) | (offset=0) |
| h | (n=0) | (offset=0) |
| l | (n=0) | (offset=0) |
| v | (n=0) | (offset=0) |
| a | (n=0) | (offset=0) |
| red/blue/doji | (n=0) | (offset=0) |
| body/body_top/body_bottom/body_center | (n=0) | (offset=0) |
| up_tail/down_tail/length | (n=0) | (offset=0) |
| body_pct/up_tail_pct/down_tail_pct/length_pct | (n=0) | (offset=0) |
| gap_up/gap_down | (n=0) | (offset=0) |
| is_doji | (n=0, threshold=0.1) | (offset=0, threshold_pct=0.1) |
| is_hammer | (n=0) | (offset=0) |
| bar_time/bar_date | (n=0) | (offset=0) |
| up_start/down_start | (n=0) | (offset=0) |
| bar | (n=0) | (offset=0) |

- 캔들 특수 패턴

| 메소드 | 현행 시그니처 | 제안 시그니처 |
|---|---|---|
| marubozu | (n=0) | (offset=0) |
| long_body | (n=0, m=10, k=2.0) | (offset=0, length=10, min_body_ratio=2.0) |
| short_body | (n=0, m=10, k=0.5) | (offset=0, length=10, max_body_ratio=0.5) |
| is_shooting_star | (n=0, length=2.0, up=2.0, down=None) | (offset=0, min_up_tail_pct=2.0, min_up_tail_body_ratio=2.0, max_down_to_up_tail_ratio=None) |
| is_hanging_man | (n=0, length=2.0, down=2.0, up=None) | (offset=0, min_down_tail_pct=2.0, min_down_tail_body_ratio=2.0, max_up_to_down_tail_ratio=None) |
| is_engulfing | (n=0, body_pct=1.0, bullish=True) | (offset=0, min_body_pct=1.0, bullish=True) |
| is_harami | (n=0, body_pct=1.0, bullish=True) | (offset=0, min_body_pct=1.0, bullish=True) |

- 이동평균/지표

| 메소드 | 현행 시그니처 | 제안 시그니처 |
|---|---|---|
| ma | (period=20, before=0) | (period=20, offset=0) |
| get_ma | (period=20, count=1) | (period=20, length=1) |
| avg | (value_func, n, m=0) | (value_func, length, start_offset=0) |
| highest/lowest/sum | (value_func, n, m=0) | (value_func, length, start_offset=0) |
| eavg/wavg/stdev | (value_func, n, m=0) | (value_func, length, start_offset=0) |
| rsi | (period=14, m=0) | (period=14, offset=0) |
| macd | (fast=12, slow=26, signal=9, m=0) | (fast_period=12, slow_period=26, signal_period=9, offset=0) |
| bollinger_bands | (period=20, std_dev=2, m=0) | (period=20, std_dev=2, offset=0) |
| stochastic | (k_period=14, d_period=3, m=0) | (k_period=14, d_period=3, offset=0) |
| atr | (period=14, m=0) | (period=14, offset=0) |

- 추세/크로스

| 메소드 | 현행 시그니처 | 제안 시그니처 |
|---|---|---|
| trend_up | (n=0, m=20) | (offset=0, ma_period=20) |
| trend_down | (n=0, m=20) | (offset=0, ma_period=20) |
| reverse_up | (k=5, n=0) | (ma_period=5, offset=0) |
| reverse_down | (k=5, n=0) | (ma_period=5, offset=0) |
| cross_up/cross_down | (a_func, b_func) | (a_func, b_func) |

- 조건 기반 스캔/유틸

| 메소드 | 현행 시그니처 | 제안 시그니처 |
|---|---|---|
| bars_since | (condition_func) | (condition_func) |
| highest_since | (nth, condition_func, data_func) | (nth, condition_func, data_func) |
| lowest_since | (nth, condition_func, data_func) | (nth, condition_func, data_func) |
| value_when | (nth, condition_func, data_func) | (nth, condition_func, data_func) |
| indicator | (func, *args) | (func, *args) |
| get_obv_array | (count=10) | (length=10) |
| percent | (a, b, c=None, default=0) | (value, base, divisor=None, default=0) |

- 집계/검색

| 메소드 | 현행 시그니처 | 제안 시그니처 |
|---|---|---|
| longest_bar | (p=2.0, n=0) | (min_change_pct=2.0, offset=0) |
| get_highest_candle | (n=128, m=0) | (length=128, start_offset=0) |
| get_highest_volume | (n=128, m=0) | (length=128, start_offset=0) |
| past_bars | (dt=None) | (date=None) |
| segment_angle_slope | (n, m, max_daily_pct=0.30) | (length, offset, max_daily_pct=0.30) |
| get_extremes | (n=128, m=1) | (length=128, start_offset=1) |
| top_volume_avg | (n=128, cnt=10, m=1) | (length=128, top_k=10, start_offset=1) |
| top_amount_avg | (n=128, cnt=10, m=1) | (length=128, top_k=10, start_offset=1) |
| get_close_tops | (n=128, cnt=80, m=1) | (length=128, window=80, start_offset=1) |

- 연속/패턴 카운트

| 메소드 | 현행 시그니처 | 제안 시그니처 |
|---|---|---|
| consecutive_count | (condition_func, m=0, max_check=128) | (condition_func, offset=0, max_bars=128) |
| consecutive_true_false | (condition_func, m=0, max_check=100) | (condition_func, offset=0, max_bars=100) |
| streak_pattern | (condition_func, pattern, m=0, max_check=100) | (condition_func, pattern, offset=0, max_bars=100) |
| find_last_condition_break | (condition_func, m=0, max_check=128) | (condition_func, offset=0, max_bars=128) |

- 기타

| 메소드 | 현행 시그니처 | 제안 시그니처 |
|---|---|---|
| rise_pct_since_ma_cross_up | (n=0, period=5) | (offset=0, ma_period=5) |
| clear_cache | (code=None) | (code=None) |
| get_raw_data | () | () |

요청하시면 위 권장안대로 실제 코드에 반영하는 “에디트 계획(안전 범위/호환성 포함)”도 제시하겠습니다.

- 이번 변경의 핵심 효과
  - 같은 의미의 인수를 전부 `offset/length/start_offset/period` 축으로 정규화
  - 퍼센트/배수는 `_pct`/`_ratio` 접미사로 즉시 식별 가능
  - MA·MACD 등 지표 전용 기간 명칭을 명확화해 오독 방지