# 사용자 함수 작성 매뉴얼

## 1. 개요

사용자 함수는 여러 스크립트에서 재사용할 수 있는 공통 로직을 정의하는 방법입니다. 복잡한 계산이나 자주 사용되는 패턴을 함수로 만들어 사용하면 스크립트가 더 간결해지고 오류 가능성을 줄일 수 있습니다.

## 2. 사용자 함수 기본 구조

```python
# 첫 번째 인수는 항상 code(종목코드)입니다.
# 추가 인수는 자유롭게 정의할 수 있습니다.
dy = ChartManager('dy')  # 차트 매니저 생성

# 함수 내용 (스크립트와 동일한 제약 적용)
value = dy.c(code) / dy.avg(code, dy.c, 20)

# 반환값 (다양한 타입 가능)
return value
```

## 3. 함수 작성 규칙

1. 첫 번째 매개변수는 항상 `code`(종목코드)입니다.
2. 추가 매개변수는 자유롭게 정의할 수 있습니다.
3. 함수 내용은 일반 스크립트와 동일한 제약사항이 적용됩니다.
4. 함수는 반드시 결과값을 반환해야 합니다(`return` 문 사용).
5. 함수 내에서 다른 사용자 함수를 호출할 수 있습니다.

## 4. 반환값

사용자 함수는 스크립트와 달리 다양한 타입의 값을 반환할 수 있습니다:

- 논리값(Boolean): `True` / `False`
- 숫자(Number): 정수 또는 실수
- 문자열(String): 텍스트
- 리스트(List): 값의 목록
- 튜플(Tuple): 고정된 크기의 값의 집합
- 사전(Dict): 키-값 쌍의 집합

## 5. 사용자 함수 예제

### 5.1. 가격 돌파 확인 함수

```python
# 특정 기간 내 최고가/최저가 돌파 확인
periods = [5, 10, 20, 60]  # 확인할 기간
comparator = highest if direction == 'up' else lowest
   
for period in periods:
   threshold = comparator(code, h if direction == 'up' else l, period, 1)
   current = c(code)
      
   if direction == 'up' and current > threshold:
      return True  # 상향 돌파
   elif direction == 'down' and current < threshold:
      return True  # 하향 돌파
      
return False  # 돌파 없음
```

### 5.2. 볼린저 밴드 위치 확인 함수

```python
# 가격이 볼린저 밴드 어디에 위치하는지 반환
# 반환값: 1(상단 위), 0(밴드 내), -1(하단 아래)
upper, middle, lower = bollinger_bands(code, period, 2)
price = c(code)
   
if price > upper:
   return 1  # 상단 위
elif price < lower:
   return -1  # 하단 아래
else:
   return 0  # 밴드 내부
```

### 5.3. 추세 강도 계산 함수

```python
# 추세 강도 계산 (1~10 범위로 정규화)
# 반환값: 강세(1~10), 약세(-1~-10), 중립(0)
price = c(code)
ma20 = avg(code, c, 20)
ma60 = avg(code, c, 60)
   
# 방향 결정
if price > ma20 and ma20 > ma60:
   direction = 1  # 상승 추세
elif price < ma20 and ma20 < ma60:
   direction = -1  # 하락 추세
else:
   return 0  # 중립
   
# 강도 계산
rsi_value = rsi(code, 14)
momentum_value = momentum(code, 10)
   
if direction > 0:
   # 상승 추세 강도 (1~10)
   strength = min(10, int((rsi_value - 50) / 5) + int(momentum_value / 10))
   return max(1, strength)
else:
   # 하락 추세 강도 (-1~-10)
   strength = min(10, int((50 - rsi_value) / 5) + int(-momentum_value / 10))
   return -max(1, strength)
```

## 6. 함수 사용 팁

1. **의미 있는 이름 사용**: 함수 이름은 기능을 명확하게 설명해야 합니다.
2. **인수 제한**: 너무 많은 인수를 사용하지 마세요. 필요한 경우 기본값을 제공하세요.
3. **재사용성 고려**: 특정 상황에만 사용할 수 있는 함수보다 범용적으로 사용할 수 있는 함수를 만드세요.
4. **문서화**: 함수 설명에 용도, 인수, 반환값 등을 명확히 기록하세요.
5. **단일 책임**: 각 함수는 하나의 작업만 수행하도록 설계하세요.

## 7. 디버깅 및 테스트

함수를 작성한 후에는 다양한 입력값으로 테스트하여 예상대로 동작하는지 확인하세요. 테스트 스크립트를 만들어 여러 종목코드와 조건에서 함수가 올바르게 작동하는지 확인할 수 있습니다.
