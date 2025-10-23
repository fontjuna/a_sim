from chart import ChartManager, echo, is_args, ret, div, percent, ma, hoga, 일반매도, 거래량매도, bar_idx
import math
from datetime import datetime, timedelta

code = '005930'
name = '삼성전자'
price = 100000
qty = 100
buy_dt = '20250927100000'
result_cache = {}

# =============================================================================================
# 스크립트명 : 실전_돌파매수 v20250917.002800

"""
<키움 검색식에 구현해야 할 조건들>
1. 거래대금 상위 200종목 또는 거래량 상위 200종목 이고,
2. 주가범위 전일 기준 1,200원 ~ 99,900원 이고,
3. 현재가 기준 시가 총액 500억원 ~ 5조원 이고,
4. 현재가는 상승률 20% 이내이면서 전일 대비 시가가 2% 이상이거나, 시가대비 현재가가 5%이상이고,
5. 현재봉이 양봉이면서 시가는 10이평 위이며 종가는 5이평 위이면서 3분봉 기준 128봉 중 최고종가이고
6. 전일 최고가 대비 종가 하락율 7.5%이내이거나 전일 최고가 대비 종가 하락율 7.5%이상이면서 현재가가 전일 최고가를 넘어서야 하고
7. 현재봉 포함 20일 최고거래량대비 1분 0, 1, 2전봉중 하나의 거래량이 2% 이상

<이 스크립트에서 구현 할 조건들>
0. 키움 검색식과 AND로 연결
1. 최고종가 0개 또는 당일 첫봉이면 매수 안함
2. 당일 첫봉이 음봉이고 그 고가를 돌파 못하면 매수 안함
3. 일반매도 스크립트 조건에 해당하면 매수 안함
4. 최고거래량 조건 불충족하면 매수 안함
5. 5봉중 0.75% 상승 여부 불충족하면 매수 안함
6. 3연속 최고종가 회피 (0.5% 이하 제외)
7. 최고종가봉 보다 2% 이상에서 상승하면 매수 안함
8. 최고종가봉이 하락 우세이면 매수 안함
9. 전고점 넘지 못한 최고종가 회피
10. 전 최고종가의 고가저항에 윗 꼬리 발생하면 매수 안함
11. 최고종가 고점을 넘지 못하면 매수 안함
12. 당일 하락율 조건 불충족하면 매수 안함
13. 최근 10개봉 중 몸통보다 긴 윗꼬리 봉 3개 이상이면 매수 안함
"""
m3 = ChartManager(code, 'mi', 3)
dt = ChartManager(code, 'dy')

# 기본 값 접근자 별칭
o, h, l, c, v, ma = m3.o, m3.h, m3.l, m3.c, m3.v, m3.ma

# 최고종가 조건 찾기 ========================================================================
m3._ensure_data_cache()
with m3.suspend_ensure():
    c_tops, 당일봉수 = m3.get_close_tops( k=1, w=128, m=128, n=1 )
    첫봉 = 당일봉수 - 1

ymd = datetime.datetime.now().strftime('%H%M%S')
if 첫봉 == 0:
    bar_time_str = m3._raw_data[첫봉]['체결시간'][8:14]
    bar_time_dt = datetime.datetime.strptime(bar_time_str, "%H%M%S") + datetime.timedelta(minutes=1)
    bar_time = bar_time_dt.strftime("%H%M%S")
    if ymd <= bar_time:
        reason = f'당일 첫봉 1 분간 매수 하지 않음'

if len(c_tops) == 0:
    echo(f'[False] ({code} {name}) / 최고종가 0개 매수 안함 : ({당일봉수}) {c_tops}')
    ret(False)

pos = c_tops[0]

# 당일 첫봉이 음봉이면 그 봉 고가 밑에서 매수 안 함 =========================================
with m3.suspend_ensure():
    if o(첫봉) > c(첫봉):
        if h(첫봉) > c():
            echo(f'[False] ({code} {name}) / 당일 첫봉이 음봉이고 그 고가를 돌파 못함 : ({당일봉수}) {c_tops})')
            ret(False)
        elif percent(h(첫봉), c(첫봉)) >= 5.0:
            echo(f'[False] ({code} {name}) / 당일 첫봉이 음봉이고 고가 대비 5%이상 하락 : ({당일봉수}) {c_tops})')
            ret(False)
        elif percent(h(첫봉), o(첫봉)) > 3.0:
            echo(f'[False] ({code} {name}) / 당일 첫봉이 음봉이고 윗꼬리 3% 이상 발생 : ({당일봉수}) {c_tops})')
            ret(False)

