import fitz
import os
import re

class Split:

    def __init__(self, path, crawl=True):
        self.paths = []
        if crawl:
            self.crawl(path)
        else:
            self.paths.append(path)
        path_num = len(self.paths)
        for index, path in enumerate(self.paths):
            self.reader = fitz.open(path)
            self.questions = []
            self.blankPages = []
            self.info = {}
            self.border = 50
            self.padding = 10
            
            # Get info (including the new subject code)
            self.get_info(path)
            
            ### CHANGED: The output path is now hierarchical.
            # It will look like: "extracted_questions/0620/0620_s23_qp_41"
            output_folder_path = os.path.join("extracted_questions", self.info['subject_code'], self.info['name'])
            os.makedirs(output_folder_path, exist_ok=True)

            self.extract_questions()
            if not self.check_order():
                print(f"\nError in '{path}': Could not load all questions in order. Skipping file.")
                continue
            self.compute_crop()
            self.trim_page()
            
            # Pass the new, specific output folder to the split_questions method
            self.split_questions(output_folder_path)

            print(f"\r'{self.info['name']}' processed: {index + 1}/{path_num}", end=" ")
        print("\nFinished processing all papers.")

    def crawl(self, path):
        # No changes needed here
        rootdir = os.fsencode(path)
        if rootdir is not None:
            if os.path.isfile(rootdir):
                self.paths.append(rootdir.decode('UTF-8'))
            elif os.path.exists(rootdir):
                for subdir, dirs, files in os.walk(rootdir):
                    for file in files:
                        filepath = (subdir + os.sep.encode('UTF-8') + file).decode('UTF-8')
                        if filepath.endswith(".pdf") and "qp" in filepath:
                            self.paths.append(filepath)

    def _is_new_format(self, page):
        # No changes needed here
        phrase = "DO NOT WRITE IN THIS MARGIN"
        found_rects = page.search_for(phrase,)
        return len(found_rects) >= 1

    def locate_questions(self, page, page_number):
        # No changes needed here
        if self._is_new_format(page):
            rect = fitz.Rect(0, 60, 60, 770)
        else:
            rect = fitz.Rect(0, 50, 60, page.rect.y1)
        page_dict = page.get_text("dict")
        bold_spans = [span for block in page_dict["blocks"] if block["type"] == 0
                        for line in block["lines"]
                        for span in line["spans"]
                        if fitz.Rect(span["bbox"]).intersects(rect)]
        questions = []
        valid_question_pattern = re.compile(r"^\s*\d+\.?\s*(\(\s*[a-z]\s*\))?(\(\s*[ivx]+\s*\))?\s*$")
        for a in bold_spans:
            match = re.search(r'\d+', a["text"])
            text = a["text"].strip()
            if valid_question_pattern.fullmatch(text):
                current_num_str = match.group()
                if (len(questions) == 0 
                        or int(current_num_str) == (int(questions[-1]['question_num']) + 1)):
                    questions.append({
                        'question_num': current_num_str, 
                        'bbox': [round(n) for n in a["bbox"]], 
                        'page': page_number
                    })
        return questions

    def flag_blank(self, page):
        # No changes needed here
        wordList = ["BLANK PAGE", "ADDITIONAL PAGE", "Mathematical Formulae", "TURN PAGE FOR QUESTION", 
                    "printed on the next page", "The Periodic Table of Elements", "starts on the next page.",
                    "Note for use in qualitative analysis", "Important values, constants and standards"]
        for word in wordList:
            if page.search_for(word):
                return True
        title_version_exists = page.search_for("Qualitative analysis notes")
        sentence_version_exists = page.search_for("Qualitative analysis notes.")
        if title_version_exists and not sentence_version_exists:
            return True
        return False
        
    def extract_questions(self):
        # No changes needed here
        for page_number, content in enumerate(self.reader):
            if not (self.flag_blank(content) or page_number == 0):
                self.questions += self.locate_questions(content, page_number)
            else:
                self.blankPages.append(page_number)

    def get_info(self, path):
        ### CHANGED: This method now also extracts the 4-digit subject code.
        base_name = os.path.basename(path)
        file_name_without_ext, _ = os.path.splitext(base_name)
        
        # Use regex to find the first 4-digit number in the filename
        match = re.search(r'\d{4}', file_name_without_ext)
        subject_code = match.group(0) if match else "unknown_subject"
        
        self.info = {
            "name": file_name_without_ext,
            "subject_code": subject_code
        }
        
    def compute_crop(self):
        # No changes needed here
        dimensions = {"height": self.reader[0].rect.y1, "width": self.reader[0].rect.x1}
        for index, question in enumerate(self.questions):
            self.questions[index]["questionArea"] = []
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

    def trim_page(self):
        # No changes needed here
        text = [self.reader[page].get_text("dict") for page in range(len(self.reader))]
        drawings = [self.reader[page].get_drawings() for page in range(len(self.reader))]
        for question in self.questions:
            for area in question["questionArea"]:
                page = self.reader[area["page_number"]]
                rect = fitz.Rect(0, area["y_coord"][0], page.rect.x1, area["y_coord"][1])
                regiontext = [block for block in text[area["page_number"]]["blocks"]
                                                    if fitz.Rect(block["bbox"]).intersects(rect)]
                regiondrawing = [box["rect"] for box in drawings[area["page_number"]]
                                    if box["stroke_opacity"] is not None
                                        and (fitz.Rect(box["rect"]) in rect)]
                try:
                    proposedy = [min([x["bbox"][1] for x in regiontext] + [x.y1 for x in regiondrawing]) - self.padding,
                                    max([x["bbox"][3] for x in regiontext] + [x.y1 for x in regiondrawing]) + self.padding]
                    area["y_coord"] = [max(area["y_coord"][0], proposedy[0]), min(area["y_coord"][1], proposedy[1])]
                except ValueError:
                    continue

    def split_questions(self, output_dir):
        # No changes needed here
        for index, question in enumerate(self.questions):
            filename = os.path.join(output_dir, f"Q{question['question_num']}.pdf")
            output = fitz.open()
            for area in question["questionArea"]:
                source_page = self.reader[area["page_number"]]
                if self._is_new_format(source_page):
                    crop_x0, crop_x1 = 25, source_page.rect.width - 25
                    crop_y0, crop_y1 = area["y_coord"][0] + 9, area["y_coord"][1] - 2
                    cropbox = fitz.Rect(crop_x0, crop_y0, crop_x1, crop_y1)
                else:
                    cropbox = fitz.Rect(0, area["y_coord"][0], source_page.rect.width, area["y_coord"][1])
                outbox = fitz.Rect(0, 0, cropbox.width, cropbox.height)
                outPage = output.new_page(-1, width=outbox.width, height=max(outbox.height, 90))
                outPage.show_pdf_page(outbox, self.reader, area["page_number"], clip=cropbox)
            try:
                output.save(filename, garbage=4, deflate=True)
            except Exception as e:
                print(f"Error: Could not write to file {filename}. Reason: {e}")

    def check_order(self):
        # No changes needed here
        if len(self.questions) == 0:
            return False
        priorQuestion = self.questions[0]["question_num"]
        for question in self.questions[1:]:
            if int(question["question_num"]) != (int(priorQuestion) + 1):
                return False
            priorQuestion = question["question_num"] 
        return True

if __name__ == '__main__':
    path_to_papers = "."
    Split(path_to_papers, crawl=True)