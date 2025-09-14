from chart import ChartManager, echo, is_args, ret, div, percent, ma, hoga, 일반매도
import math

code = '005930'
name = '삼성전자'
price = 100000
qty = 100
result_cache = {}

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

# 기본 값 접근자 별칭
o, h, l, c, v, ma = m3.o, m3.h, m3.l, m3.c, m3.v, m3.ma

# 최고종가 조건 찾기 ========================================================================
m3._ensure_data_cache()
with m3.suspend_ensure():
    최고종가, 당일봉수 = m3.get_close_tops( k=1, w=128, m=128, n=1 )
    첫봉위치 = 당일봉수 - 1

if len(최고종가) == 0 or 첫봉위치 == 0: # 현재봉이 첫봉
    echo(f'[False] ({code} {name}) / 최고종가 0개 또는 당일 첫봉 매수 안함 : ({당일봉수}) {최고종가})')
    ret(False)

pos = 최고종가[0]

# 당일 첫봉이 음봉이면 그 봉 고가 밑에서 매수 안 함 =========================================
with m3.suspend_ensure():
    if o(첫봉위치) > c(첫봉위치) and h(첫봉위치) > c():
        echo(f'[False] ({code} {name}) / 당일 첫봉이 음봉이고 그 고가를 돌파 못함 : ({당일봉수}) {최고종가})')
        ret(False)

# 일반매도 조건 찾기 ========================================================================
reason = 일반매도(logoff=True)
if reason:
    echo(f'[False] ({code} {name}) / {reason}')
    ret(False)

# 최고거래량 조건 찾기 ========================================================================
dt._ensure_data_cache()
with dt.suspend_ensure():
    cache_key = f'{code}_dt_volume'
    if cache_key not in result_cache:
        max_vol = 0
        max_idx = 1
        for i in range(1, 119):
            vol = dt.v(i)
            if vol > max_vol:
                max_vol = vol
                max_idx = i
        
        # 필요한 데이터만 개별 접근
        hv_h = dt.h(max_idx)
        hv_l = dt.l(max_idx)
        result_cache[cache_key] = {'v': max_vol, 'h': hv_h, 'l': hv_l}

    dt_v = dt.v(0)
    hv_l = result_cache[cache_key]['l']
    hv_h = result_cache[cache_key]['h']
    hv_v = result_cache[cache_key]['v']

if not (hv_h <= o(0) or hv_l > h(1) and max_idx > 1 or dt_v >= hv_v * 0.67):
    echo(f'[False] ({code} {name}) / 최고거래량 조건 불충족')
    ret(False)

# 상승율 조건 찾기 ========================================================================
with m3.suspend_ensure():
    more_than = 0
    for i in range(5):
        if percent(c(i), c(i + 1)) >= 0.5: 
            more_than += 1
            break

if more_than == 0: # or less_than > 0:
    echo(f'[False] ({code} {name}) / 5봉중 0.5% 상승 여부 불충족')
    ret(False)

# 연속봉수 조건 찾기 ========================================================================
with m3.suspend_ensure():
    연속갯수 = 0
    for i in range(1, 128):
        if c(i) == 0: break
        compare_start = i + 1
        compare_end = i + 128
        max_close = 0
        for j in range(compare_start, compare_end):
            cj = c(j)
            if cj == 0: break
            if cj > max_close: max_close = cj
        if c(i) > max_close:
            상승률 = percent(c(i), c(i + 1))
            if 상승률 > 0.5:
                연속갯수 += 1
                if 연속갯수 >= 3:
                    break
        else:
            break

if 연속갯수 >= 3:
    echo(f'[False] ({code} {name}) / 3연속 최고종가 회피 (0.5% 이하 제외) (연속갯수: {연속갯수})')
    ret(False)

