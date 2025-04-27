# 스크립트 시스템 사용 안내서 - 부록

## 부록 A: 함수 레퍼런스

### A.1 기본 데이터 접근 함수

| 함수 | 설명 | 예시 | 반환값 |
|------|------|------|--------|
| `c([n])` | n봉 이전 종가 반환, 기본값은 0(현재 봉) | `c()`, `c(0)` - 현재봉 종가<br>`c(1)` - 1봉 전 종가 | 숫자(float) |
| `o([n])` | n봉 이전 시가 반환, 기본값은 0(현재 봉) | `o()`, `o(0)` - 현재봉 시가<br>`o(1)` - 1봉 전 시가 | 숫자(float) |
| `h([n])` | n봉 이전 고가 반환, 기본값은 0(현재 봉) | `h()`, `h(0)` - 현재봉 고가<br>`h(1)` - 1봉 전 고가 | 숫자(float) |
| `l([n])` | n봉 이전 저가 반환, 기본값은 0(현재 봉) | `l()`, `l(0)` - 현재봉 저가<br>`l(1)` - 1봉 전 저가 | 숫자(float) |
| `v([n])` | n봉 이전 거래량 반환, 기본값은 0(현재 봉) | `v()`, `v(0)` - 현재봉 거래량<br>`v(1)` - 1봉 전 거래량 | 숫자(int) |
| `a([n])` | n봉 이전 거래대금 반환, 기본값은 0(현재 봉) | `a()`, `a(0)` - 현재봉 거래대금<br>`a(1)` - 1봉 전 거래대금 | 숫자(float) |
| `time([n])` | n봉 이전 시간 반환(분봉에서만 유효) | `time()`, `time(0)` - 현재봉 시간<br>`time(1)` - 1봉 전 시간 | 문자열('HHmmss') |
| `today()` | 오늘 날짜 반환 | `today()` | 문자열('YYYYMMDD') |

### A.2 이동평균 관련 함수

| 함수 | 설명 | 예시 | 반환값 |
|------|------|------|--------|
| `ma(a, n[, m, k])` | a의 n기간 이동평균 (m봉 이전, k는 유형) | `ma(c, 5)` - 종가 5일 단순이동평균<br>`ma(c, 5, 1, 'e')` - 1봉 전 종가 5일 지수이동평균 | 숫자(float) |
| `avg(a, n[, m])` | a의 n기간 단순이동평균 (m봉 이전) | `avg(c, 5)` - 종가 5일 단순이동평균<br>`avg(c, 5, 1)` - 1봉 전 종가 5일 단순이동평균 | 숫자(float) |
| `eavg(a, n[, m])` | a의 n기간 지수이동평균 (m봉 이전) | `eavg(c, 12)` - 종가 12일 지수이동평균<br>`eavg(c, 12, 1)` - 1봉 전 종가 12일 지수이동평균 | 숫자(float) |
| `wavg(a, n[, m])` | a의 n기간 가중이동평균 (m봉 이전) | `wavg(c, 9)` - 종가 9일 가중이동평균<br>`wavg(c, 9, 1)` - 1봉 전 종가 9일 가중이동평균 | 숫자(float) |

**매개변수 설명**:
- `a`: 값을 가져올 함수 (c, o, h, l, v, a 등)
- `n`: 기간 (일수 또는 봉 수)
- `m`: 이전 봉 위치 (기본값 0, 현재 봉)
- `k`: 이동평균 유형 ('a': 단순, 'e': 지수, 'w': 가중)

### A.3 값 계산 함수

| 함수 | 설명 | 예시 | 반환값 |
|------|------|------|--------|
| `highest(a, n[, m])` | a의 n기간 중 최고값 | `highest(h, 10)` - 최근 10봉 중 최고 고가<br>`highest(c, 5, 1)` - 1봉 전부터 5봉간 최고 종가 | 숫자(float) |
| `lowest(a, n[, m])` | a의 n기간 중 최저값 | `lowest(l, 10)` - 최근 10봉 중 최저 저가<br>`lowest(c, 5, 1)` - 1봉 전부터 5봉간 최저 종가 | 숫자(float) |
| `stdev(a, n[, m])` | a의 n기간 표준편차 | `stdev(c, 20)` - 최근 20봉 종가의 표준편차 | 숫자(float) |
| `sum(a, n[, m])` | a의 n기간 합계 | `sum(v, 5)` - 최근 5봉 거래량 합계 | 숫자(float) |

