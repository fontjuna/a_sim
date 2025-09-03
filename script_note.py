from aaa.chart import ChartManager, echo, is_args, ret, div, ma, hoga, 일반매도

code = '005930'
name = '삼성전자'
price = 100000
qty = 100

# =============================================================================================

# 스크립트명 : 실전_돌파매수
"""
<검색식에서 구현: 매수조건>
1. 거래대금 상위 200종목 또는 거래량 상위 200종목 이고,
2. 주가범위 전일 기준 1,200원 ~ 99,900원 이고,
3. 현재가 기준 시가 총액 500억원 ~ 5조원 이고,
4. 현재가는 상승률 20% 이내이면서 전일 대비 시가가 2% 이상이거나, 시가대비 현재가가 5%이상이고,
5. 현재봉이 양봉이면서 시가는 10이평 위이며 종가는 5이평 위이면서 3분봉 기준 128봉 중 최고종가이고
6. 전일 최고가 대비 종가 하락율 5%이내이거나 전일 최고가 대비 종가 하락율 5%이상이면서 현재가가 전일 최고가를 넘어서야 하고
7. 현재봉 포함 60일 최고거래량대비 1분 0, 1, 2전봉중 하나의 거래량이 2% 이상

<스크립트에서 구현>
1. 일반매도 스크립트 조건에 해당하지 않고,
2. 최고종가 갱신봉이 당일 1개 이상이어야 하고,
3. 최고종가봉중 0.5% 이하 상승봉은 없는 봉으로 간주하여 3연속 최고종가는 회피하고,
4. 당일 최고종가 대비 최저 종가는 -5%이상이고,
5. 마지막 최고종가의 봉상태가 고가와 종가 차이가 저가와 종가 차이보다 작아야 하고 아니면 그 고가를 넘어서야 함,
6. 59일(당일 제외) 최고거래량 봉의 최고가를 넘어서야 하고 아니면 그 거래량의 67% 이상이어야 함.
"""
m3 = ChartManager(code, 'mi', 3)
dt = ChartManager(code, 'dy')
dh, dc, do, dv = dt.h, dt.c, dt.o, dt.v
mo, mh, ml, mc, mv = m3.o, m3.h, m3.l, m3.c, m3.v

매도조건 = 일반매도(logoff=True)
if 매도조건:
    echo(f'[{False}] ({code} {name}) / 매도조건에 해당')
    ret(False)

# 이전 n봉부터 m봉까지 이전 cnt봉중 최고종가 얻기 (최고종가, 당일봉수)
gcts = m3.get_close_tops(n=128, cnt=128, m=1) # 업데이트된 최고종가 리스트와 당일 봉수
최고종가 = gcts[0] #개장후n봉최고종가
당일봉수 = gcts[1]
최고종가_len = len(최고종가) if 최고종가 else 0

if 최고종가_len == 0:
    echo(f'[False] ({code} {name}) / 최고종가 0개')
    ret(False)

if 당일봉수 == 1: 
    echo(f'[False] ({code} {name}) / 당일 첫봉 매수 안함 : ({당일봉수}) {최고종가}')
    ret(False)

# 3연속 최고종가 회피 (0.5% 이하는 없는 봉으로 간주)
if 최고종가_len >= 2:
    연속갯수 = 0
    for i in range(최고종가_len):
        봉위치 = 최고종가[-(i+1)]  # 뒤에서부터 읽기 (현재봉부터)
        if i > 0 and 봉위치 != 최고종가[-(i)] - 1:  # 연속되지 않으면 종료
            break
        상승률 = div(mc(봉위치) - mc(봉위치 + 1), mc(봉위치 + 1), 0)
        if 상승률 > 0.005:  # 양봉이면서 0.5% 초과
            연속갯수 += 1
            if 연속갯수 >= 3:  # 3개 이상이면 즉시 종료
                break
        # 음봉이거나 0.5% 이하면 없는 봉으로 간주하고 계속 진행
    
    if 연속갯수 >= 3:
        echo(f'[False] ({code} {name}) / 3연속 최고종가 회피 (0.5% 이하 제외) : ({당일봉수}) {최고종가} (연속갯수: {연속갯수})')
        ret(False)

loc = 최고종가[-1]

extr = m3.get_extremes(n=loc-1, m=1)
if div(extr['hc'] - extr['lc'], extr['hc'], 0) < -0.05:
    echo(f'[False] ({code} {name}) / 당일 하락율 조건 불충족 : ({당일봉수}) {최고종가}')
    ret(False)

