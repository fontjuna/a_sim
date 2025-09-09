from chart import ChartManager, echo, is_args, ret, div, percent, ma, hoga, 일반매도

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
7. 현재봉 포함 20일 최고거래량대비 1분 0, 1, 2전봉중 하나의 거래량이 2% 이상

<스크립트에서 구현>
1. 일반매도 스크립트 조건에 해당하지 않고,
2. 전봉이 유성형 캔들이 아니고,
3. 전봉이 교수형 캔들이 아니고,
4. 전봉이 긴 음봉이 아니고,
5. 최고종가 갱신봉이 당일 1개 이상이어야 하고,
6. 최고종가봉중 0.5% 이하 상승봉은 없는 봉으로 간주하여 3연속 최고종가는 회피하고,
7. 당일 최고종가 대비 최저 종가는 -5%이상이거나 시가가 고가 보다 높아야 하고,
8. 마지막 최고종가의 봉상태가 고가와 종가 차이가 저가와 종가 차이보다 작아야 하고 아니면 그 고가를 넘어서야 함,
9. 119일(당일 제외) 최고거래량 봉의 최고가를 시가가 높거나 최고거래량의 시가와 현재봉 시가가 -20%이하 이거나 최고 거래량의 67% 이상이어야 함.
"""
m3 = ChartManager(code, 'mi', 3)
dt = ChartManager(code, 'dy')

if 일반매도(logoff=True):
    echo(f'[False] ({code} {name}) / 매도조건에 해당')
    ret(False)

최고종가, 당일봉수 = m3.get_close_tops(w=128, m=128, n=1)
종가수 = len(최고종가) if 최고종가 else 0

if 종가수 == 0:
    echo(f'[False] ({code} {name}) / 최고종가 0개')
    ret(False)

if 당일봉수 == 1: 
    echo(f'[False] ({code} {name}) / 당일 첫봉 매수 안함 : ({당일봉수}) {최고종가}')
    ret(False)

pos = 최고종가[-1]
# 기본 값 접근자 별칭
o, h, l, c, v, ma = m3.o, m3.h, m3.l, m3.c, m3.v, m3.ma

# 최근 5봉 중 1.2% 이상 상승 여부(경량 계산)
with m3.suspend_ensure():
    has_big_up = any(((abs(c(i) - o(i)) / o(i) * 100) if o(i) else 0) >= 1.2 for i in range(5))
if not has_big_up:
    echo(f'[False] ({code} {name}) / 5봉중 1.2% 이상 상승 없으면 매수 안함')
    ret(False)

# 3연속 최고종가 회피 (0.5% 이하는 없는 봉으로 간주)
if 종가수 >= 2:
    연속갯수 = 0
    with m3.suspend_ensure():
        for i in range(종가수):
            loc = 최고종가[-(i+1)]  # 뒤에서부터 읽기 (현재봉부터)
            if i > 0 and loc != 최고종가[-(i)] - 1:  # 연속되지 않으면 종료
                break
            상승률 = percent(c(loc), c(loc + 1))
            if 상승률 > 0.5:  # 양봉이면서 0.5% 초과
                연속갯수 += 1
                if 연속갯수 >= 3:  # 3개 이상이면 즉시 종료
                    break
            # 음봉이거나 0.5% 이하면 없는 봉으로 간주하고 계속 진행
    
    if 연속갯수 >= 3:
        echo(f'[False] ({code} {name}) / 3연속 최고종가 회피 (0.5% 이하 제외) : ({당일봉수}) {최고종가} (연속갯수: {연속갯수})')
        ret(False)

# 전 최고종가의 고가 아래이면 다음을 만족 해야 함
if c(0) < h(pos):
    with m3.suspend_ensure():
        if h(pos) - c(pos) > c(pos) - l(pos) and h(pos) > o(0):
            echo(f'[False] ({code} {name}) / 최고종가봉이 하락 우세임 : ({당일봉수}) {최고종가}')
            ret(False)

        extr = m3.get_extremes(m=pos, n=1)
        up_tail_pct = m3.up_tail_pct
        body_pct = m3.body_pct
        if up_tail_pct(pos+1) > 1.0 and h(pos+1) >= h(pos):
            echo(f'[False] ({code} {name}) / 전고점 넘지 못한 최고종가 회피 : ({당일봉수}) {최고종가}')
            ret(False)

        # 전 최고종가를 넘었어도 윗꼬리가 계속 발생하며 고가 갱신을 못함
        if up_tail_pct(pos) > 1.0 and h(pos) >= h(1) > c(1) and up_tail_pct(1) > body_pct(1) * 1.5:
            echo(f'[False] ({code} {name}) / 전 최고종가의 고가저항에 윗 꼬리 발생 : ({당일봉수}) {최고종가}')
            ret(False)

        # 윗 꼬리 단 최고 종가의 고점을 넘지 못하면 매물대 라는 뜻으로 올라가기 쉽지 않다.
        if pos > 1:
            if up_tail_pct(pos) > 1.0 and h(pos) > extr['hh']:
                echo(f'[False] ({code} {name}) / 최고종가 고점을 넘지 못함 : ({당일봉수}) {최고종가}')
                ret(False)

        하락률 = percent(extr['hh'], extr['ll'])
        if 하락률 > 5.0:
            echo(f'[False] ({code} {name}) / 당일 하락율 조건 불충족 : ({당일봉수}) {최고종가}')
            ret(False)

        if not (extr['hv'] > v(pos) or v(pos) * 0.8 < v(0)):
            echo(f'[False] ({code} {name}) / 전고돌파 수급 조건 불충족 : ({당일봉수}) {최고종가}')
            ret(False)

        # 일봉상 긴 윗꼬리가 달린 봉이 많이 나타나는 종목은 털리기 쉽다.
        윗꼬리_많은종목 = 0
        한계치 = 3
        for i in range(1, 11):
            up_tail = dt.h(i) - max(dt.o(i), dt.c(i))
            body = abs(dt.o(i) - dt.c(i))
            if body > 0 and up_tail > body: 윗꼬리_많은종목 += 1
            if 윗꼬리_많은종목 >= 한계치: break
        if 윗꼬리_많은종목 >= 한계치:
            echo(f'[False] ({code} {name}) / 최근 10개봉 중 몸통보다 긴 윗꼬리 봉 {윗꼬리_많은종목}개')
            ret(False)

with dt.suspend_ensure():
    idx, date, hv_o, hv_h, hv_l, hv_c, hv_v, hv_a = dt.get_highest_volume(m=119, n=1)

diff = percent(hv_l, dt.o(0)) > 20.0
if not (hv_h <= o(0) or diff or dt.v(0) >= hv_v * 0.67):
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

tops = m3.get_close_tops(w=128, m=128, n=1)
최고종가 = tops[0]
당일봉수 = tops[1]

if len(최고종가) < 1: pos = 1
else: pos = 최고종가[-1]

# 상승율 = m3.rise_pct_since_ma_cross_up(mp=5, n=pos)
# 직접 값으로만 연산 (경량)
o, h, l, c, ma = m3.o, m3.h, m3.l, m3.c, m3.ma
# 봉 특성 별칭 (필요 시 즉시 호출)
top, bottom = m3.body_top, m3.body_bottom
up_tail, down_tail = m3.up_tail, m3.down_tail
body = m3.body
body_pct = m3.body_pct
length_pct = m3.length_pct
up_tail_pct = m3.up_tail_pct
down_tail_pct = m3.down_tail_pct

msg = ''
with m3.suspend_ensure():
    # 최상위: 매우 가벼운 판정들
    if hoga(dm.c(1), 99) <= dm.c(0):
        msg = f'상한가'
    elif ma(10, 1) > ma(5, 1):
        msg = f'전봉 5, 10이평 역전'
    elif c(1) < ma(10, 1):
        msg = f'종가가 10이평 아래'
    else:
        if not msg and c(2) > o(2) > c(1):
            idx, date, hv_o, hv_h, hv_l, hv_c, hv_v, hv_a = m3.get_highest_volume(m=10, n=1)
            if min(hv_o, hv_c) > c(1):
                msg = f'10봉중 최고거래량봉 아래로 이탈'

        if not msg and (h(2) > h(1) and bottom(1) >= top(2)):
            if up_tail(1) > down_tail(1):
                msg = f'전봉 고가 갱신 불발후 위꼬리 내부에서 마감'

        if not msg and up_tail_pct(1) >= 2.0:
            if bottom(1) == l(1) or up_tail(1) > (c(1) - l(1)) * 2.5:
                msg = f'윗꼬리 2%이상 유성형 패턴으로 급락'

        # 음봉 패턴군 (blue)
        if not msg and (c(1) < o(1)):
            if up_tail_pct(1) >= 1.0:
                if top(2) < bottom(1):
                    msg = f'윗꼬리 1%이상 음봉 갭 상승 마감'
                elif up_tail(1) >= body(1) * 2.5 and up_tail(1) * 0.2 > down_tail(1):
                    msg = f'윗꼬리 1%이상 유성형 음봉'
                elif body(1) >= up_tail(1) * 0.8:
                    msg = f'윗꼬리 1%이상 떨어지는 칼날'
            elif up_tail_pct(2) >= 1.0 and up_tail(2) > down_tail(2):
                if h(2) >= h(1) and (h(1) - c(1)) / o(1) > 0.01:
                    msg = f'윗꼬리 1%이상 연속 고가 저항'
            elif (c(2) >= o(2)) and (body_pct(2) > 1):
                if top(2) >= top(1) and bottom(2) < bottom(1) and length_pct(1) < 1:
                    msg = f'하락 잉태형 패턴'
                elif top(2) <= top(1) and bottom(2) > bottom(1):
                    msg = f'하락 장악형 패턴'

        # 양봉 패턴군 (red)
        if not msg and (c(1) >= o(1)):
            if up_tail_pct(1) >= 1.5 and (o(1) == l(1) or (up_tail(1) >= body(1) * 3 and up_tail(1) * 0.2 > down_tail(1))):
                msg = f'윗꼬리 1.5% 이상 몸통의 3배 유성형 양봉'
            elif (c(2) >= o(2)) and (body_pct(2) > 1):
                if top(2) >= top(1) and bottom(2) < bottom(1) and length_pct(1) < 0.5:
                    msg = f'하락 잉태형 패턴'

        # 최고종가 봉 패턴군 (pos)
        if not msg and pos > 2:
            if h(pos) > h(1) and bottom(1) >= top(pos):
                msg = f'최고종가봉 고가 갱신 불발후 위꼬리 내부에서 마감'
            elif (c(pos) >= o(pos)) and (((c(pos) - o(pos)) / o(pos) * 100.0) if o(pos) else 0.0) > 1:
                if top(pos) >= top(1) and bottom(pos) < bottom(1) and length_pct(1) < 1:
                    msg = f'최고종가 하락 잉태형 패턴'
                elif top(pos) <= top(1) and bottom(pos) > bottom(1):
                    msg = f'최고종가 하락 장악형 패턴'

    if not msg and down_tail_pct(1) >= 1.0 and down_tail(1) > body(1) * 5 and up_tail(1) < down_tail(1) * 0.2:
        msg = f'교수형 캔들'

if msg: 
    if not logoff:
        echo(f'[{True}] ({code} {name}) 현재가={dm.c()} / {msg}')
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
    gcts = m3.get_close_tops(w=128, m=128, n=1) # 업데이트된 최고종가 리스트와 당일 봉수
    최고종가 = gcts[0] #개장후n봉최고종가
    당일봉수 = gcts[1]

msg = ''
if not logoff:
    if m3.is_shooting_star(length=1.5, up=2.5) and max(mo(1), mc(1)) > mc() and 최고종가[-1] == 1:
        msg += f'유성형'

if msg: 
    if not logoff:
        echo(f'[{True}] ({code} {name}) 현재가={dc()} / 매도조건: {msg}')
    ret(True)

ret(False)


# =============================================================================================

# 스크립트명 : 실전_돌파매수_백업
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

매도조건 = 일반매도(logoff=True)
if 매도조건:
    echo(f'[{False}] ({code} {name}) / 매도조건에 해당')
    ret(False)

최고종가, 당일봉수 = m3.get_close_tops(w=128, m=128, n=1)
종가수 = len(최고종가) if 최고종가 else 0

if 종가수 == 0:
    echo(f'[False] ({code} {name}) / 최고종가 0개')
    ret(False)

if 당일봉수 == 1: 
    echo(f'[False] ({code} {name}) / 당일 첫봉 매수 안함 : ({당일봉수}) {최고종가}')
    ret(False)

pos = 최고종가[-1]
B = m3.snapshot(0, 1, 2, 3, 4, pos)
if any((not d.get('is_valid')) or ('body_pct' not in d) for d in B.values()):
    echo(f'[False] ({code} {name}) / 캔들 데이터 이상')
    ret(False)

if not any(d.get('body_pct', 0) >= 1.2 for d in B.values()):
    echo(f'[False] ({code} {name}) / 5봉중 1.2% 이상 상승 없으면 매수 안함')
    ret(False)

# 3연속 최고종가 회피 (0.5% 이하는 없는 봉으로 간주)
if 종가수 >= 2:
    연속갯수 = 0
    for i in range(종가수):
        loc = 최고종가[-(i+1)]  # 뒤에서부터 읽기 (현재봉부터)
        if i > 0 and loc != 최고종가[-(i)] - 1:  # 연속되지 않으면 종료
            break
        상승률 = percent(m3.c(loc), m3.c(loc + 1))
        if 상승률 > 0.5:  # 양봉이면서 0.5% 초과
            연속갯수 += 1
            if 연속갯수 >= 3:  # 3개 이상이면 즉시 종료
                break
        # 음봉이거나 0.5% 이하면 없는 봉으로 간주하고 계속 진행
    
    if 연속갯수 >= 3:
        echo(f'[False] ({code} {name}) / 3연속 최고종가 회피 (0.5% 이하 제외) : ({당일봉수}) {최고종가} (연속갯수: {연속갯수})')
        ret(False)

extr = m3.get_extremes(m=(pos - 1), n=1)
하락률 = percent(extr['hh'], extr['lc'], extr['hc'])
if not (하락률 > -5.0 or 하락률 < -5.0 and extr['hh'] < B[0]['o']):
    echo(f'[False] ({code} {name}) / 당일 하락율 조건 불충족 : ({당일봉수}) {최고종가}')
    ret(False)

if B[pos]['c'] - B[pos]['l'] < B[pos]['h'] - B[pos]['c'] and B[pos]['h'] > B[0]['o']:
    echo(f'[False] ({code} {name}) / 최고종가봉이 하락 우세임 : ({당일봉수}) {최고종가}')
    ret(False)

idx, date, o, h, l, c, v, a = dt.get_highest_volume(m=119, n=1)
diff = percent(l, B[0]['o']) > 20.0
if not (h <= B[0]['o'] or diff or dt.v(0) >= v * 0.67):
    echo(f'[False] ({code} {name}) / 최고거래량 조건 불충족 : ({당일봉수}) {최고종가}')
    ret(False)

echo(f'[True] ({code} {name}) / ({당일봉수}) {최고종가}')
ret(True)

# =============================================================================================

# 스크립트명 : 일반매도_백업

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

tops = m3.get_close_tops(w=128, m=128, n=1)
최고종가 = tops[0]
당일봉수 = tops[1]

if len(최고종가) < 1: pos = 1
else: pos = 최고종가[-1]

# 상승율 = m3.rise_pct_since_ma_cross_up(mp=5, n=pos)
B = m3.snapshot(1, 2, pos)
if any(not d.get('is_valid') for d in B.values()):
    echo(f'[False] ({code} {name}) / 캔들 데이터 이상')
    ret(False)

ma10_1 = ma(10, 1)
ma5_1 = ma(5, 1)

msg = ''
if hoga(dm.c(1), 99) <= dm.c(0):
    msg = f'상한가'
# elif logoff and ma10(1) > B[1]['c']: #logoff면 5봉이내에 기준% 이상 상승봉 있음
#     msg = f'전봉 종가가 10이평 아래'
elif ma10_1 > ma5_1:
    msg = f'전봉 5, 10이평 역전'
elif B[pos]['center'] < ma5_1 and m3.reverse_down(mp=5, n=1):
    msg = f'전봉 5이평 하락 전환'
elif B[2]['h'] > B[1]['h'] and B[1]['bottom'] >= B[2]['top']:
    msg = f'전봉 고가 갱신 불발후 위꼬리 내부에서 마감'
elif B[1]['up_tail_pct'] >= 2.0:
    if B[1]['bottom'] == B[1]['l'] or B[1]['up_tail'] > (B[1]['c'] - B[1]['l']) * 2.5: 
        msg = f'윗꼬리 2%이상 유성형 패턴으로 급락'
elif B[1]['blue']:
    # 전봉을 대상으로
    if B[1]['up_tail_pct'] >= 1.0:
        if B[2]['top'] < B[1]['bottom']:
            msg = f'윗꼬리 1%이상 음봉 갭 상승 마감'
        elif B[1]['up_tail'] >= B[1]['body'] * 2.5 and B[1]['up_tail'] > B[1]['down_tail'] * 5:
            msg = f'윗꼬리 1%이상 유성형 음봉'
    elif B[2]['red'] and B[2]['body_pct'] > 1:
        if B[2]['top'] >= B[1]['top'] and B[2]['bottom'] < B[1]['bottom'] and B[1]['length_pct'] < 1:
            msg = f'하락 잉태형 패턴'
        elif B[2]['top'] <= B[1]['top'] and B[2]['bottom'] > B[1]['bottom']:
            msg = f'하락 장악형 패턴'

    # 최고종가봉 대상
    elif pos > 2:
        if B[pos]['h'] > B[1]['h'] and B[1]['bottom'] >= B[pos]['top']:
            msg = f'최고종가봉 고가 갱신 불발후 위꼬리 내부에서 마감'
        elif B[pos]['red'] and B[pos]['body_pct'] > 1:
            if B[pos]['top'] >= B[1]['top'] and B[pos]['bottom'] < B[1]['bottom'] and B[1]['length_pct'] < 1:
                msg = f'최고종가 하락 잉태형 패턴'
            elif B[pos]['top'] <= B[1]['top'] and B[pos]['bottom'] > B[1]['bottom']:
                msg = f'최고종가 하락 장악형 패턴'
elif B[1]['red']:
    # 전봉을 대상으로
    if B[1]['up_tail_pct'] >= 1.0:
        if B[1]['o'] == B[1]['l'] or B[1]['up_tail'] >= B[1]['body'] * 2.5 and B[1]['up_tail'] > B[1]['down_tail'] * 5:
            msg = f'윗꼬리 1%이상 유성형 양봉'
    elif B[2]['red'] and B[2]['body_pct'] > 1:
        if B[2]['top'] >= B[1]['top'] and B[2]['bottom'] < B[1]['bottom'] and B[1]['length_pct'] < 0.5:
            msg = f'하락 잉태형 패턴'

    # 최고종가봉 대상
    elif pos > 2:
        if B[pos]['h'] > B[1]['h'] and B[1]['bottom'] >= B[pos]['top']:
            msg = f'최고종가봉 고가 갱신 불발후 위꼬리 내부에서 마감'
        elif B[pos]['red'] and B[pos]['body_pct'] > 1:
            if B[pos]['top'] >= B[1]['top'] and B[pos]['bottom'] < B[1]['bottom'] and B[1]['length_pct'] < 0.5:
                msg = f'최고종가 하락 잉태형 패턴'
elif m3.is_hanging_man(length=1, down=5, up=0.2, n=1) and B[pos]['h'] > B[1]['h']:
    msg = f'교수형 캔들'

if msg: 
    if not logoff:
        echo(f'[{True}] ({code} {name}) 현재가={dm.c()} / 매도조건: {msg}')
    ret(True)

ret(False)