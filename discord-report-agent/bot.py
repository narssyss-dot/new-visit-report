"""
디스코드 비즈니스 에이전트 — 파일 업로드 → 합쳐서 HTML 리포트 생성 봇

지정한 채널(TARGET_CHANNEL_NAMES)에 엑셀/CSV 파일을 올리면:
  1. 업로드된 모든 파일을 읽어서 텍스트(CSV)로 변환
  2. Claude API에 "합치고 분석해서 HTML 리포트 만들어줘" 라고 요청
  3. 완성된 HTML 파일을 같은 채널에 첨부파일로 올려줌

설정 방법은 README.md 참고.
"""

import io
import os
import re
from datetime import datetime

import anthropic
import discord
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN = os.environ["DISCORD_BOT_TOKEN"]
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")  # 없으면 SDK가 다른 인증 방식을 자동 탐색
MODEL = os.environ.get("CLAUDE_MODEL", "claude-opus-5-5")
TARGET_CHANNELS = {
    c.strip() for c in os.environ.get("TARGET_CHANNEL_NAMES", "business,business-2").split(",") if c.strip()
}

SUPPORTED_EXTS = (".xlsx", ".xls", ".csv")
MAX_CHARS_PER_FILE = 40_000   # 파일 하나당 텍스트로 바꿨을 때 최대 글자 수 (넘으면 잘라냄)
MAX_TOTAL_CHARS = 150_000     # 전체 합쳐서 Claude에게 보낼 최대 글자 수

SYSTEM_PROMPT = """\
너는 업로드된 여러 개의 파일을 하나로 합쳐서 결과를 보여주는 HTML 리포트를
만드는 업무용 에이전트야.

[절차]
1. 전달된 각 파일의 내용(파일명 + CSV로 변환된 데이터)을 확인한다.
2. 파일들 사이에 공통된 항목(날짜, 지점/센터명, 담당자, 수치 지표 등)을 찾아
   하나의 통합된 데이터셋 관점으로 정리한다. 같은 항목이 여러 파일에 걸쳐
   있으면 하나로 합치고, 겹치지 않는 항목은 각자 살려서 포함한다.
3. 합친 데이터를 바탕으로 핵심 결과를 요약한다 — 전체 합계/평균, 눈에 띄는
   증감, 이상치, 미해결 이슈 등을 짚어준다.
4. 위 내용을 하나의 완결된 HTML 문서로 작성한다.
   - 외부 라이브러리/인터넷 연결 없이 그 자체로 열리는 순수 HTML+CSS(+최소 JS).
   - 구성: ① 제목·생성일 ② 요약(핵심 결과 3~5줄) ③ 통합 데이터 표
     ④ 필요하면 간단한 차트(막대/도넛 등, 인라인 SVG로) ⑤ 특이사항/후속 조치 제안
   - 모바일에서도 안 깨지게 반응형으로 만든다.
   - 라이트/다크 모드 모두 고려해서 배경·글자색을 명시적으로 지정한다.

[중요]
- 답변에는 완성된 HTML 코드만 출력한다. 설명, 인사말, 마크다운 코드펜스
  (```html 같은 것) 없이 <!DOCTYPE html> 로 바로 시작해서 </html> 로 끝낸다.
- 파일 형식이 서로 너무 달라서 합치기 애매하면, 임의로 넘겨짚지 말고
  리포트 상단에 "다음 항목을 기준으로 합쳤습니다"라고 근거를 밝힌다.
- 파일이 1개뿐이면 억지로 "병합"하지 말고 그 파일 내용만으로 리포트를 만든다.
"""

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else anthropic.Anthropic()

intents = discord.Intents.default()
intents.message_content = True  # 디스코드 개발자 포털에서도 반드시 켜야 함 (README 참고)
bot = discord.Client(intents=intents)


def strip_code_fence(text: str) -> str:
    """모델이 지시를 어기고 ```html ... ``` 로 감싸서 응답한 경우 벗겨낸다."""
    m = re.match(r"^\s*```(?:html)?\s*\n(.*)\n```\s*$", text, re.S)
    return m.group(1) if m else text


