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
