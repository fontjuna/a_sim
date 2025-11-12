from chart import ChartManager, echo, is_args, ret, div, percent, ma, hoga, 일반매도, 거래량매도, bar_idx, set_trade_state, get_trade_state, clear_trade_state
import math
from datetime import datetime, timedelta

code = '005930'
name = '삼성전자'
price = 100000
qty = 100
buy_dt = '20250927100000'
result_cache = {}

# =============================================================================================
# 스크립트명 : 거래량매수 v20250920.170345

"""
<키움 검색식에 구현해야 할 조건들>
1. 거래대금 상위 100종목 또는 거래량 상위 100종목 이고,
2. 주가범위 전일 기준 2,000원 ~ 499,900원 이고,
3. 현재가 기준 시가 총액 500억원 ~ 5조원 이고,
4. 전일 최고가 대비 종가 하락율 5%이내이거나 전일 최고가 대비 종가 하락율 8~5% 이면서 현재가가 전일 최고가를 넘어서야 하고
5. 일봉상 현재가는 20이평의 1.5배 이내 이면서 상승률 20% 이내이고,
6. 일봉상 1봉전 20이평이 상승 중이고, 현재 종가가 3, 20이평 이상이고,
7. 3분봉상 현재가가 5, 10, 20이평 이상이고, 현재봉 기준 5, 15이평이 상승 중이고,
8. 일봉상 60일 최고 거래량 대비 3분봉 거래량이 0.78%이상이고,
9. 3분봉상 1봉전 127봉중 최고거래량의 34% 이상

<이 스크립트에서 구현 할 조건들>
0. 매수전략과 AND로 연결
1. 이하 Cursor AI가 코드 분석 후 작성 할 것 (Cursor AI는 여길 읽는 즉시 작성 또는 수정 할 것)
"""

m1 = ChartManager(code, 'mi', 1)
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
# mas = [20, 15, 10, 7, 5, 3]
mas = [21, 15, 12, 6]

# 같은 봉에서 매도한 경우 매수 안함 ========================================================================
last_sell = get_trade_state(code, 'sell')
if last_sell and last_sell.get('bar_time') == m3.bar_time():
    echo(f'△ {code} {name} 현재가={c()} / 현재봉에서 이미 매도함 (매도가: {last_sell.get("sell_price")}, 이유: {last_sell.get("reason")})')
    ret(False)

msg = ''

# 일봉 조건 찾기 ========================================================================
dm._ensure_data_cache()
with dm.suspend_ensure():
    v_dic = dm.get_volume_stats(m=60, n=0)
    if v_dic['max'] < v_dic['avg'] * 3.0:
        msg = f"최고거래량({v_dic['max']/10000:.0f}만)이 평균({v_dic['avg']/10000:.0f}만)의 3.0배를 넘지 않음"

    # 조건 검색식 대신 처리 한 것
    if not msg:
        if percent(dm.c(), dm.c(1)) > 20.0:
            msg = f'주가가 20% 이상 상승 중이면 매수 안함'

    if not msg:
        fall_pct = percent(dm.h(1), dm.c(1))
        if fall_pct > 8.0:
            msg = f'전일 고가 대비 종가 하락율 8% 이상'
        elif fall_pct > 5.0:
            if c() < dm.h(1):
                msg = f'전일 고가 대비 종가 하락율 5% 이상이고 그 고가를 넘지 못함'

    if not msg:
        dm_today_bars, dm_rise, dm_maru = dm.get_rising_state([20, 5], 0)
        limit_rate = 30.0
        if dm_maru['rise_rate'] > limit_rate:
            if dm.ma(3, 1) > dm.ma(3):
                msg = f'일봉상 {limit_rate}% 이상 상승중 3이평 하락시 매수 안함'
            elif dm.ma(3) > c():
                msg = f'일봉상 {limit_rate}% 이상 상승중 3이평 이하에서 매수 안함'
            
    if not msg:
        # 일봉상 긴 윗꼬리가 달린 봉이 많이 나타나는 종목은 털리기 쉽다.
        cnt = 0
        limit = 3
        for i in range(0, 10):
            if dm.body_pct(i) > 2.0 and dm.up_tail(i) > dm.body(i): cnt += 1
            if cnt >= limit: break

        if cnt >= limit:
            msg = f'최근 10개봉 중 몸통보다 긴 윗꼬리 봉 {cnt}개'

    if msg:
        echo(f"△ {code} {name} 현재가={dm.c()} / {msg}")
        ret(False)