# 현재봉이 5%이상 상승 중이면 매수 안 함 =========================================
with m3.suspend_ensure():
    if percent(c(0), o(0)) > 5.0:
        echo(f'[False] ({code} {name}) / 현재봉이 5%이상 상승 중이면 매수 안 함 : ({당일봉수}) {c_tops})')
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
    max_vol = 0
    max_idx = 1
    if cache_key not in result_cache:
        for i in range(1, 59):
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
        if c(i) >= hoga(c(i + 1), 3): 
            more_than += 1
            break

if more_than == 0: # or less_than > 0:
    echo(f'[False] ({code} {name}) / 5봉중 3호가 이상 상승 여부 불충족')
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
        if percent(c(pos), o()) > 2.0:
            echo(f'[False] ({code} {name}) / 최고종가봉 보다 2% 이상에서 상승 : ({당일봉수}) {c_tops}')
            ret(False)

        if h(pos) - c(pos) > c(pos) - l(pos) and h(pos) > c(0):
            echo(f'[False] ({code} {name}) / 최고종가봉이 하락 우세임 : ({당일봉수}) {c_tops}')
            ret(False)

        up_tail_pct = m3.up_tail_pct
        body_pct = m3.body_pct
        
        if up_tail_pct(pos+1) > 1.0 and h(pos+1) >= h(pos):
            echo(f'[False] ({code} {name}) / 전고점 넘지 못한 최고종가 회피 : ({당일봉수}) {c_tops}')
            ret(False)

        # 전 최고종가를 넘었어도 윗꼬리가 계속 발생하며 고가 갱신을 못함
        if up_tail_pct(pos) > 1.0 and h(pos) >= h(1) > c(1) and up_tail_pct(1) > body_pct(1) * 1.5:
            echo(f'[False] ({code} {name}) / 전 최고종가의 고가저항에 윗 꼬리 발생 : ({당일봉수}) {c_tops}')
            ret(False)

        # 윗 꼬리 단 최고 종가의 고점을 넘지 못하면 매물대 라는 뜻으로 올라가기 쉽지 않다.
        if pos > 1:
            label, pct = m3.price_position(n=pos, price=c(0))
            if pct['h_pct'] - pct['c_pct'] > 1.0 and h(pos) > dt.h(0):
                # 추가적인 조건이 필요 함
                echo(f'[False] ({code} {name}) / 최고종가 고점을 넘지 못함 : ({당일봉수}) {c_tops}')
                ret(False)

        if pos > 1:
            extr = m3.get_extremes(m=pos, n=1)
            하락률 = percent(extr['hh'], extr['ll'])
            시작위치 = percent(extr['ll'], o(0))
            if 하락률 > 5.0 and 시작위치 < 80.0 and not (l(pos) <= extr['ll'] and h(pos) >= extr['hh']):
                echo(f'[False] ({code} {name}) / 당일 하락율 조건 불충족 : ({당일봉수}) {c_tops}')
                ret(False)

        # if not (extr['hv'] > v(pos) or v(pos) * 0.8 < v(0)):
        #     echo(f'[False] ({code} {name}) / 전고돌파 수급 조건 불충족 : ({당일봉수}) {c_tops}')
        #     ret(False)

        # 일봉상 긴 윗꼬리가 달린 봉이 많이 나타나는 종목은 털리기 쉽다.
        윗꼬리_많은종목 = 0
        한계치 = 3
        for i in range(1, 11):
            up_tail = dt.h(i) - max(dt.o(i), dt.c(i))
            body = abs(dt.o(i) - dt.c(i))
            body_pct = percent(body, dt.o(i))
            if body > 0 and body_pct > 1 and up_tail > body: 윗꼬리_많은종목 += 1
            if 윗꼬리_많은종목 >= 한계치: break
        if 윗꼬리_많은종목 >= 한계치:
            echo(f'[False] ({code} {name}) / 최근 10개봉 중 몸통보다 긴 윗꼬리 봉 {윗꼬리_많은종목}개')
            ret(False)

echo(f'[True] ({code} {name}) / ({당일봉수}) {c_tops}')
ret(True)



# =============================================================================================
# 스크립트명 : 일반매수 v20250925

m3 = ChartManager(code, 'mi', 3)
dt = ChartManager(code, 'dy')

# 기본 값 접근자 별칭
o, h, l, c, v, ma = m3.o, m3.h, m3.l, m3.c, m3.v, m3.ma
up_tail_pct = m3.up_tail_pct
body_pct = m3.body_pct
bottom, top = m3.body_bottom, m3.body_top
# 최고종가 조건 찾기 ========================================================================
m3._ensure_data_cache()
with m3.suspend_ensure():
    c_tops, 당일봉수 = m3.get_close_tops( k=1, w=128, m=128, n=1 )
    첫봉 = 당일봉수 - 1

