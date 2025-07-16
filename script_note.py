from aaa.chart import ChartManager, echo, is_args, ret, div, ma

code = '005930'
name = '삼성전자'
price = 100000
qty = 100

# =============================================================================================

# 스크립트명 : 돌파4시간3분5억_매도

# 다른종목으로 테스트
#code = '234030'

# 차트정의
dm = ChartManager(code, 'dy')
m3 = ChartManager(code, 'mi', 3)

#echo(f'code={code} 현재가={일.c()}')

# 함수주입
dc = dm.c
mo, mc, ma = m3.o, m3.c, m3.ma

# 미리 계산
c_limit = int(dc(1) * 1.295)
m_down_rate = div(mo() - mc(), mo(), 0 )
ma0, ma1, ma2, ma10 = ma(5, 0), ma(5, 1), ma(5, 2), ma(10)

# 조건정의(결과 값이 논리값이 되도록 작성)
상한가 = c_limit < dc(0)
급락 = mo() > mc() and m_down_rate > 0.03 # 봉하나에 3% 급락
하락전환_3분5이평 = ma2 <= ma1 and ma1 > ma0
이평역전_3분5_10이평 = ma10 > ma0
이평아래 = ma10 > mc()

# 로깅
msg = ''
if 상한가: 
    msg += f'상한가' #(전일{dc(1)}, 현재가{dc()}, 상한가{c_limit})'
elif 급락: 
    msg += f'급락' #(시가:{mo()}, 현재가:{mc()}, 하락률:{m_down_rate:.2f})'
elif 하락전환_3분5이평: 
    msg += f'하락전환_3분5이평' #(2:{ma2}, 1:{ma1}, 0:{ma0})'
elif 이평역전_3분5_10이평: 
    msg+= f'이평역전_3분5_10이평' #(5:{ma0}, 10:{ma10})'
elif 이평아래: 
    msg += f'이평아래' #(이평:{ma10}, 현재가:{dc()})'

if not msg: msg = " 없음"
#echo(f"매도조건: code={code} {name}/{msg}")

# 전략평가 전송
result = 상한가 or 하락전환_3분5이평 or 이평역전_3분5_10이평 or 이평아래 or 급락
echo(f'[{result}] ({code} {name}) 현재가={dc()}/매도조건: {msg}')
ret(result)