### A.4 신호 함수

| 함수 | 설명 | 예시 | 반환값 |
|------|------|------|--------|
| `cross_up(a, b)` | a가 b를 상향돌파했는지 확인 | `cross_up(lambda c, n: ma(c, 5, n, 'a'), lambda c, n: ma(c, 20, n, 'a'))` - 5일선이 20일선 상향돌파 | 불리언(True/False) |
| `cross_down(a, b)` | a가 b를 하향돌파했는지 확인 | `cross_down(lambda c, n: ma(c, 5, n, 'a'), lambda c, n: ma(c, 20, n, 'a'))` - 5일선이 20일선 하향돌파 | 불리언(True/False) |
| `bars_since(condition)` | 조건 만족 이후 지난 봉 수 | `bars_since(lambda c, n: c(n) > o(n))` - 마지막으로 종가가 시가보다 높았던 이후 봉 수 | 숫자(int) |

### A.5 기술적 지표 함수

| 함수 | 설명 | 예시 | 반환값 |
|------|------|------|--------|
| `rsi(period[, m])` | 상대강도지수(RSI) | `rsi(14)` - 14일 RSI<br>`rsi(14, 1)` - 1봉 전 14일 RSI | 숫자(0~100) |
| `macd(fast, slow, signal[, m])` | MACD 지표 | `macd(12, 26, 9)` - MACD(12,26,9)<br>`macd(12, 26, 9)[0]` - MACD 라인 값 | 튜플(macd, signal, histogram) |
| `bollinger_bands(period, std_dev[, m])` | 볼린저 밴드 | `bollinger_bands(20, 2)` - 20일, 2표준편차 볼린저 밴드<br>`bollinger_bands(20, 2)[0]` - 상단 밴드 | 튜플(upper, middle, lower) |
| `stochastic(k_period, d_period[, m])` | 스토캐스틱 오실레이터 | `stochastic(14, 3)` - 14,3 스토캐스틱<br>`stochastic(14, 3)[0]` - %K 값 | 튜플(%K, %D) |
| `atr(period[, m])` | 평균 실제 범위(ATR) | `atr(14)` - 14일 ATR | 숫자(float) |

### A.6 캔들 패턴 함수

| 함수 | 설명 | 예시 | 반환값 |
|------|------|------|--------|
| `is_doji([n, threshold])` | n봉 이전이 도지 캔들인지 확인 | `is_doji()` - 현재봉이 도지 캔들인지<br>`is_doji(1, 0.05)` - 1봉 전이 5% 이하 몸통을 가진 도지인지 | 불리언(True/False) |
| `is_hammer([n])` | n봉 이전이 망치형 캔들인지 확인 | `is_hammer()` - 현재봉이 망치형 캔들인지<br>`is_hammer(1)` - 1봉 전이 망치형 캔들인지 | 불리언(True/False) |
| `is_engulfing([n, bullish])` | n봉 이전이 포괄 패턴인지 확인 | `is_engulfing(0, True)` - 현재봉이 상승 포괄 패턴인지<br>`is_engulfing(0, False)` - 현재봉이 하락 포괄 패턴인지 | 불리언(True/False) |

### A.7 추세 함수

| 함수 | 설명 | 예시 | 반환값 |
|------|------|------|--------|
| `is_uptrend(period[, m])` | 상승 추세인지 확인 | `is_uptrend(20)` - 20일 이동평균 기준 상승 추세인지 | 불리언(True/False) |
| `is_downtrend(period[, m])` | 하락 추세인지 확인 | `is_downtrend(20)` - 20일 이동평균 기준 하락 추세인지 | 불리언(True/False) |
| `momentum(period[, m])` | 모멘텀 계산 | `momentum(10)` - 10일 모멘텀 (현재 종가 - 10일 전 종가) | 숫자(float) |

