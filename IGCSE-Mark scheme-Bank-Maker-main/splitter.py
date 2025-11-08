import fitz
import copy
import os
import csv
import io
import re
import itertools

# Class to split a pdf into individual questions and store them in a csv file
class Split:
    
    def __init__(self, path, crawl=True):
        self.paths = []

        if crawl:
            self.crawl(path)
        else:
            self.paths.append(path)

        path_num = len(self.paths)
        for index, path in enumerate(self.paths):
            try:
                self.reader = fitz.open(path)
            except Exception as e:
                print(f"\nError opening file {path}. Reason: {e}")
                continue

            # --- PDF PRE-PROCESSING ---
            if len(self.reader) > 0:
                self.reader.delete_page(0)
            # --- END PRE-PROCESSING ---
            self.blankPages = []
            self.questions, self.rows = [], []
            self.info = {}
            self.border = 50
            self.padding = 10
            
            self.extract_questions()

            if self.questions:
                grouped_questions = []
                last_base_num = None
                for question in self.questions:
                    # If the main number changes, it's a new question group
                    if question['base_num'] != last_base_num:
                        grouped_questions.append(question)
                        last_base_num = question['base_num']
                
                # 3. Overwrite the detailed list with our new list of main questions.
                # The rest of the script will now treat "4(a)" as the start of the entire
                # Question 4 block, and "5(a)" as the start of the next.
                self.questions = grouped_questions
            self.get_info(path)
            
            if not self.check_order():
                print(f"\nSkipping file due to error: {path}")
                continue
            
            self.compute_crop()
            self.create_debug_pdf() 
            self.trim_page()
            self.split_questions()
            self.to_csv()

            # Print progress
            print(f"\r{self.info['name']} loaded into database: {index + 1}/{path_num}", end=" ")

        print("\nFinished loading all papers into database")
        clear_duplicates()


    def crawl(self, path):
        rootdir = os.fsencode(path)

        # Split all pdfs in the root directory if it exists
        if rootdir is not None:
            if os.path.isfile(rootdir):
                self.paths.append(rootdir.decode('UTF-8'))
            elif os.path.exists(rootdir):
                for subdir, dirs, files in os.walk(rootdir):
                    for file in files:
                        filepath = (subdir + os.sep.encode('UTF-8') + file).decode('UTF-8')
                        # --- MODIFICATION: Search for "ms" (mark scheme) instead of "qp" ---
                        if filepath.endswith(".pdf") and "ms" in filepath:
                            self.paths.append(filepath)


    def make_text(self, words):
        """
        Return textstring output of get_text("words").

        Word items are sorted for reading sequence left to right,
        top to bottom.
        """
        # Group words by their rounded bottom coordinate
        line_dict = {}

        # Sort by horizontal coordinate
        for x, _, _, y, word, _, _, _ in sorted(words, key=lambda w: (round(w[1]), w[0])):
            # Appends words to list of words approximately in the same line
            line_dict.setdefault(round(y), []).append(word)

        # Join words in each line and sort lines vertically
        lines = [" ".join(line_words) for _, line_words in sorted(line_dict.items())]

        return "".join(lines).upper()

    def _is_new_format(self, page):
        """
        Checks if the page follows the new format by looking for repetition
        of "DO NOT WRITE THIS MARGIN" in the right-side margin.
        """
        # Define the search area for the "DO NOT WRITE THIS MARGIN" phrase
        # x0: 574, x1: largest x unit (end of the page), y0: 0, y1: largest y unit (page.rect.y1)
        margin_rect = fitz.Rect(574, 0, page.rect.x1, page.rect.y1)

        # Search for all occurrences of the phrase within the defined margin
        phrase = "DO NOT WRITE IN THIS MARGIN"
        found_rects = page.search_for(phrase, clip=margin_rect)
        # "Repetition" implies it appears multiple times.
        # Let's consider 1 or more occurrences as "repetition".
        return len(found_rects) >= 1


    # Locates the questions in the paper
    global x0, y0, x1, y1
    x0 = 50
    y0 = 735
    x1 = 450
    y1 = 790
    def locate_questions(self, page, page_number):
            # Determine the question number search area based on the format
            if self._is_new_format(page):
                # New format rect: x0: 0, y0: 60, x1: 60, y1: 778
                rect = fitz.Rect(0, 60, 60, 770)
            else:
                # Original format rect
                rect = fitz.Rect(x0, y0, x1, y1)

            page_dict = page.get_text("dict")

            # Extracts the text spans within the boundary
            spans_in_margin = [span for block in page_dict["blocks"] if block["type"] == 0 # text blocks
                            for line in block["lines"] # text lines
                            for span in line["spans"] # text spans
                            if fitz.Rect(span["bbox"]).intersects(rect)] # within boundary

            questions = []
            # This flexible pattern recognizes a number followed by zero or more
            # parenthesized sub-parts like (a), (i), (b)(ii), etc.
            valid_question_pattern = re.compile(r"^\s*\d+\.?\s*(\(\s*([a-z]+|[ivx]+)\s*\)\s*)*$")

            for a in spans_in_margin:
                text = a["text"].strip()
                # Use regex to find the first sequence of digits in the span's text
                match = re.search(r'\d+', text)
                
                if match and valid_question_pattern.fullmatch(text):
                    
                    # Extract the primary number (e.g., '2' from '2(b)(i)')
                    base_num_str = match.group()

                    # --- START OF FIX ---
                    # The condition for adding a question now correctly checks the previously added question's base number.
                    if (len(questions) == 0 or
                    (int(base_num_str) >= int(questions[-1]['base_num']) and
                        int(base_num_str) <= int(questions[-1]['base_num']) + 1)):

                        # We now store BOTH the full text ('question_num') and the base integer ('base_num')
                        questions.append({
                            'question_num': text,        # Store the full text like "1(a)(i)"
                            'base_num': base_num_str,  # Store just the base number "1"
                            'bbox': [round(n) for n in a["bbox"]],
                            'page': page_number
                        })
                    # --- END OF FIX ---
            return questions

        # Flag blank pages
    def flag_blank(self, page):
        # List of words to search for
        wordList = ["GENERIC MARKING PRINCIPLE",
                    "Science-Specific Marking Principles",
                    "Calculation specific guidance",
                    ]
        special_phrases = {
            "Qualitative analysis notes": 13.0 # We use a dict to easily add more special cases later
        }

        for word in wordList:
            if page.search_for(word):
                return True

        # Check if the title version (without a period) exists on the page.
        title_version_exists = page.search_for("Qualitative analysis notes")

        # Check if the sentence version (with a period) exists on the page.
        sentence_version_exists = page.search_for("Qualitative analysis notes.")

        # The new rule:
        # Flag the page ONLY IF the title version is found AND the sentence version is NOT found.
        # This means if "Qualitative analysis notes." is present, it's a question page and we do NOT flag it.
        if title_version_exists and not sentence_version_exists:
            return True

        # --- Step 3: If no conditions were met, the page is a valid question page ---
        return False




    # Extracts the location of the questions in the paper
    def extract_questions(self):
        questions = []
        for page_number, content in enumerate(self.reader):

            if not (self.flag_blank(content) or page_number == 0):
                # Adds the page of the question to the question object
                self.questions += self.locate_questions(content, page_number)

            else:
                self.blankPages.append(page_number)

    # Gets the name and info of the paper from the filename
    def get_info(self, path):
        # Gets the info from the filename
        temp_info = path[max([path.rfind(char) for char in ['\\', '/']]) + 1: -4].upper().split('_')

        # Stores the info in a dictionary
        self.info = {
            "subject_code": temp_info[0],
            "year": f"20{temp_info[1][1:]}",
            "season": temp_info[1][0],
            "paper": temp_info[3][0],
            "variant": temp_info[3][1:],
            "name": f"{temp_info[0]}_{temp_info[1]}_{temp_info[3]}"}
        
    def compute_crop(self):
        if not self.questions: return

        for index, question in enumerate(self.questions):
            # Initialize the area for this question
            self.questions[index]["questionArea"] = []

            # Get info for the start of the current question block
            current_q_info = question

            # Determine the end boundary for this question block
            if index < (len(self.questions) - 1):
                next_q_info = self.questions[index + 1]
            else:
                # This is the last question in the PDF. It should end at the far edge of its page.
                last_page_num = len(self.reader) - 1
                # In the inverted coordinate system, the far "right" edge is the maximum Y value (page height).
                end_y_coord = self.reader[last_page_num].rect.height
                next_q_info = {"bbox": [0, end_y_coord, 0, end_y_coord], "page": last_page_num}

            start_page = current_q_info["page"]
            end_page = next_q_info["page"]

            # Get the horizontal boundaries (in landscape view) from the y-coordinates of the bboxes
            # In landscape PDFs, Y coordinates represent horizontal position
            y_start_boundary = current_q_info["bbox"][1]
            y_end_boundary = next_q_info["bbox"][1]

            # --- REVISED LOGIC ---

            # Case 1: The entire question block is on a single page
            if start_page == end_page:
                self.questions[index]["questionArea"].append({
                    "y_coord": [y_start_boundary, y_end_boundary], # From this question to the next
                    "page_number": start_page
                })
                continue # Go to the next question in the loop

            # Case 2: The question block spans multiple pages
            else:
                # Part 1: The first page of the question block
                # Crop from the question number to the far right edge of the page.
                page_end_y = self.reader[start_page].rect.height
                self.questions[index]["questionArea"].append({
                    "y_coord": [y_start_boundary, page_end_y],
                    "page_number": start_page
                })

                # Part 2: Any "middle" pages that are fully covered by the question
                for page_num in range(start_page + 1, end_page):
                    full_page_y_end = self.reader[page_num].rect.height
                    self.questions[index]["questionArea"].append({
                        "y_coord": [0, full_page_y_end], # The entire page width
                        "page_number": page_num
                    })

                # Part 3: The last page of the question block
                # Crop from the far left edge of the page to the start of the next question.
                self.questions[index]["questionArea"].append({
                    "y_coord": [0, y_end_boundary],
                    "page_number": end_page
                })

    # Removes excess space where no text is present
    def trim_page(self):
        # Pre-load page data to avoid repeated calls
        page_texts = [self.reader[page].get_text("dict") for page in range(len(self.reader))]
        page_drawings = [self.reader[page].get_drawings() for page in range(len(self.reader))]

        for question in self.questions:
            for area in question["questionArea"]:
                page_num = area["page_number"]
                page = self.reader[page_num]

                # FIXED: Due to coordinate inversion in landscape PDFs:
                # y_coord values should be used as X parameters in Rect
                # We create a vertical slice (in PDF coordinates) from y_coord values
                y0 = min(area["y_coord"])
                y1 = max(area["y_coord"])
                # SWAPPED: Use y_coord as X, full page height as Y range
                horizontal_slice_rect = fitz.Rect(y0, 0, y1, page.rect.height)

                # Find all content bboxes that are inside this slice
                content_bboxes = []
                # Find text
                for block in page_texts[page_num]["blocks"]:
                    if block["type"] == 0 and fitz.Rect(block["bbox"]).intersects(horizontal_slice_rect):
                        content_bboxes.append(fitz.Rect(block["bbox"]))
                # Find drawings
                for drawing in page_drawings[page_num]:
                    drawing_rect = fitz.Rect(drawing["rect"])
                    if drawing_rect.intersects(horizontal_slice_rect):
                        content_bboxes.append(drawing_rect)

                # Calculate the Y boundaries (which represent vertical trim in visual landscape)
                if not content_bboxes:
                    # If no content, use the full page height as a fallback
                    area["vertical_trim"] = [0, page.rect.height]
                    continue

                # Find the tightest Y boundaries
                min_y = min(bbox.y0 for bbox in content_bboxes) - self.padding
                max_y = max(bbox.y1 for bbox in content_bboxes) + self.padding
                
                # Store the calculated Y trim coordinates
                area["vertical_trim"] = [
                    max(0, min_y),
                    min(page.rect.height, max_y)
                ]
                
    # Splits the questions into individual pdfs
    def split_questions(self):
        for index, question in enumerate(self.questions):
            q_num_str = question['base_num']
            filename = f"questions{os.sep}{self.info['subject_code']}{os.sep}{self.info['year']}{os.sep}{self.info['name']}-MS-{q_num_str}.pdf"
            output = fitz.open()
            text = ""

            for area in question.get("questionArea", []):
                source_page = self.reader[area["page_number"]]
                
                # FIXED: Get the Y bounds (vertical trim in visual landscape) from vertical_trim
                vertical_bounds = area.get("vertical_trim", [0, source_page.rect.height])
                y_crop_start = vertical_bounds[0]
                y_crop_end = vertical_bounds[1]
                
                # Get the X bounds (horizontal extent in visual landscape) from y_coord
                # (Remember: y_coord values represent horizontal position in landscape)
                x_start = min(area["y_coord"])
                x_end = max(area["y_coord"])
                
                # CRITICAL FIX: Due to coordinate inversion in landscape PDFs,
                # we must SWAP X and Y when constructing the Rect
                # Use y_coord (stored as x_start/x_end) as X parameters
                # Use vertical_trim (stored as y_crop_start/y_crop_end) as Y parameters
                cropbox = fitz.Rect(x_start, y_crop_start, x_end, y_crop_end)
                
                if cropbox.is_empty or cropbox.is_infinite:
                    print(f"\n--- DEBUG: Skipping invalid crop area for question '{question['question_num']}' ---")
                    print(f"    Cropbox: {cropbox}")
                    print(f"    x_start={x_start}, y_crop_start={y_crop_start}, x_end={x_end}, y_crop_end={y_crop_end}")
                    continue

                # The output page is a new, blank canvas matching the cropbox dimensions
                outbox = fitz.Rect(0, 0, cropbox.width, cropbox.height)
                outPage = output.new_page(-1, width=cropbox.width, height=cropbox.height)
                
                outPage.show_pdf_page(outbox, self.reader, area["page_number"], clip=cropbox)
                
                # Text extraction with the correct cropbox
                text += self.make_text(self.reader[area["page_number"]].get_text("words", clip=cropbox))

            if len(output) > 0:
                os.makedirs(os.path.dirname(filename), exist_ok=True)
                try:
                    output.save(filename, garbage=4, deflate=True)
                    self.rows.append({
                        "subject_code": self.info['subject_code'], "year": self.info['year'],
                        "season": self.info['season'], "paper": self.info['paper'],
                        "variant": self.info['variant'], "question": question['base_num'],
                        "filename": filename, "text": text
                    })
                except Exception as e:
                    print(f"Error: Could not write to file {filename}. Reason: {e}")

    def to_csv(self):

        headers = ["subject_code", "year", "season", "paper", "variant", "question", "filename", "text"]

        isExist = os.path.exists(f"questions{os.sep}database.csv")
        with open(f"questions{os.sep}database.csv", "a", newline='', encoding="utf-8") as csvfile:
            cwriter = csv.DictWriter(csvfile, fieldnames=headers)
            if not isExist:
                cwriter.writeheader()
            cwriter.writerows(self.rows)


    # Function to check if the question numbers are in numerical order and provide visual debug on error
    def check_order(self):
        if len(self.questions) == 0:
            print("\nError: No questions found in paper.")

            # --- NEW DEBUG FEATURE for "No Questions Found" ---
            try:
                # Ensure the document has pages to draw on
                if len(self.reader) > 0:
                    last_page_num = len(self.reader) - 1
                    page = self.reader.load_page(last_page_num)

                    # Determine the search rectangle for the last page
                    if self._is_new_format(page):
                        search_rect = fitz.Rect(0, 60, 60, 770)
                    else:
                        search_rect = fitz.Rect(x0, y0, x1, y1)

                    # Draw the green search area
                    page.draw_rect(search_rect, color=(0, 1, 0), width=1.5)

                    # Save the image with a unique, descriptive name
                    debug_filename = f"DEBUG_NO_QUESTIONS_FOUND_{self.info['name']}.png"
                    pix = page.get_pixmap(dpi=150)
                    pix.save(debug_filename)

                    # Inform the user
                    print("\n[+] A visual debug image of the LAST page has been saved!")
                    print(f"    Filename: '{debug_filename}'")
                    print("    - The Green box shows the area where the script was looking for numbers.")
                    print("    - Use this to check if the layout is unexpected or if the text is outside the search area.")
                else:
                    print("[!] Document has no pages, cannot generate debug image.")

            except Exception as e:
                print(f"\n[!] Could not generate debug image for 'No Questions Found' error. Reason: {e}")
            # --- END NEW DEBUG FEATURE ---

            return False # Stop processing this file
        
        priorQuestion = self.questions[0]

        for question in self.questions[1:]:
            current_num = int(question["base_num"])
            prior_num = int(priorQuestion["base_num"])

            is_in_order = (current_num >= prior_num and current_num <= prior_num + 1)

            if not is_in_order:
                # (The existing visual debugger for sequence errors remains unchanged)
                print("\n\n" + "="*50)
                print("--- DEBUG: Mark Scheme Order Error Detected ---")
                print(f"Error: Found question '{question['question_num']}' (base {current_num}) after '{priorQuestion['question_num']}' (base {prior_num}), which breaks the sequence.")
                print(f"Rule Violated: A number's base must be the same as the previous one, or exactly one greater.")
                
                try:
                    problem_page_num = question['page']
                    page = self.reader.load_page(problem_page_num)

                    if self._is_new_format(page):
                        search_rect = fitz.Rect(0, 60, 60, 770)
                    else:
                        search_rect = fitz.Rect(x0, y0, x1, y1)
                    page.draw_rect(search_rect, color=(0, 1, 0), width=1.5)

                    for q in self.questions:
                        if q['page'] == problem_page_num:
                            page.draw_rect(q['bbox'], color=(0, 0, 1), width=1.5)

                    if priorQuestion['page'] == problem_page_num:
                        page.draw_rect(priorQuestion['bbox'], color=(1, 1, 0), width=2)

                    page.draw_rect(question['bbox'], color=(1, 0, 0), width=2)

                    debug_filename = f"DEBUG_ORDER_ERROR_{self.info['name']}_PAGE_{problem_page_num}.png"
                    pix = page.get_pixmap(dpi=150)
                    pix.save(debug_filename)
                    
                    print("\n[+] A visual debug image has been saved!")
                    print(f"    Filename: '{debug_filename}'")
                    print("    - Green box: The exact area where the script is searching for numbers.")
                    print("    - Blue boxes: ALL numbers detected on this page.")
                    print("    - Yellow box: The last correct number.")
                    print("    - Red box: The number that broke the sequence.")

                except Exception as e:
                    print(f"\n[!] Could not generate debug image. Reason: {e}")

                print("="*50 + "\n")
                return False

            priorQuestion = question 

        return True
    
    def create_debug_pdf(self):
            """
            Creates a new PDF file with visual debugging overlays.
            - Draws blue boxes around all detected question numbers.
            - Draws green boxes showing the calculated crop areas.
            """
            if not self.questions:
                print("[Debug] No questions found, skipping debug PDF creation.")
                return

            try:
                # Create a safe copy of the document to draw on.
                # We will save this to a new file, leaving self.reader untouched.
                debug_doc = fitz.open(self.paths[0]) # Re-opening the path ensures a clean copy
                if len(debug_doc) > 0:
                    debug_doc.delete_page(0)

                # --- 1. Draw GREEN boxes for the CROP AREAS ---
                for question in self.questions:
                    for area in question.get("questionArea", []):
                        page_num = area["page_number"]
                        if page_num < len(debug_doc):
                            page = debug_doc.load_page(page_num)
                            
                            # FIXED: Use swapped coordinates for landscape PDFs
                            # y_coord values should be used as X in Rect (horizontal position in visual landscape)
                            x_start = min(area["y_coord"])
                            x_end = max(area["y_coord"])
                            # Use full page height as Y range to show the full vertical extent
                            crop_rect = fitz.Rect(x_start, 0, x_end, page.rect.height)
                            
                            # Draw a semi-transparent green rectangle
                            page.draw_rect(crop_rect, color=(0, 1, 0), fill=(0, 1, 0), fill_opacity=0.2, width=1.5)

                # --- 2. Draw BLUE boxes for the detected QUESTION NUMBERS ---
                for question in self.questions:
                    page_num = question["page"]
                    if page_num < len(debug_doc):
                        page = debug_doc.load_page(page_num)
                        bbox_rect = fitz.Rect(question["bbox"])
                        page.draw_rect(bbox_rect, color=(0, 0, 1), width=1.5)

                # --- 3. Save the new debug PDF ---
                debug_filename = f"DEBUG_CROP_AREAS_{self.info['name']}.pdf"
                debug_doc.save(debug_filename, garbage=4, deflate=True)
                print(f"\n[+] A visual debug PDF has been saved: '{debug_filename}'")

            except Exception as e:
                print(f"\n[!] Could not create debug PDF. Reason: {e}")


# Removes duplicate entries from the csv based on filename column
def clear_duplicates():
    if (os.path.exists(f"questions{os.sep}database.csv")):
        # Open the csv file and read the lines
        with open(f"questions{os.sep}database.csv", encoding="utf-8") as f:
            lines = f.readlines()
        # Get the index of the filename column from the header line
        filename_index = lines[0].split(",").index("filename")
        # Create a set to store the filenames that have been seen
        seen_filenames = set()
        # Create a list to store the lines that are not duplicates
        new_lines = []
        # Loop through the lines and check the filename column
        for line in lines:
            # Get the filename from the line
            filename = line.split(",")[filename_index]
            # If the filename is not in the seen set, add it to the new lines and the seen set
            if filename not in seen_filenames:
                new_lines.append(line)
                seen_filenames.add(filename)
        # Write the new lines to the csv file
        with open(f"questions{os.sep}database.csv", 'w', encoding="utf-8") as t:
            t.writelines(new_lines)