if len(c_tops) == 0:
    echo(f'[False] ({code} {name}) / 최고종가 0개 매수 안함 : ({당일봉수}) {c_tops}')
    ret(False)

pos = c_tops[0]
msg = ''
day_open_rate = percent(o(첫봉), dt.c(1)) # 당일 시가 갭 상승 여부 및 시작 %

with m3.suspend_ensure():
    # 장 시작후 3번째 봉 이내인 경우
    if 첫봉 < 4:
        if 첫봉 == 0: # 현재 첫봉
            ymd = datetime.datetime.now().strftime('%H%M%S')
            bar_time_str = m3._raw_data[첫봉]['체결시간'][8:14]
            bar_time_dt = datetime.datetime.strptime(bar_time_str, "%H%M%S") + datetime.timedelta(minutes=1)
            bar_time = bar_time_dt.strftime("%H%M%S")
            if ymd <= bar_time:
                msg = f'당일 첫봉 1 분간 매수 하지 않음'
        elif 첫봉 == 1: # 현재 두번째 봉
            if day_open_rate > 7.0 and c(1) > c():
                msg = f'당일 첫봉이 7%이상 과도한 갭 상승 시작 후 시가 이탈 발생'
            elif  o(1) > c(1):
                # 당일 첫봉이 음봉이면 그 봉 고가 밑에서 매수 안 함 =========================================
                if h(1) > c():
                    msg = f'당일 첫봉이 음봉이고 그 고가를 돌파 못함'
                elif percent(h(1), c(1)) >= 5.0:
                    msg = f'당일 첫봉이 음봉이고 고가 대비 5%이상 하락'
                elif percent(h(1), o(1)) > 3.0:
                    msg = f'당일 첫봉이 음봉이고 윗꼬리 3% 이상 발생' 
                elif up_tail_pct(0) > 3.0:
                    msg = f'당일 첫봉이 음봉이고 윗꼬리 3% 이상 발생'
            else:
                if c(1) + hoga(c(1), 3) < o() and c(1) < c():
                    msg = f'당일 두번째 봉이 3호가 이상 갭 상승 시작 후 전봉 종가 이탈 발생'
                elif percent(o(), c(1)) > 3.0 and c() < o():
                    msg = f'당일 두번째 봉이 3% 이상 과도한 갭 상승 시작 후 음봉 발생'
        elif 첫봉 == 2: # 현재 세번째 봉
            if  up_tail_pct(1) > 1.0 and m3.in_up_tail(price=h(), n=1) and c(1) > c():
                msg = f'당일 두번째 봉의 윗꼬리는 1%이상이며 고가 갱신 못한 음봉'
    else:
        if o(첫봉) > o():
            msg = f'3분봉 시가가 당일 시가 이하이면 매수 안함'

    if not msg:
        echo(f'[False] ({code} {name}) / {msg} : ({당일봉수}) {c_tops}')
        ret(False)