### A.8 논리 함수

| 함수 | 설명 | 예시 | 반환값 |
|------|------|------|--------|
| `iif(condition, true_value, false_value)` | 조건에 따른 값 선택 | `iif(c() > o(), "상승", "하락")` - 종가가 시가보다 높으면 "상승", 아니면 "하락" | 조건에 따른 값 |
| `div(a, b, default)` | 안전한 나눗셈 (0으로 나누기 방지) | `div(v(), v(1), 1)` - 현재 거래량/이전 거래량, 이전 거래량이 0이면 1 반환 | 숫자(float) |

### A.9 Python 내장 함수

스크립트에서 사용 가능한 Python 내장 함수들입니다.

| 함수 | 설명 | 예시 | 반환값 |
|------|------|------|--------|
| `max(iterable)` 또는 `max(a, b, ...)` | 최대값 반환 | `max([10, 5, 20])` - 20 반환<br>`max(c(), o())` - 종가와 시가 중 큰 값 | 최대값 |
| `min(iterable)` 또는 `min(a, b, ...)` | 최소값 반환 | `min([10, 5, 20])` - 5 반환<br>`min(c(), o())` - 종가와 시가 중 작은 값 | 최소값 |
| `sum(iterable)` | 합계 계산 | `sum([1, 2, 3, 4])` - 10 반환 | 합계 |
| `abs(x)` | 절대값 계산 | `abs(-10)` - 10 반환<br>`abs(c() - o())` - 종가와 시가의 차이(절대값) | 절대값 |
| `round(x[, n])` | 반올림 (n자리까지) | `round(3.14159, 2)` - 3.14 반환 | 반올림된 값 |
| `int(x)` | 정수로 변환 | `int(3.7)` - 3 반환 | 정수 |
| `float(x)` | 실수로 변환 | `float(3)` - 3.0 반환 | 실수 |
| `str(x)` | 문자열로 변환 | `str(123)` - "123" 반환 | 문자열 |
| `bool(x)` | 불리언으로 변환 | `bool(0)` - False 반환<br>`bool(1)` - True 반환 | True/False |
| `len(x)` | 객체의 길이 반환 | `len([1, 2, 3])` - 3 반환 | 정수 |
| `list(iterable)` | 리스트로 변환 | `list(range(3))` - [0, 1, 2] 반환 | 리스트 |
| `tuple(iterable)` | 튜플로 변환 | `tuple([1, 2, 3])` - (1, 2, 3) 반환 | 튜플 |
| `sorted(iterable)` | 정렬된 리스트 반환 | `sorted([3, 1, 2])` - [1, 2, 3] 반환 | 리스트 |
| `reversed(sequence)` | 역순 이터레이터 반환 | `list(reversed([1, 2, 3]))` - [3, 2, 1] 반환 | 이터레이터 |
| `enumerate(iterable)` | (인덱스, 값) 쌍 생성 | `list(enumerate(['a', 'b']))` - [(0, 'a'), (1, 'b')] | 이터레이터 |
| `zip(*iterables)` | 여러 이터러블 요소 묶기 | `list(zip([1, 2], ['a', 'b']))` - [(1, 'a'), (2, 'b')] | 이터레이터 |
| `any(iterable)` | 하나라도 참이면 True | `any([False, True, False])` - True 반환 | 불리언 |
| `all(iterable)` | 모두 참이면 True | `all([True, True, False])` - False 반환 | 불리언 |
| `range(start, stop[, step])` | 범위 생성 | `list(range(1, 5))` - [1, 2, 3, 4] 반환 | 이터레이터 |
| `dict(mapping)` | 딕셔너리 생성 | `dict(a=1, b=2)` - {'a': 1, 'b': 2} 반환 | 딕셔너리 |
| `set(iterable)` | 집합 생성 | `set([1, 2, 2, 3])` - {1, 2, 3} 반환 | 집합 |
| `filter(function, iterable)` | 필터링된 이터레이터 | `list(filter(lambda x: x > 0, [-1, 0, 1, 2]))` - [1, 2] | 이터레이터 |
| `map(function, iterable)` | 매핑된 이터레이터 | `list(map(lambda x: x*2, [1, 2, 3]))` - [2, 4, 6] | 이터레이터 |

