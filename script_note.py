from aaa.chart import ChartManager, echo, is_args, ret, div, ma

code = '005930'
name = '삼성전자'
price = 100000
qty = 100

# =============================================================================================

# 스크립트명 : 돌파매수
#ret(True)
# 다른코드로 테스트
#code='018250'
#echo(f'coide={code}')

# 차트
m3 = ChartManager(code, 'mi', 3)
dt = ChartManager(code, 'dy')

# 함수주입
dh, dc, do, dv = dt.h, dt.c, dt.o, dt.v
mo, mh, ml, mc, mv = m3.o, m3.h, m3.l, m3.c, m3.v

# 빠른 리턴
매도조건 = 일반매도(logoff=True)
if 매도조건:
    echo(f'[{False}] ({code} {name}) 취소원인=매도조건에 해당')
    ret(False)

# 전일 종가는 최고가 기준 -5% 이상이 아니면 전일 고가를 넘어야 함
전일종가율 = div(dc(1) - dh(1), dh(1), 0)
if dh(1) > mc() and 전일종가율 < -0.05:
    echo(f'[{False}] ({code} {name}) 취소원인=전일종가율({전일종가율*100:.2f}) 불충족')
    ret(False)

# 1봉전 128봉중 최고거래량 cnt개의 평균    
탑텐평균 = m3.top_volume_avg(n=128, m=1, cnt=10) * 0.8
탑텐평균조건 = mv() >= 탑텐평균

# 최근 n 개봉이 전일 3분봉 평균 거래량의 5배 이상
최근최고봉 = max(mv(), mv(1), mv(2), mv(3), mv(4), mv(5))
전일삼분평균 = dv(1) / 128
삼분평균조건 = 최근최고봉 > 전일삼분평균 * 5

# 이전 n봉부터 m봉까지 이전 cnt봉중 최고종가 얻기 (최고종가, 당일봉수)
gcts = m3.get_close_tops(n=128, cnt=128, m=1) # 업데이트된 최고종가 리스트와 당일 봉수
최고종가 = gcts[0] #개장후n봉최고종가
당일봉수 = gcts[1]
최고종가_len = len(최고종가) if 최고종가 else 0

if 최고종가_len <= 1 or 최고종가[-1] > 당일봉수: 
    echo(f'[False] ({code} {name}) 취소원인={최고종가} 당일최고종가 1개 이하')
    ret(False)
echo(f'당일봉수={당일봉수} {최고종가}')

obvs = m3.get_obv_array(최고종가[-1] + 1)
OBV조건 = obvs[최고종가[-1]] < obvs[0] if 최고종가[-1] >= 2 else True

# 거래량 판단
if not (탑텐평균조건 or 삼분평균조건 or OBV조건):
    msg = ''
    if not 탑텐평균조건: msg += '탑텐평균조건, '
    if not 삼분평균조건: msg += '삼분평균조건, '
    if not OBV조건: msg += 'OBV조건, '
    echo(f'[{False}] ({code} {name}) 취소원인={msg}조건 불충족')
    ret(False)

# 마지막 최고종가의 위치까지 각 최고, 최저값 획득
extr = m3.get_extremes(n=최고종가[-1], m=1)

# 종가 기준 고가보다 저가가 더 큰것만 매수(첫봉 음봉등 배제-아래꼬리가 더 길면 매수)
loc = 최고종가[-1]
고저대비 = mc(loc) - ml(loc) > mh(loc) - mc(loc)
#고저대비 = mc() - extr['ll'] > extr['hh'] - mc()

# 시간조정조건 : 최고종가에서 종가상 5%이상 빠지면 매수 안 함
하락율 = div(extr['hc'] - extr['lc'], extr['hc'], 0)
시간조정조건 = 하락율 > -0.05
현재봉조건 = mc() >= mc(최고종가[-1])

# 로깅
msg = ''
if not 고저대비: msg += f'고저대비, '
if not 시간조정조건: msg += f'시간조정조건({하락율}>-0.05, '
if not 현재봉조건: msg += f'현재봉조건({mc():,d}>={mc(최고종가[-1]):,d})'

# 전략평가 결과 전달
result = 고저대비 and 시간조정조건 and 현재봉조건
if msg: msg = '취소원인 = ' + msg +' 불충족'
echo(f'[{result}] ({code} {name}) {msg}')

ret(result)


# 스크립트명 : 돌파4시간3분5억_매도
#ret(False)
# 다른종목으로 테스트
#code = '131030'

# 전달 값 확인
logoff = is_args('logoff', False)

# 차트정의
dm = ChartManager(code, 'dy')
m3 = ChartManager(code, 'mi', 3)

#echo(f'code={code} 현재가={일.c()}')

# 함수주입
dc = dm.c
mo, mc, ml, ma = m3.o, m3.c, m3.l, m3.ma

# 미리 계산
c_limit = hoga(dc(1), 99)
#echo(f'현재가={dc()}, 상한가={c_limit}')
up_down_rate = div(mc() - mo(), mo(), 0 )

기준가 = 0
if not logoff:
    # 이전 n봉부터 m봉까지 이전 cnt봉중 최고종가 얻기 (최고종가, 당일봉수)
    gcts = m3.get_close_tops(n=128, cnt=128, m=1) # 업데이트된 최고종가 리스트와 당일 봉수
    최고종가 = gcts[0] #개장후n봉최고종가
    당일봉수 = gcts[1]
    기준가 = min(mc(최고종가[-2]), ml(최고종가[-1])) if len(최고종가) > 1 else 0

# 조건정의(결과 값이 논리값이 되도록 작성)
상한가 = c_limit <= dc(0)
기준봉이하 = 기준가 > mc()
하락전환_3분5이평 = ma(5, 2) <= ma(5, 1) and ma(5, 1) > ma(5, 0) and ma(5) > mc()
이평역전_3분5_10이평 = ma(10) > ma(5)
현재가10이평아래 = ma(10) > mc()
급락 = up_down_rate < -0.03 # 봉하나에 3% 급락
급등 = up_down_rate > 0.05 # 봉하나에 5% 급등

# 로깅
msg = ''
if 상한가: 
    msg += f'상한가' #(전일{dc(1)}, 현재가{dc()}, 상한가{c_limit}), '
#elif 기준봉이하:
#    msg += f'기준봉이하' #(기준봉저가:{ml(최고종가[-1])}, 현재가:{mc()}), '
elif 하락전환_3분5이평: 
    msg += f'하락전환_3분5이평'
elif 이평역전_3분5_10이평: 
    msg+= f'이평역전_3분5_10이평'
elif 현재가10이평아래: 
    msg += f'현재가10이평아래'
#elif 급락: 
#    msg += f'급락' #(시가:{mo()}, 현재가:{mc()}, 하락률:{up_down_rate:.2f}), '
elif 급등:
    msg += f'급등' #(시가:{mo()}, 현재가:{mc()}, 상승률:{up_down_rate:.2f}), '

if not msg: msg = " 없음"
#echo(f"매도조건: code={code} {name}/{msg}")

# 전략평가 전송
result = 상한가 or 하락전환_3분5이평 or 이평역전_3분5_10이평 or 현재가10이평아래 #or 급등
if not logoff: echo(f'[{result}] ({code} {name}) 현재가={dc()} / 매도조건: {msg}')
ret(result)