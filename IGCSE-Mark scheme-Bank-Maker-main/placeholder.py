    def split_questions(self):
        for index, question in enumerate(self.questions):
            q_num_str = question['base_num']
            filename = f"questions{os.sep}{self.info['subject_code']}{os.sep}{self.info['year']}{os.sep}{self.info['name']}-MS-{q_num_str}.pdf"
            output = fitz.open()
            text = ""

            for area in question.get("questionArea", []):
                source_page = self.reader[area["page_number"]]

                # --- START OF ADAPTATION ---
                # Based on your rules, the coordinate system is inverted and flipped.
                # A "question" is now a VERTICAL slice of the page.
                # 'y_coord' now defines the HORIZONTAL start and end points.
                # The vertical extent is the full height of the page.
                
                # We build the fitz.Rect(x0, y0, x1, y1) accordingly:
                # x0 (left edge) is now defined by the start of our horizontal slice.
                # y0 (top edge) is the top of the page.
                # x1 (right edge) is the end of our horizontal slice.
                # y1 (bottom edge) is the bottom of the page.
                
                # Ensure x0 is always less than x1 for the Rect constructor.
                x_start = min(area["y_coord"])
                x_end = max(area["y_coord"])

                cropbox = fitz.Rect(x_start, 0, x_end, source_page.rect.height)
                # --- END OF ADAPTATION ---
                
                if cropbox.is_empty or cropbox.is_infinite:
                    print(f"\n--- DEBUG: Skipping invalid crop area for question '{question['question_num']}' ---")
                    continue

                # The output page will be a tall, thin slice that matches the cropbox.
                outbox = fitz.Rect(0, 0, cropbox.width, cropbox.height)
                outPage = output.new_page(-1, width=cropbox.width, height=cropbox.height)
                
                # The copy operation remains the same, it just uses our newly defined cropbox.
                outPage.show_pdf_page(outbox, self.reader, area["page_number"], clip=cropbox)
                
                # Text extraction also uses the same vertical cropbox.
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
    # Writes paper info to the database