### A.10 수학 관련 함수 (math 모듈)

| 함수 | 설명 | 예시 | 반환값 |
|------|------|------|--------|
| `math.sqrt(x)` | 제곱근 계산 | `math.sqrt(16)` - 4.0 반환 | 실수 |
| `math.pow(x, y)` | x의 y제곱 계산 | `math.pow(2, 3)` - 8.0 반환 | 실수 |
| `math.exp(x)` | e의 x제곱 계산 | `math.exp(1)` - 2.718... 반환 | 실수 |
| `math.log(x[, base])` | 로그 계산 | `math.log(100, 10)` - 2.0 반환 | 실수 |
| `math.log10(x)` | 밑이 10인 로그 | `math.log10(100)` - 2.0 반환 | 실수 |
| `math.floor(x)` | 내림 | `math.floor(3.7)` - 3 반환 | 정수 |
| `math.ceil(x)` | 올림 | `math.ceil(3.2)` - 4 반환 | 정수 |
| `math.sin(x)` | 사인 | `math.sin(math.pi/2)` - 1.0 반환 | 실수 |
| `math.cos(x)` | 코사인 | `math.cos(0)` - 1.0 반환 | 실수 |
| `math.tan(x)` | 탄젠트 | `math.tan(math.pi/4)` - 1.0 반환 | 실수 |
| `math.radians(x)` | 각도를 라디안으로 변환 | `math.radians(180)` - π 반환 | 실수 |
| `math.degrees(x)` | 라디안을 각도로 변환 | `math.degrees(math.pi)` - 180.0 반환 | 실수 |
| `math.fabs(x)` | 절대값 (실수) | `math.fabs(-3.14)` - 3.14 반환 | 실수 |
| `math.factorial(x)` | 팩토리얼 | `math.factorial(5)` - 120 반환 | 정수 |
| `math.gcd(a, b)` | 최대공약수 | `math.gcd(12, 8)` - 4 반환 | 정수 |

### A.11 문자열 메서드

| 메서드 | 설명 | 예시 | 반환값 |
|------|------|------|--------|
| `str.upper()` | 대문자로 변환 | `"hello".upper()` - "HELLO" 반환 | 문자열 |
| `str.lower()` | 소문자로 변환 | `"HELLO".lower()` - "hello" 반환 | 문자열 |
| `str.strip()` | 앞뒤 공백 제거 | `" hello ".strip()` - "hello" 반환 | 문자열 |
| `str.replace(old, new)` | 문자열 치환 | `"hello".replace("l", "x")` - "hexxo" 반환 | 문자열 |
| `str.split(sep)` | 문자열 분할 | `"a,b,c".split(",")` - ["a", "b", "c"] 반환 | 리스트 |
| `str.join(iterable)` | 문자열 결합 | `",".join(["a", "b", "c"])` - "a,b,c" 반환 | 문자열 |
| `str.startswith(prefix)` | 접두사 확인 | `"hello".startswith("he")` - True 반환 | 불리언 |
| `str.endswith(suffix)` | 접미사 확인 | `"hello".endswith("lo")` - True 반환 | 불리언 |
| `str.find(sub)` | 부분문자열 위치 | `"hello".find("l")` - 2 반환 (첫 일치) | 정수 |
| `str.isdigit()` | 숫자 문자열 확인 | `"123".isdigit()` - True 반환 | 불리언 |
| `str.isalpha()` | 알파벳 문자열 확인 | `"abc".isalpha()` - True 반환 | 불리언 |
| `str.format()` | 문자열 포맷팅 | `"{} {}".format("hello", "world")` - "hello world" | 문자열 |

### A.12 리스트 메서드

