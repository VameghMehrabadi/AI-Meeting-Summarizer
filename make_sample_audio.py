"""Generate a sample English meeting audio file for testing.

Uses Windows SAPI5 (offline, no internet) via pyttsx3 to synthesize a short
meeting transcript and save it as a .wav file. The generated audio can then be
uploaded through the web UI to test the full pipeline (Whisper transcription
-> BART summarization -> action-item extraction).

Run:
    python make_sample_audio.py
Output:
    tests/sample_meeting_en.wav
"""
import sys
from pathlib import Path

OUTPUT = Path(__file__).resolve().parent / "tests" / "sample_meeting_en.wav"

# A short, realistic English meeting transcript with action items, owners,
# and deadlines so the extractor has something to find.
MEETING_TEXT = (
    "Project Phoenix kickoff meeting. "
    "Sarah: Welcome everyone. Today we are kicking off Project Phoenix. "
    "John: Thanks for having me. I will be leading the engineering team. "
    "Sarah: We decided that the first milestone is the API design. "
    "John will prepare the API spec by next Friday. "
    "Maria: I am responsible for the QA plan. I need to draft the test strategy "
    "before the end of this month. "
    "Sarah: David, you are tasked with setting up the CI pipeline. "
    "David will configure GitHub Actions by next Monday. "
    "Sarah: We approved a budget of fifty thousand dollars for the first quarter. "
    "Action item: Maria to send the budget breakdown to finance by this Friday. "
    "John: The frontend team needs to deliver the wireframes by the end of next week. "
    "Sarah: Let us wrap up. Decisions: Python and FastAPI backend, "
    "fifty thousand dollar Q1 budget approved. Next meeting is on Wednesday. "
    "Thanks everyone. Meeting adjourned."
)


def synthesize_with_pyttsx3():
    import pyttsx3
    engine = pyttsx3.init()
    # Slightly slower rate for clearer speech (better transcription accuracy)
    rate = engine.getProperty("rate")
    engine.setProperty("rate", int(rate * 0.9))
    # Try to pick a natural-sounding voice if available
    voices = engine.getProperty("voices")
    if voices:
        engine.setProperty("voice", voices[0].id)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    engine.save_to_file(MEETING_TEXT, str(OUTPUT))
    engine.runAndWait()
    print(f"Saved: {OUTPUT}")


def synthesize_with_gtts():
    from gtts import gTTS
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    tts = gTTS(MEETING_TEXT, lang="en", slow=False)
    out_mp3 = OUTPUT.with_suffix(".mp3")
    tts.save(str(out_mp3))
    print(f"Saved (gTTS): {out_mp3}")
    # Try to convert to wav if ffmpeg is available; otherwise keep mp3
    try:
        import subprocess
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(out_mp3), "-ar", "16000", "-ac", "1", str(OUTPUT)],
            check=True, capture_output=True,
        )
        print(f"Converted to wav: {OUTPUT}")
    except Exception:
        print("ffmpeg not found; keeping the .mp3 file (Whisper accepts mp3 too).")


def main():
    print("Generating a sample English meeting audio file...\n")
    print("Text to synthesize:")
    print(MEETING_TEXT[:200], "...\n")
    try:
        synthesize_with_pyttsx3()
    except ImportError:
        print("pyttsx3 not installed; trying gTTS (requires internet)...")
        try:
            synthesize_with_gtts()
        except ImportError:
            print("\nNeither pyttsx3 nor gTTS is installed.", file=sys.stderr)
            print("Install one of them and retry:", file=sys.stderr)
            print("  pip install pyttsx3   (offline, Windows SAPI)", file=sys.stderr)
            print("  pip install gTTS       (online, Google TTS)", file=sys.stderr)
            sys.exit(1)
    except Exception as e:
        print(f"\nOffline TTS failed: {e}", file=sys.stderr)
        print("Trying gTTS (requires internet)...", file=sys.stderr)
        try:
            synthesize_with_gtts()
        except Exception as e2:
            print(f"\nBoth TTS options failed: {e2}", file=sys.stderr)
            sys.exit(1)

    print("\nDone. Upload this file through the web UI (Upload Audio tab) to test the pipeline.")


if __name__ == "__main__":
    main()
