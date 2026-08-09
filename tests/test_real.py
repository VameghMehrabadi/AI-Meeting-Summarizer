"""REAL end-to-end pipeline test (downloads + uses actual models).

Unlike test_pipeline.py (which stubs the summarizer), this runs the REAL
summarizer (BART for English, mT5 XLSum for Farsi) and the REAL extractor
(spaCy for English, ParsBERT NER for Farsi). It does NOT test audio/Whisper.

Requires the full install: torch, transformers, faster-whisper, spacy +
en_core_web_sm, dateparser, jdatetime, sqlalchemy.

Run:
    python tests/test_real.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.language import detect_language
from app.services import preprocessor, summarizer, extractor, report_builder
from app.db.database import SessionLocal, init_db
from app.db import crud

SAMPLE_EN = """\
Sarah: Welcome everyone. Today we're kicking off Project Phoenix.

John: I'll be leading the engineering team. We decided that the first milestone is the API design. John will prepare the API spec by next Friday.

Maria: I'm responsible for the QA plan. I need to draft the test strategy before the end of this month.

Sarah: David, you are tasked with setting up the CI pipeline. David will configure GitHub Actions by next Monday. We approved a budget of fifty thousand dollars for Q1. Action item: Maria to send the budget breakdown to finance by this Friday.

John: The frontend team needs to deliver the wireframes by the end of next week.
"""

SAMPLE_FA = """\
سارا: خوش آمدید. امروز جلسه آغاز پروژه ققنوس را شروع می‌کنیم.

رضا: من مسئول تیم مهندسی خواهم بود. ما تصمیم گرفتیم اولین مرحله طراحی API باشد. رضا باید مشخصات API را تا جمعه آینده آماده کند.

مریم: من مسئول برنامه تضمین کیفیت هستم. باید استراتژی تست را تا پایان این ماه آماده کنم.

سارا: علی، تو مکلفی خط لوله CI را راه‌اندازی کنی. علی باید GitHub Actions را تا دوشنبه آینده پیکربندی کند. ما بودجه پنجاه هزار دلاری فصل اول را تأیید کردیم. اقدام: مریم باید تفکیک بودجه را تا این جمعه به امور مالی ارسال کند.

رضا: تیم فرانت‌اند باید وایرفریم‌ها را تا پایان هفته آینده تحویل دهد.
"""


def run_real(name, sample):
    print("=" * 70)
    print(f"REAL SAMPLE: {name}")
    print("=" * 70)
    lang = detect_language(sample)
    print(f"Detected language: {lang}\n")

    cleaned = preprocessor.clean(sample)
    chunks = preprocessor.chunk(cleaned)
    print(f"Chunks: {len(chunks)}\n")

    print("--- REAL SUMMARIZATION (this downloads the model on first run) ---")
    try:
        summary = summarizer.summarize(chunks, lang=lang)
        print("Summary:", summary, "\n")
    except Exception as e:
        print(f"[summarization failed: {e}]\n")
        summary = f"[summarization failed: {e}]"

    print("--- REAL EXTRACTION ---")
    try:
        extracted = extractor.extract(cleaned, lang=lang)
        print(json.dumps(extracted, indent=2, ensure_ascii=False), "\n")
    except Exception as e:
        print(f"[extraction failed: {e}]\n")
        extracted = {"action_items": [], "decisions": [], "participants": []}

    print("--- PERSIST TO DB ---")
    init_db()
    db = SessionLocal()
    try:
        meeting = crud.create_meeting(db, title=f"Real test ({lang})", source_type="text", transcript=cleaned, status="building")
        meeting.language = lang
        meeting.summary = summary
        db.commit()
        report_builder.build(db, meeting, extracted)
        crud.update_meeting(db, meeting, status="done")
        m = crud.get_meeting(db, meeting.id)
        print(f"Meeting id={m.id} lang={m.language} status={m.status}")
        print(f"  participants: {m.participants}")
        print(f"  decisions ({len(m.decisions)}):")
        for d in m.decisions:
            print(f"    - {d.text}")
        print(f"  action_items ({len(m.action_items)}):")
        for a in m.action_items:
            print(f"    - text='{a.text}'  owner={a.owner}  due={a.due_date}")
        crud.delete_meeting(db, m)
        print("[test meeting deleted]\n")
    finally:
        db.close()
    return lang


def main():
    print("NOTE: first run downloads BART (~1.5GB) and possibly mT5 + ParsBERT for Farsi.\n")
    run_real("English", SAMPLE_EN)
    run_real("Farsi", SAMPLE_FA)
    print("=" * 70)
    print("REAL TEST COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