| 메서드 | 설명 | 예시 | 반환값 |
|------|------|------|--------|
| `list.append(x)` | 항목 추가 | `[1, 2].append(3)` - [1, 2, 3] | None (변경) |
| `list.extend(iterable)` | 리스트 확장 | `[1, 2].extend([3, 4])` - [1, 2, 3, 4] | None (변경) |
| `list.insert(i, x)` | 특정 위치에 삽입 | `[1, 3].insert(1, 2)` - [1, 2, 3] | None (변경) |
| `list.remove(x)` | 항목 제거 | `[1, 2, 3].remove(2)` - [1, 3] | None (변경) |
| `list.pop([i])` | 항목 추출 | `[1, 2, 3].pop(1)` - 2 반환, 리스트는 [1, 3] | 항목 |
| `list.index(x)` | 항목 위치 반환 | `[1, 2, 3].index(2)` - 1 반환 | 정수 |
| `list.count(x)` | 항목 개수 세기 | `[1, 2, 2, 3].count(2)` - 2 반환 | 정수 |
| `list.sort()` | 정렬 | `[3, 1, 2].sort()` - [1, 2, 3] | None (변경) |
| `list.reverse()` | 역순 정렬 | `[1, 2, 3].reverse()` - [3, 2, 1] | None (변경) |
| `list.copy()` | 리스트 복사 | `[1, 2, 3].copy()` - [1, 2, 3] 반환 | 리스트 |

### A.13 딕셔너리 메서드

| 메서드 | 설명 | 예시 | 반환값 |
|------|------|------|--------|
| `dict.get(key[, default])` | 키로 값 가져오기 | `{"a": 1, "b": 2}.get("a")` - 1 반환<br>`{"a": 1}.get("b", 0)` - 0 반환 | 값 |
| `dict.keys()` | 모든 키 반환 | `{"a": 1, "b": 2}.keys()` - dict_keys(['a', 'b']) | dict_keys |
| `dict.values()` | 모든 값 반환 | `{"a": 1, "b": 2}.values()` - dict_values([1, 2]) | dict_values |
| `dict.items()` | (키, 값) 쌍 반환 | `{"a": 1, "b": 2}.items()` - dict_items([('a', 1), ('b', 2)]) | dict_items |
| `dict.update(other)` | 딕셔너리 갱신 | `{"a": 1}.update({"b": 2})` - {"a": 1, "b": 2} | None (변경) |
| `dict.pop(key[, default])` | 키로 값 제거 | `{"a": 1, "b": 2}.pop("a")` - 1 반환, 딕셔너리는 {"b": 2} | 값 |
| `dict.setdefault(key[, default])` | 키가 없으면 추가 | `{"a": 1}.setdefault("b", 2)` - 2 반환, 딕셔너리는 {"a": 1, "b": 2} | 값 |

### A.14 datetime 모듈 함수

| 함수/클래스 | 설명 | 예시 | 반환값 |
|------|------|------|--------|
| `datetime.now()` | 현재 날짜와 시간 | `datetime.now()` - 현재 날짜시간 | datetime 객체 |
| `datetime.strptime(date_str, format)` | 문자열을 날짜로 변환 | `datetime.strptime("20240101", "%Y%m%d")` | datetime 객체 |
| `datetime.strftime(format)` | 날짜를 문자열로 변환 | `datetime.now().strftime("%Y-%m-%d")` - "2024-01-01" 형식 | 문자열 |
| `timedelta(days=0, seconds=0, ...)` | 시간 간격 | `datetime.now() + timedelta(days=1)` - 내일 날짜 | datetime 객체 |
| `date.year, date.month, date.day` | 날짜 속성 | `datetime.now().year` - 현재 연도 | 정수 |
| `time.hour, time.minute, time.second` | 시간 속성 | `datetime.now().hour` - 현재 시간 | 정수 |

## 부록 B: 스크립트 제약사항 및 주의점

### B.1 금지된 기능

