from aaa.chart import ChartManager, echo, is_args, ret, div, ma

code = '005930'
name = '삼성전자'
price = 100000
qty = 100

# =============================================================================================

# 스크립트명 : 돌파매수

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
    
#거래량평균 = m3.top_volume_avg(n=130, m=2, cnt=10) * 0.8
#if abs(mv(1)) < 거래량평균:
#    echo(f'[{False}] ({code} {name}) 취소원인=거래량조건({mv(1):,d}>={거래량평균:,.0f}) 불충족')
#    ret(False)

비교거래량 = max(mv(), mv(1), mv(2), mv(3), mv(4), mv(5))
거래량기준 = dv(1) / 128 * 5 # 전일 3분봉 평균 거래량의 5배
#if 비교거래량 < 거래량기준:
#    echo(f'[{False}] ({code} {name}) 취소원인=거래량조건({비교거래량:,d}>={거래량기준:,.0f}) 불충족')
#    ret(False)

종가하락률 = div(dc(1) - dh(1), dc(1), 0)
if dh(1) > mc() and 종가하락률 < -0.05:
    echo(f'[{False}] ({code} {name}) 취소원인=전일종가조건 불충족 ({종가하락률*100:.2f})')
    ret(False)

# 데이타 수집
gcts = m3.get_close_tops(n=130, cnt=80, m=1) # 업데이트된 최고종가 리스트와 당일 봉수
highs = gcts[0] #개장후n봉최고종가(pre_bars=80)
today_bars = gcts[1]
highs_len = len(highs) if highs else 0

if highs_len<2 or highs[-1] > today_bars: 
    echo(f'[False] ({code} {name}) 취소원인={highs} 당일최고종가 1개 미만')
    ret(False)
echo(f'당일봉수={gcts[1]}, {gcts[0]}')

obvs = m3.get_obv_array(highs[-1] + 1)
거래량조건 = obvs[highs[-1]] < obvs[0] if len(obvs) > 1 else 거래량기준 <= 비교거래량
if not 거래량조건:
    echo(f'[{False}] ({code} {name}) 취소원인=거래량조건 불충족 ({obvs[highs[-1]]} < {obvs[0]})')
    ret(False)

extr = m3.get_extremes(n=highs[-1])
# 조건정의
하락률조건 = div(extr['hc'] - extr['lc'], extr['hc'], 0) < -0.05 and mc() < extr['hc']
현재봉조건 = dc() >= do() and mc() >= mc(highs[-1])

# 로깅
msg = ''
if 하락률조건 and mc() < extr['hc']: msg += '하락률조건, '
if not 현재봉조건: msg += '현재봉조건'

# 전략평가 결과 전달
result = not 하락률조건 and 현재봉조건
if msg: msg = '취소원인 = ' + msg +' 불충족'
echo(f'[{result}] ({code} {name}) {msg}')

ret(result)