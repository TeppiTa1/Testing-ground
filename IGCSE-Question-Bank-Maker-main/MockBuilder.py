import fitz  # PyMuPDF
import os

# --- CONFIGURATION ---
SORTED_ROOT_DIR = "sorted_questions_by_topic"

# --- HELPER FUNCTION for USER INTERACTION ---

def select_from_list(options, prompt_text):
    """
    Displays a numbered list of options to the user and returns the selected option.
    Handles input validation.

    Args:
        options (list): A list of strings to be displayed as choices.
        prompt_text (str): The question to ask the user.

    Returns:
        str: The selected option from the list, or None if no choice is made.
    """
    if not options:
        print("No options available.")
        return None
    while True:
        print(f"\n{prompt_text}")
        # Use enumerate to display a numbered list starting from 1
        for i, option in enumerate(options, 1):
            print(f"- {option} (press {i})")

        try:
            choice = input("Your choice: ")
            choice_index = int(choice) - 1

            # Validate that the choice is within the valid range
            if 0 <= choice_index < len(options):
                selected_option = options[choice_index]
                print(f"-> You selected: {selected_option}")
                return selected_option
            else:
                print("!!! Invalid number. Please try again.")
        except ValueError:
            print("!!! Please enter a valid number.")

def assemble_pdf(question_paths, output_filename):
    """
    Concatenates a list of PDF files into a single new PDF document.

    Args:
        question_paths (list): A list of full paths to the question PDFs to be merged.
        output_filename (str): The name of the final output file.
    """
    if not question_paths:
        print("No questions were selected. Mock paper will not be created.")
        return

    print(f"\nAssembling {len(question_paths)} questions into '{output_filename}'...")
    final_doc = None
    try:
        # Create a new, blank document to be our mock paper
        final_doc = fitz.open()

        # Loop through each chosen question's file path
        for path in question_paths:
            snippet_doc = fitz.open(path)
            # Insert all pages from the snippet into the final document
            final_doc.insert_pdf(snippet_doc)
            snippet_doc.close()

        # Save the final, assembled document
        final_doc.save(output_filename, garbage=4, deflate=True)
        print("--- Mock paper created successfully! ---")

    except Exception as e:
        print(f"!!! An error occurred during PDF assembly: {e}")
    finally:
        if final_doc:
            final_doc.close()
        
# --- MAIN SCRIPT LOGIC ---

def main():
    """
    Main function to guide the user through creating a mock paper.
    """
    print("--- Mock Paper Assembler ---")
    
    # Check if the main sorted directory exists
    if not os.path.isdir(SORTED_ROOT_DIR):
        print(f"Error: The directory '{SORTED_ROOT_DIR}' was not found.")
        print("Please run the splitter and AI sorter scripts first.")
        return

    # --- Step 1: Select a Subject ---
    subjects = sorted([d for d in os.listdir(SORTED_ROOT_DIR) if os.path.isdir(os.path.join(SORTED_ROOT_DIR, d))])
    chosen_subject = select_from_list(subjects, "Please choose the subject you want to create a mock paper for:")
    if not chosen_subject:
        return # Exit if no subject is chosen

    subject_path = os.path.join(SORTED_ROOT_DIR, chosen_subject)

    # --- Step 2: Select a Topic ---
    topics = sorted([d for d in os.listdir(subject_path) if os.path.isdir(os.path.join(subject_path, d))])
    chosen_topic = select_from_list(topics, "Please choose the topic you want to select questions from:")
    if not chosen_topic:
        return # Exit if no topic is chosen

    topic_path = os.path.join(subject_path, chosen_topic)
    
    # --- Step 3: Select Questions in a Loop ---
    chosen_question_paths = []
    
    while True:
        # Get a list of available question PDFs in the chosen topic folder
        question_files = sorted([f for f in os.listdir(topic_path) if f.lower().endswith('.pdf')])
        
        if not question_files:
            print(f"No questions found in the topic '{chosen_topic}'.")
            break

        # Let the user select a question from the list
        chosen_question_file = select_from_list(question_files, "Please select a question to add:")
        
        if chosen_question_file:
            # Construct the full path and add it to our list
            full_path = os.path.join(topic_path, chosen_question_file)
            chosen_question_paths.append(full_path)
            print(f"'{chosen_question_file}' added to your mock paper.")

        # Ask the user if they want to add another question
        while True:
            another = input("\nAdd another question from this topic? (y/n): ").lower()
            if another in ['y', 'n']:
                break
            print("!!! Invalid input. Please enter 'y' or 'n'.")
        
        if another == 'n':
            break # Exit the main question selection loop
    
    # --- Step 4: Assemble and Save the Final PDF ---
    if chosen_question_paths:
        output_filename = f"Mock_paper_{chosen_subject}_1.pdf"
        assemble_pdf(chosen_question_paths, output_filename)

if __name__ == "__main__":
    main()
