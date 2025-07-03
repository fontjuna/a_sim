from aaa.chart import ChartManager
from aaa.log import info, debug

code = '005930'
name = '삼성전자'
price = 100000
qty = 100

# =============================================================================================

# 다른종목으로 테스트
#code = '389140'

# 차트정의
일봉 = ChartManager(code, 'dy')
분3 = ChartManager(code, 'mi', 3)

debug(f'code={code} 현재가={일봉.c()}')

# 이동평균정의
이평5 = 분3.indicator(분3.avg, 분3.c,  5)
이평10 = 분3.indicator(분3.avg, 분3.c,  10)

# 미리 계산
c, c1, c_limit = 일봉.c(), 일봉.c(1), int(일봉.c(1) * 1.3)
v1, v2, v5, v10 = 이평5(1), 이평5(2), 이평5(), 이평10()
mo, mc, m_down_rate = 분3.o(), 분3.c(), ((분3.o() - 분3.c()) / 분3.o())

# 조건정의(결과 값이 논리값이 되도록 작성)
상한가 = c >= c_limit 
급락 = mo > mc and m_down_rate > 0.03 # 봉하나에 3% 급락
하락전환_3분5이평 = v2 >= v1 and v1 >= v5 and v5 < v1
이평역전_3분5_10이평 = v10 > v5
이평아래 = v10 > mc

# 로깅
msg = ''
if 상한가: 
    msg += f'상한가(전일{c1}, 현재가{c}, 상한가{c_limit})'
elif 급락: 
    msg += f'급락(시가:{mo}, 현재가:{mc}, 하락률:{m_down_rate})'
elif 하락전환_3분5이평: 
    msg += f'하락전환_3분5이평(2:{v2}, 1:{v1}, 0:{v5})'
elif 이평역전_3분5_10이평: 
    msg+= f'이평역전_3분5_10이평(5:{v5}, 10:{v10})'
elif 이평아래: 
    msg += f'이평아래(이평:{v10}, 현재가:{c})'

if not msg: msg = " 없음"
info(f"매도조건{msg} : code={code} name={name}")

# 전략평가 전송
result = 상한가 or 하락전환_3분5이평 or 이평역전_3분5_10이평 or 이평아래 or 급락
info(f'result={result}\n')