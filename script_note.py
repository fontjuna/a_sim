from chart import ChartManager, echo, is_args, ret, div, ma, hoga, 일반매도

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
6. 전일 최고가 대비 종가 하락율 7.5%이내이거나 전일 최고가 대비 종가 하락율 7.5%이상이면서 현재가가 전일 최고가를 넘어서야 하고
7. 현재봉 포함 120일 최고거래량대비 1분 0, 1, 2전봉중 하나의 거래량이 2% 이상

<스크립트에서 구현>
1. 일반매도 스크립트 조건에 해당하지 않고,
2. 전봉이 유성형 캔들이 아니고,
3. 전봉이 교수형 캔들이 아니고,
4. 전봉이 긴 음봉이 아니고,
5. 최고종가 갱신봉이 당일 1개 이상이어야 하고,
6. 최고종가봉중 0.5% 이하 상승봉은 없는 봉으로 간주하여 3연속 최고종가는 회피하고,
7. 당일 최고종가 대비 최저 종가는 -5%이상이거나 시가가 고가 보다 높아야 하고,
8. 마지막 최고종가의 봉상태가 고가와 종가 차이가 저가와 종가 차이보다 작아야 하고 아니면 그 고가를 넘어서야 함,
9. 59일(당일 제외) 최고거래량 봉의 최고가를 시가가 높거나 최고거래량의 시가와 현재봉 시가가 -20%이하 이거나 최고 거래량의 67% 이상이어야 함.
"""
m3 = ChartManager(code, 'mi', 3)
dt = ChartManager(code, 'dy')
dh, dc, do, dv = dt.h, dt.c, dt.o, dt.v
mo, mh, ml, mc, mv = m3.o, m3.h, m3.l, m3.c, m3.v

매도조건 = 일반매도(logoff=True)
if 매도조건:
    echo(f'[{False}] ({code} {name}) / 매도조건에 해당')
    ret(False)

bars = [m3.get_candle_data(i) for i in range(5)]
if not any( d['body_pct'] >= 1.2 for d in bars ):
    echo(f'[False] ({code} {name}) / 5봉중 1.2% 이상 상승 없으면 매수 안함')
    ret(False)

if bars[1]['up_tail_pct'] >= 1.2 and bars[1]['up_tail_pct'] >= bars[1]['body_pct'] * 2.5:
    echo(f'[False] ({code} {name}) / 유성형 캔들 다음 매수 안함')
    ret(False)

if bars[1]['down_tail_pct'] >= 1 and bars[1]['down_tail_pct'] >= bars[1]['body_pct'] * 5:
    echo(f'[False] ({code} {name}) / 교수형 캔들 다음 매수 안함')
    ret(False)

if bars[1]['blue'] and bars[1]['body_pct'] > 2 and mh(1) > mc(0):
    echo(f'[False] ({code} {name}) / 긴 음봉 다음 매수 안함')
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
        pos = 최고종가[-(i+1)]  # 뒤에서부터 읽기 (현재봉부터)
        if i > 0 and pos != 최고종가[-(i)] - 1:  # 연속되지 않으면 종료
            break
        상승률 = m3.percent(mc(pos), mc(pos + 1))
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
하락률 = m3.percent(extr['hh'], extr['lc'], extr['hc'])
if not (하락률 > -5.0 or 하락률 < -5.0 and extr['hh'] < mo(0)):
    echo(f'[False] ({code} {name}) / 당일 하락율 조건 불충족 : ({당일봉수}) {최고종가}')
    ret(False)

if mc(loc) - ml(loc) < mh(loc) - mc(loc) and mh(loc) > mc(0):
    echo(f'[False] ({code} {name}) / 최고종가봉이 하락 우세임 : ({당일봉수}) {최고종가}')
    ret(False)

idx, date, o, h, l, c, v, a = dt.get_highest_volume(119, 1)
diff = m3.percent(l, mo(0)) > 20.0
if not (h <= mo(0) or diff or dv(0) >= v * 0.67):
    echo(f'[False] ({code} {name}) / 최고거래량 조건 불충족 : ({당일봉수}) {최고종가}')
    ret(False)

echo(f'[True] ({code} {name}) / ({당일봉수}) {최고종가}')
ret(True)


# =============================================================================================

# 스크립트명 : 일반매도

"""
<검색식에서 구현: 보유종목대상>
- 없음.

