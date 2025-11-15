import fitz  # PyMuPDF
import os
import google.generativeai as genai
import shutil
import re
import time

# --- CONFIGURATION ---

# 1. SET UP YOUR API KEY (do this in your terminal, not here)
#    Windows: set GOOGLE_API_KEY="YOUR_API_KEY"
#    macOS/Linux: export GOOGLE_API_KEY="YOUR_API_KEY"
try:
    genai.configure(api_key=os.environ["GOOGLE_API_KEY"])
except KeyError:
    print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
    print("!!! ERROR: GOOGLE_API_KEY environment variable not set.     !!!")
    print("!!! Please set your API key before running the script.        !!!")
    print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
    exit()

# 2. DEFINE YOUR FOLDER NAMES
EXTRACTION_ROOT_DIR = "extracted_questions"
SYLLABUS_ROOT_DIR = "syllabi"
SORTED_OUTPUT_DIR = "sorted_questions_by_topic"

# --- HELPER FUNCTIONS ---

def find_syllabus_file(subject_code):
    """Finds the syllabus.txt file for a given subject code."""
    subject_syllabus_folder = os.path.join(SYLLABUS_ROOT_DIR, subject_code)
    if not os.path.isdir(subject_syllabus_folder):
        return None  # No syllabus folder for this subject
    
    for filename in os.listdir(subject_syllabus_folder):
        if filename.endswith("_syllabus.txt"):
            return os.path.join(subject_syllabus_folder, filename)
    return None # No syllabus file found inside

def extract_text_from_pdf(pdf_path):
    """Extracts all text content from a PDF file."""
    try:
        doc = fitz.open(pdf_path)
        text = ""
        for page in doc:
            text += page.get_text()
        doc.close()
        return text.strip()
    except Exception as e:
        print(f"  -> Error reading PDF {pdf_path}: {e}")
        return ""

def get_topics_from_gemini(syllabus_content, question_text, subject_code):
    """
    Constructs a prompt to classify a question by MAJOR TOPIC ONLY,
    with a strict output format.
    """
    model = genai.GenerativeModel('gemini-2.5-flash')

    # Enforce the strict formatting you want: Topic_X_Name
    output_format_instruction = (
        "Output the topics as a comma-separated list. "
        "Each topic MUST be formatted as: 'Topic_<Number>_<Major Topic Name>' (e.g., 'Topic_1_The Particulate Nature of Matter'). "
        "Remove all special characters (e.g., dashes, slashes, parentheses, commas) from the topic name itself, using only spaces or underscores. "
        "If multiple topics apply, separate them with a comma and a single space (, ). "
        "If no Major Topics apply, respond with ONLY the word 'None'."
    )
    
    prompt = f"""
You are an expert examiner for Subject Code {subject_code}. Your task is to analyze an exam question and classify it against the provided official syllabus.

--- CONTEXT & TASK ---
1. You must only identify **MAJOR TOPICS** (Level 1 headings) from the syllabus. Ignore all sub-topics, details, and bullet points.
2. For each relevant Major Topic, you must include its primary number.
3. Questions may cover multiple Major Topics; identify all that apply.
--- SYLLABUS CONTEXT ---
{syllabus_content}
--- END SYLLABUS ---

--- EXAM QUESTION TO ANALYZE ---
{question_text}
--- END EXAM QUESTION ---

{output_format_instruction}
"""
    try:
        # Increased temperature for better creative classification, but keep it low for accuracy
        time.sleep(25)  # To avoid hitting rate limits
        response = model.generate_content(prompt, generation_config={"temperature": 0.2})
        return response.text.strip()
    except Exception as e:
        print(f"  -> Gemini API Error: {e}")
        return "None"
# --- MAIN SCRIPT LOGIC ---

def main():
    """
    Main function to walk through extracted questions and sort them using AI.
    """
    print("Starting AI question sorting process...")
    
    # Create the main output directory if it doesn't exist
    os.makedirs(SORTED_OUTPUT_DIR, exist_ok=True)

    # Walk through the directory structure created by your splitter script
    for subject_code_folder in os.listdir(EXTRACTION_ROOT_DIR):
        subject_path = os.path.join(EXTRACTION_ROOT_DIR, subject_code_folder)
        if not os.path.isdir(subject_path):
            continue

        print(f"\nProcessing Subject: {subject_code_folder}")

        # 1. Find and load the syllabus for this subject
        syllabus_file = find_syllabus_file(subject_code_folder)
        if not syllabus_file:
            print(f"  - WARNING: Syllabus not found for subject {subject_code_folder}. Skipping.")
            continue
        
        with open(syllabus_file, 'r', encoding='utf-8') as f:
            syllabus_text = f.read()
        print(f"  - Loaded syllabus from: {os.path.basename(syllabus_file)}")

        # 2. Loop through each paper folder within the subject folder
        for paper_name_folder in os.listdir(subject_path):
            paper_path = os.path.join(subject_path, paper_name_folder)
            if not os.path.isdir(paper_path):
                continue
            
            print(f"  - Processing Paper: {paper_name_folder}")

            # 3. Loop through each question PDF in the paper folder
            for question_filename in os.listdir(paper_path):
                if question_filename.lower().endswith('.pdf'):
                    question_filepath = os.path.join(paper_path, question_filename)
                    
                    # 4. Extract text from the question PDF
                    question_text = extract_text_from_pdf(question_filepath)
                    if not question_text:
                        print(f"    - Could not extract text from {question_filename}. Skipping.")
                        continue
                        
                    # 5. Call the AI to get topics
                    print(f"    - Analyzing {question_filename} with Gemini...")
                    topics_string = get_topics_from_gemini(syllabus_text, question_text, subject_code_folder)
                    
                    if not topics_string or topics_string.lower() == 'none':
                        print(f"    - No topics found for {question_filename}.")
                        continue

                    # 6. Parse the response and copy the file
                    topics = [topic.strip() for topic in topics_string.split(',')]
                    print(f"    - Found Topics: {topics}")
                    
                    for topic in topics:
                        # Sanitize the topic name to make it a valid folder name
                        # Removes characters like / \ : * ? " < > |
                        sanitized_topic = re.sub(r'[\\/*?:"<>|]', "", topic)
                        
                        # Create the final output path
                        topic_folder_path = os.path.join(SORTED_OUTPUT_DIR, subject_code_folder, sanitized_topic)
                        os.makedirs(topic_folder_path, exist_ok=True)
                        
                        # Create a descriptive new filename to avoid clashes
                        new_filename = f"{paper_name_folder}_{question_filename}"
                        destination_path = os.path.join(topic_folder_path, new_filename)
                        
                        # Copy the original question file to the new topic folder
                        shutil.copy(question_filepath, destination_path)
    
    print("\n--- AI sorting process complete! ---")

if __name__ == "__main__":
    main()