# 현재봉이 5%이상 상승 중이면 매수 안 함 =========================================
with m3.suspend_ensure():
    if percent(c(0), o(0)) > 5.0:
        echo(f'[False] ({code} {name}) / 현재봉이 5%이상 상승 중이면 매수 안 함 : ({당일봉수}) {c_tops})')
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
    max_vol = 0
    max_idx = 1
    if cache_key not in result_cache:
        for i in range(1, 59):
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
        if c(i) >= hoga(c(i + 1), 3): 
            more_than += 1
            break

    if more_than == 0: # or less_than > 0:
        echo(f'[False] ({code} {name}) / 5봉중 3호가 이상 상승 여부 불충족')
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
        if percent(c(pos), o()) > 2.0:
            echo(f'[False] ({code} {name}) / 최고종가봉 보다 2% 이상에서 상승 : ({당일봉수}) {c_tops}')
            ret(False)

        if h(pos) - c(pos) > c(pos) - l(pos) and h(pos) > c(0):
            echo(f'[False] ({code} {name}) / 최고종가봉이 하락 우세임 : ({당일봉수}) {c_tops}')
            ret(False)

        if up_tail_pct(pos+1) > 1.0 and h(pos+1) >= h(pos):
            echo(f'[False] ({code} {name}) / 전고점 넘지 못한 최고종가 회피 : ({당일봉수}) {c_tops}')
            ret(False)

        # 전 최고종가를 넘었어도 윗꼬리가 계속 발생하며 고가 갱신을 못함
        if up_tail_pct(pos) > 1.0 and h(pos) >= h(1) > c(1) and up_tail_pct(1) > body_pct(1) * 1.5:
            echo(f'[False] ({code} {name}) / 전 최고종가의 고가저항에 윗 꼬리 발생 : ({당일봉수}) {c_tops}')
            ret(False)

        # 윗 꼬리 단 최고 종가의 고점을 넘지 못하면 매물대 라는 뜻으로 올라가기 쉽지 않다.
        if pos > 1:
            label, pct = m3.price_position(n=pos, price=c(0))
            if pct['h_pct'] - pct['c_pct'] > 1.0 and h(pos) > dt.h(0):
                # 추가적인 조건이 필요 함
                echo(f'[False] ({code} {name}) / 최고종가 고점을 넘지 못함 : ({당일봉수}) {c_tops}')
                ret(False)

        if pos > 1:
            extr = m3.get_extremes(m=pos, n=1)
            하락률 = percent(extr['hh'], extr['ll'])
            시작위치 = percent(extr['ll'], o(0))
            if 하락률 > 5.0 and 시작위치 < 80.0 and not (l(pos) <= extr['ll'] and h(pos) >= extr['hh']):
                echo(f'[False] ({code} {name}) / 당일 하락율 조건 불충족 : ({당일봉수}) {c_tops}')
                ret(False)

        # if not (extr['hv'] > v(pos) or v(pos) * 0.8 < v(0)):
        #     echo(f'[False] ({code} {name}) / 전고돌파 수급 조건 불충족 : ({당일봉수}) {c_tops}')
        #     ret(False)

        # 일봉상 긴 윗꼬리가 달린 봉이 많이 나타나는 종목은 털리기 쉽다.
        윗꼬리_많은종목 = 0
        한계치 = 3
        for i in range(1, 11):
            up_tail = dt.h(i) - max(dt.o(i), dt.c(i))
            body = abs(dt.o(i) - dt.c(i))
            body_pct = percent(body, dt.o(i))
            if body > 0 and body_pct > 1 and up_tail > body: 윗꼬리_많은종목 += 1
            if 윗꼬리_많은종목 >= 한계치: break
        if 윗꼬리_많은종목 >= 한계치:
            echo(f'[False] ({code} {name}) / 최근 10개봉 중 몸통보다 긴 윗꼬리 봉 {윗꼬리_많은종목}개')
            ret(False)

echo(f'[True] ({code} {name}) / ({당일봉수}) {c_tops}')
ret(True)







# =============================================================================================

# 스크립트명 : 일반매도 v20250917.002800

"""
<키움 검색식에 구현해야 할 조건들>
- 없음.

<이 스크립트에서 적용한 조건들>
- 작성 중.
"""

dm = ChartManager(code, 'dy')
m3 = ChartManager(code, 'mi', 3)
logoff = is_args('logoff', False)

c_tops, 당일봉수 = m3.get_close_tops(k=1, w=128, m=128, n=1)

if len(c_tops) == 0: pos = 0
else: pos = c_tops[0]

o, h, l, c, v, ma = m3.o, m3.h, m3.l, m3.c, m3.v, m3.ma
# 봉 특성 별칭 (필요 시 즉시 호출)
top, bottom = m3.body_top, m3.body_bottom
up_tail, down_tail = m3.up_tail, m3.down_tail
body = m3.body
body_pct = m3.body_pct
length_pct = m3.length_pct
up_tail_pct = m3.up_tail_pct
down_tail_pct = m3.down_tail_pct
red = m3.red
blue = m3.blue