# 전 최고종가의 고가 아래이면 다음을 만족 해야 함 ========================================================================
with m3.suspend_ensure():
    if c(0) < h(pos):
        if h(pos) - c(pos) > c(pos) - l(pos) and h(pos) > c(0):
            echo(f'[False] ({code} {name}) / 최고종가봉이 하락 우세임 : ({당일봉수}) {최고종가}')
            ret(False)

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
            label, pct = m3.price_position(n=pos, price=c(0))
            if pct['h_pct'] - pct['c_pct'] > 1.0 and h(pos) > dt.h(0):
                # 추가적인 조건이 필요 함
                echo(f'[False] ({code} {name}) / 최고종가 고점을 넘지 못함 : ({당일봉수}) {최고종가}')
                ret(False)

        if pos > 1:
            extr = m3.get_extremes(m=pos, n=1)
            하락률 = percent(extr['hh'], extr['ll'])
            시작위치 = percent(extr['ll'], o(0))
            if 하락률 > 5.0 and 시작위치 < 80.0 and not (l(pos) <= extr['ll'] and h(pos) >= extr['hh']):
                echo(f'[False] ({code} {name}) / 당일 하락율 조건 불충족 : ({당일봉수}) {최고종가}')
                ret(False)

        # if not (extr['hv'] > v(pos) or v(pos) * 0.8 < v(0)):
        #     echo(f'[False] ({code} {name}) / 전고돌파 수급 조건 불충족 : ({당일봉수}) {최고종가}')
        #     ret(False)

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

echo(f'[True] ({code} {name}) / ({당일봉수}) {최고종가}')
ret(True)








# =============================================================================================

# 스크립트명 : 일반매도

