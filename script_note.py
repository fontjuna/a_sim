from aaa.chart import ChartManager
from aaa.log import echo, is_args

code = '005930'
name = '삼성전자'
price = 100000
qty = 100

# =============================================================================================

# 지정 종목
code = '361610'

# 차트 매니저 생성 (3분봉)
cm = ChartManager(code, 'mi', 3)

# 이전봉수
pre_bars = is_args('pre_bars', 65)

# 현재봉 날짜 추출
current_time = cm.time(1)
echo(f'current_time={current_time}')
if len(current_time) < 8:
    result = -1
else:
    current_date = current_time[:8]  # YYYYMMDD
    target_time = current_date + "090000"  # 9시 봉
    
    # 9시 봉 인덱스 찾기
    nine_oclock_index = -1
    data_length = len(cm._get_data())
    
    for i in range(data_length):
        time_str = cm.time(i)
        if len(time_str) >= 12 and time_str[:12] == target_time[:12]:
            nine_oclock_index = i
            break
    echo(f'nine_oclock_index={nine_oclock_index}')
    result = -1  # 기본값: 찾지 못함
    
    if nine_oclock_index != -1:
        # 9시 봉부터 현재봉(0)까지 역순으로 검사
        for check_idx in range(nine_oclock_index, -1, -1):
            current_close = cm.c(check_idx)
            
            # 자신을 제외 한 이전 129봉 중 최고가 구하기
            highest_in_pre_bars = cm.highest(cm.h, pre_bars, check_idx + 1)
            
            # 현재 종가가 이전 129봉 최고가보다 높으면 해당 인덱스 반환
            if current_close > highest_in_pre_bars:
                result = check_idx
                break

echo(f'result = {result}')