msg = ''
m3._ensure_data_cache()
with m3.suspend_ensure():
    # 최상위: 매우 가벼운 판정들
    if hoga(dm.c(1), 99) <= dm.c(0):
        msg = f'상한가'
    elif percent(c(0), h(0)) < -5.0:
        msg = f'현재봉 고가 대비 -5% 이하 하락 중'
    elif ma(5, 1) > ma(5, 0):
        msg = f'현재 5이평 하락 중'
    elif ma(10, 0) > ma(5, 0):
        msg = f'현재 5, 10이평 역전 상태'
    elif c(1) < ma(10, 1):
        msg = f'전봉 종가, 10이평 역전 상태'
    else:
        # 현재봉으로 판단
        if c(1) < o(0):
            if percent(o(0), c(1)) > 1.0 and c(1) > c(0):
                msg = f'1% 이상 갭 상승 시작 후 전봉 종가 이하로 하락'
        elif pos == 1 and o(0) < c(1) and c(0) < o(0):
            msg = f'현재봉 갭 하락 시작 음봉'

        if not msg:
            idx, candle = m3.get_highest_volume(m=10, n=1)
            if candle['현재가'] > candle['시가'] >= candle['저가'] > c():
                msg = f'10봉중 최고거래량봉 아래로 이탈'

        if not msg and h(1) >= c():
            if down_tail_pct(1) >= 1.0 and (o(1) == c(1) or down_tail(1) > body(1) * 5) and up_tail(1) < down_tail(1) * 0.2:
                msg = f'교수형 캔들의 고가 갱신 못함'

        if not msg and blue(0) and all([red(3), red(2), red(1)]) and c(3) < c(2) < c(1):
            min_body = hoga(o(1), 5) - o(1)
            if not (body(1) < min_body or body(3) < min_body):
                if body(3) > body(2) > body(1) and c(1) - (c(1) - o(1)) / 2 > c():
                    msg = f'상승 체력 소진으로 3연속 몸통이 작아 지면서 전봉 중간 이하로 하락'

                elif body(1) > body(2) > body(3) and c(1) - (c(1) - o(1)) / 3 > c():
                    msg = f'3연속 몸통이 커졌으나 체력 소진으로 고가 돌파 못한 전봉 1/3 이하로 하락'

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
        # elif not msg and pos >= 1:
        #     if (c(pos) - o(pos)) / 2 > c() and h(pos) > h():
        #         msg = f'전봉 최고종가봉 고가 갱신 불발후 퇴고 종가봉 몸통 중간 이하로 하락'


if msg: 
    if logoff:
        ret(msg)
    else:
        echo(f'[{True}] ({code} {name}) 현재가={dm.c()} / {msg}')
        ret(True)
ret(False)



# =============================================================================================
# 스크립트명 : 거래량매수 v20250920.170345

m3 = ChartManager(code, 'mi', 3)
dm = ChartManager(code, 'dy')

# 기본 값 접근자 별칭
o, h, l, c, v, ma = m3.o, m3.h, m3.l, m3.c, m3.v, m3.ma
up_tail, up_tail_pct = m3.up_tail, m3.up_tail_pct
down_tail, down_tail_pct = m3.down_tail, m3.down_tail_pct
body, body_pct = m3.body, m3.body_pct
length, length_pct = m3.length, m3.length_pct
bottom, top = m3.body_bottom, m3.body_top
blue, red = m3.blue, m3.red

# 거래량 조건 찾기 ========================================================================
dm._ensure_data_cache()
with dm.suspend_ensure():
    v_dic = dm.get_volume_stats(m=60, n=0)
    if v_dic['max'] < v_dic['avg'] * 5:
        echo(f"[False] ({code} {name}) 현재가: {c()} / 최고거래량({v_dic['max']/10000:.0f}만)이 평균({v_dic['avg']/10000:.0f}만)에 비해 큰 차이(5배)가 나지 않음")
        ret(False)

# 최고종가 조건 찾기 ========================================================================
m3._ensure_data_cache()
with m3.suspend_ensure():
    # c_tops, 당일봉수 = m3.get_close_tops( k=1, w=128, m=128, n=1 )
    mas = [10, 15, 7, 5, 3]
    rise, fall, below = m3.get_rising_state(mas, 0)
    try:
        hcx = rise['hc']    # 상승 시작 후 최고 종가 봉
        sbx = rise['sb']    # 상승 시작 봉 (종가가 모든 이평위로 올라온 봉의 직전 봉)
        bars = rise['bars']     # sb - hc 상승 구간 봉 개수
        첫봉 = rise['today_bars'] - 1
        day_open_rate = percent(o(첫봉), dm.c(1)) # 당일 시가 갭 상승 여부 및 시작 % (상승 gap 이면 > 0)
        rise_rate = rise['rise_rate']
        three_rate = rise['three_rate']
        hc_rate = percent(c(hcx), c(hcx + 1))
    except Exception as e:
        echo(f'[False] ({code} {name}) / 상승 상태 분석 실패: {e}')
        ret(False)

msg = ''

