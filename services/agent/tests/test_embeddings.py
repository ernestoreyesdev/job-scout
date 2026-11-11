from app.embeddings import job_text, resume_chunks


def test_a_resume_is_split_at_line_breaks_into_pieces_the_model_reads_whole():
    text = "Summary\n\n" + "\n".join(f"Bullet {n} " + "x" * 90 for n in range(40))

    chunks = resume_chunks(text, max_chars=1000)

    assert all(len(chunk) <= 1000 for chunk in chunks) and len(chunks) > 1
    assert chunks[0].startswith("Summary\nBullet 0")
    assert "\n".join(chunks).replace("\n", "") == text.replace("\n", "")


def test_a_line_longer_than_a_piece_is_cut():
    assert resume_chunks("y" * 50, max_chars=20) == ["y" * 20]


def test_job_text_leaves_out_a_missing_location():
    assert job_text("Engineer", "Acme", None, "Builds things.") == "Engineer at Acme\n\nBuilds things."