# if m3.is_shooting_star(n=loc, length=1.5, up=2.5, down=1) and max(mo(loc), mc(loc)) > mc(0):
#     echo(f'[False] ({code} {name}) / 최고종가봉이 유성형 : ({당일봉수}) {최고종가}')
#     ret(False)

# if mh(loc) < extr['hh'] and mc() < extr['hh']:
#     echo(f'[False] ({code} {name}) / 직전 최고종가의 고가를 갱신 했다면 그 밑에서 매수 안함 ({당일봉수}) {최고종가}')
#     ret(False)

if mc(loc) - ml(loc) < mh(loc) - mc(loc) and mh(loc) > mc(0):
    echo(f'[False] ({code} {name}) / 최고종가봉이 하락 우세임 : ({당일봉수}) {최고종가}')
    ret(False)

idx, date, o, h, l, c, v, a = dt.get_highest_volume(59, 1)
if not (h <= mc(0) or dv(0) >= v * 0.67):
    echo(f'[False] ({code} {name}) / 최고거래량 조건 불충족 : ({당일봉수}) {최고종가}')
    ret(False)

echo(f'[True] ({code} {name}) / ({당일봉수}) {최고종가}')
ret(True)


# =============================================================================================

## 스크립트명 : 실전_일반매도

"""
<검색식에서 구현: 보유종목대상>
1. 상한가 이거나,
2. 현재봉 기준 3분봉 5이평이 하락전환 하거나,
3. 현재봉 기준 3분봉 5이평이 10이평 이하 이거나,
4. 현재가가 10이평 이하 이거나,
5. 3분봉에서 봉 하나에 3%이상 급락 하거나,
6. 3분봉에서 봉 하나에 7.5%이상 급등시

<스크립트에서 구현>
1. 유성형 캔들
2. 긴 윗꼬리 달고 최고종가 이하로 하락
"""

dm = ChartManager(code, 'dy')
m3 = ChartManager(code, 'mi', 3)
logoff = is_args('logoff', False)
dc = dm.c
mo, mc, ml, ma = m3.o, m3.c, m3.l, m3.ma

if not logoff:
    # 이전 n봉부터 m봉까지 이전 cnt봉중 최고종가 얻기 (최고종가, 당일봉수)
    gcts = m3.get_close_tops(n=128, cnt=128, m=1) # 업데이트된 최고종가 리스트와 당일 봉수
    최고종가 = gcts[0] #개장후n봉최고종가
    당일봉수 = gcts[1]

msg = ''
if not logoff:
    if m3.is_shooting_star(n=1, length=1.5, up=2.5) and max(mo(1), mc(1)) > mc() and 최고종가[-1] == 1:
        msg += f'유성형'

if msg: 
    if not logoff:
        echo(f'[{True}] ({code} {name}) 현재가={dc()} / 매도조건: {msg}')
    ret(True)

ret(False)

# =============================================================================================

# 스크립트명 : 일반매도

dm = ChartManager(code, 'dy')
m3 = ChartManager(code, 'mi', 3)
logoff = is_args('logoff', False)
dc = dm.c
mo, mc, ml, mh, ma = m3.o, m3.c, m3.l, m3.h, m3.ma

if not logoff:
    # 이전 n봉부터 m봉까지 이전 cnt봉중 최고종가 얻기 (최고종가, 당일봉수)
    tops = m3.get_close_tops(n=128, cnt=128, m=1) # 업데이트된 최고종가 리스트와 당일 봉수
    최고종가 = tops[0]
    당일봉수 = tops[1]

msg = ''
c_limit = hoga(dc(1), 99)
if c_limit <= dc(0):
    msg += f'상한가'
elif ma(5, 2) <= ma(5, 1) and ma(5, 1) > ma(5, 0) and ma(5) > mc():
    msg += f'하락전환_3분5이평'
elif ma(10) > ma(5):
    msg += f'이평역전_3분5_10이평'
elif ma(10) > mc():
    msg += f'현재가10이평아래'
elif not logoff:
    if m3.is_shooting_star(n=1, length=1.5, up=2.5) and max(mo(1), mc(1)) > mc() and 최고종가[-1] == 1:
        msg += f'유성형 캔들 발생'
    # elif (mh(0) - max(mo(0), mc(0))) / mo(0) >= 0.02 and mc(최고종가[-1]) > mc(0):
    #     msg += f'긴 윗꼬리 달고 최고종가 이하로 하락'

if msg: 
    if not logoff:
        echo(f'[{True}] ({code} {name}) 현재가={dc()} / 매도조건: {msg}')
    ret(True)

ret(False)

# =============================================================================================

# 스크립트명 : 고점하락예측매도

