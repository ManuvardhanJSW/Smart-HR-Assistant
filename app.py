import streamlit as st
import requests
import os
import json
import re
from dotenv import load_dotenv
import fitz  # PyMuPDF
import pandas as pd
from docx import Document  # NEW import for Word support

def extract_pdf_text(uploaded_file):
    text = ""
    with fitz.open(stream=uploaded_file.read(), filetype="pdf") as doc:
        for page in doc:
            text += page.get_text()
    return text

def extract_docx_text(uploaded_file):
    try:
        doc = Document(uploaded_file)
        return "\n".join([para.text for para in doc.paragraphs])
    except Exception as e:
        raise Exception(f"Error reading Word document: {str(e)}")

def extract_text(uploaded_file):
    if uploaded_file.name.lower().endswith(".pdf"):
        return extract_pdf_text(uploaded_file)
    elif uploaded_file.name.lower().endswith(".docx"):
        return extract_docx_text(uploaded_file)
    else:
        raise Exception("Unsupported file format")

def get_gemini_response(prompt, api_key):
    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
    headers = {
        "Content-Type": "application/json",
        "X-goog-api-key": api_key
    }
    body = {
        "contents": [{"parts": [{"text": prompt}]}]
    }
    response = requests.post(url, headers=headers, json=body)
    response.raise_for_status()
    return response.json()["candidates"][0]["content"]["parts"][0]["text"]

def prepare_prompt(resume_text, jd_text, weights, remark_tone):
    tone_instruction = {
        "Professional": "Use a neutral and formal tone.",
        "Critical": "Be sharply evaluative, pointing out weaknesses clearly.",
        "Blunt": "Give a direct, no-nonsense assessment without sugarcoating."
    }

    return f"""
You are acting as a professional HR Manager at JSW Paints.

Evaluate the following resume against the job description.

Scoring Logic:
1. Experience Match - {weights['experience']}%
2. Skill Match - {weights['skills']}%
3. Education Quality - {weights['education']}%
4. Industry relevance - {weights['industry']}%
5. Policy Compliance - {weights['policy']}%


- {tone_instruction.get(remark_tone, "Use a professional tone.")}

Return ONLY JSON:
{{
  "name": "Full name",
  "score": Final score out of 100,
  "education": "Degree and college",
  "experience": "Total years of experience",
  "skills_matched": ["skill1", "skill2"],
  "remark": "30-word summary on fitment and verdict"
}}

Resume:
{resume_text}

Job Description:
{jd_text}
"""

def extract_comparison_data(jd_text):
    exp_range = re.search(r"(\d+)\s*(?:to|–|-)\s*(\d+)\s*years", jd_text, re.IGNORECASE)
    if exp_range:
        experience = f"{exp_range.group(1)} to {exp_range.group(2)} years"
    else:
        exp_match = re.search(r"(\d+\+?\s*years?)", jd_text, re.IGNORECASE)
        experience = exp_match.group(1) if exp_match else "Not specified"

    edu_match = re.search(r"qualification\s*[:\-]?\s*([^\n,]+)", jd_text, re.IGNORECASE)
    qualification = edu_match.group(1).strip() if edu_match else "Not specified"

    common_skills = [
        "python", "sql", "excel", "tableau", "power bi", "machine learning",
        "marketing", "branding", "data analysis", "communication", "leadership",
        "sales", "negotiation", "strategy", "presentation", "problem-solving"
    ]
    jd_lower = jd_text.lower()
    skills_found = [skill for skill in common_skills if skill in jd_lower]
    skills = ", ".join(skills_found) if skills_found else "Not specified"

    return experience, skills, qualification

def parse_json_response(text):
    try:
        json_str = re.search(r"\{.*\}", text, re.DOTALL).group()
        return json.loads(json_str)
    except Exception as e:
        raise ValueError(f"❌ Could not parse JSON from Gemini:\n{text[:500]}...")

