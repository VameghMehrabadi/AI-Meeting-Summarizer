"""Action-item, decision, and entity extraction (English + Farsi).

English:  spaCy NER (en_core_web_sm) + English rule patterns.
Farsi:    HuggingFace Persian NER (ParsBERT) + Farsi rule patterns.

Both produce the same output shape:
    {
        "action_items": [{"text", "owner", "due_date", "status"}],
        "decisions": [{"text"}],
        "participants": [str, ...],
    }
"""
import logging
import re
from datetime import datetime, date
from typing import List, Dict, Any, Optional

from app.core.config import NER_FA_MODEL_NAME

logger = logging.getLogger(__name__)

# ---------- spaCy (English) ----------
_nlp = None


def _get_nlp():
    global _nlp
    if _nlp is None:
        import spacy
        try:
            _nlp = spacy.load("en_core_web_sm")
        except OSError:
            logger.warning("spaCy model 'en_core_web_sm' not found; downloading...")
            from spacy.cli.download import download as spacy_download
            spacy_download("en_core_web_sm")
            _nlp = spacy.load("en_core_web_sm")
    return _nlp


# ---------- HuggingFace Persian NER ----------
_fa_ner = None


def _get_fa_ner():
    global _fa_ner
    if _fa_ner is None:
        from transformers import pipeline
        logger.info("Loading Persian NER model '%s'...", NER_FA_MODEL_NAME)
        _fa_ner = pipeline(
            "ner",
            model=NER_FA_MODEL_NAME,
            tokenizer=NER_FA_MODEL_NAME,
            aggregation_strategy="simple",
        )
        logger.info("Persian NER model loaded.")
    return _fa_ner


# ---------- English cue patterns ----------
_EN_ACTION_VERB_CUE = re.compile(
    r"\b(will|shall|needs? to|need to|has to|have to|must|should|is going to|are going to|"
    r"agreed to|will be responsible for|is responsible for|are responsible for|"
    r"is tasked with|are tasked with|to do|to follow up|to send|to prepare|to review|to share|to schedule)\b",
    re.IGNORECASE,
)
_EN_ACTION_MARKER = re.compile(r"\b(action item|todo|task|follow-?up|next step|action point)\b\s*:?\s*", re.IGNORECASE)
_EN_DECISION_CUE = re.compile(
    r"\b(we (?:decided|agreed|concluded|approved|confirmed|chose|selected)|"
    r"decisions?|approved|agreed that|resolved that|conclusion)\b",
    re.IGNORECASE,
)
_EN_NEG_ACTION = re.compile(r"\b(won't|will not|should not|must not|cannot|can't|do not|don't)\b", re.IGNORECASE)


# ---------- Farsi cue patterns ----------
_FA_ACTION_VERB_CUE = re.compile(
    r"(باید|خواهد|قرار است|می\u200c?بایست|می\u200c?باید|مسئول|مکلف|تکلیف دارد|"
    r"انجام می\u200c?دهد|پیگیری می\u200c?کند|آماده می\u200c?کند|ارسال می\u200c?کند|"
    r"بررسی می\u200c?کند|زمان\u200c?بندی می\u200c?کند|تحویل می\u200c?دهد)"
)
_FA_ACTION_MARKER = re.compile(r"(اقدام|اقدامات|کار|کارها|پیگیری|پیگیری\u200c?ها|گام بعدی|وظیفه)\s*[:：]\s*")
_FA_DECISION_CUE = re.compile(
    r"(تصمیم (?:گرفته شد|گرفتیم|این بود|ما|شده است)|تصمیم(?:ات)?|موافقه شد|موافقت شد|"
    r"تأیید شد|تایید شد|توافق شد|نتیجه\u200c?گیری|تصمیم\u200c?گیری)"
)
_FA_NEG_ACTION = re.compile(r"(نباید|نخواهد|انجام نمی\u200c?دهد|نمی\u200c?تواند)")


# ---------- Helpers ----------
_FA_DIGIT_MAP = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
# Persian month names (used by jdatetime) -> mapping for parsing
_FA_MONTHS = {
    "فروردین": 1, "اردیبهشت": 2, "خرداد": 3, "تیر": 4, "مرداد": 5, "شهریور": 6,
    "مهر": 7, "آبان": 8, "آذر": 9, "دی": 10, "بهمن": 11, "اسفند": 12,
}


def _to_ascii_digits(s: str) -> str:
    return s.translate(_FA_DIGIT_MAP)


