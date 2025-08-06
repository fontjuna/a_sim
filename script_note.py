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
echo(f'당일봉수={당일봉수}\n{최고종가}')

obvs = m3.get_obv_array(최고종가[-1] + 1)
OBV조건 = obvs[최고종가[-1]] < obvs[0]

# 거래량 판단
if not (탑텐평균조건 or 삼분평균조건 or OBV조건):
    msg = ''
    if not 탑텐평균조건: msg += '탑텐평균조건, '
    if not 삼분평균조건: msg += '삼분평균조건, '
    if not OBV조건: msg += 'OBV조건, '
    echo(f'[{False}] ({code} {name}) 취소원인={msg} 불충족')
    ret(False)

# 마지막 최고종가의 위치까지 각 최고, 최저값 획득
extr = m3.get_extremes(n=최고종가[-1])

# 시간조정조건 : 최고종가에서 종가상 5%이상 빠지면 매수 안 함
시간조정조건 = div(extr['hc'] - extr['lc'], extr['hc'], 0) > -0.05
현재봉조건 = mc() >= mc(최고종가[-1])

# 로깅
msg = ''
if not 시간조정조건: msg += '시간조정조건, '
if not 현재봉조건: msg += '현재봉조건'

# 전략평가 결과 전달
result = 시간조정조건 and 현재봉조건
if msg: msg = '취소원인 = ' + msg +' 불충족'
echo(f'[{result}] ({code} {name}) {msg}')

ret(result)