# 디스코드 비즈니스 에이전트 — 파일 합쳐서 HTML 리포트 만들기

지정한 채널에 엑셀(xlsx/xls)이나 CSV 파일을 올리면, 봇이 자동으로 파일들을
읽어서 하나로 합치고, Claude에게 분석을 맡겨서 결과를 보여주는 HTML 리포트를
만들어 같은 채널에 다시 올려줍니다.

---

## 1. 필요한 것

- Discord 계정 (서버 관리 권한 있는 계정)
- Anthropic API 키 (console.anthropic.com)
- Python 3.10 이상이 설치된 컴퓨터 (봇을 계속 켜둘 곳 — 본인 PC도 가능)

---

## 2. Discord 봇 만들기

1. https://discord.com/developers/applications 접속 → 로그인
2. 우측 상단 **New Application** 클릭 → 이름 입력 (예: "리포트 에이전트") → Create
3. 왼쪽 메뉴 **Bot** 클릭
   - **Reset Token** 클릭 → 나오는 토큰을 복사해둔다 (나중에 `.env`에 넣을 값, `DISCORD_BOT_TOKEN`)
   - 아래로 스크롤 → **Privileged Gateway Intents** 섹션에서
     **MESSAGE CONTENT INTENT** 를 반드시 켜고(ON) 저장한다
     (이게 꺼져 있으면 봇이 파일 첨부를 못 읽습니다)
4. 왼쪽 메뉴 **OAuth2 → URL Generator** 클릭
   - **SCOPES**: `bot` 체크
   - **BOT PERMISSIONS**: 아래 항목 체크
     - View Channels
     - Send Messages
     - Attach Files
     - Read Message History
   - 화면 하단에 생성된 URL을 복사해서 브라우저 주소창에 붙여넣기
   - 봇을 초대할 서버(구굿 서버) 선택 → 권한 승인

이제 서버 멤버 목록에 봇이 "BOT" 표시와 함께 추가되어 있을 거예요 (오프라인 상태로 보일 수 있는데, 아직 코드를 실행 안 해서 그런 것 — 정상입니다).

---

## 3. Anthropic API 키 발급

1. https://console.anthropic.com 접속 → 로그인/가입
2. **API Keys** 메뉴 → **Create Key**
3. 생성된 키를 복사해둔다 (`ANTHROPIC_API_KEY`)

---

## 4. 코드 실행 준비

이 폴더(`discord-report-agent/`)를 봇을 돌릴 컴�터로 옮긴 뒤:

```bash
cd discord-report-agent
pip install -r requirements.txt
cp .env.example .env
```

`.env` 파일을 열어서 2번, 3번에서 복사해둔 값을 채워 넣으세요:

```
DISCORD_BOT_TOKEN=실제_봇_토큰
ANTHROPIC_API_KEY=실제_API_키
TARGET_CHANNEL_NAMES=business,business-2
CLAUDE_MODEL=claude-opus-5-5
```

`TARGET_CHANNEL_NAMES` 에는 봇이 반응할 채널 이름을 `#` 없이, 쉼표로 구분해서 적습니다.

---

## 5. 실행

```bash
python bot.py
```

터미널에 아래처럼 뜨면 정상 작동 중입니다:

```
✅ 로그인 완료: 리포트 에이전트#1234 (지켜보는 채널: business, business-2)
```

이 터미널 창을 닫으면 봇도 꺼집니다. 계속 켜두려면:
- 그냥 이 컴퓨터를 계속 켜두거나
- Railway, Render 같은 무료/저가 호스팅에 올려서 24시간 돌리기 (별도 설정 필요, 필요하면 말씀해주세요)

---

## 6. 사용법

- `#business` (또는 설정한 채널)에 xlsx/csv 파일을 1개 이상 첨부해서 메시지를 보내면, 봇이 자동으로:
  1. "파일 N개 받았어요, 분석 중..." 이라고 답장
  2. 파일들을 합치고 Claude로 분석
  3. 완성된 HTML 리포트 파일을 채널에 첨부파일로 올림
- 그냥 봇을 `@멘션` 만 하면 "작동 중이에요!" 라고 답장해서 살아있는지 확인할 수 있어요.

---

## 7. 자주 발생하는 문제

| 증상 | 원인/해결 |
|---|---|
| 파일을 올려도 반응이 없다 | ① `python bot.py` 를 실행한 터미널이 켜져 있는지 확인 ② Developer Portal에서 MESSAGE CONTENT INTENT를 켰는지 확인 ③ `TARGET_CHANNEL_NAMES`에 그 채널 이름이 정확히 들어있는지 확인 |
| "Anthropic API 키가 잘못됐어요" | `.env`의 `ANTHROPIC_API_KEY` 값 다시 확인 |
| 리포트 내용이 중간에 잘린 것 같다 | 파일이 너무 크면 일부만 잘라서 분석해요 (`bot.py`의 `MAX_CHARS_PER_FILE`, `MAX_TOTAL_CHARS` 값을 늘리면 되지만, 그만큼 Claude API 비용이 늘어나요) |
| 여러 명이 동시에 파일을 올린다 | 현재는 순서대로 하나씩 처리돼요. 요청이 많으면 대기 시간이 길어질 수 있어요 |

---

## 8. 비용 안내

파일을 올릴 때마다 Anthropic API 요청이 1번 발생하고, 파일 크기와 리포트 길이에 따라
비용이 달라집니다 (`claude-opus-5-5` 기준 입력 $4/1M 토큰, 출력 $20/1M 토큰).
평소 업무용 엑셀 몇 개 정도면 요청 1건당 보통 몇십~몇백 원 수준입니다.