| 금지된 기능 | 이유 | 대안 |
|------------|------|------|
| `while` 루프 | 무한 루프 위험 | `loop` 함수 사용 |
| `for` 루프 | 무한 루프 위험 | `loop` 함수 사용 |
| `def` 키워드 (함수 정의) | 실행 환경 제약 | 람다 함수 사용 |
| 파일 열기/쓰기 | 보안 위험 | 필요한 데이터는 ChartManager를 통해 접근 |
| `exec()`, `eval()` | 코드 삽입 위험 | 명시적 로직 사용 |
| 허용되지 않은 모듈 임포트 | 보안 위험 | 허용된 모듈만 사용 |
| 변수 이름으로 `_`로 시작하는 이름 | 내부 변수 접근 방지 | 다른 변수명 사용 |
| ChartManager 내부 메서드 직접 호출 | 안정성 위험 | 공개된 메서드만 사용 |

### B.2 허용된 모듈

다음 모듈만 스크립트에서 사용할 수 있습니다:
- `math`: 수학 함수 (math.sin, math.cos 등)
- `datetime`: 날짜 및 시간 처리
- `re`: 정규 표현식
- `logging`: 로깅 기능
- `json`: JSON 파싱
- `collections`: 컬렉션 자료구조 (collections.defaultdict 등)

### B.3 성능 최적화 팁

1. **캐싱 활용**: 동일한 계산을 반복하지 마세요.
   ```python
   # 나쁜 예
   if ma(c, 5) > ma(c, 20) and ma(c, 5) > ma(c, 10):
       # 로직...
   
   # 좋은 예
   ma5 = ma(c, 5)
   if ma5 > ma(c, 20) and ma5 > ma(c, 10):
       # 로직...
   ```

2. **불필요한 계산 줄이기**: 조건문에서 가장 빠르게 평가할 수 있는 조건을 먼저 넣으세요.
   ```python
   # 나쁜 예
   if rsi(14) < 30 and c() > ma(c, 200):  # rsi 계산이 비용이 큼
   
   # 좋은 예
   if c() > ma(c, 200) and rsi(14) < 30:  # 간단한 조건 먼저 확인
   ```

3. **계산량 줄이기**: 필요한 만큼만 데이터를 처리하세요.
   ```python
   # 불필요하게 많은 데이터 분석
   prices = loop(range(100), lambda i: c(i))
   
   # 필요한 데이터만 분석
   prices = loop(range(20), lambda i: c(i))  # 20개 봉만 필요한 경우
   ```

## 부록 C: 샘플 스크립트 분석

### C.1 골든 크로스 스크립트 분석

```python
# 골든 크로스 전략
dy = ChartManager('dy')  # 일봉

# 단기/장기 이동평균
short_ma = dy.ma(code, dy.c, 5, 0, 'a')  # 5일 단순이동평균
long_ma = dy.ma(code, dy.c, 20, 0, 'a')  # 20일 단순이동평균

# 골든 크로스 확인
is_golden_cross = dy.cross_up(code, 
    lambda c, n: dy.ma(c, dy.c, 5, n, 'a'), 
    lambda c, n: dy.ma(c, dy.c, 20, n, 'a'))

# 결과 로깅
logging.debug(f"코드: {code}, 5MA: {short_ma:.2f}, 20MA: {long_ma:.2f}, 신호: {is_golden_cross}")

# 결과 반환
result = is_golden_cross
```

**주요 포인트**:
1. `ChartManager('dy')`: 일봉 데이터를 사용하기 위한 차트 매니저 생성
2. 함수 사용: `ma()`, `cross_up()`, `c()`로 데이터 접근
3. 람다 함수 사용: `cross_up()` 내에서 이동평균 비교를 위한 콜백 함수 (def 사용 불가)
4. 로깅: `logging.debug()`로 결과 기록
5. 결과 반환: `result = is_golden_cross`로 스크립트 결과 설정

### C.2 반복문 사용 예제 분석