# 분봉 조건 찾기 ========================================================================
m1._ensure_data_cache()
with m1.suspend_ensure():
    # 현재봉 판단
    if not msg:
        if m1.blue(): 
            msg = f'1분봉이 음봉이면 매수 안함'
        elif m1.is_shooting_star(2.0, 4.0, 1.0, n=0):
            msg = f'1분봉이 유성형 패턴이면 매수 안 함'
    
    # 전봉으로 판단
    if not msg:
        if m1.body_top(2) <= m1.o(1) and m1.body_bottom(2) > m1.c(1):
            msg = f'1분봉 하락 장악형 패턴 다음 매수 안 함'
        elif m1.is_shooting_star(2.0, 4.0, 1.0, n=1):
            msg = f'1분봉 유성형 패턴 다음 매수 안 함'

    if msg:
        echo(f"△ {code} {name} 현재가={m1.c()} / {msg}")
        ret(False)

m3._ensure_data_cache()
with m3.suspend_ensure():
    # 조건 검색식 대신 처리 한 것
    if not msg:
        if ma(6) > c(): msg = f'6'
        if ma(15) > c(): msg = f'15' if not msg else msg+', 15'
        msg = f'{msg} 이평 이하에서 매수 안함' if msg else ''

    if not msg:
        if ma(6, 1) > ma(6) or ma(15, 1) > ma(15):
            msg = f'6 또는 15 이평 하락 중이면 매수 안함'

    if msg:
        echo(f"△ {code} {name} 현재가={c()} / {msg}")
        ret(False)

    # 여기 부터 스크립트
    today_bars, rise, maru = m3.get_rising_state(mas, 0)
    
    try:
        # 빈 딕셔너리 처리 (확정 봉 없음)
        if not rise or not maru:
            if today_bars == 1 and all(c() >= ma(mp) for mp in mas):
                sb_gap = percent(max(ma(mp, 1) for mp in mas), c(1))
                # 값사용시 반드시 기본 값인지 확인 할 것 기본값적용 해도 되는 조건인지 확인 필수
                rise = maru = {'hc': 0, 'sb': 1, 'bars': 1, 'rise_rate': percent(c(), c(1)), 'three_rate': 0.0,
                              'sb_gap': sb_gap, 'max_red': (0, body_pct()), 'max_blue': (None, 0.0), 'max_volumn': 0,
                              'red_count': int(c() >= o()), 'blue_count': int(c() < o()), 'below': {mp: [] for mp in mas}}
            else:
                raise ValueError(f'마루 없음 - {"첫봉 이평 이하" if today_bars == 1 else "이평 이하"}')
        
        첫봉 = today_bars - 1
        thcx = maru['hc']   # 최고 마루 봉 (당일 가장 높은 종가)
        hcx = rise['hc']    # 최고종가봉 (가장 마지막 마루)
        sbx = rise['sb']    # 상승 시작 봉 (최고종가의 시작점)
        sb_gap = rise['sb_gap'] # SB 종가 대비 최고 이평값 갭(%)
        bars = rise['bars'] # sb - hc 상승 구간 봉 개수
        day_open_rate = percent(o(첫봉), dm.c(1)) # 당일 시가 갭 상승 여부 및 시작 % (상승 gap 이면 > 0)
        rise_rate = rise['rise_rate']
        three_rate = rise['three_rate']
        max_v = rise['max_volumn']
        hc_rate = percent(c(hcx), c(hcx + 1))
    except Exception as e:
        echo(f'△ {code} {name} 현재가={c()} / {e}')
        ret(False)

    if not msg:        
        if 첫봉 == 0: # 현재 첫봉
            if rise_rate > 2:
                # 1분봉 현재봉 체결시간 분 = 첫 1분봉 인덱스 (09:00->0, 09:01->1, 09:02->2)
                bar_idx = int(m1.bar_time()[2:4])
                
                if bar_idx == 0:  # 첫 1분 (09:00:00~09:00:59)
                    msg = f'당일 첫봉 1 분간 매수 하지 않음'
                elif m1.o(bar_idx) >= m1.c(bar_idx):  # 첫 1분봉이 음봉
                    msg = f'당일 첫 1분봉 음봉시 매수 안 함'
        else:
            if hcx == 1 and bars < 6:
                rise_limit = lambda x: percent(c(), o(sbx-1)) > 3 * x
                if rise_limit(bars):
                    msg = f'상승 시작 후 {bars}봉 이내 {3 * bars}% 이상 상승 중'
            elif 5 > hcx > 1 and c() > c(hcx) and max_v * 0.8 > v():
                msg = f'최고종가 위에서 매수시 최고거래량의의 80% 이하이면 안함'
            elif blue(첫봉) and body_pct(첫봉) > 2.0 and 첫봉 < 5 and bottom(첫봉) > c():
                msg = f'당일 첫봉 몸통 이하면 매수 안함'
            elif blue() and hcx < 4:
                half_body = (c(hcx) + o(hcx)) / 2
                if half_body > c():
                    msg = f'음봉이면 최고종가봉 중간 이하에서 매수 안 함'
            elif o() < hoga(c(1), -3):
                msg = f'-3호가 이상 갭 하락 시작시 매수 금지'
            elif ma(9) > o() and percent(h(thcx), o()) > 3.0:
                msg = f'9이평 아래에서 시가가 최고마루봉의 고가 대비 -3.0% 이하이면 매수 금지'
            elif sbx < 4 and sb_gap > 2.0:
                msg = f'SB 종가 대비 최고이평값 갭 2.0% 이상이면 매수 금지'

    if not msg and thcx > 0:
        # 최고마루봉의 고가 위
        if c() > h(thcx):
            # 갭 상승 시작 추격매수 금지
            if c() > hoga(c(1), 3) and blue():
                msg = f'3호가 이상 갭 상승 시작 후 음봉 매수 금지'

        # 최고마루봉의 고가 아래
        elif h(thcx) > c():
            # 최고마루봉 전봉의 위꼬리가 1% 이상이고 그 봉의 고가 갱신 못함
            if up_tail_pct(thcx + 1) > 1.0 and h(thcx + 1) >= h(thcx):
                msg = f'최고마루봉 전봉이 1% 이상 윗꼬리가 있고 그 고점 넘지 못한 최고마루봉 회피'

            # 최고마루봉이 종가 기준 고가 폭이 저가 폭보다 크고 현재가가 최고마루봉 고가 아래이면 매수 안함
            elif h(thcx) - c(thcx) > c(thcx) - l(thcx) and h(thcx) > c():
                if v(thcx) * 0.8 > v():
                    msg = f'하락 우세인 최고마루봉의 고점(거래량)을 넘지 못 함'

            # 최고마루봉 윗꼬리가 1% 이상이고 전봉이 그 고점을 못 넘었고 몸통의 1.5배이상인 윗꼬리 발생
            elif thcx > 1 and up_tail_pct(thcx) > 1.0 and h(thcx) >= h(1) and h(thcx) > c() and up_tail_pct(1) > body_pct(1) * 1.5:
                msg = f'최고마루봉의 고가저항에 몸통의 1.5배인 윗 꼬리 발생'

            elif up_tail_pct(thcx) > 2.5:
                msg = f'최고마루봉의 윗꼬리 2.5% 이상 발생'

            elif up_tail_pct() > 1.0 and blue():
                msg = f'현재봉 윗꼬리 1.0% 이상 발생하고 음봉'

