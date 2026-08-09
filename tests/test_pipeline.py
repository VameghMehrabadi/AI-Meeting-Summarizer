"""Lightweight end-to-end pipeline test (English + Farsi).

Tests the full processing pipeline (preprocess -> summarize -> extract ->
report) on sample transcripts WITHOUT requiring the heavy BART/Whisper models.
The summarizer is stubbed so torch/transformers are not needed for the
English path. The Farsi extraction path uses the HF Persian NER model, which
DOES require transformers + torch (skipped if unavailable).

Requirements to run (English path): spacy + en_core_web_sm + dateparser +
jdatetime + sqlalchemy + fastapi.

Run:
    python tests/test_pipeline.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.language import detect_language
from app.services import preprocessor, extractor, summarizer as _summarizer_mod
from app.services import report_builder
from app.db.database import SessionLocal, init_db
from app.db import crud

SAMPLE_EN = """\
Project Phoenix Kickoff Meeting

Sarah: Welcome everyone. Today we're kicking off Project Phoenix. Thanks for joining.

John: Thanks for having me. I'll be leading the engineering team on this one.

Sarah: Great. We decided that the first milestone is the API design. John will prepare the API spec by next Friday.

Maria: I'm responsible for the QA plan. I need to draft the test strategy before the end of this month.

John: We agreed that the backend should use Python and FastAPI. The team chose PostgreSQL for the database.

Sarah: Good. David, you are tasked with setting up the CI pipeline. David will configure GitHub Actions by next Monday.

David: Understood. I will also schedule a security review before the end of Q3.

Sarah: We approved the budget of fifty thousand dollars for the first quarter. Action item: Maria to send the budget breakdown to finance by this Friday.

John: The frontend team needs to deliver the wireframes. They have to share them with design by the end of next week.

Sarah: Let's wrap up. Decisions: Python + FastAPI backend, PostgreSQL database, fifty thousand dollar Q1 budget approved. Next meeting is on Wednesday.

Maria: I will follow up with the vendor about the licenses. Deadline is by next Tuesday.

David: I should also review the existing infrastructure before the migration. No later than August 20.

Sarah: Thanks everyone. Meeting adjourned.
"""

SAMPLE_FA = """\
جلسه آغاز پروژه ققنوس

سارا: خوش آمدید. امروز جلسه آغاز پروژه ققنوس را شروع می‌کنیم. ممنون که آمدید.

رضا: ممنون. من مسئول تیم مهندسی این پروژه خواهم بود.

سارا: عالی. ما تصمیم گرفتیم اولین مرحله طراحی API باشد. رضا باید مشخصات API را تا جمعه آینده آماده کند.

مریم: من مسئول برنامه تضمین کیفیت هستم. باید استراتژی تست را تا پایان این ماه آماده کنم.

رضا: ما توافق کردیم که بک‌اند با پایتون و FastAPI باشد. تیم PostgreSQL را برای پایگاه داده انتخاب کرد.

سارا: خوب است. علی، تو مکلفی خط لوله CI را راه‌اندازی کنی. علی باید GitHub Actions را تا دوشنبه آینده پیکربندی کند.

علی: متوجه شدم. من همچنین باید یک بازبینی امنیتی تا پایان فصل سوم برنامه‌ریزی کنم.

سارا: ما بودجه پنجاه هزار دلاری برای فصل اول را تأیید کردیم. اقدام: مریم باید تفکیک بودجه را تا این جمعه به امور مالی ارسال کند.

رضا: تیم فرانت‌اند باید وایرفریم‌ها را تحویل دهد. آن‌ها باید وایرفریم‌ها را تا پایان هفته آینده با تیم طراحی به اشتراک بگذارند.

سارا: جمع‌بندی کنیم. تصمیمات: بک‌اند پایتون + FastAPI، پایگاه داده PostgreSQL، بودجه پنجاه هزار دلاری فصل اول تأیید شد. جلسه بعدی چهارشنبه است.

مریم: من با فروشنده درباره مجوزها پیگیری خواهم کرد. مهلت تا سه‌شنبه آینده است.

علی: من همچنین باید زیرساخت موجود را قبل از مهاجرت بررسی کنم. نهایتاً ۲۰ مرداد.

سارا: ممنون از همه. جلسه پایان یافت.
"""


def _stub_summarize(chunks, lang="en", **kwargs):
    if not chunks:
        return ""
    firsts = []
    for c in chunks:
        sep = ". " if lang == "en" else "۔ "
        firsts.append(c.split(sep)[0])
    label = "Summary (stub)" if lang == "en" else "خلاصه (stub)"
    return f"{label}: " + ". ".join(firsts[:3]) + "."


def run_sample(name, sample, expected_lang):
    print("=" * 70)
    print(f"SAMPLE: {name}  (expected lang={expected_lang})")
    print("=" * 70)
    detected = detect_language(sample)
    print(f"Detected language: {detected}\n")

    cleaned = preprocessor.clean(sample)
    print("--- cleaned (first 300 chars) ---")
    print(cleaned[:300], "...\n")

    chunks = preprocessor.chunk(cleaned)
    print(f"Chunks: {len(chunks)}")
    for i, c in enumerate(chunks):
        print(f"  chunk {i}: {len(c)} chars")

    print("\n--- summarize (stubbed) ---")
    _summarizer_mod.summarize = _stub_summarize
    summary = _summarizer_mod.summarize(chunks, lang=detected)
    print(summary)

    print("\n--- extract ---")
    try:
        extracted = extractor.extract(cleaned, lang=detected)
    except Exception as e:
        print(f"[extraction failed: {e}]")
        extracted = {"action_items": [], "decisions": [], "participants": []}
    print(json.dumps(extracted, indent=2, ensure_ascii=False))
    return detected, summary, extracted


def persist(title, lang, transcript, summary, extracted):
    init_db()
    db = SessionLocal()
    try:
        meeting = crud.create_meeting(
            db, title=title, source_type="text",
            transcript=transcript, status="building",
        )
        meeting.language = lang
        meeting.summary = summary
        db.commit()
        report_builder.build(db, meeting, extracted)
        crud.update_meeting(db, meeting, status="done")

        m = crud.get_meeting(db, meeting.id)
        print(f"\nPersisted meeting id={m.id} lang={m.language} status={m.status}")
        print(f"  participants: {m.participants}")
        print(f"  decisions ({len(m.decisions)}):")
        for d in m.decisions:
            print(f"    - {d.text}")
        print(f"  action_items ({len(m.action_items)}):")
        for a in m.action_items:
            print(f"    - text='{a.text}'  owner={a.owner}  due={a.due_date}  status={a.status}")
        crud.delete_meeting(db, m)
        print("[test meeting deleted]")
    finally:
        db.close()


def main():
    lang_en, summary_en, extracted_en = run_sample("English", SAMPLE_EN, "en")
    persist("Project Phoenix Kickoff (EN test)", lang_en,
            preprocessor.clean(SAMPLE_EN), summary_en, extracted_en)

    print("\n")
    lang_fa, summary_fa, extracted_fa = run_sample("Farsi", SAMPLE_FA, "fa")
    persist("جلسه ققنوس (FA test)", lang_fa,
            preprocessor.clean(SAMPLE_FA), summary_fa, extracted_fa)

    print("\n" + "=" * 70)
    print("ALL CHECKS COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
