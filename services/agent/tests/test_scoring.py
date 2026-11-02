from app.agents.scoring.prompts import trim_description

ROLE = "About the role\nBuild payments infrastructure.\n\nRequirements\n- 5 years of Python\n- Distributed systems\n"


def test_trim_drops_benefits_and_legal_text_at_the_end():
    description = ROLE + "BENEFITS AVAILABLE TO ALL EMPLOYEES\n- Health insurance\n\nEqual Opportunity\nWe welcome everyone."

    assert trim_description(description) == ROLE.rstrip()


def test_trim_keeps_a_heading_near_the_start():
    description = "Benefits team engineer\n" + ROLE

    assert trim_description(description) == description


def test_trim_keeps_text_without_boilerplate():
    assert trim_description(ROLE) == ROLE


def test_trim_keeps_pay_lines_from_the_text_it_drops():
    description = ROLE + "Benefits\n- Health insurance\n\nPay Transparency\nThe base salary range is $150,000 - $190,000 USD.\n"

    assert trim_description(description) == (
        ROLE.rstrip() + "\n\nPay stated later in the posting:\nThe base salary range is $150,000 - $190,000 USD."
    )

