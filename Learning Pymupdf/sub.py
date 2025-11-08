import pymupdf
import re
import os


#Initiate some boxes :)
def create_pdf_snippet(source_doc, source_page, crop_rect, base_filename, question_index, output_dir, part_suffix="", save_to_disk=True):

    new_doc = None
    try:
        # 1. Create a new, blank PDF in memory.
        new_doc = pymupdf.open()

        # 2. Copy the *entire source page* into the new document.
        # This preserves all content, rotation, and coordinate systems.
        new_doc.insert_pdf(source_doc, from_page=source_page.number, to_page=source_page.number)

        # 3. Get the newly copied page (it's always the first page in new_doc).
        new_page = new_doc[0]

        # 4. This is the key step: Set the page's "crop box" (visible area)
        # to be your blue box rectangle. This effectively crops the page
        # without distorting any content.
        new_page.set_cropbox(crop_rect)

        # 5. The rest of the logic remains the same.
        if save_to_disk:
            snippet_filename = f"{base_filename}_q{question_index}{part_suffix}.pdf"
            snippet_output_path = os.path.join(output_dir, snippet_filename)
            new_doc.save(snippet_output_path)
            print(f"   -> Successfully created snippet: {snippet_filename}")
            new_doc.close()
            return None
        else:
            return new_doc

    except Exception as e:
        print(f"   -> !!! Error creating snippet for q{question_index}: {e}")
        if new_doc:
            new_doc.close()
        return None

    #Page.draw_rect(
    #    Box_Rect,
    #    color=(0, 0, 1),    # Blue border
    #    fill=(0, 0, 1),     # Blue fill
    #   fill_opacity=0.2,   # 20% transparent
    #    width=1.5)

# Open PDF file

