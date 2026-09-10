"""
동행복권에서 최신 로또 당첨번호를 크롤링하여
data/latest.json 파일로 저장
"""
import requests
from bs4 import BeautifulSoup
import json
import os
from datetime import datetime

def get_latest_draw():
    url = 'https://dhlottery.co.kr/common.do?method=main'
    try:
        res = requests.get(url, timeout=30)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, 'lxml')
        return int(soup.find('strong', id='lottoDrwNo').text)
    except Exception as e:
        print(f"최신 회차 조회 실패: {e}")
        return None

def get_draw_info(draw_no):
    url = f'https://dhlottery.co.kr/gameResult.do?method=byWin&drwNo={draw_no}'
    try:
        res = requests.get(url, timeout=30)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, 'lxml')

        date_text = soup.find('p', class_='desc').text
        date = datetime.strptime(date_text, '(%Y년 %m월 %d일 추첨)').strftime('%Y-%m-%d')

        win_numbers = soup.find('div', class_='num win').find('p').text.strip().split('\n')
        nums = [int(n) for n in win_numbers if n.strip()]
        bonus = int(soup.find('div', class_='num bonus').find('p').text.strip())

        return {
            'draw': draw_no, 'date': date,
            'n1': nums[0], 'n2': nums[1], 'n3': nums[2],
            'n4': nums[3], 'n5': nums[4], 'n6': nums[5],
            'bonus': bonus
        }
    except Exception as e:
        print(f"{draw_no}회차 조회 실패: {e}")
        return None

def main():
    latest = get_latest_draw()
    if not latest:
        print("최신 회차를 가져올 수 없습니다.")
        return
    print(f"최신 회차: {latest}")
    info = get_draw_info(latest)
    if info:
        os.makedirs('data', exist_ok=True)
        with open('data/latest.json', 'w', encoding='utf-8') as f:
            json.dump(info, f, ensure_ascii=False, indent=2)
        print("저장 완료: data/latest.json")
    else:
        print("데이터 저장 실패")

if __name__ == '__main__':
    main()