# 일반매도 조건 찾기 #####
if not msg:
    msg = 거래량매도(logoff=True, today_bars=today_bars, rise=rise, maru=maru)

# 매수 성공 - 매도 상태 클리어
if msg == '':
    clear_trade_state(code, 'sell')

echo(f'{"▲" if msg == "" else "△"} {code} {name} 현재가= {c()} / {msg} : HC={hcx} ({bars}/{today_bars})')
ret(msg == '')


# =============================================================================================
#  스크립트명 : 거래량매도 v20250920.170415

"""
<키움 검색식에 구현해야 할 조건들>
1. 적용할 조건 없음.

<이 스크립트에서 구현 할 조건들>
0. 매도전략과 OR로 연결
1. 이하 Cursor AI가 코드 분석 후 작성 할 것 (Cursor AI는 여길 읽는 즉시 작성 또는 수정 할 것)
"""
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

buy_idx = bar_idx(buy_dt)

mas = [21, 15, 12, 6]
msg = ''

m3._ensure_data_cache()
with m3.suspend_ensure():
    
    profit_pct = percent(c(), price) - 0.85 if price else 0

    rise = is_args('rise', False)
    if rise:
        today_bars = is_args('today_bars', 0)
        maru = is_args('maru', False)
    else:
        today_bars, rise, maru = m3.get_rising_state(mas, 0)
    
    try:
        # 빈 딕셔너리 처리 (확정 봉 없음)
        if not rise or not maru:
            if today_bars == 1:
                sb_gap = percent(max(ma(mp, 1) for mp in mas), c(1))
                # 값사용시 반드시 기본 값인지 확인 할 것 기본값적용 해도 되는 조건인지 확인 필수
                rise = maru = {'hc': 0, 'sb': 1, 'bars': 1, 'rise_rate': percent(c(), c(1)), 'three_rate': 0.0,
                              'sb_gap': sb_gap, 'max_red': (0, body_pct()), 'max_blue': (None, 0.0), 'max_volumn': 0,
                              'red_count': int(c() >= o()), 'blue_count': int(c() < o()), 'below': {mp: [] for mp in mas}}
            else:
                raise ValueError('마루 없음 - 이평 이하')
        
        첫봉 = today_bars - 1
        bars = rise['bars'] # sb - hc 상승 구간 봉 개수
        thcx = maru['hc']   # 최고 마루 봉 (당일 가장 높은 종가)
        hcx = rise['hc']    # 최고종가봉 (가장 마지막 마루)
        sbx = rise['sb']    # 상승 시작 봉 (최고종가의 시작점)
        sb_gap = rise['sb_gap'] # SB 종가 대비 최고 이평값 갭(%)
        day_open_rate = percent(o(첫봉), dm.c(1)) # 당일 시가 갭 상승 여부 및 시작 % (상승 gap 이면 > 0)
        rise_rate = rise['rise_rate']
        three_rate = rise['three_rate']
        max_v = rise['max_volumn']
        hc_rate = percent(c(hcx), c(hcx + 1)) # 최고종가봉 전봉 대비 상승률
        size = max(rise['max_red'][1], rise['max_blue'][1])
    except Exception as e:
        msg = str(e)
        ret(msg if logoff else False)

    drop_pct = lambda x: max(percent(h(x+1) - c(x), c(x)), percent(h(x) - c(x), c(x)))
    rebuy = lambda x: c() > h(1) > o(1) > ma(x, 1)# 매수시 매도조건에 걸려 매수 못 하는 문제 해소 즉 현재봉이 다시 상승인데 전봉이 매도조건에 걸리면 매수 못 함
    gijun = lambda x: 0.25 * x < rise_rate - 1.5

    # 현재봉: 현재봉을 기준으로 판단시 매수와 매도를 같은 봉에서 반복하지 않도록 유념할 것 ***********
    if hoga(dm.c(1), 99) <= dm.c(0):
        msg = f'상한가'
    elif l(첫봉) > c() and ma(6) > c():
        msg = f'당일 첫봉의 저점 및 6 이평을 이탈'
    elif h(sbx) > c() and price > c(): 
        msg = f'상승 시작 봉 고가 ({h(sbx):,}) 이하 하락 매도'
    elif hcx == 2 and hc_rate > 3 and drop_pct(0) > hc_rate:
        msg = f'3%이상인 기준봉 이하로 하락'
    elif buy_idx == 1 and price < o(buy_idx) and l(buy_idx) < ma(3, buy_idx) and blue(buy_idx) and l(buy_idx) > c():
        msg = f'매수봉 종가가 3이평 이하의 음봉이고 재차 음봉으로 매수봉 저점 이탈'
    elif up_tail_pct() > 3.0:
        if c() < m3.bollinger_bands(20, 2)[0]:
            msg = f'현재봉 윗꼬리 3% 이상 발생으로 볼밴상단 이탈'
    elif up_tail_pct() > 2.5:
        if body() < up_tail() and c() < m3.bollinger_bands(20, 2)[0]:
            msg = f'현재봉 몸통보다 긴 2.5% 이상 윗꼬리 발생으로 볼밴상단 이탈'
    elif hoga(c(1), -3) >= o():
        if blue():
            msg = f'3호가 이상 갭하락 음봉 매도'
    elif hoga(c(1), 3) < o():
        if c() < h() - hoga(h(), -3) and red():
            msg = f'3호가 이상 갭 상승 시작 후 상승 중 3호가 이상 윗꼬리 발생'

    # 현재봉으로 판단할지 더 고민 할 사항
    elif hc_rate >= 6: 
        if hcx > 0 and c(hcx) < c() and up_tail_pct() > 2.0:
            msg = f'최고종가봉 6% 이상 ({hc_rate:.2f}%) 상승후후 윗꼬리 2% 이상 발생 매도'
        elif hcx < 3 and c(hcx) - body(hcx) / 4 > c():
            msg = f'최고종가봉 6% 이상 ({hc_rate:.2f}%) 상승후 몸통의 1/4 이하로 하락 매도'

    # 이전봉 : 이전봉으로 판단 ***********************************************************************
    if not msg:
        if bars > 2:
            thresholds = [(1.0, 1.0), (1.5, 1.5), (2.0, 2.0), (2.5, 2.5)]
            for size_limit, pct_limit in thresholds:
                if size < size_limit:
                    if drop_pct(1) > pct_limit:
                        msg = f'{pct_limit}% 이내 완만한 상승중 2봉 {pct_limit}% 이상 급락 매도'
                    elif up_tail_pct(1) > pct_limit:
                        msg = f'{pct_limit}% 이내 완만한 상승중 윗꼬리 {pct_limit}% 이상 발생 매도'
                    break

    if not msg: 
        # 이평 이탈 후 조건 검사
        if not rebuy(21) and ma(21, 1) > c(1):
            if blue(1):
                msg = f'20이평 이탈 매도' # size < 1.0 인경우도 매도 함
        elif not rebuy(18) and ma(18, 1) > c(1):
            if size < 1.0 and gijun(18): pass # gijun = 6.0% : 봉수만큼 상승률 이내면 패스스
            elif blue(1): msg = f'18 이평 이탈 매도'
        elif not rebuy(15) and ma(15, 1) > c(1):
            if size < 1.5 and gijun(15): pass # 5.25%
            elif blue(1): msg = f'15 이평 이탈 매도'
        elif not rebuy(12) and ma(12, 1) > c(1):
            if size < 1.8 and gijun(12): pass # 4.5%
            elif blue(1): msg = f'12 이평 이탈 매도'
        elif not rebuy(9) and ma(9, 1) > c(1):
            if size < 2.2 and gijun(9): pass # 3.75%
            elif profit_pct >= 3:msg = f'이익 3% 이상 ({profit_pct:.2f}%) 9이평 이탈 매도'
            elif hc_rate >= 3: msg = f'최고종가봉 3% 이상 ({hc_rate:.2f}%) 9이평 이탈 매도'
            elif three_rate >= 5: msg = f'3봉 상승 5% 이상 ({three_rate:.2f}%) 9이평 이탈 매도'
            elif rise_rate >= 7: msg = f'상승 시작 후 7% 이상 ({rise_rate:.2f}%) 9이평 이탈 매도'
            elif blue(1): msg = f'9 이평 이탈 매도' # size >= 2.0 
            # 추가 조건 검사 필요 함   
        elif not rebuy(6) and ma(6, 1) > c(1):
            if size < 2.2: pass
            elif profit_pct >= 5: msg = f'이익 5% 이상 ({profit_pct:.2f}%) 6이평 이탈 매도'
            elif hc_rate >= 4: msg = f'최고종가봉 4% 이상 ({hc_rate:.2f}%) 6이평 이탈 매도'
            elif three_rate >= 6: msg = f'3봉 상승 6% 이상 ({three_rate:.2f}%) 6이평 이탈 매도'
            elif rise_rate >= 10: msg = f'상승 시작 후 10% 이상 ({rise_rate:.2f}%) 6이평 이탈 매도'
            # 추가 조건 검사 필요 함    
        elif not rebuy(3) and ma(3, 1) > c(1):
            if size < 2.2: pass
            elif profit_pct >= 8: msg = f'이익 8% 이상 ({profit_pct:.2f}%) 3이평 이탈 매도'
            elif 첫봉 > 0:
                if hc_rate >= 5: msg = f'최고종가봉 5% 이상 ({hc_rate:.2f}%) 3이평 이탈 매도'
                elif three_rate >= 8: msg = f'3봉 상승 8% 이상 ({three_rate:.2f}%) 3이평 이탈 매도'
                elif rise_rate >= 15: msg = f'상승 시작 후 15% 이상 ({rise_rate:.2f}%) 3이평 이탈 매도'
            # 추가 조건 검사 필요 함

        else: # 이평 이탈 전 조건 검사
            if up_tail_pct(2) >= 1.5:
                up = up_tail(2)
                if c(2) > c(1) and (o(2) == c(2) or (up >= body(2) * 3 and up * 0.2 > down_tail(2))):
                    msg = f'전전봉 윗꼬리 1.5% 이상 몸통의 3배 유성형 양봉' # 윗꼬리는 밑꼬리의 5배 이상
                elif up_tail_pct(1) > 1.5 and blue(1) and c(2) > c(1):
                    msg = f'전전봉과 전봉 윗꼬리 1.5% 이상 발생하고 전봉 음봉'
            elif up_tail_pct(1) >= 2.0:
                if o(1) == c(1) or up_tail(1) > body(1) * 3:
                    msg = f'전봉 윗꼬리 2%이상 유성형 패턴으로 급락'
            elif up_tail_pct(hcx) > 1.5 and up_tail_pct(1) > 1.5 and h(hcx) > h(1) and c(hcx) > c(1): 
                msg = f'최고종가봉 고가 갱신 불발후 윗꼬리 1.5% 이상 발생 하락'
            elif body_pct(2) > 1:
                if top(2) > top(1) and bottom(2) < bottom(1) and length_pct(1) < 1.0:
                    msg = f'전봉 하락 잉태형 패턴'
                elif c(2) >= o(2):
                    if top(2) <= top(1) and bottom(2) > bottom(1):
                        msg = f'전봉 하락 장악형 패턴'
            elif h(2) > h(1) and top(2) <= bottom(1):
                if up_tail(1) > down_tail(1):
                    msg = f'전봉 고가 갱신 불발후 위꼬리 내부에서 마감'
            elif hcx > 2:
                if h(hcx) > h(1) and bottom(1) >= top(hcx):
                    msg = f'전봉 최고종가봉 고가 갱신 불발후 위꼬리 내부에서 마감'
                elif (c(hcx) >= o(hcx)) and body_pct(hcx) > 1:
                    if top(hcx) <= top(1) and bottom(hcx) > bottom(1):
                        msg = f'전봉 최고종가 하락 장악형 패턴'
            elif hcx == 2 and blue(1):
                if m3.in_up_tail(price=h(1), n=hcx) and hoga(c(2), -1) > o(1): # 한호가 보다 큰 갭 하락
                    msg = f'갭 하락 약세(강세) 출발 고가 갱신 불발 음봉 발생'
                elif c(1) < ma(3, 1) and c(2) > o(1):
                    msg = f'갭 하락 약세 출발 3이평 이탈 음봉 발생'
                    
if logoff: ret(msg)
if msg:
    # 매도 상태 저장 (같은 봉에서 재매수 방지)
    set_trade_state(code, 'sell', {
        'bar_time': m3.bar_time(),
        'sell_price': m3.c(),
        'reason': msg
    })
    
    echo(f'▼ {code} {name}: {msg}')
    echo(f'▽ {code} {name} 현재가: {dm.c():,} 손익률: {profit_pct:.2f}% ({price:,}원, {buy_idx}봉전 {buy_dt[:8]}_{buy_dt[8:14]} 매수)')
ret(msg != '')

