import os
# We import the other scripts as modules to access their functions/classes
import splitter
import sorting
import MockBuilder

def get_user_choice(prompt):
    """A helper function to get a clean 'y' or 'n' from the user."""
    while True:
        choice = input(prompt).lower().strip()
        if choice in ['y', 'n']:
            return choice
        print("!!! Invalid input. Please enter 'y' or 'n'.")

def main_workflow():
    """Controls the main execution flow of the entire process."""
    
    print("--- Cambridge Question Bank Toolkit ---")

    # --- Step 1: Run the PDF Splitter ---
    if get_user_choice("\nDo you want to extract questions from new PDFs in the 'papers' folder? (y/n): ") == 'y':
        papers_directory = "papers"
        # Check if the source folder exists before trying to run
        if os.path.isdir(papers_directory):
            print("\n>>> Running the PDF Splitter...")
            # We call the Split class from the imported splitter module
            splitter.Split(papers_directory)
            print(">>> PDF Splitting Complete.\n")
        else:
            print(f"!!! ERROR: The '{papers_directory}' folder was not found. Please create it and add PDFs to process.")

    # --- Step 2: Run the AI Sorter ---
    if get_user_choice("Do you want to sort the extracted questions into topics using AI? (y/n): ") == 'y':
        extraction_directory = "extracted_questions"
        # Check if the splitter has been run and its output folder exists
        if os.path.isdir(extraction_directory):
            print("\n>>> Running the AI Sorter (this may take a while)...")
            # We call the main() function from the imported sorting module
            sorting.main()
            print(">>> AI Sorting Complete.\n")
        else:
            print(f"!!! ERROR: The '{extraction_directory}' folder was not found. Please run the splitter first.")

    # --- Step 3: Run the Mock Paper Builder ---
    if get_user_choice("Do you want to build a mock paper from the sorted questions? (y/n): ") == 'y':
        sorted_directory = "sorted_questions_by_topic"
        # Check if the sorter has been run and its output folder exists
        if os.path.isdir(sorted_directory):
            print("\n>>> Starting the Mock Paper Builder...")
            # We call the main() function from the imported MockBuilder module
            MockBuilder.main()
            print(">>> Mock Paper Builder Finished.\n")
        else:
            print(f"!!! ERROR: The '{sorted_directory}' folder was not found. Please run the AI sorter first.")

# --- This ensures the script runs when you execute it directly ---
if __name__ == "__main__":
    main_workflow()
    input("--- All tasks finished. Press Enter to exit. ---")