"""
Import script for See My Mind UK Schools & Contacts
Imports data from sample_data/See_My_Mind_Schools_Contacts-3.xlsx
into smm_schools and smm_contacts.
"""

import os
import re
import sys
import uuid
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

from smm_app.database import SessionLocal
from smm_app.models import School, SchoolContact, SchoolPipelineStage, ContactStatus


def parse_xlsx_sheets(xlsx_path: Path):
    with zipfile.ZipFile(xlsx_path, "r") as z:
        shared_strings = []
        if "xl/sharedStrings.xml" in z.namelist():
            tree = ET.fromstring(z.read("xl/sharedStrings.xml"))
            for si in tree.findall("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}si"):
                texts = [
                    t.text for t in si.findall(".//{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t") if t.text
                ]
                shared_strings.append("".join(texts))

        wb_tree = ET.fromstring(z.read("xl/workbook.xml"))
        sheets = wb_tree.findall(".//{http://schemas.openxmlformats.org/spreadsheetml/2006/main}sheet")
        rels_tree = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        rel_map = {
            r.attrib["Id"]: r.attrib["Target"]
            for r in rels_tree.findall("{http://schemas.openxmlformats.org/package/2006/relationships}Relationship")
        }

        def get_sheet_rows(sheet_name_target):
            for s in sheets:
                if s.attrib.get("name") == sheet_name_target:
                    r_id = s.attrib.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
                    target = rel_map[r_id]
                    if not target.startswith("xl/"):
                        target = "xl/" + target
                    sheet_tree = ET.fromstring(z.read(target))
                    rows = sheet_tree.findall(
                        "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}sheetData/{http://schemas.openxmlformats.org/spreadsheetml/2006/main}row"
                    )
                    parsed_rows = []
                    for row in rows:
                        cols = {}
                        for c in row.findall("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}c"):
                            cell_ref = c.attrib.get("r")
                            col_letter = re.match(r"([A-Z]+)", cell_ref).group(1)
                            t = c.attrib.get("t")
                            v = c.find("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}v")
                            val = v.text if v is not None else None
                            if t == "s" and val is not None:
                                val = shared_strings[int(val)]
                            cols[col_letter] = val
                        if any(cols.values()):
                            parsed_rows.append(cols)
                    return parsed_rows
            return []

        schools_rows = get_sheet_rows("Schools")
        heads_rows = get_sheet_rows("Heads")
        sencos_rows = get_sheet_rows("SENCOs")

    return schools_rows, heads_rows, sencos_rows


