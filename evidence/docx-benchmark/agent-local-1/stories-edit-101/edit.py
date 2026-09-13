from docx import Document

def replace_marker(input_path, output_path):
    doc = Document(input_path)
    
    for paragraph in doc.paragraphs:
        for run in paragraph.runs:
            if 'EDITBEFORE' in run.text:
                new_text = run.text.replace('EDITBEFORE', 'EDITAFTER')
                run._element.text = new_text
                break
    
    doc.save(output_path)

try:
    replace_marker('input.docx', 'output.docx')
except Exception as e:
    raise Exception(f"Failed to perform the task: {e}")
