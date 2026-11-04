import uuid
from datetime import datetime, timezone

from smm_app.database import Base, SessionLocal, engine
from smm_app.models import (
    AuditStatus,
    ContactStatus,
    School,
    SchoolAuditRun,
    SchoolContact,
    SchoolPipelineStage,
)
from smm_app.prompts import DEFAULT_PROMPTS, get_prompt


def seed():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    try:
        # Seed prompts first
        for name in DEFAULT_PROMPTS:
            get_prompt(db, name)

        # Check if already seeded
        if db.query(School).count() > 0:
            print("Database already contains schools. Skipping seed.")
            return

        print("Seeding sample schools, audits, and outreach...")

        # 1. Oasis Academy Johanna (High Need, MAT)
        s1 = School(
            id=str(uuid.uuid4()),
            name="Oasis Academy Johanna",
            urn="142859",
            phase="Primary",
            school_type="Academy Converter",
            mat_name="Oasis Community Learning",
            local_authority="Lambeth",
            website="https://www.oasisacademyjohanna.org",
            postcode="SE1 7PB",
            address="Johanna Street, Lower Marsh, London SE1 7PB",
            sen_percentage=21.5,
            ehcp_count=16,
            ofsted_rating="Good",
            ofsted_inspection_date="November 2023",
            ofsted_send_excerpt=(
                "Pupils with special educational needs and/or disabilities (SEND) are fully included in all aspects of school life. "
                "Leaders identify pupils' needs accurately. However, in some subjects, teaching adaptations are not always sufficiently "
                "precise to help pupils remember their learning securely over time."
            ),
            pipeline_stage=SchoolPipelineStage.outreach_ready,
            overall_score=88,
            priority="Immediate Focus",
            notes="High proportion of neurodivergent learners. Part of Oasis MAT (54 academies nationally).",
        )
        db.add(s1)
        db.flush()

        # SENCO Contact
        c1 = SchoolContact(
            id=str(uuid.uuid4()),
            school_id=s1.id,
            name="Claire Thompson",
            role="SENCO & Inclusion Leader",
            email="claire.thompson@oasisjohanna.org",
            email_is_verified=True,
            phone_extension="204",
            source="Statutory SEND Information Report 2025/26 (Page 2)",
            status=ContactStatus.outreach_drafted,
            personalized_hook="Addressing Ofsted recommendation on daily lesson adaptations and home-school consistency.",
            email_subject="Coordinating daily classroom notes and parent check-ins at Oasis Johanna",
            email_draft="""Dear Claire,

I was reviewing Oasis Academy Johanna's recent SEND Information Report, particularly your focus on coordinating provision and sensory regulation for your 21.5% SEN support cohort.

SENCOs we collaborate with often tell us that while tracking software records the formal plan, the hardest part is getting teachers and TAs to consistently log quick classroom notes and keeping families informed without losing hours in the evening.

We built See My Mind to give class teachers visual morning briefings, TAs 1-tap transition logs, and parents a shared daily mood check-in — turning everyday observations into structured evidence for EHCP reviews automatically.

We put together a brief 3-minute video showing how a primary SENCO runs their morning briefings and annual review packs: https://seemymind.co.uk/product.html

If this sounds like it could save time for your team at Johanna, I'd be delighted to send across a preview or compare notes.

Warm regards,

Munish Kanwar
See My Mind Partnerships
hello@seemymind.co.uk | https://seemymind.co.uk""",
            letter_draft="""See My Mind Ltd
London, United Kingdom
https://seemymind.co.uk

4th November 2026

Mrs. Claire Thompson
SENCO & Inclusion Leader
Oasis Academy Johanna
Johanna Street, Lower Marsh
London SE1 7PB

Dear Mrs. Thompson,

RE: Coordinating daily classroom support and parent loops at Oasis Academy Johanna

I am writing to you directly following a review of Oasis Academy Johanna's published SEND Information Report and recent Ofsted inspection, particularly your team's dedication to supporting your high-need cohort.

Across London primary schools, SENCOs consistently tell us that their biggest operational challenge isn't identifying pupil needs — it is ensuring that teachers and teaching assistants have clear, practical next steps in the classroom every morning, and collecting ongoing evidence for annual reviews without drowning in paperwork.

We developed See My Mind specifically to address this gap. The platform connects teachers, TAs, and parents in a shared daily loop:
• Teachers see morning regulation zones and sensory tools before the day begins.
• Teaching assistants log key transition notes and micro-observations with a single tap.
• Parents share home context and mood check-ins, creating an auditable evidence trail for statutory reviews.

If you are currently evaluating how to streamline SEND coordination and reduce administrative strain across your team, I would welcome the opportunity to share a short overview.

You can explore our approach at https://seemymind.co.uk or book a 20-minute conversation with our education team at https://seemymind.co.uk/book-a-demo.

Yours sincerely,

Munish Kanwar
Education Partnerships Director
See My Mind
hello@seemymind.co.uk""",
        )
        db.add(c1)

        # Headteacher Contact
        c2 = SchoolContact(
            id=str(uuid.uuid4()),
            school_id=s1.id,
            name="Dawn Dipple",
            role="Headteacher",
            email="principal@oasisjohanna.org",
            email_is_verified=True,
            source="School Leadership Directory",
            status=ContactStatus.outreach_drafted,
            email_subject="Supporting SEND consistency and staff workload at Oasis Johanna",
            email_draft="""Dear Ms. Dipple,

As Headteacher at Oasis Academy Johanna, ensuring inclusion while protecting teacher workload is an ongoing balancing act, particularly with an above-average SEND roll.

Ofsted commended your inclusive ethos while noting that lesson adaptations could be reinforced more consistently across subjects. 

We developed See My Mind to give senior leaders whole-school oversight of daily provision and to reduce staff burnout by replacing fragmented notes with a coordinated morning dashboard.

I would be delighted to share a 3-minute walk-through of how our partner schools are strengthening their inclusion evidence trail: https://seemymind.co.uk/product.html

Kind regards,

Munish Kanwar
See My Mind Partnerships""",
        )
        db.add(c2)

        # Audit Run for s1
        run1 = SchoolAuditRun(
            id=str(uuid.uuid4()),
            school_id=s1.id,
            status=AuditStatus.completed,
            current_message="Audit complete",
            send_report_url="https://www.oasisacademyjohanna.org/curriculum/send",
            ofsted_report_url="https://reports.ofsted.gov.uk/provider/21/142859",
            detected_tools="Edukey Provision Map, CPOMS, Arbor MIS",
            strengths_found="• Strong whole-school inclusive ethos\n• Dedicated sensory room and morning speech & language groups\n• Active family coffee mornings",
            challenges_found="• 21.5% SEN support cohort requires extensive daily TA coordination\n• Teachers report administrative pressure gathering weekly evidence for 16 EHCPs",
            recommended_angle="Highlight morning classroom regulation overviews and reducing evening paperwork for the inclusion team.",
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
        )
        db.add(run1)

        # 2. Reach Academy Feltham (All-through, MAT)
        s2 = School(
            id=str(uuid.uuid4()),
            name="Reach Academy Feltham",
            urn="138249",
            phase="All-through",
            school_type="Free School",
            mat_name="Reach Foundation",
            local_authority="Hounslow",
            website="https://www.reachacademyfeltham.com",
            postcode="TW13 4AB",
            address="53-65 High Street, Feltham, Middlesex TW13 4AB",
            sen_percentage=17.4,
            ehcp_count=22,
            ofsted_rating="Outstanding",
            ofsted_inspection_date="March 2024",
            ofsted_send_excerpt=(
                "Pupils with SEND achieve exceptionally well. Leaders ensure that staff have the training and information needed to adapt "
                "curriculums seamlessly. Collaboration with parents and external therapists is exemplary."
            ),
            pipeline_stage=SchoolPipelineStage.qualified,
            overall_score=82,
            priority="Immediate Focus",
            notes="Exemplary cradle-to-career model. Strong candidate for early adopter pilot.",
        )
        db.add(s2)

        # 3. St Jude's Church of England Primary
        s3 = School(
            id=str(uuid.uuid4()),
            name="St Jude's Church of England Primary School",
            urn="100049",
            phase="Primary",
            school_type="Voluntary Aided School",
            mat_name=None,
            local_authority="Southwark",
            website="https://www.st-judes.southwark.sch.uk",
            postcode="SE1 7EW",
            address="St George's Road, Elephant and Castle, London SE1 7EW",
            sen_percentage=16.8,
            ehcp_count=9,
            ofsted_rating="Good",
            pipeline_stage=SchoolPipelineStage.discovered,
            overall_score=68,
            priority="Target School",
            notes="Single maintained primary school in Southwark. High pupil mobility and neurodiversity need.",
        )
        db.add(s3)

        db.commit()
        print("Successfully seeded demo schools and contacts!")

    finally:
        db.close()


if __name__ == "__main__":
    seed()