```python
# 최근 10개 봉 중 최고가 찾기
dy = ChartManager('dy')  # 일봉
max_high = 0
max_high_idx = -1

# loop 함수를 사용하여 최근 10개 봉 확인
# def 키워드 사용 불가, 람다 함수 사용
check_high = lambda i: dy.h(code, i)

high_prices = loop(range(10), check_high)
max_high = max(high_prices)
max_high_idx = high_prices.index(max_high)

# 현재가 계산
current_price = dy.c(code, 0)
drop_pct = ((max_high - current_price) / max_high) * 100 if max_high > 0 else 0

# 결과 반환
result = drop_pct >= 10  # 최고가 대비 10% 이상 하락
```

**주요 포인트**:
1. `loop` 함수: `for` 대신 안전한 반복문 사용
2. 람다 함수: `check_high = lambda i: dy.h(code, i)` 형태로 사용 (`def` 사용 불가)
3. 리스트 처리: 표준 Python 함수 `max()`, `index()` 활용
4. 계산: 최고가 대비 하락률 계산
5. 조건부 결과: 특정 조건(`drop_pct >= 10`)에 따른 결과 반환

## 부록 D: 자주 묻는 질문 (FAQ)

### D.1 기본 사용법 관련

**Q: 스크립트에서 꼭 `result` 변수를 설정해야 하나요?**  
A: 네, 모든 스크립트는 최종적으로 `result` 변수에 값을 할당해야 합니다. 이 값이 스크립트의 실행 결과로 반환됩니다.

**Q: `loop` 함수는 어떻게 사용하나요?**  
A: `loop` 함수는 `loop(iterable, callback)` 형태로 사용합니다. `iterable`은 반복할 항목(예: range(10)), `callback`은 각 항목에 적용할 함수입니다.

**Q: 여러 주기의 데이터를 어떻게 함께 사용하나요?**  
A: 각 주기별로 ChartManager 인스턴스를 생성하면 됩니다.
```python
dy = ChartManager('dy')  # 일봉
mi3 = ChartManager('mi', 3)  # 3분봉
```

### D.2 오류 및 디버깅 관련

**Q: "보안 위반 코드"라는 오류가 발생했어요.**  
A: 스크립트에 금지된 기능(예: `while` 루프, 파일 접근 등)이 포함되어 있는 경우 발생합니다. 부록 B.1의 금지된 기능 목록을 참고하세요.

**Q: 함수가 정의되지 않았다는 오류가 발생했어요.**  
A: 함수 이름이나 객체 참조가 잘못된 경우 발생합니다. ChartManager 인스턴스를 생성했는지, 함수 이름이 정확한지 확인하세요.

**Q: 스크립트가 너무 오래 실행된다는 경고가 나왔어요.**  
A: 스크립트는 0.1초 이내에 실행이 완료되어야 합니다. 복잡한 계산이나 긴 반복문이 있는지 확인하고 최적화하세요.

### D.3 고급 사용법

**Q: 여러 스크립트를 조합해서 사용할 수 있나요?**  
A: 네, `run_script()` 함수를 사용하여 다른 스크립트를 호출할 수 있습니다.
```python
golden_cross_signal = run_script('GoldenCross')
rsi_signal = run_script('RSIOverSold')
result = golden_cross_signal and rsi_signal
```

**Q: 변수를 스크립트에 어떻게 전달하나요?**  
A: 스크립트 등록 시 `vars` 딕셔너리를 통해 변수를 전달할 수 있습니다. 이 변수들은 스크립트 내에서 전역 변수로 사용할 수 있습니다.

**Q: 스크립트에서 사용자 정의 함수를 만들 수 있나요?**  
A: 스크립트 내에서 `def` 키워드를 사용하여 함수를 정의할 수 없습니다. 대신 람다 함수를 사용하여 간단한 함수를 정의할 수 있습니다.
```python
# 사용 불가 (def 키워드 금지)
# def calculate_gain_ratio(open_price, close_price):
#     return (close_price - open_price) / open_price if open_price > 0 else 0

# 사용 가능 (람다 함수)
calculate_gain_ratio = lambda open_price, close_price: (close_price - open_price) / open_price if open_price > 0 else 0

# 실제 사용 예
gain = calculate_gain_ratio(o(), c())
```