def _try_jalali(phrase: str) -> Optional[str]:
    """Attempt to parse a Jalali date phrase and return a Gregorian ISO date."""
    try:
        import jdatetime
    except ImportError:
        return None
    p = _to_ascii_digits(phrase).strip()

    # Try "YYYY/MM/DD" or "YYYY-MM-DD" Jalali
    m = re.search(r"(\d{4})[/\-](\d{1,2})[/\-](\d{1,2})", p)
    if m:
        try:
            jd = jdatetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            return jd.togregorian().isoformat()
        except Exception:
            return None

    # Try "DD <month-name> YYYY" e.g. "10 مرداد 1403"
    m = re.match(r"\s*(\d{1,2})\s+([آ-ی]+)\s+(\d{2,4})\s*$", p)
    if m:
        month_name = m.group(2)
        if month_name in _FA_MONTHS:
            try:
                year = int(m.group(3))
                if year < 100:
                    year += 1400
                jd = jdatetime.date(year, _FA_MONTHS[month_name], int(m.group(1)))
                return jd.togregorian().isoformat()
            except Exception:
                return None
    return None


def _normalize_deadline(phrase: str, lang: str, reference: Optional[date] = None) -> Optional[str]:
    """Normalize a date phrase to ISO (YYYY-MM-DD) when possible."""
    if not phrase:
        return None

    # For Farsi, first try Jalali absolute dates, then dateparser for relatives.
    if lang == "fa":
        jalali = _try_jalali(phrase)
        if jalali:
            return jalali

    try:
        import dateparser
    except ImportError:
        return phrase.strip()

    ref = reference or date.today()
    languages = ["fa"] if lang == "fa" else ["en"]
    parsed = dateparser.parse(
        phrase,
        languages=languages,
        settings={
            "RELATIVE_BASE": datetime(ref.year, ref.month, ref.day),
            "PREFER_DAY_OF_MONTH": "first",
            "RETURN_AS_TIMEZONE_AWARE": False,
        },
    )
    if parsed:
        return parsed.date().isoformat()
    return phrase.strip()


def _extract_deadline_from_sentence(sent_text: str, lang: str) -> Optional[str]:
    """Find and normalize a deadline phrase inside a sentence."""
    if lang == "fa":
        patterns = [
            r"تا\s+(.+?)(?:[.;،؟\n]|$)",
            r"تا قبل از\s+(.+?)(?:[.;،؟\n]|$)",
            r"مهلت(?:\s+آن)?\s+(.+?)(?:[.;،؟\n]|$)",
            r"سررسید(?:\s+آن)?\s+(.+?)(?:[.;،؟\n]|$)",
            r"نهایتاً\s+(.+?)(?:[.;،؟\n]|$)",
        ]
    else:
        patterns = [
            r"\bby\s+(.+?)(?:[.;,\n]|$)",
            r"\bdue(?:\s+on)?\s+(.+?)(?:[.;,\n]|$)",
            r"\bdeadline(?:\s+is)?\s+(.+?)(?:[.;,\n]|$)",
            r"\bno later than\s+(.+?)(?:[.;,\n]|$)",
            r"\bbefore\s+(.+?)(?:[.;,\n]|$)",
        ]
    for pat in patterns:
        m = re.search(pat, sent_text, re.IGNORECASE if lang == "en" else 0)
        if m:
            phrase = m.group(1).strip().rstrip(".,;،")
            words = phrase.split()
            if len(words) > 6:
                phrase = " ".join(words[:6])
            iso = _normalize_deadline(phrase, lang)
            if iso:
                return iso
    return None


def _split_sentences(text: str, lang: str) -> List[str]:
    """Lightweight sentence splitter for both languages."""
    if lang == "fa":
        parts = re.split(r"(?<=[.!?؟])\s+", text)
    else:
        text_protected = re.sub(r"\b(Mr|Mrs|Ms|Dr|Prof|Inc|Ltd|Corp|vs|e\.g|i\.e)\.", r"\1<DOT>", text)
        parts = re.split(r"(?<=[.!?])\s+(?=[A-Z\u0600-\u06FF])", text_protected)
        parts = [p.replace("<DOT>", ".") for p in parts]
    return [p.strip() for p in parts if p.strip()]


# ---------- English extraction ----------
def _extract_en(text: str) -> Dict[str, Any]:
    nlp = _get_nlp()
    doc = nlp(text)

    participants = sorted({ent.text for ent in doc.ents if ent.label_ == "PERSON"})

    action_items: List[Dict[str, Any]] = []
    decisions: List[Dict[str, Any]] = []
    seen_actions = set()
    seen_decisions = set()

    for sent in doc.sents:
        sent_text = sent.text.strip()
        if len(sent_text) < 15:
            continue

        if _EN_DECISION_CUE.search(sent_text):
            if sent_text.lower() not in seen_decisions:
                seen_decisions.add(sent_text.lower())
                decisions.append({"text": sent_text})

        is_marker = bool(_EN_ACTION_MARKER.search(sent_text))
        is_cue = bool(_EN_ACTION_VERB_CUE.search(sent_text))
        if not (is_marker or is_cue):
            continue
        if _EN_NEG_ACTION.search(sent_text):
            continue

        action_text = _EN_ACTION_MARKER.sub("", sent_text).strip()
        if len(action_text) < 10:
            continue

        verb_match = _EN_ACTION_VERB_CUE.search(sent_text)
        owner = None
        if verb_match:
            doc_char_start = sent.start_char + verb_match.start()
            token_idx = None
            for t in sent:
                if t.idx >= doc_char_start:
                    token_idx = t.i
                    break
            if token_idx is None and len(sent) > 0:
                token_idx = sent[-1].i
            if token_idx is not None:
                owner = _nearest_person_en(doc, token_idx, max_distance=8)

        due = _extract_deadline_from_sentence(sent_text, "en")

        key = action_text.lower()
        if key in seen_actions:
            continue
        seen_actions.add(key)
        action_items.append({"text": action_text, "owner": owner, "due_date": due, "status": "open"})

    return {"action_items": action_items, "decisions": decisions, "participants": participants}


