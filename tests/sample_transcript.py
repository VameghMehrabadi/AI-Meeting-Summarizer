"""Sample meeting transcript for end-to-end testing."""

SAMPLE_TRANSCRIPT = """Project Phoenix Kickoff Meeting

Sarah: Welcome everyone. Today we're kicking off Project Phoenix. Thanks for joining.

John: Thanks for having me. I'll be leading the engineering team on this one.

Sarah: Great. We decided that the first milestone is the API design. John will prepare the API spec by next Friday.

Maria: I'm responsible for the QA plan. I need to draft the test strategy before the end of this month.

John: We agreed that the backend should use Python and FastAPI. The team chose PostgreSQL for the database.

Sarah: Good. David, you are tasked with setting up the CI pipeline. David will configure GitHub Actions by next Monday.

David: Understood. I will also schedule a security review before the end of Q3.

Sarah: We approved the budget of fifty thousand dollars for the first quarter. Action item: Maria to send the budget breakdown to finance by this Friday.

John: The frontend team needs to deliver the wireframes. They have to share them with design by the end of next week.

Sarah: Let's wrap up. Decisions: Python + FastAPI backend, PostgreSQL database, fifty thousand dollar Q1 budget approved. Action items are tracked. Next meeting is on Wednesday.

Maria: I will follow up with the vendor about the licenses. Deadline is by next Tuesday.

David: I should also review the existing infrastructure before the migration. No later than August 20.

Sarah: Thanks everyone. Meeting adjourned.
"""

if __name__ == "__main__":
    from app.services import preprocessor, extractor

    cleaned = preprocessor.clean(SAMPLE_TRANSCRIPT)
    print("=== CLEANED ===")
    print(cleaned)
    print("\n=== CHUNKS ===")
    chunks = preprocessor.chunk(cleaned)
    for i, c in enumerate(chunks):
        print(f"--- chunk {i} ({len(c)} chars) ---")
        print(c)

    print("\n=== EXTRACTION ===")
    import json
    result = extractor.extract(cleaned)
    print(json.dumps(result, indent=2))
