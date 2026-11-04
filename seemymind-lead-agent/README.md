# See My Mind — Education Lead Intelligence Agent

Evidence-backed outbound prospecting and research agent built specifically for UK Primary/Secondary Schools, Multi-Academy Trusts (MATs), and Special Schools.

Unlike corporate B2B prospecting tools that depend on LinkedIn and generic job titles, this agent operates on the real mechanics of the UK education system:
1. **Statutory SEND Information Reports** (mandated under the Children & Families Act 2014) to extract the **named SENCO** and verified contact details.
2. **Ofsted Inspection Reports** to quote specific inspection findings regarding SEND provision.
3. **Department for Education (DfE) GIAS data** (URN, phase, trust, postcode, SEN roll %).
4. **Dual Outreach Generator**:
   - Empathetic, jargon-free emails for the named SENCO and Headteacher.
   - Print-ready 1-page physical letters formatted for postal delivery ("Lumpy Mail").

---

## Quick Start

### 1. Requirements
- Python 3.12+
- OpenAI API Key

### 2. Configure Environment
Copy `.env.example` to `.env` (already pre-configured with SQLite for instant local use, or point `DATABASE_URL` to the LeadGen Supabase project):

```powershell
cd C:\Apps\LeadGen\seemymind-lead-agent
```

### 3. Seed Demo Data (Optional)
To test immediately with pre-loaded UK schools and drafted SENCO outreach:

```powershell
python seed_demo_data.py
```

### 4. Start the Application
```powershell
python -m uvicorn app.main:app --reload --port 8001
```

### 5. Open the Dashboard
Navigate to: **http://127.0.0.1:8001/ui**

- **Dashboard:** View schools by phase, trust, SEN %, and pipeline stage.
- **School Detail:** Inspect Ofsted quotes, SEND reports, detected tools, and tailored outreach.
- **Key Contacts Directory:** Master list of all named SENCOs with direct emails and phone extensions.
- **Physical Letter:** Click "Print 1-Page Letter" to preview or print postal mailers formatted for A4 envelopes.
- **Prompt Config:** Customize AI prompts for your specific campaigns.
