from aaa.chart import ChartManager
from aaa.log import echo, is_args, ret

code = '005930'
name = '삼성전자'
price = 100000
qty = 100

# =============================================================================================

# 지정 종목
#code = '249420'
echo(f'code={code}')
# 차트 매니저 생성 (3분봉)
cm = ChartManager(code, 'mi', 3)

# 넘겨진 인자 있는지 검사
pre_bars = is_args('pre_bars', 65)


# 원본 데이터를 직접 가져오기 (최고 성능)
data = cm.get_raw_data()

result = []
if len(data) > 1:
    # 현재봉 날짜 추출
    current_time = data[1].get('체결시간', '')
    #echo(f'current_time={current_time}')
    
    if len(current_time) >= 8:
        current_date = current_time[:8]  # YYYYMMDD
        target_time = current_date + "090000"  # 9시 봉

        # 9시 봉 인덱스 찾기
        nine_oclock_index = -1
        for i in range(len(data)):
            time_str = data[i].get('체결시간', '')
            if len(time_str) >= 12 and time_str[:12] == target_time[:12]:
                nine_oclock_index = i
                break
        
        if nine_oclock_index != -1:
            # 9시 봉부터 현재봉(0)까지 역순으로 검사
            for check_idx in range(nine_oclock_index, -1, -1):
                current_close = data[check_idx]['현재가']

                # 현재봉을 제외한 이전 pre_bars-1개 봉의 최고가 구하기
                start_idx = check_idx + 1
                end_idx = min(start_idx + pre_bars - 1, len(data))
                
                if start_idx < len(data):
                    high_values = [data[i]['고가'] for i in range(start_idx, end_idx)]
                    if high_values:
                        max_high = max(high_values)
                        
                        # 현재 종가가 이전 봉들의 최고가보다 같거나 높으면
                        if current_close >= max_high:
                            result.append(check_idx)
ret(result if 'result' in locals() else [])
echo(f'code={code} result = {result}')