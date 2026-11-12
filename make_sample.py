"""BridgeNote 수업용 가상 데이터를 data/ 폴더에 만들어요.
- data/contacts.csv    : 가상 상대 5명 (영어 2 · 중국어 2 · 일본어 1)
- data/phrases.csv     : 가상 검수 완료 문장 10줄 (날짜는 '오늘' 기준으로 만들어져요)
- data/check_rules.csv : 보내기 전 점검 단어 목록 (PRD F5 표 그대로)
- 모든 이름 · 문장은 지어낸 가상 정보예요. 실제 회사 · 개인 정보는 없어요.
- 이미 파일이 있으면 지우지 않고 멈춰요. (다시 만들고 싶으면: python3 make_sample.py --reset)
"""
import csv, sys, datetime, pathlib

DATA = pathlib.Path(__file__).parent / "data"
FILES = ["contacts.csv", "phrases.csv", "check_rules.csv"]

existing = [n for n in FILES if (DATA / n).exists()]
if existing and "--reset" not in sys.argv:
    print(f"이미 {', '.join('data/' + n for n in existing)} 가 있어요. 지우지 않고 멈출게요. (새로 만들려면 --reset)")
    sys.exit(0)

t = datetime.date.today()
d = lambda n: (t - datetime.timedelta(days=n)).isoformat()

contacts = [
    # id, name, relation, language, formality
    (1, "Emily Carter", "client", "en", "formal"),
    (2, "Jake", "friend", "en", "casual"),
    (3, "王小明", "boss", "zh", "formal"),
    (4, "李娜", "colleague", "zh", "normal"),
    (5, "佐藤健", "client", "ja", "formal"),
]

phrases = [
    # id, date, text, language, situation, contact_id, source_ko
    (1, d(12), "Dear Ms. Carter, thank you for your quick reply. Best regards,", "en", "email", 1,
     "카터 님, 빠른 답장 감사합니다."),
    (2, d(11), "Sounds good! See you at 7 then.", "en", "chat", 2, "좋아! 그럼 7시에 봐."),
    (3, d(9), "尊敬的王经理，附件是本周的报告，请您查收。此致敬礼", "zh", "email", 3,
     "왕 팀장님, 이번 주 보고서를 첨부드립니다. 확인 부탁드립니다."),
    (4, d(8), "李娜，明天的会议改到下午三点了。", "zh", "chat", 4, "리나, 내일 회의 오후 3시로 바뀌었어."),
    (5, d(6), "佐藤様、お世話になっております。見積書をお送りいたします。よろしくお願いいたします。", "ja", "email", 5,
     "사토 님, 견적서를 보내드립니다. 잘 부탁드립니다."),
    (6, d(5), "Could you share the updated schedule by Friday?", "en", "email", 1, ""),  # 원문 빈칸
    (7, d(4), "Thanks for the help today, really appreciate it.", "en", "chat", "", ""),  # 상대 지정 안 함
    (8, d(3), "谢谢您的耐心等待，我们会尽快回复。", "zh", "email", "", "기다려 주셔서 감사합니다. 최대한 빨리 답드리겠습니다."),
    (9, d(2), "明日の打ち合わせ、よろしくお願いします。", "ja", "chat", 5, "내일 미팅 잘 부탁드립니다."),
    (10, d(1), "Hi Jake, are you free this weekend?", "en", "chat", 2, "제이크, 이번 주말에 시간 돼?"),
]

check_rules = [
    # language, type, word
    ("en", "greeting", "Dear"), ("en", "greeting", "Hi"), ("en", "greeting", "Hello"),
    ("en", "closing", "Best regards"), ("en", "closing", "Thanks"),
    ("en", "casual", "gonna"), ("en", "casual", "wanna"), ("en", "casual", "lol"), ("en", "casual", "btw"),
    ("zh", "greeting", "尊敬的"), ("zh", "greeting", "您好"), ("zh", "greeting", "你好"),
    ("zh", "closing", "此致敬礼"), ("zh", "closing", "谢谢"), ("zh", "closing", "祝好"),
    ("zh", "casual", "哈哈"), ("zh", "casual", "啥"), ("zh", "casual", "咋"),
    ("ja", "greeting", "様"), ("ja", "greeting", "お世話になっております"),
    ("ja", "closing", "よろしくお願いいたします"), ("ja", "closing", "敬具"),
    ("ja", "casual", "マジ"), ("ja", "casual", "やばい"), ("ja", "casual", "(笑)"),
]


def write(name, header, rows):
    p = DATA / name
    with p.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    print(f"{len(rows)}줄 → {p}")


DATA.mkdir(exist_ok=True)
write("contacts.csv", ["id", "name", "relation", "language", "formality"], contacts)
write("phrases.csv", ["id", "date", "text", "language", "situation", "contact_id", "source_ko"], phrases)
write("check_rules.csv", ["language", "type", "word"], check_rules)
print("가상 데이터를 만들었어요.")
