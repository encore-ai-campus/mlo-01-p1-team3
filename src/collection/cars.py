"""원본 차량 API의 공개키 조회와 재시도 요청 기능."""

# =============================================================================
# [차량 API 수집 시작] API Key 조회
# 기능: AutoData 공개키 API에서 현재 API Key를 읽어 반환한다.
# 원본 위치: load_cars_initial.py의 get_api_key()
# =============================================================================
import time

import requests

from common.config import PUBLIC_KEY_URL


def get_api_key():
    response = requests.get(
        PUBLIC_KEY_URL,
        timeout=10,
    )
    response.raise_for_status()
    body = response.json()
    api_key = body["data"]["current"]["api_key"]

    print("[API KEY] 현재 API Key 조회 완료")
    return api_key


# =============================================================================
# [차량 API 수집 끝]
# =============================================================================


# =============================================================================
# [차량 API 수집 시작] 인증·Rate Limit·네트워크 재시도 요청
# 기능: 403이면 API Key를 갱신하고, 429/네트워크 오류면 재시도한다.
# 원본 위치: load_cars_initial.py의 request_api()
# =============================================================================
def request_api(url, api_key):
    max_retries = 10
    retry_count = 0

    while True:
        try:
            headers = {
                "X-API-Key": api_key,
            }
            response = requests.get(
                url,
                headers=headers,
                timeout=(10, 30),
            )

            if response.status_code == 403:
                retry_count += 1
                if retry_count > max_retries:
                    response.raise_for_status()

                print("[WARN] API Key 변경 감지 -> 새 Key 조회")
                api_key = get_api_key()
                time.sleep(2)
                continue

            if response.status_code == 429:
                retry_count += 1
                if retry_count > max_retries:
                    response.raise_for_status()

                retry_after = response.headers.get("Retry-After")
                if retry_after:
                    try:
                        wait_seconds = int(retry_after)
                    except ValueError:
                        wait_seconds = 10
                else:
                    wait_seconds = min(5 * retry_count, 60)

                print(f"[429] 요청 제한 발생 -> {wait_seconds}초 대기 ({retry_count}/{max_retries})")
                time.sleep(wait_seconds)
                continue

            response.raise_for_status()
            return response.json(), api_key

        except (
            requests.exceptions.ConnectTimeout,
            requests.exceptions.ReadTimeout,
            requests.exceptions.ConnectionError,
        ) as error:
            retry_count += 1
            if retry_count > max_retries:
                raise

            wait_seconds = min(5 * retry_count, 60)
            print(f"[NETWORK] {type(error).__name__} -> {wait_seconds}초 후 재시도 ({retry_count}/{max_retries})")
            time.sleep(wait_seconds)
# =============================================================================
# [차량 API 수집 끝]
# =============================================================================