def _nearest_person_en(doc, token_index: int, max_distance: int = 6) -> Optional[str]:
    persons = [(ent.start, ent.end, ent.text) for ent in doc.ents if ent.label_ == "PERSON"]
    if not persons:
        return None
    best, best_dist = None, max_distance + 1
    for start, end, txt in persons:
        dist = min(abs(token_index - start), abs(token_index - end))
        if dist < best_dist:
            best_dist, best = dist, txt
    return best


# ---------- Farsi extraction ----------
# Label names emitted by HooshvareLab/bert-fa-zwnj-base-ner for persons
_FA_PERSON_LABELS = {"B-PER", "I-PER", "PER", "B-person", "I-person", "person"}


def _fa_persons(ner_results) -> List[str]:
    """Extract person names from the HF NER pipeline output (aggregated)."""
    persons = []
    for ent in ner_results:
        label = ent.get("entity_group") or ent.get("entity") or ""
        word = ent.get("word", "")
        if label in _FA_PERSON_LABELS or "PER" in label.upper():
            # Clean subword tokens (## prefixes from BERT)
            word = word.replace("##", "")
            word = re.sub(r"\s+", " ", word).strip()
            if word and len(word) > 1:
                persons.append(word)
    # Merge adjacent duplicates / overlapping
    return persons


def _extract_fa(text: str) -> Dict[str, Any]:
    ner = _get_fa_ner()
    # Run NER; chunk to avoid exceeding model max length (512 tokens)
    ner_results = _run_fa_ner_chunked(ner, text)
    participants = sorted({p for p in _fa_persons(ner_results) if p})

    action_items: List[Dict[str, Any]] = []
    decisions: List[Dict[str, Any]] = []
    seen_actions = set()
    seen_decisions = set()

    sentences = _split_sentences(text, "fa")
    for sent_text in sentences:
        if len(sent_text) < 10:
            continue

        if _FA_DECISION_CUE.search(sent_text):
            if sent_text not in seen_decisions:
                seen_decisions.add(sent_text)
                decisions.append({"text": sent_text})

        is_marker = bool(_FA_ACTION_MARKER.search(sent_text))
        is_cue = bool(_FA_ACTION_VERB_CUE.search(sent_text))
        if not (is_marker or is_cue):
            continue
        if _FA_NEG_ACTION.search(sent_text):
            continue

        action_text = _FA_ACTION_MARKER.sub("", sent_text).strip()
        if len(action_text) < 8:
            continue

        # Owner: nearest participant name appearing in the sentence
        owner = _nearest_person_fa(sent_text, participants)

        due = _extract_deadline_from_sentence(sent_text, "fa")

        key = action_text
        if key in seen_actions:
            continue
        seen_actions.add(key)
        action_items.append({"text": action_text, "owner": owner, "due_date": due, "status": "open"})

    return {"action_items": action_items, "decisions": decisions, "participants": participants}


def _run_fa_ner_chunked(ner, text: str, char_window: int = 1500) -> List[dict]:
    """Run the NER pipeline on overlapping windows to handle long texts."""
    if len(text) <= char_window:
        return ner(text)
    results = []
    step = char_window - 200  # 200 char overlap
    i = 0
    while i < len(text):
        chunk = text[i:i + char_window]
        try:
            results.extend(ner(chunk))
        except Exception as e:
            logger.warning("Farsi NER chunk failed at %d: %s", i, e)
        i += step
    return results


def _nearest_person_fa(sent_text: str, participants: List[str]) -> Optional[str]:
    """Return the first participant name that appears in the sentence."""
    for p in participants:
        if p and p in sent_text:
            return p
    return None


# ---------- Public API ----------
def extract(text: str, lang: str = "en") -> Dict[str, Any]:
    """Extract action items, decisions, and participants.

    Args:
        text: cleaned transcript text.
        lang: ``"en"`` or ``"fa"``.
    """
    if not text or not text.strip():
        return {"action_items": [], "decisions": [], "participants": []}
    if lang == "fa":
        try:
            return _extract_fa(text)
        except Exception as e:
            logger.warning("Farsi extraction failed (%s); falling back to participants only.", e)
            return {"action_items": [], "decisions": [], "participants": []}
    return _extract_en(text)