def highlight_score(val):
    try:
        val = int(val)
        if val >= 80:
            return 'background-color: lightgreen'
        elif val >= 60:
            return 'background-color: khaki'
        else:
            return 'background-color: lightcoral'
    except:
        return ''

def main():
    load_dotenv()
    api_key = os.getenv("GOOGLE_API_KEY")

    st.title("📄 THE HRminator 💥🤖")

    jd = st.text_area("📌 Job Description", placeholder="Paste the job description here...")

    st.markdown("### 🎯 Scoring Criteria Weights (Total must be 100%)")
    col1, col2, col3 = st.columns(3)
    with col1:
        experience_weight = st.number_input("Experience Match %", min_value=0, max_value=100, value=40)
        skills_weight = st.number_input("Skill Match %", min_value=0, max_value=100, value=20)
    with col2:
        education_weight = st.number_input("Education Quality %", min_value=0, max_value=100, value=10)
        industry_weight = st.number_input("Industry Relevance %", min_value=0, max_value=100, value=20)
    with col3:
        policy_weight = st.number_input("Policy Compliance %", min_value=0, max_value=100, value=10)

    st.markdown("### 💬 Remark Style")
    remark_tone = st.selectbox(
        "Choose AI Remark Tone",
        ["Professional", "Critical", "Blunt"]
    )

    total = experience_weight + skills_weight + education_weight + industry_weight + policy_weight
    if total != 100:
        st.error(f"Total is {total}%. Adjust to equal 100.")
        return

    weights = {
        "experience": experience_weight,
        "skills": skills_weight,
        "education": education_weight,
        "industry": industry_weight,
        "policy": policy_weight
    }

    uploaded_files = st.file_uploader("📎 Upload Resumes (PDF or Word)", type=["pdf", "docx"], accept_multiple_files=True)

    if "results" not in st.session_state:
        st.session_state.results = []

    if st.button("Analyze Resumes"):
        if not jd or not uploaded_files:
            st.warning("Please provide both Job Description and Resumes.")
            return

        st.session_state.results = []

        with st.spinner("🔍 Analyzing resumes..."):
            for file in uploaded_files:
                try:
                    resume_text = extract_text(file)
                    prompt = prepare_prompt(resume_text, jd, weights, remark_tone)
                    response_text = get_gemini_response(prompt, api_key)
                    response_json = parse_json_response(response_text)

                    st.session_state.results.append({
                        "filename": file.name,
                        "name": response_json.get("name", "N/A"),
                        "score": int(response_json.get("score", 0)),
                        "education": response_json.get("education", "N/A"),
                        "experience": response_json.get("experience", "N/A"),
                        "skills_matched": response_json.get("skills_matched", []),
                        "remark": response_json.get("remark", "N/A"),
                    })
                except Exception as e:
                    st.error(f"{file.name} ❌ Error: {e}")

    if st.session_state.results:
        st.markdown("### 📌 Job Description Summary")
        exp_required, skills_required, qualification = extract_comparison_data(jd)
        st.info(f"**Expected Experience:** {exp_required}\n\n**Required Education:** {qualification}\n\n**Key Skills Required:** {skills_required}")

        df = pd.DataFrame(st.session_state.results)
        df["skills_matched"] = df["skills_matched"].apply(lambda x: ", ".join(x))
        df.sort_values(by="score", ascending=False, inplace=True)

        accepted_df = df[df['score'] >= 60].reset_index(drop=True)
        rejected_df = df[df['score'] < 60].reset_index(drop=True)

        st.markdown("### ✅ First Round: Accepted Candidates")
        st.dataframe(accepted_df.style.applymap(highlight_score, subset=["score"]), use_container_width=True)

        st.markdown("### ❌ First Round: Rejected Candidates")
        st.dataframe(rejected_df.style.applymap(highlight_score, subset=["score"]), use_container_width=True)

if __name__ == "__main__":
    main()
