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

        # If crawl is true, crawl the directory and subdirectories for all pdfs
        if crawl:
            self.crawl(path)
        else:
            self.paths.append(path)

        path_num = len(self.paths)
        for index, path in enumerate(self.paths):
            self.reader = fitz.open(path)
            self.questions, self.rows = [], []
            self.blankPages = []
            self.info = {}
            self.border = 50
            self.padding = 10
            self.extract_questions()
            if not self.check_order():
                print(path, "Error loading all questions")
                continue
            self.compute_crop()
            self.trim_page()
            self.get_info(path)
            self.split_questions()
            self.to_csv()

            # Print progress
            print(f"\r{self.info['name']} loaded into database: {index + 1}/{path_num}", end=" ")

        print("\nFinished loading all papers into database")
        # Clear duplicates from the csv file
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
                        if filepath.endswith(".pdf") and "qp" in filepath:
                            self.paths.append(filepath)


    def make_text(self, words):
        """Return textstring output of get_text("words").

        Word items are sorted for reading sequence left to right,
        top to bottom.
        """
        # Group words by their rounded bottom coordinate
        line_dict = {}

        # Sort by horizontal coordinate
        for x, _, _, y, word, _, _, _ in sorted(words):
            # Appends words to list of words approximately in the same line
            line_dict.setdefault(round(y, 1), []).append(word)
        
        # Join words in each line and sort lines vertically
        lines = ["".join(words) for _, words in sorted(line_dict.items())]

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
    def locate_questions(self, page, page_number):
        # Determine the question number search area based on the format
        if self._is_new_format(page):
            print("\n Identified new format!")
            # New format rect: x0: 0, y0: 60, x1: 60, y1: 778
            rect = fitz.Rect(0, 60, 60, 770)
        else:
            # Original format rect
            rect = fitz.Rect(0, 50, 60, page.rect.y1)

        page_dict = page.get_text("dict")

        # Extracts the bold text within the boundary
        bold_spans = [span for block in page_dict["blocks"] if block["type"] == 0 # text blocks
                        for line in block["lines"] # text lines
                        for span in line["spans"] # text spans
                        #if (span["flags"] & 2**4)# bold text
                        if fitz.Rect(span["bbox"]).intersects(rect)] # within boundary

        questions = []
        valid_question_pattern = re.compile(r"^\s*\d+\.?\s*(\(\s*[a-z]\s*\))?(\(\s*[ivx]+\s*\))?\s*$")

        for a in bold_spans:
            # Use regex to find the first sequence of digits in the span's text
            match = re.search(r'\d+', a["text"])
            text = a["text"].strip()
            # We now apply a refined 3-part filter:
            # 1. A number must exist in the span.
            # 2. The number must be short (to filter out years).
            # 3. The span must NOT contain two or more consecutive letters (to filter out "Test", "FA", etc., while allowing "(a)", "(i)").
            if valid_question_pattern.fullmatch(text):
                
                # Now that we have a valid candidate, apply the sequential logic
                current_num_str = match.group()
                if (len(questions) == 0 
                        or int(current_num_str) == (int(questions[-1]['question_num']) + 1)):
                    
                    questions.append({
                        'question_num': current_num_str, 
                        'bbox': [round(n) for n in a["bbox"]], 
                        'page': page_number
                    })




        #for a in bold_spans:
            #if (any(char.isdigit() for char in a["text"]) 
                #and (len(questions) == 0 
                    #or int(re.search(r'\d+', a["text"]).group()) == (int(questions[-1]['question_num']) + 1))):
                #questions += [{'question_num': re.search(r'\d+', a["text"]).group(), 
                                #'bbox': [round(n) for n in a["bbox"]], 
                                #'page': page_number} ]

        return questions

    # Flag blank pages    
    def flag_blank(self, page):
        # List of words to search for
        wordList = ["BLANK PAGE", 
                    "ADDITIONAL PAGE", 
                    "Mathematical Formulae",
                    "TURN PAGE FOR QUESTION", 
                    "printed on the next page",
                    "The Periodic Table of Elements",
                    "starts on the next page.",
                    "Note for use in qualitative analysis",
                    "Important values, constants and standards"
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
        dimensions = {"height": self.reader[0].rect.y1, "width": self.reader[0].rect.x1}

        for index, question in enumerate(self.questions):
            
            # Stores the area of the questions
            self.questions[index]["questionArea"] = []

            # Stores the next question if it exists else stores the last page of the paper
            if index < (len(self.questions) - 1):
                next_question = self.questions[index + 1]
            else:
                next_question = {"bbox": [0, 0, 0, 0], "page": len(self.reader)}
            
            offset = 0
            
            while (question["page"] + offset) <= next_question["page"]:
                y_coord = []

                if not ((question["page"] + offset) in self.blankPages):

                    y_coord = [question["bbox"][1] - self.padding if offset == 0 else self.border,
                                next_question["bbox"][1] - self.padding if (question["page"] + offset) == next_question["page"] 
                                    else dimensions["height"] - self.border]

                    if not (next_question["bbox"][1] < 75 and (question["page"] + offset) == next_question["page"]):
                        self.questions[index]["questionArea"].append({"y_coord": y_coord, "page_number": question["page"] + offset})

                offset += 1

    # Removes excess space where no text is present
    def trim_page(self):
        text = [self.reader[page].get_text("dict") for page in range(len(self.reader))]
        drawings = [self.reader[page].get_drawings() for page in range(len(self.reader))]
        for question in self.questions:
            for area in question["questionArea"]:
                page = self.reader[area["page_number"]]
                rect = fitz.Rect(0, area["y_coord"][0], page.rect.x1, area["y_coord"][1])
                regiontext = [block for block in text[area["page_number"]]["blocks"]
                                                    if fitz.Rect(block["bbox"]).intersects(rect)]
                regiondrawing = [box["rect"] for box in drawings[area["page_number"]]
                                    if box["stroke_opacity"] != None
                                        and (fitz.Rect(box["rect"]) in rect)]
                
                try:
                    proposedy = [min([x["bbox"][1] for x in regiontext] + [x.y1 for x in regiondrawing]) - self.padding,
                                    max([x["bbox"][3] for x in regiontext] + [x.y1 for x in regiondrawing]) + self.padding]
                except:
                    return
                area["y_coord"] = [max(area["y_coord"][0], proposedy[0]), min(area["y_coord"][1], proposedy[1])]
                
    # Splits the questions into individual pdfs
    def split_questions(self):

        for index, question in enumerate(self.questions):

            filename = f"questions{os.sep}{self.info['subject_code']}{os.sep}{self.info['year']}{os.sep}{self.info['name']}-Q{question['question_num']}.pdf"
            output = fitz.open()
            text = ""


            for area in question["questionArea"]:
                
                source_page = self.reader[area["page_number"]]

                # Check if the page uses the new format to apply custom margins
                if self._is_new_format(source_page):
                    # NEW FORMAT: Define a cropbox with margins
                    crop_x0 = 25
                    crop_x1 = source_page.rect.width - 25
                    crop_y0 = area["y_coord"][0] + 9
                    crop_y1 = area["y_coord"][1] - 2
                    cropbox = fitz.Rect(crop_x0, crop_y0, crop_x1, crop_y1)
                else:
                    # OLD FORMAT: Use the full width and original vertical crop
                    cropbox = fitz.Rect(0, area["y_coord"][0], source_page.rect.width, area["y_coord"][1])

                # The outbox (destination rectangle) must match the dimensions of the cropbox
                outbox = fitz.Rect(0, 0, cropbox.width, cropbox.height)

                # Creates a new page with dimensions matching our final cropped area
                outPage = output.new_page(-1, width=outbox.width, height=max(outbox.height, 90))
                
                # *** ERROR FIX HERE ***
                # The method requires the source DOCUMENT (self.reader) and the PAGE NUMBER,
                # not the source page object itself.
                outPage.show_pdf_page(outbox, self.reader, area["page_number"], clip=cropbox)

                text += self.make_text(self.reader[area["page_number"]].get_text("words", clip = cropbox))

            os.makedirs(os.path.dirname(filename), exist_ok=True)

            try:
                # Outputs to file with appropriate name
                output.save(filename, garbage=4, deflate=True)

                self.rows.append({
                    "subject_code": self.info['subject_code'],
                    "year": self.info['year'],
                    "season": self.info['season'],
                    "paper": self.info['paper'],
                    "variant": self.info['variant'],
                    "question": question['question_num'],
                    "filename": filename,
                    "text": text
                })
            except Exception as e:
                print(f"Error: Could not write to file {filename}. Reason: {e}")

    # Writes paper info to the database
    def to_csv(self):

        headers = ["subject_code", "year", "season", "paper", "variant", "question", "filename", "text"]

        isExist = os.path.exists(f"questions{os.sep}database.csv")
        with open(f"questions{os.sep}database.csv", "a", newline='', encoding="utf-8") as csvfile:
            cwriter = csv.DictWriter(csvfile, fieldnames=headers)
            if not isExist:
                cwriter.writeheader()
            cwriter.writerows(self.rows)


    # Function to check if the question numbers are in numerical order, if not throw an error
    def check_order(self):
        if len(self.questions) == 0:
            print("Error: No questions found in paper")
            return False
        
        priorQuestion = self.questions[0]["question_num"]

        for question in self.questions[1:]:
            if int(question["question_num"]) != (int(priorQuestion) + 1) or len(self.questions) == 0:
                print("Error: Question numbers are not in order", [question["question_num"] for question in self.questions])
                return False
            priorQuestion = question["question_num"] 

        return True


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