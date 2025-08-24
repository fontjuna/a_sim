from aaa.chart import ChartManager, echo, is_args, ret, div, ma

code = '005930'
name = '삼성전자'
price = 100000
qty = 100

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
"""

logoff = is_args('logoff', False)
dm = ChartManager(code, 'dy')
dc = dm.c
m3 = ChartManager(code, 'mi', 3)
mo, mc, ml, ma = m3.o, m3.c, m3.l, m3.ma

기준가 = 0
if not logoff:
    # 이전 n봉부터 m봉까지 이전 cnt봉중 최고종가 얻기 (최고종가, 당일봉수)
    gcts = m3.get_close_tops(n=128, cnt=128, m=1) # 업데이트된 최고종가 리스트와 당일 봉수
    최고종가 = gcts[0] #개장후n봉최고종가
    당일봉수 = gcts[1]
    기준가 = min(mc(최고종가[-2]), ml(최고종가[-1])) if len(최고종가) > 1 else 0

윗그림자조건 = False

msg = ''
if not 윗그림자조건: msg = '윗그림자조건'

if not msg: msg = " 없음"

# 전략평가 전송
result = 윗그림자조건
if not logoff: echo(f'[{result}] ({code} {name}) 현재가={dc()} / 매도조건: {msg}')
ret(result)