with m3.suspend_ensure():
    if not msg:        
        if 첫봉 == 0: # 현재 첫봉
            hms = datetime.datetime.now().strftime('%H%M%S')
            bar_time_str = m3._raw_data[첫봉]['체결시간'][8:14]
            bar_time_dm = datetime.datetime.strptime(bar_time_str, "%H%M%S") + datetime.timedelta(minutes=1)
            bar_time = bar_time_dm.strftime("%H%M%S")
            if hms <= bar_time:
                msg = f'당일 첫봉 1 분간 매수 하지 않음'
        else:
            if bottom(첫봉) > c():
                msg = f'당일 첫봉 몸통 이하면 매수 안함'
            elif blue():
                half_body = body() / 2
                if half_body > down_tail() or half_body < up_tail():
                    msg = f'음봉은 밑 꼬리 짧거나 윗꼬리 길면 매수 안함'
            elif o() < hoga(c(1), -3):
                msg = f'-3호가 이상 갭 하락 시작시 매수 금지'
            elif percent(h(hcx), o()) > 5.0:
                msg = f'최고종가의 고가 대비 -5.0% 이하인 시가봉 매수 금지'
            elif hcx == 1 and (rise_rate > 12.0 or three_rate > 8.0) and bars < 10:
                msg = f'상승 시작 후 12% 또는 3봉 상승 8% 이상 상승 중'

    if not msg and hcx > 0:
        # 전 최고종가의 고가 위
        if c() > h(hcx):
            # 갭 상승 시작 추격매수 금지
            if c() > hoga(c(1), 3) and blue():
                msg = f'3호가 이상 갭 상승 시작 후 음봉 매수 금지'

        # 전 최고종가의 고가 아래
        elif h(hcx) > c():
            # 최고종가봉 전봉의 위꼬리가 1% 이상이고 그 봉의 고가 갱신 못함
            if up_tail_pct(hcx + 1) > 1.0 and h(hcx + 1) >= h(hcx):
                msg = f'최고종가 전봉이 1% 이상 윗꼬리가 있고 그 고점 넘지 못한 최고종가 회피'

            # 최고종가봉이 종가 기준 고가 폭이 저가 폭보다 크고 현재가가 최고종가봉 고가 아래이면 매수 안함
            elif h(hcx) - c(hcx) > c(hcx) - l(hcx) and h(hcx) > c():
                msg = f'하락 우세인 최고종가봉의 고점을 넘지 못 함'

            # 최고종가봉 윗꼬리가 1% 이상이고 전봉이 그 고점을 못 넘었고 몸통의 1.5배이상인 윗꼬리 발생
            elif hcx > 1 and up_tail_pct(hcx) > 1.0 and h(hcx) >= h(1) and h(hcx) > c() and up_tail_pct(1) > body_pct(1) * 1.5:
                msg = f'전 최고종가의 고가저항에 윗 꼬리 발생'

            elif up_tail_pct(hcx) > 2.5:
                msg = f'전 최고종가의 윗꼬리 2.5% 이상 발생'

            elif up_tail_pct() > 1.0 and blue():
                msg = f'현재봉 윗꼬리 1.0% 이상 발생하고 음봉'

    if not msg:
        # 일봉상 긴 윗꼬리가 달린 봉이 많이 나타나는 종목은 털리기 쉽다.
        윗꼬리긴봉 = 0
        한계치 = 3
        for i in range(1, 11):
            up_tail = dm.h(i) - max(dm.o(i), dm.c(i))
            body = abs(dm.o(i) - dm.c(i))
            body_pct = percent(body, dm.o(i))
            if body > 0 and body_pct > 1.0 and up_tail > body: 윗꼬리긴봉 += 1
            if 윗꼬리긴봉 >= 한계치: break

        if 윗꼬리긴봉 >= 한계치:
            msg = f'최근 10개봉 중 몸통보다 긴 윗꼬리 봉 {윗꼬리긴봉}개'

# 일반매도 조건 찾기 #####
if not msg:
    msg = 거래량매도(logoff=True, rise=rise, fall=fall, below=below)

echo(f'[{msg==""}] ({code} {name}) 현재가: {c()} / {msg} : HC={hcx} ({bars}/{rise["today_bars"]})')
ret(msg=='')



# =============================================================================================
# 스크립트명 : 거래량매도 v20250920.170415

dm = ChartManager(code, 'dy')
m3 = ChartManager(code, 'mi', 3)
logoff = is_args('logoff', False)

# 기본 값 접근자 별칭
o, h, l, c, v, ma = m3.o, m3.h, m3.l, m3.c, m3.v, m3.ma
up_tail, up_tail_pct = m3.up_tail, m3.up_tail_pct
down_tail, down_tail_pct = m3.down_tail, m3.down_tail_pct
body, body_pct = m3.body, m3.body_pct
length, length_pct = m3.length, m3.length_pct
bottom, top = m3.body_bottom, m3.body_top
blue, red = m3.blue, m3.red

buy_idx = bar_idx(buy_dt) if buy_dt else -1
#echo(f'매수일시={buy_dt}, 봉인덱스={buy_idx}')

mas = [10, 15, 7, 5, 3]
msg = ''