<스크립트에서 구현>
1. 상한가 이거나
2. 3분봉 5이평이 하락전환 하거나
3. 3분봉 5이평이 10이평 이하 이거나
4. 현재가가 10이평 이하 이거나
5. 유성형(전봉 위꼬리는 1.5%이상 몸통의 2.5배 이상이고 max(전봉시가, 종가) 보다 현재가 낮음) 이거나
6. 교수형(전봉 아래꼬리는 1.5%이상 몸통의 5배 이상이고 전봉 고가갱신을 못함) 이거나
7. 막다른 골목(상승중 장대양봉이 서고 그 종가보다 낮은 시가로 양봉마감 했지만 고가 돌파 못함) 이거나
8. 상승장 갭 상승 음봉(현재봉 시가가 이전봉 종가보다 낮고 종가가 이전봉 시가보다 낮음) 이거나
"""
dm = ChartManager(code, 'dy')
m3 = ChartManager(code, 'mi', 3)
logoff = is_args('logoff', False)
dc = dm.c
mo, mc, ml, mh, ma = m3.o, m3.c, m3.l, m3.h, m3.ma

tops = m3.get_close_tops(n=128, cnt=128, m=1)
최고종가 = tops[0]
당일봉수 = tops[1]

if len(최고종가) < 1: pos = 1
else: pos = 최고종가[-1]

상승율 = m3.rise_pct_since_ma_cross_up(pos, 5)

msg = ''
if hoga(dc(1), 99) <= dc(0):
    msg = f'상한가'
elif 상승율 <= 3.0:
    if ma(10, 1) > mc(1):
        msg = f'전봉 종가가 10이평 아래'
elif 상승율 <= 5.0:
    if msg: pass
    elif ma(10, 1) > ma(5, 1):
        msg = f'전봉 5, 10이평 역전'
    elif m3.reverse_down(5, 1) and m3.trend_down(1, 5):
        msg = f'전봉 5이평 하락 전환'
elif 상승율 <= 30.0:
    if msg: pass
    elif mc(pos) > mo(1) > mc(1) > mo(pos): # 최고종가 보다 낮게 시작한 음봉이 최고종가 시가를 깨진 않았으나,
        # 최고종가봉은 1.5%이상이며 전봉이 고가 갱신을 못함
        if m3.percent(mc(pos), mo(pos)) >= 1.5 and mh(pos) > mh(1):
            msg = f'하락 잉태형'
    elif m3.percent(mh(1), mo(1)) >= 2.0 and m3.blue(1): #2% 이상 상승해서 시가 밑으로 하락(음봉)
        msg = f'윗꼬리 긴 음봉으로 급락'
    elif m3.percent(mh(pos), mc(pos)) >= 1.0 and mh(pos) > mh(1) > mo(1) > mc(pos) > mc(1):
        msg = f'긴 윗꼬리 최고종가봉 미 돌파 음봉 하락'
    elif m3.is_shooting_star(n=1, length=1.5, up=2.5, down=0.2) and mc(pos) <= mc(1):
        msg = f'유성형 캔들'
    elif m3.is_hanging_man(n=1, length=1, down=5, up=0.2) and mh(pos) > mh(1):
        msg = f'교수형 캔들'
    elif m3.is_engulfing(1, 1, False):
        msg = f'하락 장악형 패턴'

if msg: 
    if not logoff:
        echo(f'[{True}] ({code} {name}) 현재가={dc()} / 매도조건: {msg}')
    ret(True)

ret(False)

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