"""
<검색식에서 구현: 보유종목대상>
1. 현재봉이 유성형 캔들이거나,
2. 현재봉이 교수형(행잉맨) 캔들이거나,
3. 현재봉이 하락 포괄 패턴이거나,
4. 현재봉이 도지 캔들이면서 이전봉이 상승봉이거나,
5. 현재봉이 긴 윗꼬리를 가진 캔들이거나,
6. 현재봉이 이전봉의 고가를 돌파하지 못하고 하락하거나,
7. 현재봉이 거래량 급감과 함께 하락하거나,
8. 현재봉이 이평선을 하향 돌파하거나,
9. 현재봉이 RSI 과매수 구간에서 하락 전환하거나,
10. 현재봉이 MACD 하락 전환 신호가 나오거나

<스크립트에서 구현>
1. 고점 확인: 최근 N봉 중 최고가 대비 현재가 하락률 확인
2. 캔들 패턴 확인: 하락 암시 캔들 패턴 감지
3. 기술적 지표 확인: 과매수 구간에서의 하락 신호
4. 거래량 확인: 거래량 감소와 함께 오는 하락
5. 이평선 확인: 단기 이평선 하락 전환
"""

dm = ChartManager(code, 'dy')
m3 = ChartManager(code, 'mi', 3)
logoff = is_args('logoff', False)
dc = dm.c
mo, mc, ml, mh, mv = m3.o, m3.c, m3.l, m3.h, m3.v

if not logoff:
    # 이전 n봉부터 m봉까지 이전 cnt봉중 최고종가 얻기 (최고종가, 당일봉수)
    gcts = m3.get_close_tops(n=128, cnt=128, m=1)
    최고종가 = gcts[0]
    당일봉수 = gcts[1]

msg = ''

# 1. 고점 확인 (최근 10봉 중 최고가 대비 2% 이상 하락)
최근최고가 = m3.highest(m3.h, 10, 0)
현재가 = mc(0)
하락률 = div(현재가 - 최근최고가, 최근최고가, 0)

if 하락률 < -0.02:  # 2% 이상 하락
    msg = f'고점대비하락({하락률:.1%})'

# 2. 캔들 패턴 확인
elif m3.is_shooting_star(n=0, length=1.5, up=2.0):  # 유성형 캔들
    msg = f'유성형'

elif m3.is_hanging_man(n=0, length=2.0, down=2.0):  # 교수형(행잉맨) 캔들
    msg = f'교수형'

elif m3.is_engulfing(n=0, bullish=False):  # 하락 포괄 패턴
    msg = f'하락포괄'

elif m3.is_doji(n=0, threshold=0.1) and mc(1) > mo(1):  # 도지 캔들 (이전봉이 상승봉인 경우)
    msg = f'도지(상승후)'

elif (mh(0) - max(mo(0), mc(0))) / mo(0) >= 0.02 and mc(0) < mo(0):  # 긴 윗꼬리 캔들
    msg = f'긴윗꼬리'

# 3. 기술적 지표 확인
elif m3.rsi(14, 1) > 70 and m3.rsi(14, 0) < m3.rsi(14, 1):  # RSI 과매수 구간에서 하락 전환
    msg = f'RSI하락전환({m3.rsi(14, 0):.1f})'

elif m3.macd(12, 26, 9, 0)[2] < m3.macd(12, 26, 9, 1)[2] and m3.macd(12, 26, 9, 1)[2] > 0:  # MACD 하락 전환
    msg = f'MACD하락전환'

# 4. 거래량 확인
elif mv(0) < mv(1) * 0.7 and mc(0) < mc(1):  # 거래량 급감과 함께 하락
    msg = f'거래량급감하락'

# 5. 이평선 확인
elif m3.ma(5, 0) < m3.ma(5, 1) and mc(0) < m3.ma(5, 0):  # 단기 이평선 하락 전환
    msg = f'이평선하락전환'

# 6. 추가 조건: 최고종가 이후 하락 패턴
elif 최고종가 and 최고종가[0] <= 5:  # 최근 5봉 이내에 최고종가가 있으면
    최근최고종가 = 최고종가[0]
    최고종가봉종가 = mc(최근최고종가)
    현재가 = mc(0)
    하락률 = div(현재가 - 최고종가봉종가, 최고종가봉종가, 0)
    
    if 하락률 < -0.015:  # 1.5% 이상 하락
        msg = f'최고종가이후하락({하락률:.1%})'

# 매도 사유가 있으면 True, 없으면 False
if msg: 
    if not logoff:
        echo(f'[{True}] ({code} {name}) 현재가={dc()} / 고점하락예측매도: {msg}')
    ret(True)