def run_import(dry_run: bool = False):
    xlsx_file = PROJECT_ROOT / "sample_data" / "See_My_Mind_Schools_Contacts-3.xlsx"
    if not xlsx_file.exists():
        alt_path = PROJECT_ROOT.parent / "seemymind-lead-agent" / "sample_data" / "See_My_Mind_Schools_Contacts-3.xlsx"
        if alt_path.exists():
            xlsx_file = alt_path
        else:
            print(f"Error: Could not find {xlsx_file}")
            sys.exit(1)

    print(f"Loading data from: {xlsx_file}")
    schools_rows, heads_rows, sencos_rows = parse_xlsx_sheets(xlsx_file)

    # Index heads by school ID (col A)
    heads_by_id = {}
    for r in heads_rows[1:]:
        sid = r.get("A")
        if sid:
            heads_by_id[str(sid).strip()] = {
                "head_name": r.get("F"),
                "head_email": r.get("G"),
                "email_type": r.get("H"),
                "office_email": r.get("I"),
                "phone": r.get("J"),
                "website": r.get("K"),
                "status": r.get("L"),
                "notes": r.get("Q"),
                "source": r.get("R"),
            }

    # Index sencos by school ID (col A)
    sencos_by_id = {}
    for r in sencos_rows[1:]:
        sid = r.get("A")
        if sid:
            sencos_by_id[str(sid).strip()] = {
                "senco_name": r.get("F"),
                "senco_email": r.get("G"),
                "email_type": r.get("H"),
                "other_contacts": r.get("I"),
                "office_email": r.get("J"),
                "phone": r.get("K"),
                "data_check": r.get("L"),
                "status": r.get("M"),
                "notes": r.get("S"),
                "source": r.get("T"),
            }

    db = SessionLocal()
    imported_schools = 0
    updated_schools = 0
    created_contacts = 0
    updated_contacts = 0

    try:
        # Load existing schools into cache: by urn and by lower(name)
        existing_schools = db.query(School).all()
        by_urn = {s.urn: s for s in existing_schools if s.urn}
        by_name = {s.name.strip().lower(): s for s in existing_schools}

        for r in schools_rows[1:]:
            sid = str(r.get("A", "")).strip()
            name = (r.get("C") or "").strip()
            if not name:
                continue

            category = r.get("D") or "State primary"
            raw_phase = r.get("E") or "Primary"
            # Normalize phase
            if "Primary" in raw_phase or "primary" in category.lower():
                phase = "Primary"
            elif "Secondary" in raw_phase or "secondary" in category.lower() or "Grammar" in category:
                phase = "Secondary"
            elif "Nursery" in raw_phase:
                phase = "Nursery"
            elif "Special" in category:
                phase = "Special"
            else:
                phase = raw_phase

            la = r.get("F") or None
            region = r.get("G") or None
            postcode = (r.get("H") or "").strip() or None
            phone = (r.get("I") or "").strip() or None
            website = (r.get("J") or "").strip() or None
            if website and not website.startswith("http"):
                website = "https://" + website

            office_email = (r.get("K") or "").strip() or None
            reg_link = r.get("L") or ""
            urn_match = re.search(r"Establishment/Details/(\d+)", reg_link)
            urn = urn_match.group(1) if urn_match else None

            # Pull associated Heads and SENCOs records
            head_info = heads_by_id.get(sid, {})
            senco_info = sencos_by_id.get(sid, {})

            # Compile notes from extra intelligence
            extra_notes = []
            if senco_info.get("other_contacts"):
                extra_notes.append(f"SEND Intelligence: {senco_info['other_contacts']}")
            if senco_info.get("data_check"):
                extra_notes.append(f"Data Check: {senco_info['data_check']}")
            if head_info.get("notes"):
                extra_notes.append(f"Head Notes: {head_info['notes']}")
            if senco_info.get("notes"):
                extra_notes.append(f"SEN Notes: {senco_info['notes']}")
            combined_notes = " | ".join(extra_notes) if extra_notes else None

            # Check if school exists
            school = None
            if urn and urn in by_urn:
                school = by_urn[urn]
            elif name.lower() in by_name:
                school = by_name[name.lower()]

            if school:
                # Update existing school with any newly discovered info
                if not school.urn and urn:
                    school.urn = urn
                if not school.website and website:
                    school.website = website
                if not school.postcode and postcode:
                    school.postcode = postcode
                if not school.phone and phone:
                    school.phone = phone
                if not school.general_email and office_email:
                    school.general_email = office_email
                if not school.local_authority and la:
                    school.local_authority = la
                if not school.school_type and category:
                    school.school_type = category
                if combined_notes and not school.notes:
                    school.notes = combined_notes
                updated_schools += 1
            else:
                school = School(
                    id=str(uuid.uuid4()),
                    name=name,
                    urn=urn,
                    phase=phase,
                    school_type=category,
                    local_authority=la,
                    website=website,
                    postcode=postcode,
                    phone=phone,
                    general_email=office_email,
                    pipeline_stage=SchoolPipelineStage.discovered,
                    priority="Target School" if "Special" in category or "Grammar" in category else "Monitor",
                    notes=combined_notes,
                )
                db.add(school)
                db.flush()
                # Update cache
                if urn:
                    by_urn[urn] = school
                by_name[name.lower()] = school
                imported_schools += 1

            # ----------------------------------------------------
            # Contacts Processing
            # ----------------------------------------------------
            existing_contacts = {c.role.lower(): c for c in school.contacts}

            # 1. Process Headteacher Contact
            head_name = (head_info.get("head_name") or "").strip()
            head_email = (head_info.get("head_email") or "").strip() or None
            head_source = head_info.get("source") or reg_link or "GIAS School Register"

            if head_name:
                # Find if Head already exists
                head_c = next((c for c in school.contacts if "head" in c.role.lower() or "principal" in c.role.lower()), None)
                if head_c:
                    if head_name and head_c.name.startswith("The "):
                        head_c.name = head_name
                    if head_email and not head_c.email:
                        head_c.email = head_email
                        head_c.email_is_verified = True
                    updated_contacts += 1
                else:
                    head_c = SchoolContact(
                        id=str(uuid.uuid4()),
                        school_id=school.id,
                        name=head_name,
                        role="Headteacher",
                        email=head_email,
                        email_is_verified=bool(head_email),
                        source=head_source,
                        status=ContactStatus.discovered,
                    )
                    db.add(head_c)
                    created_contacts += 1

            # 2. Process SENCO Contact
            senco_name = (senco_info.get("senco_name") or "").strip()
            senco_email = (senco_info.get("senco_email") or "").strip() or None
            senco_source = senco_info.get("source") or "School Website / SEND Report"
            email_type = senco_info.get("email_type") or ""
            is_verified = "named person" in email_type.lower() or "senco inbox" in email_type.lower()

            if senco_name or senco_email:
                senco_c = next((c for c in school.contacts if "senco" in c.role.lower() or "inclusion" in c.role.lower()), None)
                if senco_c:
                    if senco_name and senco_c.name.startswith("The "):
                        senco_c.name = senco_name
                    if senco_email and not senco_c.email:
                        senco_c.email = senco_email
                        senco_c.email_is_verified = is_verified
                    updated_contacts += 1
                else:
                    senco_c = SchoolContact(
                        id=str(uuid.uuid4()),
                        school_id=school.id,
                        name=senco_name if senco_name else "The SENCO / Inclusion Lead",
                        role="SENCO & Inclusion Leader",
                        email=senco_email,
                        email_is_verified=is_verified,
                        source=senco_source,
                        status=ContactStatus.discovered,
                    )
                    db.add(senco_c)
                    created_contacts += 1

        if not dry_run:
            db.commit()
            print("\nDatabase commit successful!")
        else:
            db.rollback()
            print("\nDry run completed, rolled back.")

        print("\n" + "=" * 55)
        print("IMPORT SUMMARY:")
        print("=" * 55)
        print(f"New Schools Added:     {imported_schools}")
        print(f"Existing Schools Enriched: {updated_schools}")
        print(f"Total Schools in DB:   {db.query(School).count()}")
        print(f"New Contacts Created:  {created_contacts}")
        print(f"Contacts Updated:      {updated_contacts}")
        print(f"Total Contacts in DB:  {db.query(SchoolContact).count()}")
        print("=" * 55)

    finally:
        db.close()


if __name__ == "__main__":
    dry_run_flag = "--dry-run" in sys.argv
    run_import(dry_run=dry_run_flag)