def process_pdf(input_path, output_path):
    print(f"\n--- Processing file: {os.path.basename(input_path)} ---")
    doc = None
    try:
        #global all_text_location, extracted_numbers
        doc = pymupdf.open(input_path)

    # Delete first page
        for page_index in range(len(doc)):
            if page_index == 0:
                doc.delete_page(page_index)

        # Marking any unncessary pages
        pages_to_delete = []
        forbidden_text = [
            "Generic Marking Principles",
            "GENERIC MARKING PRINCIPLE 5:", 
            "Science-Specific Marking Principles",
            "Calculation specific guidance",
            "Examples of how to apply the list rule",
            ]
        for page_num, page in enumerate(doc):
            for text in forbidden_text:
                if page.search_for(text):
                    pages_to_delete.append(page_num)
                    page_flag = True
                    break
                else:
                    page_flag = False

        # Delete unncessary pages
        for page_num in sorted(pages_to_delete, reverse=True):
            doc.delete_page(page_num)

        # Extract the length of the mark scheme for each question
        extracted_numbers = []
        for page in doc:
            # 1. Find question number within this area of the page
            rectangle = pymupdf.Rect(50,720,540,780)
            # Extract the question's order from the box
            text_blocks = page.get_text("blocks", clip = rectangle)
            #-----------------------------------
            # Find the number of the question's and its boxing coordinate
            for block in text_blocks:
                #------------------------------------
                block_text = block[4]
                block_rect = pymupdf.Rect(block[:4])
                #------------------------------------
                if rectangle.intersects(block_rect):
                    #print(f"Found text block inside the search area: '{block_text.strip()}'")
                    #print(f"   -> Its precise location is: {block_rect}")
                    Qnumbers = re.findall(r'\d+', block_text)

                    for num in Qnumbers:
                        extracted_numbers.append({
                            "number": int(num),
                            "rect": block_rect,
                            "page_num": page.number
                        })

                    #page.draw_rect(
                    #    block_rect, 
                    #    color=(1, 0, 0),    # Red border
                    #    fill=(1, 0, 0),     # Red fill
                    #    fill_opacity=0.2,   # 20% transparent
                    #    width=1.5
                    #)

        increment_full = []

        if len(extracted_numbers) > 1:

            for i in range(1,len(extracted_numbers)):
                previous_number = extracted_numbers[i-1]['number']
                current_number = extracted_numbers[i]['number']

                if current_number > previous_number:
                    #this mean that the i here is the position of the number in extracted_numbers that increased
                    increment_info = {
                        "index": i,
                        "data":extracted_numbers[i] 
                    }
                    increment_full.append(increment_info)
                elif i == 1:
                    increment_info = {
                        "index": i,
                        "data":extracted_numbers[i-1] 
                    }
                    increment_full.append(increment_info)
                #elif i  == len(extracted_numbers) - 1:
                #    increment_info = {
                #            "index": i + 1,
                #            "data":extracted_numbers[i] 
                #    }
                #    increment_full.append(increment_info)
            


        print("--- Found Increments ---")
        if increment_full:
            for item in increment_full:
                index = item['index']
                number_data = item['data']
                #print(f"Increment found at index: {index}")
                #print(f"  -> Number: {number_data['number']}")
                #print(f"  -> Use this Rect for its position: {number_data['rect']}")
                #print(f"  -> On Page: {number_data['page_num'] + 1}")

        #cutting out mark schemes
        for question in range(1,len(increment_full)):
            Current_question = increment_full[question-1]['data']['rect']
            x0_coord = Current_question.x0
            y0_coord = 60
            Next_question = increment_full[question]['data']['rect']
            x1_coord = Next_question.x0
            y1_coord = 780
            page = doc[increment_full[question-1]['data']['page_num']]
            question_number_for_name = increment_full[question-1]['data']['number']
            last_question_data = increment_full[-1]['data']


            if increment_full[question-1]['data']['page_num'] == increment_full[question]['data']['page_num']:
    
                question_border = pymupdf.Rect(x0_coord -5 ,y0_coord,x1_coord -5,y1_coord)
                create_pdf_snippet(doc, page, question_border, base_name, question_number_for_name, output_folder)
                print("successfully located and created snippet for single-page question!")

            else:
                print(f"Processing multi-page question {question_number_for_name}...")

                part1_doc = None
                part2_doc = None

                try:
            # --- Create snippet for the first part IN MEMORY ---
                    page = doc[increment_full[question-1]['data']['page_num']]

                # Find x0 of the highest question and go to the end of the page
                    question_border = pymupdf.Rect(x0_coord,y0_coord,537, y1_coord)
                    part1_doc = create_pdf_snippet(doc, page, question_border, base_name, question_number_for_name, output_folder, save_to_disk=False)


                # another one for the next page
                    page2 = doc[increment_full[question]['data']['page_num']]
                    if increment_full[question-1]['data'] != last_question_data:
                        question_border2 = pymupdf.Rect(50,y0_coord,x1_coord -5, y1_coord)
                    else:
                        #This is for the Last question
                        #question_border2 = pymupdf.Rect(50,y0_coord,Next_question.x1 + 5, y1_coord)
                        last_page_num = last_question_data['page_num']
                        last_page = doc[last_page_num]

                        # 2. Get the starting coordinates for the last question's box
                        start_x0 = last_question_data['rect'].x0
                        start_y0 = last_question_data['rect'].y0

                        all_blocks = last_page.get_text("blocks")
                        
                        max_x1 = start_x0
                        for block in all_blocks:
                            block_rect = pymupdf.Rect(block[:4])

                            if 540> block_rect.x0 >= start_x0  and block_rect.y0 > 50:
                                if block_rect.x1 > max_x1:
                                    max_x1 = block_rect.y1

                        # 4. Create the final snippet with a precise bottom boundary
                        # Add a little padding to the bottom for spacing
                        final_x1 = max_x1 + 5 

                        # Use the page's width for y1 (remembering the rotation)
                        final_y1 = last_page.rect.height

                        # Construct the final, perfectly sized rectangle
                        final_question_border = pymupdf.Rect(start_x0, y0_coord, final_x1, final_y1)





                    part2_doc = create_pdf_snippet(doc, page2, final_question_border, base_name, question_number_for_name, output_folder, save_to_disk=False)

                    if part1_doc and part2_doc:
                        # Use insert_pdf() to append all pages from part2_doc into part1_doc
                        part1_doc.insert_pdf(part2_doc)

                        # Generate the final, combined filename
                        final_filename = f"{base_name}_q{question_number_for_name}.pdf"
                        final_output_path = os.path.join(output_folder, final_filename)
                
                        # Save the merged document
                        part1_doc.save(final_output_path)
                
                    print(f"   -> Successfully MERGED and created snippet: {final_filename}")
                except Exception as e:
                    print(f"   -> !!! Error merging parts for question {question_number_for_name}: {e}")
                finally:
            # --- CLEANUP: IMPORTANT ---
            # Close the in-memory documents to free up resources, no matter what.
                    if part1_doc:
                        part1_doc.close()
                    if part2_doc:
                        part2_doc.close()

        
        print(f"Successfully created: {os.path.basename(output_path)}")
    except Exception as e:
        print(f"!!! An error occurred while processing {os.path.basename(input_path)}: {e}")
    finally:
        # Make sure the document is always closed
        if doc:
            doc.close


if __name__ == "__main__":
    # 1. Define the folder names
    script_dir = os.path.dirname(os.path.abspath(__file__))
    papers_folder = os.path.join(script_dir, "papers")
    output_folder = os.path.join(script_dir, "output")

    os.makedirs(output_folder, exist_ok=True)
    if not os.path.isdir(papers_folder):
        print(f"Error: The 'papers' folder was not found. Please create it in the same directory as the script.")
    else:
        # 4. Get a list of all PDF files in the papers folder
        pdf_files = [f for f in os.listdir(papers_folder) if f.lower().endswith('.pdf')]
        
        if not pdf_files:
            print("No PDF files found in the 'papers' folder.")
        else:
            print(f"Found {len(pdf_files)} PDF(s) to process.")
            
            # 5. Loop through each PDF file and process it
            for pdf_file in pdf_files:
                input_file_path = os.path.join(papers_folder, pdf_file)
                base_name, _ = os.path.splitext(pdf_file)
                
                process_pdf(input_file_path,base_name)
                
                
            
            print("\n--- All files processed. ---")