def file_to_text(filename: str, data: bytes) -> str | None:
    """업로드된 파일(bytes)을 Claude에게 보낼 텍스트로 바꾼다. 길면 잘라낸다."""
    lower = filename.lower()
    try:
        if lower.endswith((".xlsx", ".xls")):
            xls = pd.ExcelFile(io.BytesIO(data))
            parts = []
            for sheet in xls.sheet_names:
                df = xls.parse(sheet)
                parts.append(f"### 시트: {sheet}\n{df.to_csv(index=False)}")
            text = "\n\n".join(parts)
        elif lower.endswith(".csv"):
            text = data.decode("utf-8", errors="ignore")
        else:
            return None
    except Exception as e:  # noqa: BLE001 - 파일이 깨져 있어도 봇 전체가 죽으면 안 됨
        return f"[{filename} 을(를) 읽는 데 실패했어요: {e}]"

    if len(text) > MAX_CHARS_PER_FILE:
        text = text[:MAX_CHARS_PER_FILE] + f"\n... ({filename} 내용이 길어 일부만 표시함) ..."
    return text


@bot.event
async def on_ready():
    print(f"✅ 로그인 완료: {bot.user} (지켜보는 채널: {', '.join(TARGET_CHANNELS)})")


@bot.event
async def on_message(message: discord.Message):
    if message.author == bot.user or message.author.bot:
        return

    # 그냥 봇 멘션만 하면 "살아있는지" 확인용으로 짧게 답장
    if bot.user in message.mentions and not message.attachments:
        await message.channel.send("네, 작동 중이에요! 이 채널에 파일(xlsx/csv)을 올려주시면 합쳐서 리포트를 만들어드려요.")
        return

    channel_name = getattr(message.channel, "name", None)
    if channel_name not in TARGET_CHANNELS:
        return

    targets = [a for a in message.attachments if a.filename.lower().endswith(SUPPORTED_EXTS)]
    if not targets:
        return

    async with message.channel.typing():
        status = await message.reply(f"📂 파일 {len(targets)}개 받았어요. 합쳐서 분석 중입니다... (파일이 크면 몇 분 걸릴 수 있어요)")

        file_texts = []
        for att in targets:
            data = await att.read()
            text = file_to_text(att.filename, data)
            if text:
                file_texts.append(f"=== 파일: {att.filename} ===\n{text}")

        if not file_texts:
            await status.edit(content="죄송해요, 지원하는 형식(xlsx / xls / csv)의 파일을 찾지 못했어요.")
            return

        combined = "\n\n".join(file_texts)
        if len(combined) > MAX_TOTAL_CHARS:
            combined = combined[:MAX_TOTAL_CHARS] + "\n... (전체 내용이 많아 일부만 Claude에게 전달됐어요) ..."

        user_prompt = (
            f"오늘 날짜: {datetime.now().strftime('%Y-%m-%d')}\n\n"
            f"다음은 업로드된 파일 {len(file_texts)}개의 내용이야. "
            f"지시에 따라 합치고 분석해서 HTML 리포트를 만들어줘.\n\n{combined}"
        )

        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=16000,
                system=SYSTEM_PROMPT,
                thinking={"type": "adaptive"},
                output_config={"effort": "high"},
                messages=[{"role": "user", "content": user_prompt}],
            )
        except anthropic.AuthenticationError:
            await status.edit(content="⚠️ Anthropic API 키가 잘못됐어요. .env의 ANTHROPIC_API_KEY를 확인해주세요.")
            return
        except anthropic.RateLimitError:
            await status.edit(content="⚠️ 요청이 몰려서 잠시 제한됐어요. 잠시 후 다시 파일을 올려주세요.")
            return
        except anthropic.APIStatusError as e:
            await status.edit(content=f"⚠️ Claude API 오류가 발생했어요: {e.message}")
            return
        except anthropic.APIConnectionError:
            await status.edit(content="⚠️ Claude API 연결에 실패했어요. 네트워크 상태를 확인하고 다시 시도해주세요.")
            return

        if response.stop_reason == "refusal":
            reason = response.stop_details.category if response.stop_details else "알 수 없음"
            await status.edit(content=f"⚠️ 요청이 안전 정책으로 거부됐어요 (사유: {reason}). 파일 내용을 확인해주세요.")
            return

        html_text = next((b.text for b in response.content if b.type == "text"), "")
        html_text = strip_code_fence(html_text).strip()

        if not html_text:
            await status.edit(content="⚠️ 리포트 내용을 받지 못했어요. 다시 시도해주세요.")
            return

        out_path = f"/tmp/report_{message.id}.html"
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(html_text)

        await status.edit(content="✅ 리포트를 만들었어요! 첨부파일을 다운받아 열어보세요.")
        await message.channel.send(
            file=discord.File(out_path, filename=f"report_{datetime.now().strftime('%Y%m%d_%H%M')}.html")
        )


if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