"""
<검색식에서 구현: >
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

최고종가, 당일봉수 = m3.get_close_tops(k=1, w=128, m=128, n=1)

if len(최고종가) == 0: pos = 1
else: pos = 최고종가[0]

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
m3._ensure_data_cache()
with m3.suspend_ensure():
    # 최상위: 매우 가벼운 판정들
    if hoga(dm.c(1), 99) <= dm.c(0):
        msg = f'상한가'
    elif ma(5, 2) > ma(5, 1):
        msg = f'전봉 5이평 하락 중'
    elif ma(10, 1) > ma(5, 1):
        msg = f'전봉 5, 10이평 역전 상태'
    elif c(1) < ma(10, 1):
        msg = f'전봉 종가, 10이평 역전 상태'
    else:
        # 현재봉으로 판단
        if c() > o():
            idx, candle = m3.get_highest_volume(m=10, n=1)
            if min(candle['o'], candle['c']) > c():
                msg = f'10봉중 최고거래량봉 아래로 이탈'

        if not msg and c() <= h(1):
            if down_tail_pct(1) >= 1.0 and (o(1) == c(1) or down_tail(1) > body(1) * 5) and up_tail(1) < down_tail(1) * 0.2:
                msg = f'교수형 캔들의 고가 갱신 못함'

        # 이하 전봉으로 판단
        if not msg and (h(2) > h(1) and bottom(1) >= top(2)):
            if up_tail(1) > down_tail(1):
                msg = f'전봉 고가 갱신 불발후 위꼬리 내부에서 마감'

        if not msg and up_tail_pct(1) >= 2.0:
            if o(1) == c(1) or up_tail(1) > body(1) * 3:
                msg = f'전봉 윗꼬리 2%이상 유성형 패턴으로 급락'

        # 음봉 패턴군 (blue)
        if not msg and (c(1) < o(1)):
            if up_tail_pct(1) >= 1.0:
                if top(2) < bottom(1):
                    msg = f'전봉 `윗꼬리 1%이상 음봉 갭 상승 마감'
                elif (o(1) == c(1) or up_tail(1) >= body(1) * 2.5) and up_tail(1) * 0.2 > down_tail(1):
                    msg = f'전봉 윗꼬리 1%이상 유성형 음봉'
                elif body(1) >= up_tail(1) * 0.8:
                    msg = f'전봉 윗꼬리 1%이상 떨어지는 칼날'
            elif up_tail_pct(2) >= 1.0 and up_tail(2) > down_tail(2):
                if h(2) >= h(1) and (h(1) - c(1)) / o(1) > 0.01:
                    msg = f'전봉 윗꼬리 1%이상 연속 고가 저항'
            elif (c(2) >= o(2)):
                if body_pct(2) > 1:
                    if top(2) >= top(1) and bottom(2) < bottom(1) and length_pct(1) < 1:
                        msg = f'전봉 하락 잉태형 패턴'
                    elif top(2) <= top(1) and bottom(2) > bottom(1):
                        msg = f'전봉 하락 장악형 패턴'
            elif c(3) >= o(3) and c(3) > c(1):
                if body_pct(3) > 2 and v(3) > v(2) * 2:
                    if m3.is_doji(0.2, 2) and c(1) < o(1) and v(3) > v(1) * 2:
                        msg = f'하락 전환 석별형 패턴'

        # 양봉 패턴군 (red)
        if not msg and c(2) >= o(2):
            if up_tail_pct(2) >= 1.5:
                up = up_tail(2)
                if c(2) > c(1) and (o(2) == c(2) or (up >= body(2) * 3 and up * 0.2 > down_tail(2))):
                    msg = f'전전봉 윗꼬리 1.5% 이상 몸통의 3배 유성형 양봉'
            elif body_pct(2) > 1:
                if top(2) >= top(1) and bottom(2) < bottom(1) and length_pct(1) < 0.5:
                    msg = f'전봉 하락 잉태형 패턴'

        # 최고종가 봉 패턴군 (pos)
        if not msg and pos > 2:
            if h(pos) > h(1) and bottom(1) >= top(pos):
                msg = f'전봉 최고종가봉 고가 갱신 불발후 위꼬리 내부에서 마감'
            elif (c(pos) >= o(pos)) and body_pct(pos) > 1:
                if top(pos) <= top(1) and bottom(pos) > bottom(1):
                    msg = f'전봉 최고종가 하락 장악형 패턴'

if msg: 
    if logoff:
        ret(msg)
    else:
        echo(f'[{True}] ({code} {name}) 현재가={dm.c()} / {msg}')
        ret(True)
ret(False)


# =============================================================================================

# 스크립트명 : 급등주매수후매도

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

최고종가, 당일봉수 = m3.get_close_tops(k=1, w=128, m=128, n=1)

if len(최고종가) == 0: pos = 1
else: pos = 최고종가[0]

o, h, l, c, ma = m3.o, m3.h, m3.l, m3.c, m3.ma
# 봉 특성 별칭 (필요 시 즉시 호출)
top, bottom = m3.body_top, m3.body_bottom
up_tail, down_tail = m3.up_tail, m3.down_tail
body = m3.body
body_pct = m3.body_pct
length_pct = m3.length_pct
up_tail_pct = m3.up_tail_pct
down_tail_pct = m3.down_tail_pct

dm._ensure_data_cache()
m3._ensure_data_cache()

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
            idx, candle = m3.get_highest_volume(m=10, n=1)
            if min(candle['o'], candle['c']) > c(1):
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
                elif (o(1) == c(1) or up_tail(1) >= body(1) * 2.5) and up_tail(1) * 0.2 > down_tail(1):
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
            if up_tail_pct(1) >= 1.5 and (o(1) == c(1) or (up_tail(1) >= body(1) * 3 and up_tail(1) * 0.2 > down_tail(1))):
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

    if not msg and down_tail_pct(1) >= 1.0 and (o(1) == c(1) or down_tail(1) > body(1) * 5) and up_tail(1) < down_tail(1) * 0.2:
        msg = f'교수형 캔들'

if msg: 
    if logoff:
        ret(msg)
    else:
        echo(f'[{True}] ({code} {name}) 현재가={dm.c()} / {msg}')
        ret(True)
ret(False)


# =============================================================================================