m3._ensure_data_cache()
with m3.suspend_ensure():
    
    profit_pct = percent(c(), price) - 0.85 if price else 0

    rise = is_args('rise', False)
    if not rise:
        rise, fall, below = m3.get_rising_state(mas, 0)
    else:
        fall = is_args('fall', False)
        below = is_args('below', False)
    try:
        hcx = rise['hc']    # 상승 시작 후 최고 종가 봉
        sbx = rise['sb']    # 상승 시작 봉 (종가가 모든 이평위로 올라온 봉의 직전 봉)
        bars = rise['bars']     # sb - hc 상승 구간 봉 개수
        첫봉 = rise['today_bars'] - 1
        day_open_rate = percent(o(첫봉), dm.c(1)) # 당일 시가 갭 상승 여부 및 시작 % (상승 gap 이면 > 0)
        rise_rate = rise['rise_rate']
        three_rate = rise['three_rate']
        hc_rate = percent(c(hcx), c(hcx + 1))
    except Exception as e:
        echo(f'[False] ({code} {name}) / 상승 상태 분석 실패: {e}')
        ret(False)

    size = max(rise['max_red'][1], rise['max_blue'][1])
    drop_pct = lambda x: max(percent(h(x+1) - c(x), c(x)), percent(h(x) - c(x), c(x)))
    rebuy = lambda x: c() > h(1) > o(1) > ma(x, 1)# 매수시 매도조건에 걸려 매수 못 하는 문제 해소 즉 현재봉이 다시 상승인데 전봉이 매도조건에 걸리면 매수 못 함

    if hoga(dm.c(1), 99) <= dm.c(0):
        msg = f'상한가'
    elif up_tail_pct() > 3.0:
        msg = f'현재봉 윗꼬리 3% 이상 발생 매도'
    elif up_tail_pct() > 2.0 and body() < up_tail():
        msg = f'몸통보다 긴 2% 이상 윗꼬리 현재봉에 발생'
    elif hoga(c(1), -3) >= o() and blue():
        msg = f'3호가 이상 갭하락 음봉 매도'
    elif o() > hoga(c(1), 3) and c() < hoga(h(1), -3):
        msg = f'3호가 이상 갭 상승 시작 후 3호가 이상 윗꼬리 발생'
    elif h(sbx) > c(): 
        msg = f'상승 시작 봉 고가 ({h(sbx):,}) 이하 하락 매도'
    elif up_tail_pct(hcx) > 1.5 and up_tail_pct(1) > 1.5 and h(hcx) > h(1) > c(hcx) > c(1): 
        msg = f'전 최고종가봉 고가 갱신 불발후 윗꼬리 1.5% 이상 발생 하락'
    elif hcx == 1 and blue() and o() < c(1) and m3.in_up_tail(h(), 1):
        msg = f'갭 하락 약세 출발 고가 갱신 불발 음봉 발생'
    elif buy_idx == 1 and blue(buy_idx) and l(buy_idx) > c():
        msg = f'음봉 매수후 재차 음봉으로 전봉 저점 이탈'
    elif hcx == 2 and hc_rate > 3 and drop_pct(0) > hc_rate:
        msg = f'3%이상인 기준봉 이하로 하락'

    # 여기부터 이평 조건으로 매도 조건 검사
    if not msg:
        thresholds = [(1.0, 1.0), (1.5, 1.5), (2.0, 2.0), (2.5, 2.5)]
        for size_limit, pct_limit in thresholds:
            if size < size_limit:
                if drop_pct(1) > pct_limit:
                    msg = f'{pct_limit}% 이내 완만한 상승중 2봉 {pct_limit}% 이상 급락 매도'
                elif up_tail_pct() > pct_limit:
                    msg = f'{pct_limit}% 이내 완만한 상승중 윗꼬리 {pct_limit}% 이상 발생 매도'
                break

    if not msg:
        if ma(20, 1) > c(1):
            if not rebuy(20):
                msg = f'20이평 이탈 매도' # size < 1.0 인경우도 매도 함
        elif ma(15, 1) > c(1):
            if size < 1.5 or rebuy(15): pass
            else: msg = f'15이평 이탈 매도' # size >= 1.5 
        elif ma(10, 1) > c(1):
            if size < 2.0 or rebuy(10): pass
            else: msg = f'10이평 이탈 매도' # size >= 2.0 
        elif ma(7, 1) > c(1):
            if size < 2.0 or rebuy(7): pass
            elif hc_rate >= 3: msg = f'최고종가봉 3% 이상 ({hc_rate:.2f}%) 7이평 이탈 매도'
            elif three_rate >= 5: msg = f'3봉 상승 5% 이상 ({three_rate:.2f}%) 7이평 이탈 매도'
            elif rise_rate >= 7: msg = f'상승 시작 후 7% 이상 ({rise_rate:.2f}%) 7이평 이탈 매도'
            elif profit_pct >= 3:msg = f'이익 3% 이상 ({profit_pct:.2f}%) 7이평 이탈 매도'
            # 추가 조건 검사 필요 함   
        elif ma(5, 1) > c(1):
            if size < 2.0 or rebuy(5): pass
            elif hc_rate >= 4: msg = f'최고종가봉 4% 이상 ({hc_rate:.2f}%) 5이평 이탈 매도'
            elif three_rate >= 6: msg = f'3봉 상승 6% 이상 ({three_rate:.2f}%) 5이평 이탈 매도'
            elif rise_rate >= 10: msg = f'상승 시작 후 10% 이상 ({rise_rate:.2f}%) 5이평 이탈 매도'
            elif profit_pct >= 5: msg = f'이익 5% 이상 ({profit_pct:.2f}%) 5이평 이탈 매도'
            # 추가 조건 검사 필요 함    
        elif ma(3, 1) > c(1):
            if size < 2.0 or rebuy(3): pass
            elif 첫봉 > 0:
                if hc_rate >= 5: msg = f'최고종가봉 5% 이상 ({hc_rate:.2f}%) 3이평 이탈 매도'
                elif three_rate >= 8: msg = f'3봉 상승 8% 이상 ({three_rate:.2f}%) 3이평 이탈 매도'
                elif rise_rate >= 15: msg = f'상승 시작 후 15% 이상 ({rise_rate:.2f}%) 3이평 이탈 매도'
                elif profit_pct >= 8: msg = f'이익 8% 이상 ({profit_pct:.2f}%) 3이평 이탈 매도'
            # 추가 조건 검사 필요 함
        else: # 이평 이탈 전이라도 매도 조건 맞는지 검사
            if hc_rate >= 6: 
                if c(hcx) < c() and up_tail_pct() > 2.0:
                    msg = f'최고종가봉 6% 이상 ({hc_rate:.2f}%) 상승 위 윗꼬리 2% 이상 발생 매도'
                elif hcx < 3 and c(hcx) - body(hcx) / 4 > c():
                    msg = f'최고종가봉 6% 이상 ({hc_rate:.2f}%) 상승후 몸통의 1/4 이하로 하락 매도'
            elif up_tail_pct(2) >= 1.5:
                up = up_tail(2)
                if c(2) > c(1) and (o(2) == c(2) or (up >= body(2) * 3 and up * 0.2 > down_tail(2))):
                    msg = f'전전봉 윗꼬리 1.5% 이상 몸통의 3배 유성형 양봉' # 윗꼬리는 밑꼬리의 5배 이상
                elif up_tail_pct(1) > 1.5 and blue(1) and c(2) > c(1):
                    msg = f'전전봉과 전봉 윗꼬리 1.5% 이상 발생하고 전봉 음봉'
            elif up_tail_pct(1) >= 2.0:
                if o(1) == c(1) or up_tail(1) > body(1) * 3:
                    msg = f'전봉 윗꼬리 2%이상 유성형 패턴으로 급락'
            elif body_pct(2) > 1:
                if top(2) >= top(1) and bottom(2) < bottom(1) and length_pct(1) < 0.5:
                    msg = f'전봉 하락 잉태형 패턴'
            elif hcx > 2:
                if h(hcx) > h(1) and bottom(1) >= top(hcx):
                    msg = f'전봉 최고종가봉 고가 갱신 불발후 위꼬리 내부에서 마감'
                elif (c(hcx) >= o(hcx)) and body_pct(hcx) > 1:
                    if top(hcx) <= top(1) and bottom(hcx) > bottom(1):
                        msg = f'전봉 최고종가 하락 장악형 패턴'
            elif c(2) >= o(2):
                if body_pct(2) > 1:
                    if top(2) >= top(1) and bottom(2) < bottom(1) and length_pct(1) < 1:
                        msg = f'전봉 하락 잉태형 패턴'
                    elif top(2) <= top(1) and bottom(2) > bottom(1):
                        msg = f'전봉 하락 장악형 패턴'
            elif h(2) > h(1) and top(2) <= bottom(1):
                if up_tail(1) > down_tail(1):
                    msg = f'전봉 고가 갱신 불발후 위꼬리 내부에서 마감'
                    
if logoff: ret(msg)
if msg: echo(f'[True] ({code} {name}) 현재가={dm.c()} / 손익률: {profit_pct:.2f}% / {msg}')
ret(msg!='')