ret(False)

# =============================================================================================

# 스크립트명 : 실전_매도

"""
<검색식에서 구현: 보유종목대상>
1. 상한가 이거나,
2. 현재봉 기준 3분봉 5이평이 하락전환 하거나,
3. 현재봉 기준 3분봉 5이평이 10이평 이하 이거나,
4. 현재가가 10이평 이하 이거나,
5. 3분봉에서 봉 하나에 3%이상 급락 하거나,
6. 3분봉에서 봉 하나에 7.5%이상 급등시

<스크립트에서 구현>
1. 기본 매도 조건 (일반매도)
2. 고점하락예측 매도 조건
3. 유성형 캔들
4. 긴 윗꼬리 달고 최고종가 이하로 하락
"""

dm = ChartManager(code, 'dy')
m3 = ChartManager(code, 'mi', 3)
logoff = is_args('logoff', False)
dc = dm.c
mo, mc, ml, mh, mv = m3.o, m3.c, m3.l, m3.h, m3.v

if not logoff:
    # 이전 n봉부터 m봉까지 이전 cnt봉중 최고종가 얻기 (최고종가, 당일봉수)
    gcts = m3.get_close_tops(n=128, cnt=128, m=1)
    최고종가 = gcts[0]
    당일봉수 = gcts[1]

msg = ''

# 1. 기본 매도 조건 (일반매도)
c_limit = hoga(dc(1), 99)
if c_limit <= dc(0):  # 상한가
    msg = f'상한가'

elif m3.ma(5, 2) <= m3.ma(5, 1) and m3.ma(5, 1) > m3.ma(5, 0) and m3.ma(5) > mc():  # 하락전환_3분5이평
    msg = f'하락전환_3분5이평'

elif m3.ma(10) > m3.ma(5):  # 이평역전_3분5_10이평
    msg = f'이평역전_3분5_10이평'

elif m3.ma(10) > mc():  # 현재가10이평아래
    msg = f'현재가10이평아래'

# 2. 고점하락예측 매도 조건
elif m3.highest(m3.h, 10, 0) > 0:  # 고점 확인
    최근최고가 = m3.highest(m3.h, 10, 0)
    현재가 = mc(0)
    하락률 = div(현재가 - 최근최고가, 최근최고가, 0)
    
    if 하락률 < -0.02:  # 2% 이상 하락
        msg = f'고점대비하락({하락률:.1%})'

elif m3.is_hanging_man(n=0, length=2.0, down=2.0):  # 교수형(행잉맨) 캔들
    msg = f'교수형'

elif m3.is_engulfing(n=0, bullish=False):  # 하락 포괄 패턴
    msg = f'하락포괄'

elif m3.is_doji(n=0, threshold=0.1) and mc(1) > mo(1):  # 도지 캔들 (이전봉이 상승봉인 경우)
    msg = f'도지(상승후)'

elif (mh(0) - max(mo(0), mc(0))) / mo(0) >= 0.02 and mc(0) < mo(0):  # 긴 윗꼬리 캔들
    msg = f'긴윗꼬리'

elif mc(0) < mc(1) and mc(1) < mc(2):  # 연속 하락
    msg = f'연속하락'

elif mh(0) < mh(1) and mc(0) < mc(1):  # 고가 갱신 실패
    msg = f'고가갱신실패'

elif mv(0) > mv(1) * 1.5 and mc(0) < mc(1):  # 거래량 급증과 함께 하락
    msg = f'거래량급증하락'

elif mv(0) < mv(1) * 0.5 and mc(0) < mc(1):  # 거래량 급감과 함께 하락
    msg = f'거래량급감하락'

elif 최고종가 and 최고종가[0] <= 5:  # 최근 5봉 이내에 최고종가가 있으면
    최근최고종가 = 최고종가[0]
    최고종가봉종가 = mc(최근최고종가)
    현재가 = mc(0)
    하락률 = div(현재가 - 최고종가봉종가, 최고종가봉종가, 0)
    
    if 하락률 < -0.015:  # 1.5% 이상 하락
        msg = f'최고종가이후하락({하락률:.1%})'

elif m3.is_shooting_star(n=1, length=1.5, up=2.5) and max(mo(1), mc(1)) > mc() and 최고종가 and 최고종가[-1] == 1:  # 유성형 캔들 발생
    msg = f'유성형 캔들 발생'

# 매도 사유가 있으면 True, 없으면 False
if msg: 
    if not logoff:
        echo(f'[{True}] ({code} {name}) 현재가={dc()} / 실전매도: {msg}')
    ret(True)

ret(False)

# =============================================================================================
